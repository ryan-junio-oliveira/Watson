"""LLM Query Rewriter — Query Understanding Layer para RAG técnico.

Transforma pergunta curta e pobre semanticamente em consultas ricas,
preservando termos técnicos (fabricante, modelo, códigos) e detectando intent.

Ex:
  "erro na impressora hp laser jet modelo-x"
  →
  {
    "original_query": "erro na impressora hp laser jet modelo-x",
    "normalized_query": "Erros e códigos de erro da Impressora Managed MFP Modelo-X",
    "expanded_queries": [
      "Impressora Managed MFP Modelo-X códigos de erro",
      "HP Modelo-X mensagem de erro solução",
      "Impressora Modelo-X troubleshooting",
      ...
    ],
    "entities": {"manufacturer":"HP","model":"Impressora Modelo Modelo-X","device_type":"multifunction printer"},
    "intent": "troubleshooting"
  }

Usado antes do Vector Search + BM25 + Reranker. Se LLM falhar, fallback determinístico
preserva termos técnicos sem embelezar.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

REWRITER_SYSTEM_PROMPT = """Você é um Query Understanding Layer para RAG de documentação técnica de impressoras.

TAREFA: Receba a pergunta do usuário (curta e pobre) e retorne JSON ESTRITO com:
- normalized_query: versão limpa, preservando fabricante, modelo, códigos
- expanded_queries: 3 a 5 consultas especializadas para busca híbrida (vector + keyword)
- entities: manufacturer, model, device_type, error_code (se houver)
- intent: troubleshooting | factual | comparison | procedural | listing

REGRAS CRÍTICAS:
1. PRESERVE termos técnicos: HP, LaserJet, Modelo-X, E123, fusor, toner, etc. NUNCA generalize "impressora HP" se modelo foi citado.
2. NÃO embeleze: "erro na impressora hp modelo-x" NÃO pode virar "Como solucionar impressora HP?" — perderia recall.
3. Expansões devem variar ângulo: códigos de erro, mensagem de erro, troubleshooting, diagnóstico, procedimentos — sempre com modelo.
4. Detecte intent: "erro"/"falha"/"código" → troubleshooting; "quais"/"liste" → listing; "como fazer" → procedural.
5. Responda APENAS JSON válido, sem markdown, sem explicação.

Exemplo input: "erro na impressora hp laser jet modelo-x"
Exemplo output:
{"original_query":"erro na impressora hp laser jet modelo-x","normalized_query":"Erros e códigos de erro da Impressora Managed MFP Modelo-X","expanded_queries":["Impressora Managed MFP Modelo-X códigos de erro","HP Modelo-X mensagem de erro solução","Impressora Modelo-X troubleshooting","HP Modelo-X falha de impressão diagnóstico","HP Modelo-X problemas de hardware e procedimentos de correção"],"entities":{"manufacturer":"HP","model":"Impressora Modelo Modelo-X","device_type":"multifunction printer"},"intent":"troubleshooting"}
"""


@dataclass
class RewrittenQuery:
    original_query: str
    normalized_query: str
    expanded_queries: List[str] = field(default_factory=list)
    entities: Dict[str, str] = field(default_factory=dict)
    intent: str = "factual"

    def all_queries(self) -> List[str]:
        """Retorna normalized + expandidas deduplicadas, preservando ordem."""
        seen = set()
        out: List[str] = []
        for q in [self.normalized_query] + self.expanded_queries:
            nq = (q or "").strip()
            if not nq:
                continue
            key = nq.lower()
            if key not in seen:
                seen.add(key)
                out.append(nq)
        # Garante que original esteja se tudo falhar
        if not out and self.original_query:
            out.append(self.original_query)
        return out

    def to_dict(self) -> Dict:
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "expanded_queries": self.expanded_queries,
            "entities": self.entities,
            "intent": self.intent,
        }


class QueryRewriter:
    def __init__(
        self,
        ollama_client=None,
        model: str = "",
        logger: Optional[logging.Logger] = None,
        max_expanded: int = 5,
        timeout_fallback: bool = True,
    ):
        self.client = ollama_client
        self.model = (model or "").strip() or (getattr(ollama_client, "model", "") if ollama_client else "")
        self.logger = logger
        self.max_expanded = max(1, min(5, int(max_expanded)))

    def rewrite(self, query: str) -> RewrittenQuery:
        q = (query or "").strip()
        if not q:
            return RewrittenQuery(original_query=q, normalized_query=q, expanded_queries=[], entities={}, intent="factual")

        # Tenta LLM primeiro
        if self.client:
            try:
                result = self._rewrite_with_llm(q)
                if result:
                    if self.logger:
                        self.logger.info(f"[Rewriter] ENTRADA: '{q}' → SAÍDA: normalized='{result.normalized_query}' | expanded={result.expanded_queries} | entities={result.entities} | intent={result.intent}")
                    return result
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"QueryRewriter LLM failed, fallback determinístico: {e}")

        # Fallback determinístico — preserva termos técnicos sem LLM
        fb = self._fallback_rewrite(q)
        if self.logger:
            self.logger.info(f"[Rewriter-Fallback] ENTRADA: '{q}' → SAÍDA: normalized='{fb.normalized_query}' | expanded={fb.expanded_queries} | entities={fb.entities} | intent={fb.intent}")
        return fb

    def _rewrite_with_llm(self, query: str) -> Optional[RewrittenQuery]:
        if not self.client:
            return None

        prompt = REWRITER_SYSTEM_PROMPT + f'\n\nPergunta: "{query}"\nJSON:'

        # Usa cliente com temperature 0.0 para JSON determinístico
        raw = self.client.ask(prompt, temperature=0.0, max_tokens=800, think=False)
        if not raw:
            return None

        # Extrai JSON mesmo se vier com markdown
        json_str = self._extract_json(raw)
        if not json_str:
            return None

        data = json.loads(json_str)

        original = data.get("original_query", query)
        normalized = data.get("normalized_query", query).strip()
        expanded = data.get("expanded_queries", [])
        entities = data.get("entities", {})
        intent = data.get("intent", "factual")

        # Normaliza e limita
        if not isinstance(expanded, list):
            expanded = []
        expanded = [str(x).strip() for x in expanded if str(x).strip()][: self.max_expanded]
        if not isinstance(entities, dict):
            entities = {}
        # Garante que termos técnicos do original estejam nas expandidas
        expanded = self._ensure_technical_terms(query, expanded)

        # Filtra "None"/"null" que o LLM às vezes retorna como string
        clean_entities = {}
        for k, v in entities.items():
            vs = str(v).strip()
            if not vs or vs.lower() in ("none", "null", "n/a", "-"):
                continue
            clean_entities[k] = vs
        return RewrittenQuery(
            original_query=str(original).strip() or query,
            normalized_query=normalized or query,
            expanded_queries=expanded,
            entities=clean_entities,
            intent=str(intent).strip().lower() or "factual",
        )

    def _fallback_rewrite(self, query: str) -> RewrittenQuery:
        """Fallback sem LLM — preserva modelo/fabricante e gera expansões por template."""
        # Extrai entidades por regex simples
        manufacturer = ""
        model = ""
        qlow = query.lower()

        # Fabricantes comuns
        for m in ["hp", "xerox", "brother", "kyocera", "ricoh", "lexmark", "epson", "canon", "samsung"]:
            if m in qlow:
                manufacturer = m.upper() if m == "hp" else m.capitalize()
                break

        # Modelo: captura sequência com letras/números + Modelo-X etc
        m = re.search(r"(laserjet[\s\w-]*?e\d{4,5}|e\d{4,5}|dcp[-\s]?\w+|m\d{4}\w*|mfp[\s\w-]*\d+)", query, re.IGNORECASE)
        if m:
            model = m.group(0).strip()
            # Tenta expandir com fabricante se já tem
            if manufacturer and manufacturer.lower() not in model.lower():
                model = f"{manufacturer} {model}"

        # Normalizada = query original limpa + capitalização leve
        normalized = query.strip()
        # Se tem fabricante e modelo, garante formato "Impressora ..."
        if manufacturer and model:
            # Não sobrescreve se já está bom
            pass

        # Intent simples
        intent = "factual"
        if any(k in qlow for k in ["erro", "falha", "código", "codigo", "troubleshooting", "defeito", "pane"]):
            intent = "troubleshooting"
        elif any(k in qlow for k in ["quais", "liste", "lista", "todos"]):
            intent = "listing"
        elif any(k in qlow for k in ["como ", "passo", "procedimento", "instalar", "trocar"]):
            intent = "procedural"
        elif "compar" in qlow:
            intent = "comparison"

        # Expansões por template — sempre com modelo/fabricante se detectado
        base_terms = []
        if model:
            base_terms.append(model)
        elif manufacturer:
            base_terms.append(manufacturer)
        else:
            # Sem entidade, usa query crua como base
            base_terms.append(query.strip())

        base = base_terms[0]

        if intent == "troubleshooting":
            templates = [
                f"{base} códigos de erro",
                f"{base} mensagem de erro solução",
                f"{base} troubleshooting",
                f"{base} falha de impressão diagnóstico",
                f"{base} problemas de hardware e procedimentos de correção",
            ]
        elif intent == "procedural":
            templates = [
                f"{base} passo a passo",
                f"{base} procedimento instalação",
                f"{base} manual troubleshooting",
            ]
        else:
            templates = [
                f"{base} manual",
                f"{base} especificações",
                f"{base} troubleshooting",
            ]

        expanded = templates[: self.max_expanded]
        expanded = self._ensure_technical_terms(query, expanded)

        entities: Dict[str, str] = {}
        if manufacturer:
            entities["manufacturer"] = manufacturer
        if model:
            entities["model"] = model
        # device_type genérico se troubelshooting de impressora
        if intent == "troubleshooting" and "impressora" in qlow:
            entities["device_type"] = "multifunction printer" if "mfp" in qlow else "printer"

        return RewrittenQuery(
            original_query=query,
            normalized_query=normalized,
            expanded_queries=expanded,
            entities=entities,
            intent=intent,
        )

    def _ensure_technical_terms(self, original: str, expanded: List[str]) -> List[str]:
        """Garante que termos técnicos do original não sejam perdidos nas expandidas."""
        # Extrai tokens técnicos: códigos E123, modelos Modelo-X, etc
        tech_terms = re.findall(r"\b(e\d{3,5}|[a-z]+\d{3,5}\w*)\b", original, re.IGNORECASE)
        tech_terms = [t for t in tech_terms if len(t) >= 4]
        if not tech_terms:
            return expanded
        # Verifica se ao menos uma expandida contém cada termo técnico
        out = []
        for q in expanded:
            nq = q
            for term in tech_terms:
                if term.lower() not in nq.lower():
                    # Anexa termo se faltar
                    nq = f"{nq} {term}"
            out.append(nq.strip())
        return out

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        # Tenta JSON direto
        text = text.strip()
        # Remove markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return m.group(1)
        # Procura primeiro { até último }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return None
