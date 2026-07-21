import logging
from collections import defaultdict
from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.loader import LoadedDocument


class DocumentSplitter:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        logger: Optional[logging.Logger] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.logger = logger

    def split(self, documents: List[LoadedDocument]) -> List[Document]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ".", " ", ""],
        )

        langchain_docs = [
            Document(
                page_content=doc.content,
                metadata={
                    "source": doc.filepath,
                    "filename": doc.filename,
                    "file_type": doc.file_type,
                    "modified_at": doc.modified_at,
                    "file_size": doc.file_size,
                },
            )
            for doc in documents
        ]

        chunks = splitter.split_documents(langchain_docs)

        # Count total chunks per source document
        source_counts: Dict[str, int] = defaultdict(int)
        for chunk in chunks:
            source = chunk.metadata.get("source", "unknown")
            source_counts[source] += 1

        # Add chunk index metadata for better traceability
        chunk_counters: Dict[str, int] = defaultdict(int)
        for chunk in chunks:
            source = chunk.metadata.get("source", "unknown")
            chunk_counters[source] += 1
            chunk.metadata["chunk_index"] = chunk_counters[source]
            chunk.metadata["total_chunks"] = source_counts.get(source, 1)
            chunk.metadata["chunk_size"] = len(chunk.page_content)

        if self.logger:
            self.logger.info(
                f"Split {len(documents)} documents into {len(chunks)} chunks"
            )

        return chunks