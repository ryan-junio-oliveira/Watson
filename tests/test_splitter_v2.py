from ingestion.contracts import ChunkContract
from ingestion.models import LoadedDocument, Page, Table
from ingestion.splitter import DocumentSplitter, detect_error_codes


def make_doc(content, source_type="text", file_type=".txt", pages=None,
             tables=None, chunk_size=1000, min_chunk_size=50, **kwargs):
    doc = LoadedDocument(
        content=content,
        filepath=f"/path/{kwargs.get('filename', 'doc.txt')}",
        filename=kwargs.get("filename", "doc.txt"),
        file_type=file_type,
        modified_at="2024-01-01T00:00:00",
        file_size=len(content),
        source_type=source_type,
        pages=pages or [],
        tables=tables or [],
    )
    return DocumentSplitter(
        chunk_size=chunk_size, chunk_overlap=0, min_chunk_size=min_chunk_size
    ).split([doc])


class TestHeadingChunking:
    def test_splits_at_headings(self):
        content = (
            "# Troubleshooting\n\n"
            "Texto sobre troubleshooting.\n\n"
            "## Error Codes\n\n"
            "O erro E123 indica papel preso.\n\n"
            "# Maintenance\n\n"
            "Procedimento de manutencao do equipamento."
        )
        chunks = make_doc(content, min_chunk_size=40)
        assert len(chunks) >= 2
        sections = {c.metadata.get("section") for c in chunks}
        assert sections.intersection(
            {"Troubleshooting", "Error Codes", "Maintenance"}
        )

    def test_heading_metadata_is_clean(self):
        content = "# **Quem somos?**\n\nTexto."
        chunks = make_doc(content, min_chunk_size=10)
        assert chunks[0].metadata["section"] == "Quem somos?"

    def test_subsection_metadata(self):
        content = (
            "# Manual\n\nintro\n\n"
            "## Troubleshooting\n\n"
            "### Error Codes\n\nO erro E456 aparece.\n"
        )
        chunks = make_doc(content, min_chunk_size=10)
        assert chunks[-1].metadata["section"] == "Troubleshooting"
        assert chunks[-1].metadata["subsection"] == "Error Codes"


class TestPageMetadata:
    def test_pdf_pages_carry_page_numbers(self):
        doc = LoadedDocument(
            content="",
            filepath="/path/m.pdf",
            filename="m.pdf",
            file_type=".pdf",
            modified_at="t",
            file_size=1,
            source_type="pdf",
            pages=[
                Page(number=1, text="# Page One\n\nConteudo da pagina 1."),
                Page(number=2, text="# Page Two\n\nO erro E123 aparece."),
            ],
        )
        chunks = DocumentSplitter(chunk_size=1000, min_chunk_size=10).split([doc])
        assert len(chunks) == 2
        assert chunks[0].metadata["page_start"] == 1
        assert chunks[0].metadata["page_end"] == 1
        assert chunks[1].metadata["page_start"] == 2
        assert chunks[1].metadata["section"] == "Page Two"


class TestTabularChunking:
    def test_csv_table_is_single_chunk(self):
        doc = LoadedDocument(
            content="",
            filepath="/path/data.csv",
            filename="data.csv",
            file_type=".csv",
            modified_at="t",
            file_size=1,
            source_type="csv",
            tables=[
                Table(
                    section="Impressoras",
                    headers=["codigo", "desc"],
                    rows=[["E123", "papel preso"]],
                    markdown="| codigo | desc |\n|---|---|\n| E123 | papel preso |",
                )
            ],
        )
        chunks = DocumentSplitter(chunk_size=1000, min_chunk_size=10).split([doc])
        assert len(chunks) == 1
        assert chunks[0].metadata["section"] == "Impressoras"
        assert "E123" in chunks[0].page_content
        assert chunks[0].metadata["error_codes"] == ["E123"]


class TestSizing:
    def test_oversized_block_is_split(self):
        chunks = make_doc("a" * 5000, chunk_size=500, min_chunk_size=200)
        assert len(chunks) > 1
        assert all(len(c.page_content) <= 500 for c in chunks)

    def test_small_document_single_chunk(self):
        chunks = make_doc("Conteudo curto.", chunk_size=1000, min_chunk_size=50)
        assert len(chunks) == 1


class TestMetadata:
    def test_legacy_and_contract_keys(self):
        content = "# Seção\n\nTexto com erro E999 aqui."
        chunks = make_doc(content, min_chunk_size=10, filename="manual.txt")
        meta = chunks[0].metadata
        # contrato
        assert meta["chunk_id"].startswith("chunk_")
        assert meta["document_id"].startswith("doc_")
        assert meta["source_id"].startswith("src_")
        assert meta["source_type"] == "text"
        assert meta["content_hash"]
        assert meta["parser_version"] == "1.1"
        assert meta["chunking_version"] == "2.0"
        # legado
        assert meta["source"] == "/path/manual.txt"
        assert meta["filename"] == "manual.txt"
        assert meta["file_type"] == ".txt"
        assert meta["modified_at"]
        assert meta["chunk_index"] == 1
        assert meta["total_chunks"] == 1

    def test_contract_roundtrip(self):
        content = "procedimento E123"
        chunks = make_doc(content, min_chunk_size=10)
        meta = chunks[0].metadata
        restored = ChunkContract.from_metadata(meta, content=chunks[0].page_content)
        assert restored.chunk_id == meta["chunk_id"]
        assert restored.document_id == meta["document_id"]
        assert restored.source_type == "text"

    def test_error_codes_detection(self):
        assert detect_error_codes("erro E123 e ERR-456") == ["E123", "ERR-456"]
        assert detect_error_codes("sem codigo aqui") == []

    def test_chunk_index_per_document(self):
        content = ("# A\n\n" + "paragrafo " * 50 + "\n\n# B\n\n" + "paragrafo " * 50)
        chunks = make_doc(content, chunk_size=300, min_chunk_size=100)
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(1, len(chunks) + 1))
        totals = {c.metadata["total_chunks"] for c in chunks}
        assert totals == {len(chunks)}