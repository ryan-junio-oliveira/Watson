import tempfile

import pytest

from ingestion.embedding_cache import EmbeddingCache


class TestEmbeddingCache:
    def test_set_get_roundtrip(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        cache.set_many([("hash1", "model-a", "v1", 4, [0.1, 0.2, 0.3, 0.4])])
        vec = cache.get("hash1", "model-a", "v1")
        assert vec == pytest.approx([0.1, 0.2, 0.3, 0.4])

    def test_get_missing_returns_none(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        assert cache.get("nope", "model-a", "v1") is None

    def test_get_many_with_misses(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        cache.set_many([("a", "m", "v", 2, [1.0, 2.0])])
        result = cache.get_many(["a", "b"], "m", "v")
        assert result["a"] == [1.0, 2.0]
        assert result["b"] is None

    def test_model_and_version_scoping(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        cache.set_many([("h", "model-a", "v1", 2, [1.0, 1.0])])
        assert cache.get("h", "model-a", "v1") == [1.0, 1.0]
        assert cache.get("h", "model-a", "v2") is None
        assert cache.get("h", "model-b", "v1") is None

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "cache.sqlite3")
        cache = EmbeddingCache(path)
        cache.set_many([("h", "m", "v", 3, [1.0, 2.0, 3.0])])
        cache.close()

        cache2 = EmbeddingCache(path)
        assert cache2.get("h", "m", "v") == [1.0, 2.0, 3.0]

    def test_count_and_clear(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        cache.set_many([("a", "m", "v", 2, [0.0, 0.0]), ("b", "m", "v", 2, [1.0, 1.0])])
        assert cache.count() == 2
        cleared = cache.clear()
        assert cleared == 2
        assert cache.count() == 0

    def test_replace_existing(self, tmp_path):
        cache = EmbeddingCache(str(tmp_path / "cache.sqlite3"))
        cache.set_many([("h", "m", "v", 2, [1.0, 1.0])])
        cache.set_many([("h", "m", "v", 2, [9.0, 9.0])])
        assert cache.get("h", "m", "v") == [9.0, 9.0]
        assert cache.count() == 1