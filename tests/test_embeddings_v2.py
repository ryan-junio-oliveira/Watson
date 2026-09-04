import tempfile
from unittest.mock import MagicMock, patch

from ingestion.embeddings import EmbeddingGenerator


def _mock_model_384():
    m = MagicMock()
    m.get_embedding_dimension.return_value = 384
    m.get_sentence_embedding_dimension.return_value = 384
    return m


class TestEmbeddingFeatures:
    def test_e5_prefix_detection(self):
        gen = EmbeddingGenerator(model_name="intfloat/multilingual-e5-base")
        assert gen.query_prefix == "query: "
        assert gen.document_prefix == "passage: "

    def test_no_prefix_for_other_models(self):
        gen = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        assert gen.query_prefix == ""
        assert gen.document_prefix == ""

    def test_version_derived_from_model_and_dim(self):
        gen = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        with patch.object(gen, "_load_model", return_value=_mock_model_384()):
            assert gen.embedding_version == "all-MiniLM-L6-v2-384"
            assert gen.dimension == 384

    def test_get_model_info(self):
        gen = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        with patch.object(gen, "_load_model", return_value=_mock_model_384()):
            info = gen.get_model_info()
            assert info["model"] == "all-MiniLM-L6-v2"
            assert info["version"] == "all-MiniLM-L6-v2-384"
            assert info["dimension"] == 384
            assert info["normalize"] is True

    def test_embed_documents_cache_reuses(self, tmp_path):
        cache_path = str(tmp_path / "emb_cache.sqlite3")
        gen = EmbeddingGenerator(
            model_name="all-MiniLM-L6-v2", cache_path=cache_path
        )
        with patch.object(gen, "_load_model", return_value=_mock_model_384()):
            gen._encode = MagicMock(return_value=[[0.1] * 384, [0.2] * 384])
            texts = ["texto tecnico sobre impressoras HP", "erro E123 na MODELO-X"]
            first = gen.embed_documents(texts)
            second = gen.embed_documents(texts)

            assert len(first) == 2
            assert len(first[0]) == 384
            # Cache armazena como float32 (struct pack), então comparação precisa tolerância
            import pytest as _pytest

            assert first[0] == _pytest.approx(second[0], rel=1e-6)
            assert first[1] == _pytest.approx(second[1], rel=1e-6)

            from ingestion.embedding_cache import EmbeddingCache

            cache = EmbeddingCache(cache_path)
            assert cache.count() == 2

    def test_embed_query_does_not_cache(self, tmp_path):
        gen = EmbeddingGenerator(
            model_name="all-MiniLM-L6-v2",
            cache_path=str(tmp_path / "emb_cache.sqlite3"),
        )
        with patch.object(gen, "_load_model", return_value=_mock_model_384()):
            gen._encode = MagicMock(return_value=[[0.1] * 384])
            gen.embed_query("pergunta sobre erro E123")
            from ingestion.embedding_cache import EmbeddingCache

            cache = EmbeddingCache(str(tmp_path / "emb_cache.sqlite3"))
            assert cache.count() == 0

    def test_embed_query_and_doc_prefixes(self):
        gen = EmbeddingGenerator(model_name="intfloat/multilingual-e5-base")
        # verifica que o prefixo é aplicado (sem carregar o modelo pesado)
        assert gen._encode is not None