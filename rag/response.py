from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from rag.evidence import Evidence


class Mode(str, Enum):
    auto = "auto"
    rag = "rag"


@dataclass
class Source:
    title: str
    url: str = ""
    provider: str = "rag"

    def to_dict(self) -> Dict[str, str]:
        d: Dict[str, str] = {"title": self.title, "url": self.url}
        if self.provider:
            d["provider"] = self.provider
        return d

    @staticmethod
    def from_evidence(ev: Evidence) -> "Source":
        return Source(
            title=ev.title or ev.source,
            url=ev.url,
            provider=ev.provider,
        )

    @staticmethod
    def from_evidence_list(evidences: List[Evidence]) -> List["Source"]:
        seen: set = set()
        sources: List[Source] = []
        for ev in evidences:
            src = Source.from_evidence(ev)
            key = src.url or src.title
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

    @property
    def sources(self) -> List[Source]:
        return Source.from_evidence_list(self.evidences)

    @property
    def evidence_count(self) -> int:
        return len(self.evidences)
