from unittest.mock import MagicMock, patch

import pytest

from rag.evidence import Evidence
from search.reranker import Reranker


class TestSearchReranker:
    def test_rerank_empty(self):
        reranker = Reranker()
        result = reranker.rerank("pergunta", [])
        assert result == []

    @patch.object(Reranker, "_load_model")
    def test_rerank_returns_evidence(self, mock_load):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.5, 0.7]
        mock_load.return_value = mock_model

        evs = [
            Evidence(provider="web", source="url1", title="T1", url="https://a.com", content="texto a", score=0.0),
            Evidence(provider="web", source="url2", title="T2", url="https://b.com", content="texto b", score=0.0),
            Evidence(provider="web", source="url3", title="T3", url="https://c.com", content="texto c", score=0.0),
        ]
        reranker = Reranker()
        reranker._model = mock_model
        result = reranker.rerank("pergunta", evs, top_k=2)

        assert len(result) == 2
        assert result[0].score >= result[1].score
        assert all(isinstance(e, Evidence) for e in result)

    @patch.object(Reranker, "_load_model")
    def test_rerank_top_k_defaults_to_all(self, mock_load):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.5]
        mock_load.return_value = mock_model

        evs = [
            Evidence(provider="web", source="url1", content="a", url="https://a.com"),
            Evidence(provider="web", source="url2", content="b", url="https://b.com"),
        ]
        reranker = Reranker()
        reranker._model = mock_model
        result = reranker.rerank("pergunta", evs)
        assert len(result) == 2
