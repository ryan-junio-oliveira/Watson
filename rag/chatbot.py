import logging
import re
import time
from typing import Any, Generator, List, Optional

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer
from rag.prompt import PromptBuilder
from rag.response import AgentResponse, Mode
from rag.retriever import Retriever
from tools.sql_tool import SqlQueryTool

STRUCTURED_VERBS = (
    "quantos", "quantas", "quantidade", "total", "liste", "lista",
    "quais", "conte", "conta", "somam", "soma", "media", "média",
    "maior", "menor", "vencidos", "vencendo", "expirando", "expira",
    "cadastrad", "registros", "renova", "ultimos", "últimos",
)
DB_NOUNS = (
    "licen", "client", "instala", "usuario", "usuário", "equipament",
    "impressora", "scanner", "contrato", "assinatura", "renovac",
    "dispositivo", "ativo", "inativo", "bloquead", "planos", "produtos",
    "quantidade", "registro",
)
_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(raw: str) -> str:
    """Extrai a SQL da resposta do LLM (remove fences/prefixos)."""
    m = _SQL_FENCE.search(raw)
    if m:
        raw = m.group(1)
    raw = raw.strip()
    idx = raw.upper().find("SELECT")
    if idx == -1:
        idx = raw.upper().find("SHOW")
    if idx != -1:
        raw = raw[idx:]
    return raw.rstrip().rstrip(";").strip()


class ChatBot:
    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        ollama_client: OllamaClient,
        reranker: Optional[Retriever] = None,
        sql_tool: Optional[SqlQueryTool] = None,
        logger: Optional[logging.Logger] = None,
        stt: Optional[Any] = None,
        tts: Optional[Any] = None,
    ):
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.ollama_client = ollama_client
        self._rag_reranker = reranker
        self.sql_tool = sql_tool
        self.logger = logger
        self._stt = stt
        self._tts = tts
        self.aggregator = EvidenceAggregator(logger=logger)

    # ------------------------------------------------------------------ #
    # Roteamento (§12) — desativado por padrão.
    # Tudo é respondido via RAG (documentos + dados de banco indexados).
    # O SqlQueryTool permanece disponível para uso explícito futuro, mas não
    # é acionado automaticamente no fluxo do chat.
    # ------------------------------------------------------------------ #

    def _should_use_sql(self, question: str, mode: Mode) -> bool:
        return False

    def _extract_sql_answer(self, question: str) -> tuple:
        schema_text = self.sql_tool.table_descriptions()
        gen_prompt = (
            "Você tem acesso a um banco de dados com estas tabelas:\n"
            f"{schema_text}\n\n"
            f'Gere APENAS uma consulta SQL SELECT que responda: "{question}".\n'
            "Regras: apenas leitura; use apenas tabelas e colunas listadas; "
            "não invente colunas.\n"
            "Para contagens (COUNT) use alias descritivo, ex.: "
            "COUNT(*) AS total. Selecione colunas legíveis e relevantes.\n"
            "Responda somente com a SQL, sem explicações."
        )
        raw = self.ollama_client.ask(gen_prompt, temperature=0.0)
        sql = extract_sql(raw)
        if not sql:
            raise ValueError("LLM não produziu SQL válida")
        rows = self.sql_tool.execute(sql)
        return sql, rows

    def _process_sql(self, question: str) -> AgentResponse:
        start = time.time()
        sql, rows = self._extract_sql_answer(question)
        rows_text = self.sql_tool.rows_to_text(rows)
        evidence = [
            Evidence(
                provider="sql",
                source="database",
                title=f"Resultado da consulta ({len(rows)} linha(s))",
                content=rows_text,
                metadata={"sql": sql, "rows": len(rows)},
                source_type="sql",
            )
        ]
        prompt = self.prompt_builder.build_sql(question, sql, rows_text)
        answer = self._call_llm(prompt)
        resp = self._build_response(answer, evidence, start)
        resp.metadata["provider"] = "sql"
        resp.metadata["sql"] = sql
        resp.metadata["rows"] = len(rows)
        return resp

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

    def _stream_sql(self, question: str) -> Generator[str, None, AgentResponse]:
        start = time.time()
        try:
            resp = self._process_sql(question)
            yield resp.answer
            return resp
        except Exception as e:
            if self.logger:
                self.logger.warning(f"SQL stream failed ({e}), falling back to RAG")
            resp = self._build_response(
                "Não foi possível executar a consulta SQL.", [], start
            )
            resp.metadata["fallback"] = "sql_failed"
            yield resp.answer
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

    def _speak(self, text: str) -> None:
        if self._tts is None or not text:
            return
        if self.logger:
            self.logger.info(f"Speaking ({len(text)} chars) via TTS")
        self._tts.speak(text)

    def chat_loop(self, use_voice: bool = False) -> None:
        from presentation.formatter import CliFormatter

        formatter = CliFormatter()

        print("\n=== Watson RAG ===")
        voice_active = use_voice and self._stt is not None
        if voice_active:
            print(
                "Modo voz ativado. Fale sua pergunta. "
                "Diga 'sair' ou 'encerrar' para encerrar.\n"
            )
        else:
            print("Digite 'exit' ou 'quit' para sair.\n")

        while True:
            try:
                if voice_active:
                    print("\n[Ouvindo...]", flush=True)
                    question = self._stt.listen()
                    if question is None:
                        if self.logger:
                            self.logger.debug("No speech captured, continuing loop")
                        continue
                    print(f"\n> {question}")
                else:
                    question = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nEncerrando...")
                break

            if not question:
                continue

            if question.lower() in ("exit", "quit", "sair", "encerrar", "parar"):
                print("Encerrando...")
                break

            try:
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
                    self._speak(result.answer)

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(''.join(tokens))} chars)"
                    )
            except Exception as e:
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{error_msg}")
                self._speak(error_msg)
                if self.logger:
                    self.logger.error(error_msg)
