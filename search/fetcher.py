import logging
import re
import time
from dataclasses import dataclass
from email.utils import formatdate
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx


@dataclass
class FetchResult:
    url: str
    html: str
    status_code: int
    content_length: int


_URL_PATTERN = re.compile(
    r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE
)


def _is_valid_url(url: str) -> bool:
    if not _URL_PATTERN.match(url):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _exponential_backoff(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    return min(base * (2 ** (attempt - 1)), max_delay)


class PageFetcher:
    def __init__(
        self,
        timeout: float = 15.0,
        max_size: int = 2 * 1024 * 1024,
        user_agent: str = "WatsonRAG/1.0",
        max_retries: int = 2,
        cache_ttl: float = 3600.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.timeout = timeout
        self.max_size = max_size
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self.logger = logger
        self._cache: Dict[str, Tuple[float, FetchResult]] = {}
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            max_redirects=5,
        )

    def fetch(self, url: str) -> Optional[FetchResult]:
        if not _is_valid_url(url):
            if self.logger:
                self.logger.warning(f"Invalid URL: {url}")
            return None

        cached = self._check_cache(url)
        if cached is not None:
            return cached

        if self.logger:
            self.logger.info(f"Fetching: {url[:80]}")

        for attempt in range(1, self.max_retries + 2):
            try:
                response = self._client.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                )
                content = response.content
                content_length = len(content)

                if content_length > self.max_size:
                    if self.logger:
                        self.logger.warning(
                            f"Content too large: {content_length} bytes "
                            f"(max {self.max_size}) for {url[:60]}"
                        )
                    return None

                result = FetchResult(
                    url=url,
                    html=response.text,
                    status_code=response.status_code,
                    content_length=content_length,
                )

                self._add_to_cache(url, result)
                if self.logger:
                    self.logger.info(
                        f"Fetched {url[:60]} -> {response.status_code} "
                        f"({content_length} bytes)"
                    )
                return result

            except httpx.TimeoutException:
                if self.logger:
                    self.logger.warning(
                        f"Timeout fetching {url[:60]} (attempt {attempt})"
                    )
            except httpx.HTTPStatusError as e:
                if self.logger:
                    self.logger.warning(
                        f"HTTP {e.response.status_code} for {url[:60]}"
                    )
                if e.response.status_code < 500:
                    return None
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Error fetching {url[:60]}: {e} (attempt {attempt})"
                    )

            if attempt <= self.max_retries:
                delay = _exponential_backoff(attempt)
                if self.logger:
                    self.logger.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)

        if self.logger:
            self.logger.error(f"Failed to fetch {url[:60]} after all retries")
        return None

    def _check_cache(self, url: str) -> Optional[FetchResult]:
        import time as t

        entry = self._cache.get(url)
        if entry is not None:
            timestamp, result = entry
            if t.time() - timestamp < self.cache_ttl:
                if self.logger:
                    self.logger.debug(f"Cache hit: {url[:60]}")
                return result
            del self._cache[url]
        return None

    def _add_to_cache(self, url: str, result: FetchResult) -> None:
        import time as t

        self._cache[url] = (t.time(), result)

    def clear_cache(self) -> None:
        self._cache.clear()
        if self.logger:
            self.logger.debug("Cache cleared")

    def close(self) -> None:
        self._client.close()
