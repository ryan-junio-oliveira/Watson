import logging
from typing import List, Optional

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from rag.prompt import PromptBuilder
from rag.reranker import Reranker
from rag.retriever import Retriever


class ChatBot:
    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        ollama_client: OllamaClient,
        reranker: Optional[Reranker] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.ollama_client = ollama_client
        self.reranker = reranker
        self.logger = logger

    def _retrieve_and_rerank(self, question: str) -> List[Document]:
        contexts = self.retriever.retrieve(question)
        if self.reranker and contexts:
            contexts = self.reranker.rerank(
                question, contexts, top_k=len(contexts)
            )
        return contexts

    def ask(self, question: str) -> str:
        contexts = self._retrieve_and_rerank(question)
        if not contexts and self.logger:
            self.logger.info("No relevant context found, falling back to general knowledge")
        prompt = self.prompt_builder.build(question, contexts)
        answer = self.ollama_client.ask(prompt)
        return answer

    def ask_with_context(self, question: str, history_context: str = "") -> str:
        contexts = self._retrieve_and_rerank(question)
        if not contexts and self.logger:
            self.logger.info("No relevant context found, falling back to general knowledge")
        prompt = self.prompt_builder.build_with_history(
            question, contexts, history_context
        )
        answer = self.ollama_client.ask(prompt)
        return answer

    def _retrieve_context(self, question: str) -> List[Document]:
        return self._retrieve_and_rerank(question)

    def _build_prompt(self, question: str, contexts: List[Document]) -> str:
        return self.prompt_builder.build(question, contexts)

    def chat_loop(self) -> None:
        print("\n=== Watson RAG ===")
        print("Digite 'exit' ou 'quit' para sair.\n")

        while True:
            try:
                question = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nEncerrando...")
                break

            if not question:
                continue

            if question.lower() in ("exit", "quit"):
                print("Encerrando...")
                break

            try:
                if self.logger:
                    self.logger.info(f"Question: {question}")

                contexts = self._retrieve_context(question)
                if not contexts and self.logger:
                    self.logger.info(
                        "No relevant context found, "
                        "falling back to general knowledge"
                    )
                prompt = self._build_prompt(question, contexts)
                answer_parts: List[str] = []

                print()
                for token in self.ollama_client.ask_stream(prompt):
                    print(token, end="", flush=True)
                    answer_parts.append(token)
                print()

                full_answer = "".join(answer_parts)

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(full_answer)} chars)"
                    )
            except Exception as e:
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{error_msg}")
                if self.logger:
                    self.logger.error(error_msg)
