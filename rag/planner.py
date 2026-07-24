import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from llm.ollama_client import OllamaClient


@dataclass
class Plan:
    need_rag: bool
    need_web: bool
    need_tools: bool = False
    expected_freshness: str = "low"

    def __post_init__(self):
        self.expected_freshness = (
            "low" if self.expected_freshness not in ("low", "high") else self.expected_freshness
        )


EXAMPLES = (
    'Pergunta: Quais servidores estão cadastrados?\n'
    '{"need_rag": true, "need_web": false, "need_tools": false, "expected_freshness": "low"}\n\n'
    'Pergunta: Último título do Cruzeiro\n'
    '{"need_rag": false, "need_web": true, "need_tools": false, "expected_freshness": "high"}\n\n'
    'Pergunta: O que é SOLID?\n'
    '{"need_rag": false, "need_web": false, "need_tools": false, "expected_freshness": "low"}\n\n'
    'Pergunta: Cotação do dólar hoje\n'
    '{"need_rag": false, "need_web": true, "need_tools": false, "expected_freshness": "high"}'
)

CLASSIFIER_PROMPT = (
    'Classifique a pergunta abaixo em JSON com need_rag, need_web, need_tools e expected_freshness.\n'
    'Responda APENAS com o JSON, sem explicações.\n\n'
    f'{EXAMPLES}\n\n'
    'Pergunta: {question}\n'
)


class IntentClassifier:
    def __init__(
        self,
        ollama_client: OllamaClient,
        logger: Optional[logging.Logger] = None,
    ):
        self.ollama_client = ollama_client
        self.logger = logger

    def classify(self, question: str) -> Plan:
        if self.logger:
            self.logger.info("Classifying question...")

        plan = self._try_llm(question)
        if plan is not None:
            return plan

        return self._fallback(question)

    def _try_llm(self, question: str) -> Optional[Plan]:
        prompt = CLASSIFIER_PROMPT.replace("{question}", question)
        try:
            raw = self.ollama_client.ask(
                prompt, temperature=0.0, max_tokens=128, strip_thinking=True,
            )
            data = self._parse_json(raw.strip())
            plan = Plan(
                need_rag=bool(data.get("need_rag", True)),
                need_web=bool(data.get("need_web", False)),
                need_tools=bool(data.get("need_tools", False)),
                expected_freshness=data.get("expected_freshness", "low"),
            )
            if self.logger:
                self.logger.info(
                    f"LLM plan: rag={plan.need_rag}, web={plan.need_web}, "
                    f"tools={plan.need_tools}, freshness={plan.expected_freshness}"
                )
            return plan
        except Exception as e:
            if self.logger:
                self.logger.debug(f"LLM classification failed: {e}")
            return None

    def _parse_json(self, raw: str) -> dict:
        match = re.search(r'\{[^{}]*\}', raw)
        if match:
            return json.loads(match.group())

        rag = re.search(r'"need_rag"\s*:\s*(true|false)', raw)
        web = re.search(r'"need_web"\s*:\s*(true|false)', raw)
        tools = re.search(r'"need_tools"\s*:\s*(true|false)', raw)
        fresh = re.search(r'"expected_freshness"\s*:\s*"(low|high)"', raw)

        result = {}
        if rag:
            result["need_rag"] = rag.group(1) == "true"
        if web:
            result["need_web"] = web.group(1) == "true"
        if tools:
            result["need_tools"] = tools.group(1) == "true"
        if fresh:
            result["expected_freshness"] = fresh.group(1)
        if result:
            return result

        raise ValueError(f"No JSON found in: {raw[:100]}")

    def _fallback(self, question: str) -> Plan:
        q = question.lower()
        web_keywords = {
            "último", "ultimo", "atual", "hoje", "agora", "notícia", "noticia",
            "campeão", "campeao", "título", "titulo", "campeonato",
            "cotação", "cotacao", "dólar", "dolar", "clima", "previsão",
            "previsao", "lançamento", "lancamento", "versão", "versao",
            "novo", "nova", "recente", "2023", "2024", "2025", "2026",
            "ganhou", "venceu", "resultado", "jogo", "partida",
            "eleição", "eleicao", "prêmio", "premio",
        }
        internal_keywords = {
            "servidor", "servidores", "licença", "licenças", "licenca", "licencas",
            "cliente", "clientes", "instalação", "instalacao", "instalações", "instalacoes",
            "banco", "dados", "mysql", "banco de dados", "tabela", "tabelas",
            "documento", "documentos", "manual", "manuais", "contrato", "contratos",
            "cadastrado", "cadastrados", "cadastrada", "cadastradas",
            "token", "apikey", "api key", "credencial", "credenciais",
        }
        need_web = any(kw in q for kw in web_keywords)
        need_rag = any(kw in q for kw in internal_keywords)
        if need_web and not need_rag:
            need_rag = False
        elif not need_web and not need_rag:
            need_rag = True
        freshness = "high" if need_web else "low"
        if self.logger:
            self.logger.info(
                f"Fallback plan: rag={need_rag}, web={need_web}, "
                f"tools=False, freshness={freshness}"
            )
        return Plan(
            need_rag=need_rag, need_web=need_web,
            need_tools=False, expected_freshness=freshness,
        )
