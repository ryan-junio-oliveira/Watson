from pathlib import Path

from langchain_core.documents import Document

from ingestion.loader import LoadedDocument
from ingestion.splitter import DocumentSplitter


class TestDocumentSplitter:
    def test_split_single_document(self):
        doc = LoadedDocument(
            content="Olá mundo. " * 100,
            filepath="/path/test.txt",
            filename="test.txt",
            file_type=".txt",
            modified_at="2024-01-01T00:00:00",
            file_size=100,
        )
        splitter = DocumentSplitter(chunk_size=100, chunk_overlap=20)
        chunks = splitter.split([doc])
        assert len(chunks) > 1
        assert all(isinstance(c, Document) for c in chunks)

    def test_split_preserves_metadata(self):
        doc = LoadedDocument(
            content="Conteúdo de teste.",
            filepath="/path/test.txt",
            filename="test.txt",
            file_type=".txt",
            modified_at="2024-01-01T00:00:00",
            file_size=18,
        )
        splitter = DocumentSplitter(chunk_size=1000, chunk_overlap=0)
        chunks = splitter.split([doc])
        assert len(chunks) == 1
        assert chunks[0].metadata["filename"] == "test.txt"
        assert chunks[0].metadata["source"] == "/path/test.txt"

    def test_split_multiple_documents(self):
        docs = [
            LoadedDocument(
                content="Conteúdo A. " * 50,
                filepath=f"/path/doc{i}.txt",
                filename=f"doc{i}.txt",
                file_type=".txt",
                modified_at="2024-01-01T00:00:00",
                file_size=100,
            )
            for i in range(3)
        ]
        splitter = DocumentSplitter(chunk_size=100, chunk_overlap=20)
        chunks = splitter.split(docs)
        assert len(chunks) >= 3

    def test_chunk_size_respected(self):
        doc = LoadedDocument(
            content="a" * 5000,
            filepath="/path/test.txt",
            filename="test.txt",
            file_type=".txt",
            modified_at="2024-01-01T00:00:00",
            file_size=5000,
        )
        splitter = DocumentSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split([doc])
        for chunk in chunks:
            assert len(chunk.page_content) <= 500
