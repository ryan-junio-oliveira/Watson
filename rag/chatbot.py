import logging
import time
from typing import Generator, List, Optional

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer
from rag.prompt import PromptBuilder
from rag.response import AgentResponse, Mode
from rag.retriever import Retriever


class ChatBot:
    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        ollama_client: OllamaClient,
        reranker: Optional[Retriever] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.ollama_client = ollama_client
        self._rag_reranker = reranker
        self.logger = logger
        self.aggregator = EvidenceAggregator(logger=logger)

    def _retrieve_rag(self, question: str) -> List[Evidence]:
        docs: List[Document] = self.retriever.retrieve(question)
        if self._rag_reranker and docs:
            from rag.reranker import Reranker as RagReranker

            docs = RagReranker.rerank(
                self._rag_reranker, question, docs, top_k=len(docs)
            )
        return [EvidenceNormalizer.from_chroma_document(d) for d in docs]

    def _call_llm(self, prompt: str) -> str:
        answer = self.ollama_client.ask(prompt)
        return self.ollama_client._strip_thinking(answer)

    def _call_llm_stream(self, prompt: str) -> Generator[str, None, str]:
        full_answer: List[str] = []
        try:
            for token in self.ollama_client.ask_stream(prompt):
                full_answer.append(token)
                yield token
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Stream interrupted: {e}")
        return "".join(full_answer)

    def _build_response(
        self,
        answer: str,
        evidences: List[Evidence],
        start_time: float,
    ) -> AgentResponse:
        elapsed = time.time() - start_time
        return AgentResponse(
            answer=answer,
            evidences=evidences,
            confidence=1.0 if evidences else 0.5,
            verdict="ok",
            metadata={
                "provider": "rag",
                "evidence_count": len(evidences),
            },
            execution_time=elapsed,
        )

    def _process(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> AgentResponse:
        start = time.time()

        if self.logger:
            self.logger.info(f"Question: {question}")

        evidence = self._retrieve_rag(question)
        evidence = self.aggregator.collect(rag_evidence=evidence)
        evidence = self.aggregator.rank(evidence)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found in indexed documents")
            prompt = self.prompt_builder.build(question, mode=mode)
            answer = self._call_llm(prompt)
            resp = self._build_response(answer, [], start)
            resp.metadata["fallback"] = "no_documents"
            return resp

        prompt = (
            self.prompt_builder.build_with_history(
                question, evidence, history_context, mode=mode
            )
            if history_context
            else self.prompt_builder.build(question, evidence, mode=mode)
        )

        answer_clean = self._call_llm(prompt)
        result = self._build_response(answer_clean, evidence, start)

        if self.logger:
            self.logger.info(
                f"AgentResponse: evidence={len(evidence)}, "
                f"time={result.execution_time:.2f}s"
            )

        return result

    def ask(self, question: str, mode: Mode = Mode.auto) -> AgentResponse:
        return self._process(question, mode=mode)

    def ask_with_context(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> AgentResponse:
        return self._process(question, history_context, mode)

    def _stream_evidence(
        self, prompt: str, evidence: List[Evidence]
    ) -> Generator[str, None, AgentResponse]:
        start = time.time()
        full_answer: List[str] = []
        try:
            for token in self.ollama_client.ask_stream(prompt):
                full_answer.append(token)
                yield token
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Stream interrupted: {e}")

        answer_clean = "".join(full_answer)
        result = self._build_response(answer_clean, evidence, start)

        if self.logger:
            self.logger.info(f"Stream result: time={result.execution_time:.2f}s")

        return result

    def _stream_no_evidence(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> Generator[str, None, AgentResponse]:
        start = time.time()
        prompt = (
            self.prompt_builder.build_with_history(
                question, None, history_context, mode=mode
            )
            if history_context
            else self.prompt_builder.build(question, mode=mode)
        )
        full_answer = yield from self._call_llm_stream(prompt)
        resp = self._build_response(full_answer, [], start)
        resp.metadata["fallback"] = "no_documents"
        return resp

    def ask_stream(
        self, question: str, mode: Mode = Mode.auto
    ) -> Generator[str, None, AgentResponse]:
        if self.logger:
            self.logger.info(f"Question: {question}")

        evidence = self._retrieve_rag(question)
        evidence = self.aggregator.collect(rag_evidence=evidence)
        evidence = self.aggregator.rank(evidence)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found in indexed documents")
            return (yield from self._stream_no_evidence(question, mode=mode))

        prompt = self.prompt_builder.build(question, evidence, mode=mode)
        result = yield from self._stream_evidence(prompt, evidence)
        return result

    def ask_stream_with_history(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> Generator[str, None, AgentResponse]:
        if self.logger:
            self.logger.info(f"Question: {question}")

        evidence = self._retrieve_rag(question)
        evidence = self.aggregator.collect(rag_evidence=evidence)
        evidence = self.aggregator.rank(evidence)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found in indexed documents")
            return (
                yield from self._stream_no_evidence(
                    question, history_context, mode=mode
                )
            )

        prompt = self.prompt_builder.build_with_history(
            question, evidence, history_context, mode=mode
        )
        result = yield from self._stream_evidence(prompt, evidence)
        return result

    def chat_loop(self) -> None:
        from presentation.formatter import CliFormatter

        formatter = CliFormatter()

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

                print()
                gen = self.ask_stream(question)
                tokens: List[str] = []
                try:
                    while True:
                        token = next(gen)
                        print(token, end="", flush=True)
                        tokens.append(token)
                except StopIteration as e:
                    result = e.value
                print()

                if result:
                    print()
                    print(formatter.format(result))

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(''.join(tokens))} chars)"
                    )
            except Exception as e:
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{error_msg}")
                if self.logger:
                    self.logger.error(error_msg)
