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

    def retrieve(self, query: str) -> List[Document]:
        try:
            vector_store = self._get_vector_store()
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Could not open vector store (possibly empty): {e}"
                )
            return []

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
            results = vector_store.max_marginal_relevance_search(
                query,
                k=self.top_k,
                fetch_k=self.mmr_fetch_k,
                lambda_mult=self.mmr_lambda,
            )
        else:
            results_with_scores = vector_store.similarity_search_with_relevance_scores(
                query,
                k=self.top_k,
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
