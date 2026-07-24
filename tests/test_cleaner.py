from search.cleaner import ContentCleaner


class TestContentCleaner:
    def test_clean_empty(self):
        cleaner = ContentCleaner()
        assert cleaner.clean("") == ""

    def test_clean_removes_excess_newlines(self):
        cleaner = ContentCleaner()
        result = cleaner.clean("a\n\n\n\nb")
        assert result == "a\n\n\nb"

    def test_clean_normalizes_line_endings(self):
        cleaner = ContentCleaner()
        result = cleaner.clean("a\r\nb\rc")
        assert "\r" not in result

    def test_clean_html_entities(self):
        cleaner = ContentCleaner()
        result = cleaner.clean(
            "a &amp; b &lt; c &gt; d &quot; e &#39; f"
        )
        assert "&amp;" not in result
        assert "&lt;" not in result
        assert "&gt;" not in result
        assert "&quot;" not in result
        assert "&#39;" not in result

    def test_clean_trims_whitespace(self):
        cleaner = ContentCleaner()
        result = cleaner.clean("  hello world  ")
        assert result == "hello world"

    def test_clean_collapses_spaces(self):
        cleaner = ContentCleaner()
        result = cleaner.clean("hello    world")
        assert "  " not in result
