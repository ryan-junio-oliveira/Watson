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
        logger: Optional[logging.Logger] = None,
    ):
        self.embedding_generator = embedding_generator
        self.chroma_persist_dir = chroma_persist_dir
        self.top_k = top_k
        self.logger = logger
        self._vector_store: Chroma | None = None

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
        vector_store = self._get_vector_store()
        results = vector_store.similarity_search(query, k=self.top_k)
        if self.logger:
            self.logger.info(
                f"Retrieved {len(results)} chunks for query: {query[:50]}..."
            )
        return results
