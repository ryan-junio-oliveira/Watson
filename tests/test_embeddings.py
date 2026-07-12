from ingestion.embeddings import EmbeddingGenerator


class TestEmbeddingGenerator:
    def test_get_embeddings(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        embeddings = generator.get_embeddings()
        assert embeddings is not None
        assert hasattr(embeddings, "embed_query")
        assert hasattr(embeddings, "embed_documents")

    def test_embed_query(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
        embeddings = generator.get_embeddings()
        result = embeddings.embed_query("teste de pergunta")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(v, float) for v in result)

    def test_embed_documents(self):
        generator = EmbeddingGenerator(model_name="all-MiniLM-L6-v2")
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
