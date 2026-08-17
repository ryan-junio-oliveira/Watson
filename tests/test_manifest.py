from ingestion.contracts import IndexingManifest
from ingestion.manifest import ManifestStore


class TestManifestStore:
    def test_upsert_and_get(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        store.upsert("doc_1", {"status": "completed", "chunks": 3})
        assert store.get("doc_1") == {"status": "completed", "chunks": 3}

    def test_missing_returns_none(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        assert store.get("nope") is None

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        store = ManifestStore(path)
        store.upsert("doc_1", {"status": "completed", "chunks": 2})
        store2 = ManifestStore(path)
        assert store2.get("doc_1") == {"status": "completed", "chunks": 2}

    def test_remove(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        store.upsert("doc_1", {"status": "completed"})
        assert store.remove("doc_1") is not None
        assert store.remove("doc_1") is None
        assert store.count() == 0

    def test_find_by_source(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        store.upsert("doc_1", {"document_id": "doc_1", "source_id": "src_abc", "status": "completed"})
        entry = store.find_by_source("src_abc")
        assert entry["document_id"] == "doc_1"

    def test_clear(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        store.upsert("a", {"x": 1})
        store.upsert("b", {"x": 2})
        assert store.clear() == 2
        assert store.count() == 0

    def test_corrupt_file_recovered(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text("{corrupt json", encoding="utf-8")
        store = ManifestStore(str(path))
        assert store.count() == 0
        store.upsert("doc_1", {"status": "completed"})
        assert store.get("doc_1")["status"] == "completed"

    def test_to_manifest(self, tmp_path):
        store = ManifestStore(str(tmp_path / "manifest.json"))
        store.upsert("doc_1", {
            "document_id": "doc_1", "filename": "m.pdf", "source_id": "src_1",
            "source_type": "pdf", "content_hash": "h", "parser_version": "1.0",
            "chunking_version": "2.0", "embedding_model": "m", "embedding_version": "v",
            "indexed_at": "t", "chunks": 5, "status": "completed",
        })
        m = store.to_manifest("doc_1")
        assert isinstance(m, IndexingManifest)
        assert m.chunks == 5