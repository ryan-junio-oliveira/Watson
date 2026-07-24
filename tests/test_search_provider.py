from unittest.mock import MagicMock, patch

import pytest

from search.ddgs_provider import DDGSProvider
from search.google_provider import GoogleProvider
from search.provider import SearchProvider, SearchResult


class TestSearchProvider:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            SearchProvider()


class TestSearchResult:
    def test_creation(self):
        r = SearchResult(title="Titulo", url="https://exemplo.com", snippet="Desc", source="google")
        assert r.title == "Titulo"
        assert r.url == "https://exemplo.com"
        assert r.snippet == "Desc"
        assert r.source == "google"


class TestGoogleProvider:
    @patch("search.google_provider.google_search")
    def test_search_returns_results(self, mock_gs):
        class MockResult:
            title = "Resultado"
            url = "https://exemplo.com"
            description = "Descricao"

        mock_gs.return_value = [MockResult(), MockResult()]
        provider = GoogleProvider()
        results = provider.search("teste", 5)
        assert len(results) == 2
        assert results[0].title == "Resultado"
        assert results[0].source == "google"
        mock_gs.assert_called_once_with("teste", num_results=5, advanced=True)

    @patch("search.google_provider.google_search")
    def test_search_returns_empty_on_error(self, mock_gs):
        mock_gs.side_effect = Exception("API error")
        provider = GoogleProvider()
        results = provider.search("teste", 5)
        assert results == []


class TestDDGSProvider:
    @patch("ddgs.DDGS")
    def test_search_returns_results(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__.return_value = mock_ddgs
        mock_ddgs_cls.return_value = mock_ddgs
        mock_ddgs.text.return_value = [
            {"title": "R1", "href": "https://r1.com", "body": "body1"},
            {"title": "R2", "href": "https://r2.com", "body": "body2"},
        ]
        provider = DDGSProvider()
        results = provider.search("teste", 5)
        assert len(results) == 2
        assert results[0].title == "R1"
        assert results[0].source == "ddgs"

    @patch("ddgs.DDGS")
    def test_search_returns_empty_on_error(self, mock_ddgs_cls):
        mock_ddgs_cls.side_effect = Exception("error")
        provider = DDGSProvider()
        results = provider.search("teste", 5)
        assert results == []
