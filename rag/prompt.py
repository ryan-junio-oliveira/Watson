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
        "6. Seja objetivo, direto e prefira tópicos quando apropriado."
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

    @staticmethod
    def _format_evidence_block(ev: Evidence) -> str:
        block = "============================\n"
        if ev.url:
            block += f"Fonte: {ev.url}\n"
        elif ev.source:
            block += f"Fonte: {ev.source}\n"
        if ev.title:
            block += f"Título: {ev.title}\n"
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
