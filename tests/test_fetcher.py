from unittest.mock import MagicMock, patch

import httpx
import pytest

from search.fetcher import PageFetcher, _exponential_backoff, _is_valid_url


class TestUrlValidation:
    def test_valid_http(self):
        assert _is_valid_url("http://exemplo.com")

    def test_valid_https(self):
        assert _is_valid_url("https://exemplo.com/pagina?q=1")

    def test_invalid_no_scheme(self):
        assert not _is_valid_url("exemplo.com")

    def test_invalid_empty(self):
        assert not _is_valid_url("")

    def test_invalid_ftp(self):
        assert not _is_valid_url("ftp://exemplo.com")


class TestExponentialBackoff:
    def test_first_attempt(self):
        assert _exponential_backoff(1) == 1.0

    def test_second_attempt(self):
        assert _exponential_backoff(2) == 2.0

    def test_third_attempt(self):
        assert _exponential_backoff(3) == 4.0

    def test_capped(self):
        assert _exponential_backoff(10) <= 30.0


class TestPageFetcher:
    @patch("search.fetcher.httpx.Client")
    def test_fetch_success(self, mock_client_cls):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "<html>conteudo</html>"
        mock_response.content = b"<html>conteudo</html>"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetcher = PageFetcher(max_retries=0)
        result = fetcher.fetch("https://exemplo.com")

        assert result is not None
        assert result.url == "https://exemplo.com"
        assert result.status_code == 200
        assert result.html == "<html>conteudo</html>"

    @patch("search.fetcher.httpx.Client")
    def test_fetch_invalid_url(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        fetcher = PageFetcher(max_retries=0)
        result = fetcher.fetch("not-a-url")
        assert result is None
        mock_client.get.assert_not_called()

    @patch("search.fetcher.httpx.Client")
    def test_fetch_too_large(self, mock_client_cls):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.content = b"x" * 100
        mock_response.text = "x" * 100
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetcher = PageFetcher(max_size=50, max_retries=0)
        result = fetcher.fetch("https://exemplo.com")
        assert result is None

    def test_cache(self):
        fetcher = PageFetcher(max_retries=0)
        assert fetcher._check_cache("https://exemplo.com") is None
        from search.fetcher import FetchResult
        r = FetchResult(url="https://exemplo.com", html="ok", status_code=200, content_length=2)
        fetcher._add_to_cache("https://exemplo.com", r)
        cached = fetcher._check_cache("https://exemplo.com")
        assert cached is not None
        assert cached.html == "ok"

    def test_clear_cache(self):
        fetcher = PageFetcher(max_retries=0)
        from search.fetcher import FetchResult
        r = FetchResult(url="https://exemplo.com", html="ok", status_code=200, content_length=2)
        fetcher._add_to_cache("https://exemplo.com", r)
        assert fetcher._check_cache("https://exemplo.com") is not None
        fetcher.clear_cache()
        assert fetcher._check_cache("https://exemplo.com") is None
