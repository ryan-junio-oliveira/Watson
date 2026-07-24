from unittest.mock import MagicMock, patch

import pytest

from search.extractor import ContentExtractor
from search.fetcher import FetchResult


class TestContentExtractor:
    def test_extract_empty_html(self):
        extractor = ContentExtractor()
        result = extractor.extract("")
        assert result == ""

    def test_extract_no_content(self):
        extractor = ContentExtractor()
        result = extractor.extract("<html><head></head><body></body></html>")
        assert result == ""

    @patch("search.extractor.trafilatura.extract")
    def test_extract_returns_text(self, mock_extract):
        mock_extract.return_value = "Texto extraído."
        extractor = ContentExtractor()
        result = extractor.extract("<html><body>Texto</body></html>")
        assert result == "Texto extraído."

    @patch("search.extractor.trafilatura.extract")
    def test_extract_handles_error(self, mock_extract):
        mock_extract.side_effect = Exception("erro")
        extractor = ContentExtractor()
        result = extractor.extract("<html></html>")
        assert result == ""

    @patch("search.extractor.trafilatura.extract")
    def test_extract_from_fetch(self, mock_extract):
        mock_extract.return_value = "Conteúdo da página."
        fetch_result = FetchResult(
            url="https://exemplo.com",
            html="<html><body>Conteúdo</body></html>",
            status_code=200,
            content_length=50,
        )
        extractor = ContentExtractor()
        result = extractor.extract_from_fetch(fetch_result)
        assert result == "Conteúdo da página."

    def test_extract_from_fetch_non_200(self):
        fetch_result = FetchResult(
            url="https://exemplo.com",
            html="<html>error</html>",
            status_code=404,
            content_length=20,
        )
        extractor = ContentExtractor()
        result = extractor.extract_from_fetch(fetch_result)
        assert result == ""
