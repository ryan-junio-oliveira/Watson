import logging
from typing import List, Optional

from search.provider import SearchProvider, SearchResult


class DDGSProvider(SearchProvider):
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
                results: List[SearchResult] = [
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        source="ddgs",
                    )
                    for r in raw
                ]
            if self.logger:
                self.logger.info(
                    f"DDGSProvider: {len(results)} results for '{query[:60]}'"
                )
            return results
        except Exception as e:
            if self.logger:
                self.logger.warning(f"DDGSProvider failed: {e}")
            return []
