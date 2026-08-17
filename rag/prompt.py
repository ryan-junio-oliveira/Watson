from typing import List, Optional

from rag.evidence import Evidence
from rag.response import Mode


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é um assistente especializado em responder perguntas "
        "com base em documentos internos indexados.\n"
        "Siga estas regras:\n"
        "1. Responda APENAS com base nas evidências fornecidas.\n"
        "2. NUNCA invente informações falsas — se as evidências não "
        "contiverem a resposta, diga que não encontrou.\n"
        "3. Se houver contradição entre fontes, aponte as diferentes "
        "versões.\n"
        "4. Se a informação estiver incompleta, indique o que foi "
        "encontrado e o que ainda falta.\n"
        "5. Responda em português.\n"
        "6. Seja objetivo, direto e prefira tópicos quando apropriado.\n"
        "7. Se a pergunta pedir um procedimento ou passos, liste TODOS os "
        "passos na ordem correta, sem omitir nem pular etapas numeradas.\n"
        "8. Ao final, se as evidências tiverem seção/página reais, cite-as "
        "(ex.: 'Fonte: seção X, página Y'). Se forem dados de banco (formato "
        "'campo: valor'), não invente seção/página.\n"
        "9. Quando a evidência for um registro de banco (formato 'campo: "
        "valor'), use TODOS os campos relevantes (nome, cnpj, status, "
        "datas etc.) na resposta — não repita apenas o identificador."
    )

    NO_EVIDENCE_PROMPT = (
        "Você é um assistente especializado em responder perguntas "
        "com base em documentos internos indexados.\n"
        "Não foram encontradas informações nos documentos para "
        "responder a esta pergunta.\n"
        "Siga estas regras:\n"
        "1. Informe que não encontrou dados relevantes nos "
        "documentos indexados.\n"
        "2. NÃO invente informações — seja honesto sobre a "
        "ausência de dados.\n"
        "3. Sugira verificar se os documentos pertinentes foram "
        "indexados ou reformular a pergunta.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto."
    )

    SQL_SYSTEM_PROMPT = (
        "Você é um assistente de suporte que consulta um banco de dados "
        "e responde de forma NATURAL e completa, em português.\n"
        "Os dados abaixo vêm de uma consulta SQL.\n"
        "Regras:\n"
        "1. Responda de forma conversacional e humana, transformando os "
        "dados em uma frase ou lista natural.\n"
        "2. Quando a consulta retornar itens, liste-os pelo nome/descrição "
        "relevante (ex.: nome do cliente, modelo, produto) — NÃO repita "
        "apenas o id.\n"
        "3. Quando a consulta for uma contagem, responda com o total e, se "
        "houver, detalhe os itens.\n"
        "4. NÃO invente dados que não estejam nos resultados.\n"
        "5. Use apenas os valores fornecidos; formate datas e números de "
        "forma legível."
    )

    @staticmethod
    def _format_evidence_block(ev: Evidence) -> str:
        block = "============================\n"
        if ev.url:
            block += f"Fonte: {ev.url}\n"
        elif ev.source:
            block += f"Fonte: {ev.source}\n"
        if ev.title:
            block += f"Título: {ev.title}\n"
        if ev.context_label:
            block += f"Contexto: {ev.context_label}\n"
        block += f"\n{ev.content}\n"
        return block

    def build(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        mode: Mode = Mode.auto,
    ) -> str:
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            base = f"{self.SYSTEM_PROMPT}\n\n{evidence_section}\n\n"
        else:
            base = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        return f"{base}Pergunta: {question}\n\nResposta:"

    def build_sql(
        self,
        question: str,
        sql: str,
        rows_text: str,
    ) -> str:
        """Prompt de síntese para dados estruturados (SQL Tool, §12)."""
        return (
            f"{self.SQL_SYSTEM_PROMPT}\n\n"
            f"Consulta SQL executada: {sql}\n\n"
            f"Resultados:\n{rows_text}\n\n"
            f"Pergunta: {question}\n\n"
            "Resposta:"
        )

    def build_with_history(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> str:
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            prompt = f"{self.SYSTEM_PROMPT}\n\n{evidence_section}\n\n"
        else:
            prompt = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"
        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt
