from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int) -> List[SearchResult]:
        ...
