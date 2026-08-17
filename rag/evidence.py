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

    # Contrato rico do índice (§4/§24/§31)
    section: str = ""
    subsection: str = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    manufacturer: str = ""
    model: str = ""
    device_type: str = ""
    document_type: str = ""
    error_codes: List[str] = field(default_factory=list)
    version: str = ""
    chunk_id: str = ""
    document_id: str = ""
    _cached_id: str = field(init=False, repr=False)

    def __post_init__(self):
        self._cached_id = f"{self.provider}::{self.source}::{hash(self.content[:100])}"

    @property
    def id(self) -> str:
        return self._cached_id

    def __hash__(self) -> int:
        return hash(self._cached_id)

    @property
    def context_label(self) -> str:
        """Rótulo compacto de contexto (fabricante/modelo/seção/página)."""
        parts: List[str] = []
        if self.manufacturer:
            parts.append(self.manufacturer)
        if self.model:
            parts.append(self.model)
        if self.section:
            parts.append(f"seção: {self.section}")
        if self.page_start is not None:
            parts.append(f"pág. {self.page_start}")
        if self.error_codes:
            parts.append(f"códigos: {', '.join(self.error_codes)}")
        return " | ".join(parts)


class EvidenceNormalizer:
    @staticmethod
    def from_chroma_document(doc: Document) -> Evidence:
        meta = doc.metadata or {}
        return Evidence(
            provider="chroma",
            source=meta.get("filename", meta.get("source", "documento")),
            title=meta.get("filename", ""),
            url="",
            content=doc.page_content,
            score=meta.get("relevance_score", 0.5),
            metadata=dict(meta),
            source_type="rag",
            section=meta.get("section", ""),
            subsection=meta.get("subsection", ""),
            page_start=meta.get("page_start"),
            page_end=meta.get("page_end"),
            manufacturer=meta.get("manufacturer", ""),
            model=meta.get("model", ""),
            device_type=meta.get("device_type", ""),
            document_type=meta.get("document_type", ""),
            error_codes=list(meta.get("error_codes", [])),
            version=meta.get("version", ""),
            chunk_id=meta.get("chunk_id", ""),
            document_id=meta.get("document_id", ""),
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
            if ev.context_label:
                block += f"Contexto: {ev.context_label}\n"
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
