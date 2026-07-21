from typing import List

from langchain_core.documents import Document


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é um assistente especializado em responder perguntas com base "
        "exclusivamente no contexto fornecido.\n"
        "Siga estas regras rigorosamente:\n"
        "1. Responda APENAS com base no contexto abaixo.\n"
        "2. NUNCA invente ou adicione informações externas.\n"
        "3. Se a resposta não estiver no contexto, diga claramente que "
        "não encontrou a informação nos documentos disponíveis.\n"
        "4. Ao usar uma informação, cite a fonte entre colchetes, "
        "ex: [fonte.txt].\n"
        "5. Se houver contradição entre fontes, aponte as diferentes "
        "versões encontradas.\n"
        "6. Se a informação estiver incompleta, indique o que foi "
        "encontrado e o que ainda falta.\n"
        "7. Informe seu nível de confiança na resposta "
        "(Alta / Média / Baixa).\n"
        "8. Responda em português.\n"
        "9. Seja objetivo, direto e prefira tópicos quando apropriado."
    )

    FALLBACK_PROMPT = (
        "Você é um assistente conversacional útil.\n"
        "Não foram encontrados documentos relevantes no acervo para "
        "responder à pergunta, então você deve responder com base no "
        "seu próprio conhecimento.\n"
        "Siga estas regras:\n"
        "1. Responda com suas próprias palavras, de forma clara e objetiva.\n"
        "2. Indique no início da resposta que a informação vem do seu "
        "conhecimento geral, não dos documentos indexados.\n"
        "3. Se não souber a resposta, admita que não sabe.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto."
    )

    def _format_context(self, contexts: List[Document]) -> str:
        parts = []
        for i, doc in enumerate(contexts, 1):
            source = doc.metadata.get("filename", "desconhecida")
            score = doc.metadata.get("relevance_score", None)
            header = f"[{i}] Fonte: {source}"
            if score is not None:
                header += f" (Relevância: {score:.2f})"
            parts.append(f"{header}\n{doc.page_content}")
        return "\n\n---\n\n".join(parts)

    def _build_base(self, question: str, contexts: List[Document]) -> str:
        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Contexto:\n{self._format_context(contexts)}\n\n"
        )

    def _build_fallback_base(self, question: str) -> str:
        return f"{self.FALLBACK_PROMPT}\n\n"

    def build(self, question: str, contexts: List[Document]) -> str:
        if contexts:
            base = self._build_base(question, contexts)
        else:
            base = self._build_fallback_base(question)
        return f"{base}Pergunta: {question}\n\nResposta:"

    def build_with_history(
        self, question: str, contexts: List[Document], history_context: str = ""
    ) -> str:
        if contexts:
            prompt = self._build_base(question, contexts)
        else:
            prompt = self._build_fallback_base(question)
        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"
        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt
