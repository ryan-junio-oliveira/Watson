from ingestion.contracts import (
    CHUNK_METADATA_KEYS,
    ChunkContract,
    IndexingManifest,
    PipelineVersion,
)


class TestPipelineVersion:
    def test_signature_changes_with_any_field(self):
        v1 = PipelineVersion(parser_version="1.0", chunking_version="1.0",
                             embedding_model="m", embedding_version="v1")
        v2 = PipelineVersion(parser_version="1.0", chunking_version="1.0",
                             embedding_model="m", embedding_version="v2")
        assert v1.signature() != v2.signature()

    def test_as_dict(self):
        v = PipelineVersion(parser_version="2.0", chunking_version="3.0",
                            embedding_model="e5", embedding_version="v1")
        d = v.as_dict()
        assert d == {
            "parser_version": "2.0",
            "chunking_version": "3.0",
            "embedding_model": "e5",
            "embedding_version": "v1",
        }


class TestChunkContract:
    def test_to_metadata_roundtrip(self):
        contract = ChunkContract(
            chunk_id="chunk_123",
            document_id="doc_456",
            content="procedimento",
            source_type="pdf",
            manufacturer="HP",
            model="MODELO-X",
            section="Troubleshooting",
            page_start=142,
            page_end=143,
            error_codes=["E123"],
            content_hash="abc",
        )
        meta = contract.to_metadata()
        restored = ChunkContract.from_metadata(meta, content=contract.content)
        assert restored.chunk_id == "chunk_123"
        assert restored.document_id == "doc_456"
        assert restored.manufacturer == "HP"
        assert restored.model == "MODELO-X"
        assert restored.section == "Troubleshooting"
        assert restored.page_start == 142
        assert restored.error_codes == ["E123"]

    def test_contract_keys_are_stable(self):
        assert "chunk_id" in CHUNK_METADATA_KEYS
        assert "document_id" in CHUNK_METADATA_KEYS
        assert "source_type" in CHUNK_METADATA_KEYS
        assert "section" in CHUNK_METADATA_KEYS
        assert "page_start" in CHUNK_METADATA_KEYS
        assert "content_hash" in CHUNK_METADATA_KEYS

    def test_empty_fields_not_persisted(self):
        contract = ChunkContract(
            chunk_id="c", document_id="d", content="x", source_type="pdf"
        )
        meta = contract.to_metadata()
        assert "section" not in meta
        assert "manufacturer" not in meta

    def test_extra_metadata_preserved(self):
        contract = ChunkContract(
            chunk_id="c", document_id="d", content="x", source_type="pdf",
            metadata={"custom_field": "value"},
        )
        meta = contract.to_metadata()
        assert meta["custom_field"] == "value"


class TestIndexingManifest:
    def test_as_dict_and_from_dict(self):
        manifest = IndexingManifest(
            document_id="doc_1",
            filename="manual.pdf",
            source_id="src_1",
            source_type="pdf",
            content_hash="h",
            parser_version="1.0",
            chunking_version="1.0",
            embedding_model="m",
            embedding_version="v1",
            indexed_at="2024-01-01",
            chunks=5,
            pages=10,
        )
        d = manifest.as_dict()
        restored = IndexingManifest.from_dict(d)
        assert restored.document_id == "doc_1"
        assert restored.pages == 10
        assert restored.status == "completed"