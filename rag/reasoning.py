"""Engine de raciocínio — decide estratégia de retrieval + geração por tipo de pergunta.

Centraliza:
- choice de top_k, temperature, max_tokens adaptativo
- need for chain-of-thought (CoT)
- need for multi-query + RRF
- evidence scoring boost para queries analíticas
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ReasoningPlan:
    intent: str
    needs_cot: bool
    needs_multi_query: bool
    top_k: int
    temperature: float
    max_tokens: int
    use_reranker: bool
    reasoning_hint: str  # instrução curta injetada no prompt


_ANALYTICAL_HINTS = (
    "quantos", "quantas", "por cento", "%", "variação", "variacao",
    "média", "media", "soma", "total", "comparar", "comparação", "comparacao",
    "diferença", "diferenca", "tendência", "tendencia", "evolução", "evolucao",
    "maior", "menor", "máximo", "maximo", "mínimo", "minimo", "cresceu", "caiu",
    "aumentou", "diminuiu", "proporção", "proporcao",
)
_REASONING_HINTS = (
    "por que", "porque", "explique", "analise", "analisar", "conclus",
    "justifique", "raciocine", "passo a passo", "etapa",
)


class ReasoningEngine:
    def __init__(
        self,
        base_top_k: int = 5,
        base_temperature: float = 0.1,
        base_max_tokens: int = 2048,
        reasoning_top_k: int = 12,
        reasoning_temperature: float = 0.2,
        reasoning_max_tokens: int = 3072,
        max_reasoning_tokens: int = 4096,
    ):
        self.base_top_k = base_top_k
        self.base_temperature = base_temperature
        self.base_max_tokens = base_max_tokens
        self.reasoning_top_k = reasoning_top_k
        self.reasoning_temperature = reasoning_temperature
        self.reasoning_max_tokens = reasoning_max_tokens
        self.max_reasoning_tokens = max_reasoning_tokens

    def plan(self, question: str, expanded_intent: Optional[str] = None) -> ReasoningPlan:
        q = question.lower()
        intent = expanded_intent or self._infer_intent(q)
        needs_cot = self._needs_cot(q, intent)
        needs_multi = intent in {"compare", "trend", "percent_change", "difference"}
        # top_k adaptativo
        if needs_cot or intent in {"listing"}:
            top_k = self.reasoning_top_k
        elif intent in {"percent_change", "sum", "average", "max", "min", "difference", "compare", "trend"}:
            top_k = self.base_top_k * 2
        else:
            top_k = self.base_top_k

        # temperature adaptativa: factual baixo, reasoning levemente mais alto para fluidez
        temperature = self.reasoning_temperature if needs_cot else self.base_temperature

        # max_tokens: reasoning precisa de mais espaço para CoT + citações
        if needs_cot:
            max_tokens = self.reasoning_max_tokens
        elif intent in {"listing"}:
            max_tokens = self.max_reasoning_tokens
        else:
            max_tokens = self.base_max_tokens

        use_reranker = needs_cot or intent in {"compare", "trend", "percent_change"}
        hint = self._hint(intent, needs_cot)
        return ReasoningPlan(
            intent=intent,
            needs_cot=needs_cot,
            needs_multi_query=needs_multi,
            top_k=top_k,
            temperature=temperature,
            max_tokens=max_tokens,
            use_reranker=use_reranker,
            reasoning_hint=hint,
        )

    def _infer_intent(self, q: str) -> str:
        from rag.calculator import IntentDetector

        kind = IntentDetector().detect(q)
        if kind:
            return kind
        if any(h in q for h in _ANALYTICAL_HINTS):
            return "compare"
        if any(h in q for h in _REASONING_HINTS):
            return "reasoning"
        if any(h in q for h in ("quais", "list", "disponíve")):
            return "listing"
        return "factual"

    def _needs_cot(self, q: str, intent: str) -> bool:
        if intent in {"percent_change", "difference", "compare", "trend", "reasoning"}:
            return True
        if any(h in q for h in _REASONING_HINTS):
            return True
        # Perguntas longas (>20 tokens) com múltiplas cláusulas tendem a precisar CoT
        if len(q.split()) > 18 and ("," in q or " e " in q):
            return True
        return False

    def _hint(self, intent: str, needs_cot: bool) -> str:
        if intent == "percent_change":
            return "Calcule a variação percentual passo a passo com fórmula (novo-antigo)/antigo*100."
        if intent == "difference":
            return "Calcule a diferença absoluta passo a passo."
        if intent in {"compare", "trend"}:
            return "Compare as entidades lado a lado, destaque semelhanças, diferenças e tendência."
        if intent in {"sum", "average", "max", "min"}:
            return "Agregue os valores listados e mostre a conta."
        if needs_cot:
            return "Pense passo a passo, mas responda de forma concisa e cite fontes."
        return ""

    def evidence_boost(self, evidence_content: str, question: str) -> float:
        """Boost heurístico para evidências com tabelas/números quando query é analítica."""
        q = question.lower()
        is_analytical = any(h in q for h in _ANALYTICAL_HINTS) or any(h in q for h in _REASONING_HINTS)
        if not is_analytical:
            return 0.0
        boost = 0.0
        # Tabelas markdown têm pipes
        if "|" in evidence_content and evidence_content.count("|") > 4:
            boost += 0.05
        # Números
        if re.search(r"\d+[.,]\d+|\d{3,}", evidence_content):
            boost += 0.03
        # Seção relevante
        if any(kw in evidence_content.lower() for kw in ("total", "resultado", "média", "variação")):
            boost += 0.02
        return min(boost, 0.1)
