import logging
from typing import List, Optional

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
                },
            )
            for doc in documents
        ]

        chunks = splitter.split_documents(langchain_docs)

        if self.logger:
            self.logger.info(
                f"Split {len(documents)} documents into {len(chunks)} chunks"
            )

        return chunks
