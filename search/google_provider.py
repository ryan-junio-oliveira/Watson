import logging
from typing import List, Optional

from googlesearch import search as google_search

from search.provider import SearchProvider, SearchResult


class GoogleProvider(SearchProvider):
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            results: List[SearchResult] = []
            for r in google_search(query, num_results=max_results, advanced=True):
                results.append(
                    SearchResult(
                        title=r.title,
                        url=r.url,
                        snippet=r.description,
                        source="google",
                    )
                )
            if self.logger:
                self.logger.info(
                    f"GoogleProvider: {len(results)} results for '{query[:60]}'"
                )
            return results
        except Exception as e:
            if self.logger:
                self.logger.warning(f"GoogleProvider failed: {e}")
            return []
