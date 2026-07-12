from pathlib import Path

import pytest

from ingestion.loader import DocumentLoader, LoadedDocument


class TestDocumentLoader:
    def test_load_txt(self, tmp_text_file: Path):
        loader = DocumentLoader()
        doc = loader._load_single(tmp_text_file)
        assert isinstance(doc, LoadedDocument)
        assert doc.filename == "test.txt"
        assert doc.file_type == ".txt"
        assert "céu é azul" in doc.content
        assert doc.file_size > 0

    def test_load_md(self, tmp_md_file: Path):
        loader = DocumentLoader()
        doc = loader._load_single(tmp_md_file)
        assert doc.filename == "test.md"
        assert doc.file_type == ".md"
        assert "Documento de Teste" in doc.content

    def test_load_nonexistent_directory(self):
        loader = DocumentLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/path")

    def test_load_empty_directory(self, tmp_documents_dir: Path):
        loader = DocumentLoader()
        docs = loader.load(str(tmp_documents_dir))
        assert docs == []

    def test_load_unsupported_file(self, tmp_documents_dir: Path):
        unsupported = tmp_documents_dir / "test.csv"
        unsupported.write_text("a,b,c\n1,2,3")
        loader = DocumentLoader()
        docs = loader.load(str(tmp_documents_dir))
        assert docs == []

    def test_load_recursive(self, tmp_documents_dir: Path):
        subdir = tmp_documents_dir / "subdir"
        subdir.mkdir()
        txt_file = subdir / "nested.txt"
        txt_file.write_text("conteudo aninhado")
        loader = DocumentLoader()
        docs = loader.load(str(tmp_documents_dir))
        assert len(docs) == 1
        assert docs[0].filename == "nested.txt"

    def test_loaded_document_metadata(self, tmp_text_file: Path):
        loader = DocumentLoader()
        doc = loader._load_single(tmp_text_file)
        assert doc.filepath.endswith("test.txt")
        assert doc.modified_at is not None
        assert doc.file_size == tmp_text_file.stat().st_size


class TestDocumentLoaderIntegration:
    def test_load_multiple_formats(self, tmp_documents_dir: Path, sample_text: str):
        txt_file = tmp_documents_dir / "doc1.txt"
        txt_file.write_text(sample_text)
        md_file = tmp_documents_dir / "doc2.md"
        md_file.write_text(f"# Doc 2\n\n{sample_text}")
        loader = DocumentLoader()
        docs = loader.load(str(tmp_documents_dir))
        assert len(docs) == 2
        filenames = {doc.filename for doc in docs}
        assert filenames == {"doc1.txt", "doc2.md"}
