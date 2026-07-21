from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from rag.retriever import Retriever


class TestRetriever:
    @pytest.fixture
    def mock_embeddings(self):
        mock = MagicMock()
        mock.embed_query.return_value = [0.1] * 384
        return mock

    @pytest.fixture
    def mock_embedding_generator(self, mock_embeddings):
        generator = MagicMock()
        generator.get_embeddings.return_value = mock_embeddings
        return generator

    @pytest.fixture
    def mock_chroma(self):
        with patch("rag.retriever.Chroma") as mock:
            yield mock

    def test_retrieve_returns_documents(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.similarity_search_with_relevance_scores.return_value = [
            (Document(page_content="Resultado 1", metadata={"filename": "doc1.txt"}), 0.9),
            (Document(page_content="Resultado 2", metadata={"filename": "doc2.txt"}), 0.8),
        ]

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=2,
        )
        results = retriever.retrieve("pergunta de teste")
        assert len(results) == 2
        assert all(isinstance(d, Document) for d in results)
        assert results[0].page_content == "Resultado 1"

    def test_retrieve_adds_relevance_score(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.similarity_search_with_relevance_scores.return_value = [
            (Document(page_content="Doc A", metadata={"filename": "a.txt"}), 0.95),
        ]

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=1,
        )
        results = retriever.retrieve("teste")
        assert "relevance_score" in results[0].metadata
        assert results[0].metadata["relevance_score"] == 0.95

    def test_retrieve_calls_similarity_search(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.similarity_search_with_relevance_scores.return_value = []

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=3,
        )
        retriever.retrieve("teste")
        mock_chroma_instance.similarity_search_with_relevance_scores.assert_called_once_with(
            "teste", k=3
        )

    def test_retrieve_empty_results(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.similarity_search_with_relevance_scores.return_value = []

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=5,
        )
        results = retriever.retrieve("pergunta sem match")
        assert results == []

    def test_retrieve_filters_by_threshold(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.similarity_search_with_relevance_scores.return_value = [
            (Document(page_content="Alta", metadata={"filename": "a.txt"}), 0.95),
            (Document(page_content="Baixa", metadata={"filename": "b.txt"}), 0.30),
        ]

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=5,
            similarity_threshold=0.5,
        )
        results = retriever.retrieve("teste")
        assert len(results) == 1
        assert results[0].page_content == "Alta"

    def test_vector_store_caching(self, mock_embedding_generator, mock_chroma):
        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=5,
        )
        vs1 = retriever._get_vector_store()
        vs2 = retriever._get_vector_store()
        assert vs1 is vs2
        assert mock_chroma.call_count == 1

    def test_retrieve_uses_mmr_when_enabled(self, mock_embedding_generator, mock_chroma):
        mock_chroma_instance = mock_chroma.return_value
        mock_chroma_instance.max_marginal_relevance_search.return_value = [
            Document(page_content="MMR Doc 1", metadata={"filename": "doc1.txt"}),
            Document(page_content="MMR Doc 2", metadata={"filename": "doc2.txt"}),
        ]

        retriever = Retriever(
            embedding_generator=mock_embedding_generator,
            chroma_persist_dir="/tmp/test_chroma",
            top_k=2,
            use_mmr=True,
            mmr_fetch_k=10,
            mmr_lambda=0.7,
        )
        results = retriever.retrieve("teste mmr")
        assert len(results) == 2
        mock_chroma_instance.max_marginal_relevance_search.assert_called_once_with(
            "teste mmr", k=2, fetch_k=10, lambda_mult=0.7
        )
