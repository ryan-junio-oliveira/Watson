from unittest.mock import MagicMock, patch

from ingestion.embeddings import EmbeddingGenerator


def _mock_model():
    m = MagicMock()
    m.get_embedding_dimension.return_value = 384
    m.get_sentence_embedding_dimension.return_value = 384
    # encode returns numpy-like list per text
    def _encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True):
        import numpy as np

        # return dummy vectors of 384 floats per text
        arr = np.random.rand(len(texts), 384).astype(float)
        # mimic SentenceTransformer encode returning array with .tolist()
        mock_arr = MagicMock()
        mock_arr.tolist.return_value = arr.tolist()
        # also allow direct tolist if convert_to_numpy True path uses .tolist on returned object
        # Our code does embeddings.tolist(), so mock needs tolist
        # For simplicity return list directly if we bypass tolist check
        return arr

    m.encode.side_effect = _encode
    return m


class TestEmbeddingGenerator:
    def test_get_embeddings(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        embeddings = generator.get_embeddings()
        assert embeddings is not None
        assert hasattr(embeddings, "embed_query")
        assert hasattr(embeddings, "embed_documents")

    def test_embed_query(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        with patch.object(generator, "_load_model", return_value=_mock_model()):
            # bypass cache encoding via direct _encode mock
            generator._encode = MagicMock(return_value=[[0.1] * 384])
            embeddings = generator.get_embeddings()
            result = embeddings.embed_query("teste de pergunta")
            assert isinstance(result, list)
            assert len(result) > 0
            assert all(isinstance(v, float) for v in result)

    def test_embed_documents(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        with patch.object(generator, "_load_model", return_value=_mock_model()):
            generator._encode = MagicMock(return_value=[[0.1] * 384, [0.2] * 384, [0.3] * 384])
            embeddings = generator.get_embeddings()
            results = embeddings.embed_documents(["doc1", "doc2", "doc3"])
            assert len(results) == 3
            assert all(isinstance(r, list) for r in results)

    def test_model_caching(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        emb1 = generator.get_embeddings()
        emb2 = generator.get_embeddings()
        assert emb1 is emb2

    def test_custom_model_name(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        assert generator.model_name == "all-MiniLM-L6-v2"
