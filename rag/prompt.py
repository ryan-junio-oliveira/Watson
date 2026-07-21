from typing import List

from langchain_core.documents import Document


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é um assistente especializado em responder perguntas com base "
        "exclusivamente no contexto fornecido. "
        "Siga estas regras rigorosamente:\n"
        "1. Responda APENAS com base no contexto abaixo.\n"
        "2. NUNCA invente ou adicione informações externas.\n"
        "3. Se a resposta não estiver no contexto, diga claramente que "
        "não encontrou a informação nos documentos disponíveis.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto.\n"
        "6. Se necessário, mencione o documento de origem."
    )

    def _build_base(self, question: str, contexts: List[Document]) -> str:
        context_text = "\n\n---\n\n".join(
            f"[Fonte: {doc.metadata.get('filename', 'desconhecida')}]\n"
            f"{doc.page_content}"
            for doc in contexts
        )
        return f"{self.SYSTEM_PROMPT}\n\nContexto:\n{context_text}\n\n"

    def build(self, question: str, contexts: List[Document]) -> str:
        return f"{self._build_base(question, contexts)}Pergunta: {question}\n\nResposta:"

    def build_with_history(
        self, question: str, contexts: List[Document], history_context: str = ""
    ) -> str:
        prompt = self._build_base(question, contexts)
        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"
        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt
