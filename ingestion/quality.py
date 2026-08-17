"""Quality gate da indexação (§25).

Antes de indexar um chunk, atribui scores de qualidade:

- **text_quality**: densidade/quantidade de conteúdo útil.
- **structure_quality**: presença de contexto estrutural (seção, página, tipo).
- **ocr_quality**: proxy para conteúdo vindo de OCR (menos confiável).
- **metadata_quality**: presença de identidade (document_id, source_id, tipo).

Chunks abaixo do limiar são **rejeitados** (contabilizados) — não poluem o
índice com ruído.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from langchain_core.documents import Document

from ingestion.models import LoadedDocument

_ALNUM_RE = re.compile(r"[a-zA-Z0-9áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]")


@dataclass
class QualityScore:
    text_quality: float = 0.0
    structure_quality: float = 0.0
    ocr_quality: float = 0.0
    metadata_quality: float = 0.0
    total: float = 0.0
    accepted: bool = False
    reasons: List[str] = field(default_factory=list)


class QualityGate:
    def __init__(
        self,
        min_total: float = 0.35,
        min_text: float = 0.15,
        min_chars: int = 20,
    ):
        self.min_total = min_total
        self.min_text = min_text
        self.min_chars = min_chars

    def assess(self, chunk: Document, doc: LoadedDocument) -> QualityScore:
        content = chunk.page_content or ""
        meta = chunk.metadata or {}
        reasons: List[str] = []

        text_quality = self._text_quality(content)
        if text_quality < self.min_text:
            reasons.append("low_text_quality")

        structure_quality = self._structure_quality(meta)
        if structure_quality <= 0.5:
            reasons.append("low_structure_quality")

        ocr_quality = self._ocr_quality(doc, content)
        metadata_quality = self._metadata_quality(meta)

        total = (
            0.35 * text_quality
            + 0.25 * structure_quality
            + 0.20 * ocr_quality
            + 0.20 * metadata_quality
        )

        accepted = (
            len(content) >= self.min_chars
            and text_quality >= self.min_text
            and total >= self.min_total
        )
        if len(content) < self.min_chars:
            reasons.append("too_short")

        return QualityScore(
            text_quality=round(text_quality, 3),
            structure_quality=round(structure_quality, 3),
            ocr_quality=round(ocr_quality, 3),
            metadata_quality=round(metadata_quality, 3),
            total=round(total, 3),
            accepted=accepted,
            reasons=reasons,
        )

    # ------------------------------------------------------------------ #

    def _text_quality(self, content: str) -> float:
        if not content:
            return 0.0
        alnum = len(_ALNUM_RE.findall(content))
        ratio = alnum / max(len(content), 1)
        length_score = min(1.0, len(content) / 300.0)
        return max(0.0, min(1.0, 0.6 * ratio + 0.4 * length_score))

    def _structure_quality(self, meta) -> float:
        score = 0.0
        if meta.get("section") or meta.get("subsection"):
            score += 0.4
        if meta.get("page_start") is not None:
            score += 0.3
        if meta.get("source_type"):
            score += 0.3
        return min(1.0, score)

    def _ocr_quality(self, doc: LoadedDocument, content: str) -> float:
        if not doc.pages:
            return 1.0  # sem páginas OCR envolvidas, não penaliza
        ocr_pages = sum(1 for p in doc.pages if p.ocr)
        if ocr_pages == 0:
            return 1.0
        # Proxy: conteúdo curto vindo de OCR é menos confiável
        if len(content.strip()) < 60:
            return 0.3
        return 0.8

    def _metadata_quality(self, meta) -> float:
        score = 0.0
        if meta.get("document_id"):
            score += 0.4
        if meta.get("source_id"):
            score += 0.3
        if meta.get("source_type"):
            score += 0.3
        return min(1.0, score)
