"""Interface de Vector Store (§30).

Isola a pipeline de indexação do backend vetorial concreto (Chroma, Qdrant,
PgVector...). O indexador e o retriever dependem desta interface, não do Chroma
diretamente — permitindo reindex, delete, audit e migração sem acoplamento
irreversível.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from langchain_core.documents import Document


class VectorStore(ABC):
    """Contrato mínimo entre a pipeline e o índice vetorial."""

    @abstractmethod
    def add(self, documents: List[Document], vectors: List[List[float]]) -> None:
        """Adiciona (ou substitui por id determinístico) chunks já embarcados."""
        raise NotImplementedError

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        """Remove todos os chunks de um documento."""
        raise NotImplementedError

    @abstractmethod
    def delete_by_source(self, source_id: str) -> None:
        """Remove todos os chunks de uma fonte."""
        raise NotImplementedError

    @abstractmethod
    def delete_by_path(self, filepath: str) -> None:
        """Remove chunks indexados por um caminho legado (metadata `source`)."""
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> int:
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """Implementação sobre Chroma (persistente em disco)."""

    def __init__(
        self,
        persist_directory: str,
        embedding_function: Any,
        collection_name: str = "documents",
        logger: Optional[logging.Logger] = None,
    ):
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function
        self.collection_name = collection_name
        self.logger = logger
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_chroma import Chroma

            self._client = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embedding_function,
                collection_name=self.collection_name,
            )
        return self._client

    def add(self, documents: List[Document], vectors: List[List[float]]) -> None:
        if not documents:
            return
        client = self._get_client()
        client.add_texts(
            texts=[d.page_content for d in documents],
            metadatas=[dict(d.metadata) for d in documents],
            ids=[d.metadata["chunk_id"] for d in documents],
            embeddings=vectors,
        )

    def delete_by_document(self, document_id: str) -> None:
        if not document_id:
            return
        client = self._get_client()
        client.delete(where={"document_id": document_id})

    def delete_by_source(self, source_id: str) -> None:
        if not source_id:
            return
        client = self._get_client()
        client.delete(where={"source_id": source_id})

    def delete_by_path(self, filepath: str) -> None:
        if not filepath:
            return
        client = self._get_client()
        client.delete(where={"source": filepath})

    def count(self) -> int:
        try:
            return self._get_client()._collection.count()
        except Exception as e:  # pragma: no cover
            if self.logger:
                self.logger.warning(f"Could not count vector store: {e}")
            return 0

    def clear(self) -> int:
        client = self._get_client()
        try:
            n = self.count()
            client._collection.delete(where={})
            return n
        except Exception as e:  # pragma: no cover
            if self.logger:
                self.logger.error(f"Failed to clear vector store: {e}")
            return 0
