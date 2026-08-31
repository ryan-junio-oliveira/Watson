"""Analista proativo (Watson Analista, sob demanda).

Apos a resposta principal, o analista:
1. Reflete sobre a propria resposta (conclusoes, suposicoes, incertezas);
2. Gera perguntas de acompanhamento derivadas dos dados;
3. Busca mais informacao no acervo indexado (retrieval proativo).

Roda apenas quando o usuario pede ("aprofundar" / `analyze=true`) para manter
o chat rapido por padrao. A resposta principal nunca e poluida: tudo e
entregue como dados estruturados (chips na UI).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from llm.ollama_client import OllamaClient
from rag.evidence import Evidence, EvidenceNormalizer
from rag.retriever import Retriever

_REFLECTION_PROMPT = """Você é o Watson — analista cordial, preciso e prestativo.

Você acabou de responder à pergunta abaixo com base nos dados fornecidos.
Agora reflita sobre a SUA PRÓPRIA resposta e produza três blocos no formato
exato abaixo (use exatamente os marcadores, sem mais nada):

CONCLUSOES:
- (conclusões que você tirou: o que ficou respondido, suposições assumidas,
  incertezas e o que confirmaria/descartaria a resposta)

PERGUNTAS:
1. (pergunta de acompanhamento útil e natural, baseada nos dados e no que foi respondido)
2. (outra pergunta, se fizer sentido)
3. (outra pergunta, se fizer sentido)

TOPICOS:
- (tópico a pesquisar no acervo para aprofundar a análise, se fizer sentido)

Pergunta: {question}

Sua resposta: {answer}

Dados utilizados:
{evidence}

LIMITES:
- Máximo de {max_followups} perguntas.
- Não invente dados que não estejam nos fornecidos.
- Se não houver o que aprofundar, deixe TOPICOS vazio.
"""

_SYNTHESIS_PROMPT = """Você é o Watson — cordial e direto ao ponto.
Você buscou informação adicional no acervo sobre o tema abaixo.
Resuma em no máximo 3 frases objetivas o que a informação nova acrescenta,
citando brevemente a fonte. Se nada acrescentar, responda apenas: "Nada."

Tema: {topic}
Informação encontrada:
{content}
"""


@dataclass
class AnalystResult:
    conclusions: List[str] = field(default_factory=list)
    follow_up: List[str] = field(default_factory=list)
    additional_info: List[str] = field(default_factory=list)
    extra_sources: List[Evidence] = field(default_factory=list)


def _split_items(text: str) -> List[str]:
    items: List[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        m = re.match(r"^\d+[\.\)]\s*(.*)$", line)
        if m:
            line = m.group(1).strip()
        if line:
            items.append(line)
    return items


def _extract_block(text: str, marker: str) -> str:
    m = re.search(
        rf"{marker}:(.*?)(?:CONCLUSOES:|PERGUNTAS:|TOPICOS:|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


class Analyst:
    def __init__(
        self,
        retriever: Retriever,
        ollama_client: OllamaClient,
        logger: Optional[logging.Logger] = None,
        max_followups: int = 3,
    ):
        self.retriever = retriever
        self.ollama_client = ollama_client
        self.logger = logger
        self.max_followups = max_followups

    def analyze(
        self,
        question: str,
        answer: str,
        evidence: List[Evidence],
    ) -> AnalystResult:
        result = AnalystResult()
        raw = self._reflect(question, answer, evidence)
        result.conclusions = _split_items(_extract_block(raw, "CONCLUSOES"))
        result.follow_up = _split_items(_extract_block(raw, "PERGUNTAS"))[
            : self.max_followups
        ]
        topics = _split_items(_extract_block(raw, "TOPICOS"))

        if topics:
            result.extra_sources = self._proactive_search(topics, evidence)
            result.additional_info = self._synthesize(topics, result.extra_sources)

        if self.logger:
            self.logger.info(
                f"Analyst: {len(result.conclusions)} conclusions, "
                f"{len(result.follow_up)} follow-ups, "
                f"{len(result.extra_sources)} extra sources"
            )
        return result

    def _evidence_summary(self, evidence: List[Evidence]) -> str:
        if not evidence:
            return "(sem dados)"
        parts: List[str] = []
        for ev in evidence[:8]:
            src = ev.source or ev.title or "fonte"
            content = ev.content[:200].replace("\n", " ")
            parts.append(f"[{src}] {content}")
        return "\n".join(parts)

    def _reflect(self, question: str, answer: str, evidence: List[Evidence]) -> str:
        prompt = _REFLECTION_PROMPT.format(
            question=question,
            answer=answer,
            evidence=self._evidence_summary(evidence),
            max_followups=self.max_followups,
        )
        try:
            raw = self.ollama_client.ask(prompt, temperature=0.3)
            return self.ollama_client._strip_thinking(raw)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Reflection failed: {e}")
            return ""

    def _proactive_search(
        self, topics: List[str], original: List[Evidence]
    ) -> List[Evidence]:
        seen = {
            ev.chunk_id for ev in original if getattr(ev, "chunk_id", "")
        }
        extra: List[Evidence] = []
        for topic in topics[:2]:
            try:
                docs = self.retriever.retrieve(topic, k=3)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Proactive search failed: {e}")
                continue
            for doc in docs:
                chunk_id = doc.metadata.get("chunk_id", "")
                if chunk_id and chunk_id in seen:
                    continue
                seen.add(chunk_id)
                ev = EvidenceNormalizer.from_chroma_document(doc)
                ev.score = doc.metadata.get("relevance_score", 0.0)
                if ev.score < 0.1:
                    continue
                extra.append(ev)
        return extra

    def _synthesize(
        self, topics: List[str], extra_sources: List[Evidence]
    ) -> List[str]:
        if not extra_sources:
            return []
        notes: List[str] = []
        for i, ev in enumerate(extra_sources[:2]):
            topic = topics[0] if topics else "o tema"
            prompt = _SYNTHESIS_PROMPT.format(
                topic=topic, content=ev.content[:600]
            )
            try:
                note = self.ollama_client.ask(prompt, temperature=0.2)
                note = self.ollama_client._strip_thinking(note).strip()
                if note and note.lower() != "nada.":
                    notes.append(note)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Synthesis failed: {e}")
        return notes
