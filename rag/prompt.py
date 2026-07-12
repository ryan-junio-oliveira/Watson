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

    def build(self, question: str, contexts: List[Document]) -> str:
        context_text = "\n\n---\n\n".join(
            f"[Fonte: {doc.metadata.get('filename', 'desconhecida')}]\n"
            f"{doc.page_content}"
            for doc in contexts
        )

        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Contexto:\n{context_text}\n\n"
            f"Pergunta: {question}\n\n"
            f"Resposta:"
        )

    def build_with_history(
        self, question: str, contexts: List[Document], history_context: str = ""
    ) -> str:
        context_text = "\n\n---\n\n".join(
            f"[Fonte: {doc.metadata.get('filename', 'desconhecida')}]\n"
            f"{doc.page_content}"
            for doc in contexts
        )

        prompt = f"{self.SYSTEM_PROMPT}\n\n"
        prompt += f"Contexto:\n{context_text}\n\n"

        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"

        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt
