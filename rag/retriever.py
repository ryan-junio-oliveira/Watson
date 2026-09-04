import logging
import re
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from ingestion.embeddings import EmbeddingGenerator

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except Exception:
    _HAS_BM25 = False


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
        use_hybrid: bool = True,
        hybrid_alpha: float = 0.5,
    ):
        self.embedding_generator = embedding_generator
        self.chroma_persist_dir = chroma_persist_dir
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.use_mmr = use_mmr
        self.mmr_fetch_k = mmr_fetch_k
        self.mmr_lambda = mmr_lambda
        self.logger = logger
        self.use_hybrid = use_hybrid
        self.hybrid_alpha = max(0.0, min(1.0, float(hybrid_alpha)))
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

        # Hybrid BM25 re-ranking — Sprint 2: combina vetor + keyword para códigos técnicos (E123, Modelo-X)
        # Só ativa se houver resultados e query tem termos técnicos ou hybrid sempre (para recall)
        if self.use_hybrid and results and len(results) > 1:
            try:
                # Detecta termos técnicos: códigos alfanuméricos, modelos
                has_tech = bool(re.search(r"[A-Za-z]+\d{2,5}|\bE\d{3,5}\b", query))
                # Aplica hybrid sempre para top_k pequeno, ou se tem termo técnico
                if has_tech or top_k <= 8:
                    corpus = [re.findall(r"\w+", (d.page_content or "").lower()) for d in results]
                    query_tokens = re.findall(r"\w+", query.lower())
                    if query_tokens and corpus:
                        if _HAS_BM25:
                            bm25 = BM25Okapi(corpus)
                            bm25_scores = bm25.get_scores(query_tokens)
                        else:
                            # Fallback TF simples sem dependência
                            bm25_scores = []
                            for doc_tokens in corpus:
                                score = sum(1 for t in query_tokens if t in doc_tokens)
                                # bonus para códigos exatos
                                score += sum(2 for t in query_tokens if re.match(r"^[a-z]+\d+$", t) and t in doc_tokens)
                                bm25_scores.append(float(score))
                        # Normaliza BM25 0-1
                        max_bm = max(bm25_scores) if bm25_scores else 1
                        if max_bm > 0:
                            bm25_norm = [s / max_bm for s in bm25_scores]
                        else:
                            bm25_norm = bm25_scores
                        # Combina com vetor score (relevance_score)
                        combined = []
                        for idx, doc in enumerate(results):
                            vec_score = float(doc.metadata.get("relevance_score", 0.5))
                            bm_score = bm25_norm[idx] if idx < len(bm25_norm) else 0
                            hybrid = self.hybrid_alpha * vec_score + (1 - self.hybrid_alpha) * bm_score
                            doc.metadata["bm25_score"] = round(bm_score, 4)
                            doc.metadata["hybrid_score"] = round(hybrid, 4)
                            combined.append((hybrid, doc))
                        # Re-ordena por hybrid
                        combined.sort(key=lambda x: x[0], reverse=True)
                        results = [d for _, d in combined]
                        if self.logger:
                            self.logger.info(f"Hybrid re-rank aplicado: alpha={self.hybrid_alpha} has_tech={has_tech}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Hybrid re-rank falhou, mantendo ordem vetorial: {e}")

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
