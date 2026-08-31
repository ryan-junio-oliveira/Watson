import logging
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from ingestion.embeddings import EmbeddingGenerator


class Retriever:
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        chroma_persist_dir: str,
        top_k: int = 5,
        similarity_threshold: Optional[float] = None,
        use_mmr: bool = False,
        mmr_fetch_k: int = 20,
        mmr_lambda: float = 0.5,
        logger: Optional[logging.Logger] = None,
    ):
        self.embedding_generator = embedding_generator
        self.chroma_persist_dir = chroma_persist_dir
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.use_mmr = use_mmr
        self.mmr_fetch_k = mmr_fetch_k
        self.mmr_lambda = mmr_lambda
        self.logger = logger
        self._vector_store: Optional[Chroma] = None

    def _get_vector_store(self) -> Chroma:
        if self._vector_store is None:
            embeddings = self.embedding_generator.get_embeddings()
            self._vector_store = Chroma(
                persist_directory=self.chroma_persist_dir,
                embedding_function=embeddings,
                collection_name="documents",
            )
        return self._vector_store

    def retrieve(
        self,
        query: str,
        k: Optional[int] = None,
        filter: Optional[dict] = None,
    ) -> List[Document]:
        try:
            vector_store = self._get_vector_store()
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Could not open vector store (possibly empty): {e}"
                )
            return []

        top_k = k or self.top_k

        try:
            # Check if collection exists and has data
            collection = vector_store._collection
            count = collection.count()
            if count == 0:
                if self.logger:
                    self.logger.info(
                        "Vector store collection is empty, no documents to retrieve"
                    )
                return []
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Could not verify collection status: {e}"
                )
            return []

        if self.use_mmr:
            mmr_kwargs = {
                "k": top_k,
                "fetch_k": self.mmr_fetch_k,
                "lambda_mult": self.mmr_lambda,
            }
            if filter is not None:
                mmr_kwargs["filter"] = filter
            results = vector_store.max_marginal_relevance_search(
                query, **mmr_kwargs
            )
        else:
            search_kwargs = {"k": top_k}
            if filter is not None:
                search_kwargs["filter"] = filter
            results_with_scores = (
                vector_store.similarity_search_with_relevance_scores(
                    query, **search_kwargs
                )
            )
            results = []
            for doc, score in results_with_scores:
                doc.metadata["relevance_score"] = round(float(score), 4)
                if self.similarity_threshold is not None:
                    if score >= self.similarity_threshold:
                        results.append(doc)
                else:
                    results.append(doc)

        if self.logger:
            self.logger.info(
                f"Retrieved {len(results)} chunks for query: {query[:60]}..."
            )

        return results

    def retrieve_all_from_source(
        self,
        source: str,
        exclude_ids: Optional[set] = None,
        max_chunks: int = 50,
    ) -> List[Document]:
        """Retorna TODOS os chunks de uma mesma fonte (ex.: um documento PDF),
        sem limite por similaridade — usado em perguntas de listagem para não
        omitir itens espalhados pelo arquivo.

        Otimização: tenta filtro `where` nativo por igualdade exata primeiro
        (zero cópia), depois fallback paginado com `contains` case-insensitive
        para compatibilidade com variações de caminho.
        """
        try:
            vector_store = self._get_vector_store()
            collection = vector_store._collection
            if collection.count() == 0:
                return []
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not query source chunks: {e}")
            return []

        needle = source.strip()
        needle_lower = needle.lower()
        results: List[Document] = []

        # 1) Tentativa rápida: where exato (Chroma suporta igualdade direta).
        #    Cobre o caso comum onde `source` é caminho absoluto idêntico.
        try:
            exact_where = {"source": needle}
            raw_exact = collection.get(
                where=exact_where, limit=max_chunks, include=["documents", "metadatas"]
            )
            docs_e = raw_exact.get("documents") or []
            metas_e = raw_exact.get("metadatas") or []
            for content, meta in zip(docs_e, metas_e):
                meta = dict(meta or {})
                chunk_id = meta.get("chunk_id", "")
                if exclude_ids and chunk_id in exclude_ids:
                    continue
                meta["relevance_score"] = meta.get("relevance_score", 0.5)
                results.append(Document(page_content=content or "", metadata=meta))
                if len(results) >= max_chunks:
                    return results
            # Se encontrou pelo menos 1 resultado exato, retorna direto.
            if results:
                return results
            # Se where exato não achou nada, cai no fallback contains
            # (pode ser variação de caixa/separador ou metadata antiga).
        except Exception:
            # where exato falhou (versão antiga do Chroma ou campo ausente) — segue para scan.
            pass

        # 2) Fallback paginado com contains — evita carregar 100k de uma vez.
        PAGE_SIZE = 1000
        offset = 0
        try:
            total = collection.count()
        except Exception:
            total = None

        while len(results) < max_chunks:
            try:
                # Chroma `get` com offset/limit é mais eficiente em memória.
                raw = collection.get(
                    limit=PAGE_SIZE, offset=offset, include=["documents", "metadatas"]
                )
            except TypeError:
                # Versões antigas podem não suportar `offset` — fallback único.
                try:
                    raw = collection.get(limit=100000, include=["documents", "metadatas"])
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Source chunk query failed: {e}")
                    return results
                docs = raw.get("documents") or []
                metas = raw.get("metadatas") or []
                for content, meta in zip(docs, metas):
                    meta = dict(meta or {})
                    meta_source = str(meta.get("source", "")).lower()
                    if needle_lower not in meta_source:
                        continue
                    chunk_id = meta.get("chunk_id", "")
                    if exclude_ids and chunk_id in exclude_ids:
                        continue
                    meta["relevance_score"] = meta.get("relevance_score", 0.5)
                    results.append(Document(page_content=content or "", metadata=meta))
                    if len(results) >= max_chunks:
                        break
                return results
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Source chunk query failed: {e}")
                return results

            docs = raw.get("documents") or []
            metas = raw.get("metadatas") or []
            if not docs and not metas:
                break

            for content, meta in zip(docs, metas):
                meta = dict(meta or {})
                meta_source = str(meta.get("source", "")).lower()
                if needle_lower not in meta_source:
                    continue
                chunk_id = meta.get("chunk_id", "")
                if exclude_ids and chunk_id in exclude_ids:
                    continue
                meta["relevance_score"] = meta.get("relevance_score", 0.5)
                results.append(Document(page_content=content or "", metadata=meta))
                if len(results) >= max_chunks:
                    return results

            if len(docs) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            if total is not None and offset >= total:
                break

        return results
