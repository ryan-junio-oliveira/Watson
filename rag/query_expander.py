"""Expansão e decomposição de queries para raciocínio multi-step.

Gera sub-queries para perguntas complexas (comparação, tendência, agregação)
usando heurísticas leves + LLM opcional. Implementa RRF fusion para multi-retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document


@dataclass
class ExpandedQuery:
    original: str
    variants: List[str]
    intent: str  # percent_change | sum | average | max | min | compare | trend | listing | factual
    needs_reasoning: bool


_COMPARE_RE = re.compile(
    r"comparar|comparação|comparacao|diferença|diferenca|versus|vs\.?|tendência|tendencia|evolução|evolucao|ao longo|entre .* e",
    re.IGNORECASE,
)
_LISTING_RE = re.compile(r"list|liste|quais|disponíve|disponive|enumer|relacione|catálogo|catalogo", re.IGNORECASE)
_TEMPORAL_RE = re.compile(r" (janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|\b20\d{2}\b)", re.IGNORECASE)
_AND_SPLIT_RE = re.compile(r"\s+e\s+|\s*,\s*|\s+vs\.?\s+", re.IGNORECASE)


class QueryExpander:
    """Heurístico, sem custo de LLM por padrão. LLM pode ser plugado depois."""

    def __init__(self, max_variants: int = 3):
        self.max_variants = max_variants

    def expand(self, question: str) -> ExpandedQuery:
        q = question.strip()
        intent = self._detect_intent(q)
        variants = self._generate_variants(q, intent)
        # Remove duplicatas preservando ordem
        seen = set()
        uniq: List[str] = []
        for v in variants:
            low = v.lower().strip()
            if low and low not in seen:
                seen.add(low)
                uniq.append(v)
        # Original sempre primeiro
        if q.lower() not in seen:
            uniq.insert(0, q)
        uniq = uniq[: self.max_variants]
        needs_reasoning = intent in {"percent_change", "difference", "sum", "average", "max", "min", "compare", "trend"}
        return ExpandedQuery(original=q, variants=uniq, intent=intent, needs_reasoning=needs_reasoning)

    def _detect_intent(self, q: str) -> str:
        low = q.lower()
        # Reusa IntentDetector do calculator para consistência
        from rag.calculator import IntentDetector

        detector = IntentDetector()
        kind = detector.detect(q)
        if kind:
            return kind
        if _COMPARE_RE.search(q):
            return "compare" if "comparar" in low or "diferença" in low or "diferen" in low else "trend"
        if _LISTING_RE.search(q):
            return "listing"
        if _TEMPORAL_RE.search(q):
            return "trend"
        return "factual"

    def _generate_variants(self, q: str, intent: str) -> List[str]:
        variants: List[str] = [q]
        # Para comparação/percentual, tenta quebrar em 2 sub-queries temporais ou por entidade
        if intent in {"percent_change", "difference", "compare", "trend"}:
            # Ex.: "Comparar vendas jan e fev" -> ["vendas jan", "vendas fev"]
            entities = self._extract_entities(q)
            if len(entities) >= 2:
                for ent in entities[:2]:
                    # Remove verbos de comparação, mantém núcleo
                    core = re.sub(r"comparar|variação|percentual|diferença|tendência", "", q, flags=re.IGNORECASE).strip()
                    if ent.lower() not in core.lower():
                        variants.append(ent)
                    else:
                        variants.append(core)
            # Variação com sinônimos para melhorar recall de embeddings E5
            if "cresceu" in q.lower() or "aumentou" in q.lower():
                variants.append(q.replace("cresceu", "variação").replace("aumentou", "variação"))
        elif intent in {"sum", "average", "max", "min"}:
            # Remove gatilho agregador, mantém o que agregar
            stripped = re.sub(r"quantos|quantas|total|soma|média|media|maior|menor|máximo|maximo|mínimo|minimo", "", q, flags=re.IGNORECASE).strip(" ?.,")
            if stripped and stripped != q:
                variants.append(stripped)
        # Para listagem, adiciona variante sem "quais"
        if intent == "listing":
            stripped = re.sub(r"quais são|quais sao|quais|liste|listar|disponíveis|disponiveis", "", q, flags=re.IGNORECASE).strip(" ?.,")
            if stripped and stripped != q:
                variants.append(stripped)
        return variants

    def _extract_entities(self, q: str) -> List[str]:
        # Heurística simples: pega trechos após "entre X e Y", "de X para Y", "jan e fev"
        candidates: List[str] = []
        # meses
        months = re.findall(r"\b(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b", q, re.IGNORECASE)
        if len(months) >= 2:
            candidates.extend(months[:2])
        # padrão "entre ... e ..."
        m = re.search(r"entre\s+(.+?)\s+e\s+(.+?)(?:\?|$)", q, re.IGNORECASE)
        if m:
            candidates.extend([m.group(1).strip(), m.group(2).strip()])
        # fallback: split por " e "
        if not candidates and " e " in q.lower():
            parts = _AND_SPLIT_RE.split(q)
            if len(parts) >= 2:
                # Pega últimos 2 segmentos que não são vazios
                filtered = [p.strip(" ?.,") for p in parts if len(p.strip()) > 3]
                if len(filtered) >= 2:
                    candidates.extend(filtered[-2:])
        return candidates


def reciprocal_rank_fusion(
    ranked_lists: List[List[Document]], k: int = 60, top_n: int = 20
) -> List[Document]:
    """Fusão RRF de múltiplas listas rankeadas. Preserva metadata e score RRF.

    Cada lista é assumida já ordenada por relevância decrescente.
    Score RRF = sum(1 / (k + rank)). Usa chunk_id como chave.
    """
    if not ranked_lists:
        return []
    if len(ranked_lists) == 1:
        return ranked_lists[0][:top_n]

    scores: Dict[str, float] = {}
    doc_map: Dict[str, Document] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs, start=1):
            cid = doc.metadata.get("chunk_id") or doc.metadata.get("source_id") or doc.page_content[:50]
            # Mantém primeiro doc encontrado para preservar metadata
            if cid not in doc_map:
                doc_map[cid] = doc
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)

    # Ordena por score RRF
    sorted_cids = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    fused: List[Document] = []
    for cid in sorted_cids[:top_n]:
        doc = doc_map[cid]
        # Injeta score RRF para EvidenceNormalizer usar
        new_meta = dict(doc.metadata)
        new_meta["relevance_score"] = round(float(scores[cid]), 4)
        new_meta["rrf_score"] = round(float(scores[cid]), 4)
        fused.append(Document(page_content=doc.page_content, metadata=new_meta))
    return fused
