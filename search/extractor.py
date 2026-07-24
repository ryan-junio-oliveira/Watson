import logging
from typing import Optional

import trafilatura

from search.fetcher import FetchResult


class ContentExtractor:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger

    def extract(self, html: str) -> str:
        try:
            text = trafilatura.extract(
                html,
                include_links=False,
                include_images=False,
                include_tables=True,
                include_formatting=False,
                output_format="txt",
                favor_precision=True,
            )
            if text:
                text = text.strip()
            if self.logger:
                self.logger.debug(
                    f"Extracted {len(text or '')} chars from {len(html)} bytes of HTML"
                )
            return text or ""
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Content extraction failed: {e}")
            return ""

    def extract_from_fetch(self, fetch_result: FetchResult) -> str:
        if fetch_result.status_code != 200:
            if self.logger:
                self.logger.warning(
                    f"Non-200 status {fetch_result.status_code} for {fetch_result.url[:60]}"
                )
            return ""
        return self.extract(fetch_result.html)

    def extract_from_url(self, url: str) -> str:
        try:
            html = trafilatura.fetch_url(url)
            if not html:
                if self.logger:
                    self.logger.warning(f"Failed to download {url[:60]}")
                return ""
            return self.extract(html)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to extract from URL {url[:60]}: {e}")
            return ""
