from ingestion.models import (
    ImageRef,
    LoadedDocument,
    Page,
    Section,
    Table,
    compute_document_id,
    compute_source_id,
    sha256_text,
)


class TestLoadedDocument:
    def test_backward_compatible_construction(self):
        doc = LoadedDocument(
            content="conteudo",
            filepath="/path/doc.txt",
            filename="doc.txt",
            file_type=".txt",
            modified_at="2024-01-01T00:00:00",
            file_size=8,
        )
        assert doc.source_type == "txt"
        assert doc.source_id == "/path/doc.txt"
        assert len(doc.content_hash) == 64
        assert doc.document_id.startswith("doc_")
        assert doc.source_key.startswith("src_")

    def test_rich_fields_default_to_empty(self):
        doc = LoadedDocument(
            content="x", filepath="f", filename="f", file_type=".pdf",
            modified_at="t", file_size=1,
        )
        assert doc.pages == []
        assert doc.sections == []
        assert doc.tables == []
        assert doc.images == []
        assert doc.metadata == {}

    def test_document_id_is_stable(self):
        d1 = LoadedDocument(content="x", filepath="/a/b.pdf", filename="b.pdf",
                            file_type=".pdf", modified_at="t", file_size=1)
        d2 = LoadedDocument(content="y", filepath="/a/b.pdf", filename="b.pdf",
                            file_type=".pdf", modified_at="t", file_size=1)
        assert d1.document_id == d2.document_id

    def test_source_type_from_file_type(self):
        doc = LoadedDocument(content="x", filepath="/a/b.csv", filename="b.csv",
                             file_type=".csv", modified_at="t", file_size=1)
        assert doc.source_type == "csv"


class TestModels:
    def test_sha256_text(self):
        assert sha256_text("abc") == sha256_text("abc")
        assert sha256_text("abc") != sha256_text("abd")

    def test_compute_document_id_deterministic(self):
        assert compute_document_id("pdf", "x") == compute_document_id("pdf", "x")
        assert compute_document_id("pdf", "x") != compute_document_id("pdf", "y")

    def test_compute_source_id_different_namespace(self):
        assert compute_source_id("pdf", "x") != compute_document_id("pdf", "x")

    def test_page_section_table_image(self):
        p = Page(number=1, text="t", ocr=True)
        assert p.number == 1 and p.ocr is True
        s = Section(heading="H", level=2, page=1)
        assert s.heading == "H" and s.level == 2
        t = Table(headers=["a"], rows=[["1"]])
        assert t.headers == ["a"]
        img = ImageRef(image_id="img_1", page=1, kind="technical")
        assert img.kind == "technical"