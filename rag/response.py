from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from rag.evidence import Evidence


class Mode(str, Enum):
    auto = "auto"
    rag = "rag"
    web = "web"


@dataclass
class Source:
    title: str
    url: str = ""
    provider: str = "rag"
    page: Optional[int] = None
    section: str = ""
    manufacturer: str = ""
    model: str = ""
    error_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, str]:
        d: Dict[str, str] = {"title": self.title, "url": self.url}
        if self.provider:
            d["provider"] = self.provider
        if self.page is not None:
            d["page"] = self.page
        if self.section:
            d["section"] = self.section
        if self.manufacturer:
            d["manufacturer"] = self.manufacturer
        if self.model:
            d["model"] = self.model
        if self.error_codes:
            d["error_codes"] = self.error_codes
        return d

    @staticmethod
    def from_evidence(ev: Evidence) -> "Source":
        return Source(
            title=ev.title or ev.source,
            url=ev.url,
            provider=ev.provider,
            page=ev.page_start,
            section=ev.section,
            manufacturer=ev.manufacturer,
            model=ev.model,
            error_codes=ev.error_codes,
        )

    @staticmethod
    def from_evidence_list(evidences: List[Evidence]) -> List["Source"]:
        seen: set = set()
        sources: List[Source] = []
        for ev in evidences:
            src = Source.from_evidence(ev)
            # normaliza url para deduplicar (lower + sem barra final)
            raw = (src.url or "").strip().lower().replace(" ", "")
            norm = raw.rstrip("/") if raw else (src.title or "").strip().lower()
            key = norm
            if key and key not in seen:
                seen.add(key)
                sources.append(src)
        return sources


@dataclass
class AgentResponse:
    answer: str
    evidences: List[Evidence]
    confidence: float = 0.0
    verdict: str = "unknown"
    issues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0

    # Analista proativo (sob demanda — chips na UI)
    conclusions: List[str] = field(default_factory=list)
    follow_up: List[str] = field(default_factory=list)
    additional_info: List[str] = field(default_factory=list)

    @property
    def sources(self) -> List[Source]:
        return Source.from_evidence_list(self.evidences)

    @property
    def evidence_count(self) -> int:
        return len(self.evidences)
