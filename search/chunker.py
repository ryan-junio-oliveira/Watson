import logging
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


class Chunker:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        logger: Optional[logging.Logger] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.logger = logger
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ".", " ", ""],
        )

    def chunk(self, text: str) -> List[str]:
        if not text:
            return []
        chunks = self._splitter.split_text(text)
        if self.logger:
            self.logger.info(
                f"Split {len(text)} chars into {len(chunks)} chunks "
                f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
            )
        return chunks

    def chunk_documents(self, documents: List[str]) -> List[str]:
        all_chunks: List[str] = []
        for doc in documents:
            all_chunks.extend(self.chunk(doc))
        return all_chunks
