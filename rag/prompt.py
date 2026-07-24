from typing import List, Optional

from rag.evidence import Evidence


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é um assistente especializado em responder perguntas com base "
        "EXCLUSIVAMENTE nas evidências fornecidas abaixo.\n"
        "Siga estas regras rigorosamente:\n"
        "1. Responda APENAS com base nas evidências fornecidas.\n"
        "2. NUNCA invente, adicione informações externas ou use seu próprio "
        "conhecimento.\n"
        "3. Se a resposta não estiver nas evidências, diga claramente que "
        "não encontrou a informação.\n"
        "4. Ao usar uma informação, cite a fonte completa entre colchetes, "
        "ex: [https://www.site.com.br/artigo] para resultados da internet "
        "ou [Documento: nome_do_arquivo] para documentos internos.\n"
        "5. Se houver contradição entre fontes, aponte as diferentes "
        "versões encontradas.\n"
        "6. Se a informação estiver incompleta, indique o que foi "
        "encontrado e o que ainda falta.\n"
        "7. Responda em português.\n"
        "8. Seja objetivo, direto e prefira tópicos quando apropriado.\n"
        "9. NUNCA diga 'com base no meu conhecimento' ou 'no meu "
        "conhecimento geral' — você só tem as evidências abaixo."
    )

    NO_EVIDENCE_PROMPT = (
        "Você é um assistente honesto e objetivo.\n"
        "Não foram encontradas evidências (documentos internos ou resultados "
        "de pesquisa na internet) para responder à pergunta.\n"
        "Siga estas regras:\n"
        "1. Informe claramente que não foi possível encontrar a resposta "
        "nas fontes disponíveis.\n"
        "2. NÃO tente adivinhar ou usar seu conhecimento interno.\n"
        "3. Sugira que o usuário refine a pergunta ou forneça mais "
        "informações.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto."
    )

    @staticmethod
    def _format_evidence_block(ev: Evidence) -> str:
        block = f"============================\n"
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
