import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from typing import TYPE_CHECKING

from langchain_core.documents import Document

if TYPE_CHECKING:
    from search.fetcher import FetchResult
    from search.provider import SearchResult


@dataclass
class Evidence:
    provider: str
    source: str
    content: str
    title: str = ""
    url: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "web"

    @property
    def id(self) -> str:
        return f"{self.provider}::{self.source}::{hash(self.content[:100])}"

    def __hash__(self) -> int:
        return hash(self.id)


class EvidenceNormalizer:
    @staticmethod
    def from_search_result(result) -> "Evidence":
        from search.provider import SearchResult
        if not isinstance(result, SearchResult):
            result = SearchResult(
                title=getattr(result, "title", ""),
                url=getattr(result, "url", ""),
                snippet=getattr(result, "snippet", ""),
                source=getattr(result, "source", "web"),
            )
        return Evidence(
            provider=result.source,
            source=result.url,
            title=result.title,
            url=result.url,
            content=result.snippet,
            score=0.5,
            metadata={"snippet": result.snippet},
            source_type="web",
        )

    @staticmethod
    def from_fetch_result(fetch, search_result=None) -> "Evidence":
        title = search_result.title if search_result else ""
        return Evidence(
            provider="web",
            source=fetch.url,
            title=title,
            url=fetch.url,
            content=fetch.html,
            score=0.7,
            metadata={"status_code": fetch.status_code, "content_length": fetch.content_length},
            source_type="web",
        )

    @staticmethod
    def from_chroma_document(doc: Document) -> Evidence:
        return Evidence(
            provider="chroma",
            source=doc.metadata.get("filename", doc.metadata.get("source", "documento")),
            title=doc.metadata.get("filename", ""),
            url="",
            content=doc.page_content,
            score=doc.metadata.get("relevance_score", 0.5),
            metadata=dict(doc.metadata),
            source_type="rag",
        )

    @staticmethod
    def from_extracted_content(
        url: str,
        title: str,
        content: str,
        provider: str = "web",
        score: float = 0.7,
    ) -> Evidence:
        return Evidence(
            provider=provider,
            source=url,
            title=title,
            url=url,
            content=content,
            score=score,
            metadata={},
            source_type="web",
        )


class EvidenceAggregator:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger

    def collect(
        self,
        rag_evidence: Optional[List[Evidence]] = None,
        web_evidence: Optional[List[Evidence]] = None,
    ) -> List[Evidence]:
        combined: List[Evidence] = []
        if rag_evidence:
            combined.extend(rag_evidence)
        if web_evidence:
            combined.extend(web_evidence)

        if self.logger:
            rag_count = sum(1 for e in combined if e.source_type == "rag")
            web_count = sum(1 for e in combined if e.source_type == "web")
            self.logger.info(
                f"Collected {len(combined)} evidence "
                f"(rag={rag_count}, web={web_count})"
            )
        return self.deduplicate(combined)

    def deduplicate(self, evidence: List[Evidence]) -> List[Evidence]:
        seen: set = set()
        unique: List[Evidence] = []
        for ev in evidence:
            key = ev.id
            if key not in seen:
                seen.add(key)
                unique.append(ev)
        if self.logger:
            dups = len(evidence) - len(unique)
            if dups:
                self.logger.debug(f"Removed {dups} duplicate evidence")
        return unique

    def rank(self, evidence: List[Evidence]) -> List[Evidence]:
        return sorted(evidence, key=lambda e: e.score, reverse=True)

    def format_for_prompt(self, evidence: List[Evidence]) -> str:
        parts: List[str] = []
        for ev in evidence:
            block = f"============================\n"
            block += f"Fonte: {ev.provider}\n"
            if ev.url:
                block += f"URL: {ev.url}\n"
            if ev.title:
                block += f"Título: {ev.title}\n"
            block += f"\n{ev.content}\n"
            parts.append(block)
        return "\n\n".join(parts)

    def sources_text(self, evidence: List[Evidence]) -> str:
        sources: set = set()
        for ev in evidence:
            if ev.url:
                if ev.title:
                    sources.add(f"{ev.title} ({ev.url})")
                else:
                    sources.add(ev.url)
            else:
                sources.add(ev.source)
        return "; ".join(sorted(sources))
