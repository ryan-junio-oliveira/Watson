import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document


@dataclass
class Evidence:
    provider: str
    source: str
    content: str
    title: str = ""
    url: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "rag"
    _cached_id: str = field(init=False, repr=False)

    def __post_init__(self):
        self._cached_id = f"{self.provider}::{self.source}::{hash(self.content[:100])}"

    @property
    def id(self) -> str:
        return self._cached_id

    def __hash__(self) -> int:
        return hash(self._cached_id)


class EvidenceNormalizer:
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


class EvidenceAggregator:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger

    def collect(
        self,
        rag_evidence: Optional[List[Evidence]] = None,
    ) -> List[Evidence]:
        combined: List[Evidence] = list(rag_evidence) if rag_evidence else []

        if self.logger:
            self.logger.info(
                f"Collected {len(combined)} evidence chunks"
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
            block = "============================\n"
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
