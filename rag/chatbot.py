import logging
import re
import sys
import threading
import time
from typing import Generator, List, Optional

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from metrics.store import MetricsStore
from rag.analyst import Analyst
from rag.calculator import Calculator
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
        enable_reasoning: bool = False,
        analyst: Optional[Analyst] = None,
        agent_name: str = "Watson",
        metrics: Optional[MetricsStore] = None,
    ):
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.ollama_client = ollama_client
        self._rag_reranker = reranker
        self.logger = logger
        self.aggregator = EvidenceAggregator(logger=logger)
        self.calculator = Calculator()
        self.enable_reasoning = enable_reasoning
        self.analyst = analyst
        self.agent_name = agent_name
        self.metrics = metrics or MetricsStore(logger=logger)

    def _is_analytical(self, question: str) -> bool:
        q = question.lower()
        return self.calculator.detector.detect(question) is not None or any(
            v in q
            for v in (
                "comparar", "comparação", "comparacao", "tendência",
                "tendencia", "evolução", "evolucao", "ao longo",
            )
        )

    _LISTING_HINTS = (
        "list", "liste", "lista", "quais", "quais são", "quais sao",
        "disponíve", "disponive", "enumer", "relacione",
        "me mostre", "me liste", "catálogo", "catalogo", "tabela de",
    )

    _FULL_CONTEXT_HINTS = (
        "todos", "todas", "tudo", "complet", "completo", "todas as",
        "todos os", "mais informa", "mais detalhe", "aprofund", "ampli",
        "integral", "por extenso", "lista completa", "relacione todos",
        "me da todos", "me dê todos", "não omita", "sem omitir",
        "não deixe de fora", "todos os disponíve", "todas as disponíve",
    )

    def _is_listing(self, question: str) -> bool:
        q = question.lower()
        return any(h in q for h in self._LISTING_HINTS)

    def _wants_full_context(self, question: str) -> bool:
        """Detecta pedido de resposta completa/completa (TOP_K ampliado):
        por padrão retornamos menos, e o contexto aumenta dinamicamente quando
        o usuário pede 'mais informações', 'todos', 'completo', etc."""
        q = question.lower()
        return any(h in q for h in self._FULL_CONTEXT_HINTS) or self._is_listing(q)

    def _retrieve_rag(self, question: str) -> List[Evidence]:
        # Padrão: contexto normal (rápido). Aumenta dinamicamente quando o
        # usuário pede a resposta completa (mais informações, todos, completo).
        full = self._wants_full_context(question)
        top_k = self.retriever.top_k * 4 if full else (
            self.retriever.top_k * 2 if self._is_analytical(question) else None
        )
        docs: List[Document] = self.retriever.retrieve(question, k=top_k)
        if self._rag_reranker and docs:
            from rag.reranker import Reranker as RagReranker

            docs = RagReranker.rerank(
                self._rag_reranker, question, docs, top_k=len(docs)
            )
        evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]

        if full:
            evidence = self._expand_document_context(evidence)

        return evidence

    def _expand_document_context(self, evidence: List[Evidence]) -> List[Evidence]:
        """Para perguntas de listagem, junta TODOS os chunks do mesmo
        documento/fonte para garantir que a resposta não omita itens
        (ex.: todos os PINs disponíveis). Expande apenas as fontes mais
        relevantes (maior score) para não poluir o contexto."""
        if not evidence:
            return evidence

        # Fontes mais relevantes primeiro (por score) — expande as top 2.
        ranked = sorted(evidence, key=lambda e: e.score, reverse=True)
        sources: list = []
        seen: set = set()
        for ev in ranked:
            source = ev.metadata.get("source", "") or ev.source or ""
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
            if len(sources) >= 2:
                break

        if not sources:
            return evidence

        exclude = {ev.metadata.get("chunk_id", "") for ev in evidence}
        extra_docs: List[Document] = []
        # Limita o contexto para não estourar o tempo de geração em CPU.
        MAX_EXTRA_CHUNKS = 12
        for source in sources:
            if len(extra_docs) >= MAX_EXTRA_CHUNKS:
                break
            try:
                related = self.retriever.retrieve_all_from_source(
                    source, exclude_ids=exclude
                )
                extra_docs.extend(related[: MAX_EXTRA_CHUNKS - len(extra_docs)])
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Document expansion failed: {e}")

        if not extra_docs:
            return evidence

        extra = [EvidenceNormalizer.from_chroma_document(d) for d in extra_docs]
        if self.logger:
            self.logger.info(
                f"Expanded listing context with {len(extra)} chunks from same source"
            )
        return evidence + extra

    def _inject_computed_facts(
        self, question: str, evidence: List[Evidence]
    ) -> List[Evidence]:
        """Injeta o resultado da calculadora determinística nas evidências."""
        if not evidence:
            return evidence
        texts = [ev.content for ev in evidence]
        computed = self.calculator.compute_for_question(question, texts)
        if computed is None:
            return evidence
        if self.logger:
            self.logger.info(f"Computed fact injected: {computed.kind}")
        evidence = list(evidence)
        evidence.append(
            Evidence(
                provider="computed",
                source="cálculo verificado",
                title="Cálculo verificado sobre os dados",
                content=computed.prompt_block(),
                metadata={"computed_kind": computed.kind, "computed": computed.human},
                source_type="computed",
            )
        )
        return evidence

    def _call_llm(self, prompt: str, reasoning: Optional[bool] = None) -> str:
        kwargs: dict = {}
        if reasoning is not None:
            kwargs["think"] = reasoning
        answer = self.ollama_client.ask(prompt, **kwargs)
        return self.ollama_client._strip_thinking(answer)

    def _should_reason(self, question: str) -> bool:
        """Habilita raciocínio (think) para perguntas analíticas, se configurado
        e o modelo suportar."""
        if not self.enable_reasoning or not self.ollama_client.supports_thinking():
            return False
        q = question.lower()
        return any(
            kw in q
            for kw in (
                "quantos", "quantas", "por cento", "%", "variação", "media",
                "média", "soma", "total", "comparar", "comparação", "diferença",
                "analise", "análise", "conclus", "tendência", "tendencia",
            )
        )

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

    def _run_analyst(self, question: str, resp: AgentResponse) -> AgentResponse:
        """Aplica a análise proativa (sob demanda) sobre a resposta gerada."""
        if self.analyst is None:
            return resp
        try:
            result = self.analyst.analyze(
                question, resp.answer, resp.evidences
            )
            resp.conclusions = result.conclusions
            resp.follow_up = result.follow_up
            resp.additional_info = result.additional_info
            if result.extra_sources:
                resp.evidences = list(resp.evidences) + result.extra_sources
            resp.metadata["analyzed"] = True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Analyst pass failed: {e}")
        return resp

    def _process(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> AgentResponse:
        start = time.time()
        provider = "rag"

        if self.logger:
            self.logger.info(f"Question: {question}")

        try:
            evidence = self._retrieve_rag(question)
            evidence = self.aggregator.collect(rag_evidence=evidence)
            evidence = self.aggregator.rank(evidence)
            evidence = self._inject_computed_facts(question, evidence)

            if not evidence:
                if self.logger:
                    self.logger.info("No evidence found in indexed documents")
                prompt = self.prompt_builder.build(question, mode=mode)
                answer = self._call_llm(prompt)
                resp = self._build_response(answer, [], start)
                resp.metadata["fallback"] = "no_documents"
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, provider, resp, start, analyze)
                return resp

            prompt = (
                self.prompt_builder.build_with_history(
                    question, evidence, history_context, mode=mode
                )
                if history_context
                else self.prompt_builder.build(question, evidence, mode=mode)
            )

            answer_clean = self._call_llm(prompt, reasoning=self._should_reason(question))
            result = self._build_response(answer_clean, evidence, start)

            if self.logger:
                self.logger.info(
                    f"AgentResponse: evidence={len(evidence)}, "
                    f"time={result.execution_time:.2f}s"
                )

            if analyze:
                result = self._run_analyst(question, result)

            self._record_request(question, mode, provider, result, start, analyze)
            return result
        except Exception as e:
            self.metrics.record_request(
                question=question, mode=str(mode), provider=provider,
                execution_ms=(time.time() - start) * 1000,
                analyze=analyze, success=False, error=str(e),
            )
            raise

    def _record_request(
        self, question: str, mode: Mode, provider: str,
        resp: AgentResponse, start: float, analyze: bool,
    ) -> None:
        try:
            self.metrics.record_request(
                question=question, mode=str(mode), provider=provider,
                evidence_count=len(resp.evidences),
                execution_ms=resp.execution_time * 1000,
                analyze=analyze, success=True,
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Metrics request record failed: {e}")

    def ask(
        self,
        question: str,
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> AgentResponse:
        return self._process(question, mode=mode, analyze=analyze)

    def ask_with_context(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> AgentResponse:
        return self._process(question, history_context, mode, analyze=analyze)

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
        self,
        question: str,
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        if self.logger:
            self.logger.info(f"Question: {question}")

        start = time.time()
        try:
            evidence = self._retrieve_rag(question)
            evidence = self.aggregator.collect(rag_evidence=evidence)
            evidence = self.aggregator.rank(evidence)
            evidence = self._inject_computed_facts(question, evidence)

            if not evidence:
                if self.logger:
                    self.logger.info("No evidence found in indexed documents")
                resp = yield from self._stream_no_evidence(question, mode=mode)
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, "rag", resp, start, analyze)
                return resp

            prompt = self.prompt_builder.build(question, evidence, mode=mode)
            result = yield from self._stream_evidence(prompt, evidence)
            if analyze:
                result = self._run_analyst(question, result)
            self._record_request(question, mode, "rag", result, start, analyze)
            return result
        except Exception as e:
            self.metrics.record_request(
                question=question, mode=str(mode), provider="rag",
                execution_ms=(time.time() - start) * 1000,
                analyze=analyze, success=False, error=str(e),
            )
            raise

    def ask_stream_with_history(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        if self.logger:
            self.logger.info(f"Question: {question}")

        start = time.time()
        try:
            evidence = self._retrieve_rag(question)
            evidence = self.aggregator.collect(rag_evidence=evidence)
            evidence = self.aggregator.rank(evidence)
            evidence = self._inject_computed_facts(question, evidence)

            if not evidence:
                if self.logger:
                    self.logger.info("No evidence found in indexed documents")
                resp = yield from self._stream_no_evidence(
                    question, history_context, mode=mode
                )
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, "rag", resp, start, analyze)
                return resp

            prompt = self.prompt_builder.build_with_history(
                question, evidence, history_context, mode=mode
            )
            result = yield from self._stream_evidence(prompt, evidence)
            if analyze:
                result = self._run_analyst(question, result)
            self._record_request(question, mode, "rag", result, start, analyze)
            return result
        except Exception as e:
            self.metrics.record_request(
                question=question, mode=str(mode), provider="rag",
                execution_ms=(time.time() - start) * 1000,
                analyze=analyze, success=False, error=str(e),
            )
            raise

    def _format_analyst(self, resp: AgentResponse) -> str:
        parts: List[str] = []
        if resp.conclusions:
            parts.append("Conclusões da análise:")
            for c in resp.conclusions:
                parts.append(f"  - {c}")
        if resp.additional_info:
            parts.append("Informação adicional do acervo:")
            for a in resp.additional_info:
                parts.append(f"  - {a}")
        if resp.follow_up:
            parts.append("Perguntas de acompanhamento:")
            for i, q in enumerate(resp.follow_up, 1):
                parts.append(f"  {i}. {q}")
        if not parts:
            parts.append("(não foi possível aprofundar a análise)")
        return "\n".join(parts)

    def _greeting(self) -> str:
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            periodo = "bom dia"
        elif 12 <= hour < 18:
            periodo = "boa tarde"
        else:
            periodo = "boa noite"
        return (
            f"Olá, {periodo}! Sou o {self.agent_name}, seu agente de IA. "
            "Como posso ajudar?"
        )

    def chat_loop(self) -> None:
        print("\n=== Watson RAG ===")
        print(self._greeting())
        print("Digite 'exit' ou 'quit' para sair.\n")

        last_question: Optional[str] = None
        last_result: Optional[AgentResponse] = None

        while True:
            try:
                question = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nEncerrando...")
                break

            if not question:
                continue

            if question.lower() in ("exit", "quit", "sair", "encerrar", "parar"):
                print("Encerrando...")
                break

            if question.lower() in ("aprofundar", "analisar", "aprofundar análise"):
                if last_result is not None and last_question:
                    print("\n[Analisando a resposta anterior...]", flush=True)
                    result = self._run_analyst(last_question, last_result)
                    print(self._format_analyst(result))
                else:
                    print("\nNenhuma resposta anterior para aprofundar.")
                continue

            last_question = question
            last_result = None

            stop_status = threading.Event()
            status_thread = threading.Thread(
                target=self._status_loop, args=(stop_status,), daemon=True
            )
            status_thread.start()

            try:
                print()
                gen = self.ask_stream(question)
                tokens: List[str] = []
                started = False
                try:
                    while True:
                        token = next(gen)
                        if not started:
                            stop_status.set()
                            started = True
                            # Limpa a linha do status ANTES do primeiro token,
                            # evitando sobrar "Watson está analisando..." na tela.
                            sys.stdout.write("\r\033[K")
                            sys.stdout.flush()
                        print(token, end="", flush=True)
                        tokens.append(token)
                except StopIteration as e:
                    result = e.value
                stop_status.set()
                print()

                if result:
                    last_result = result
                    # A resposta já foi exibida no stream — mostramos apenas as
                    # fontes e a análise proativa, sem repetir o texto.
                    if result.sources:
                        print("\nSources")
                        print("-------")
                        for s in result.sources:
                            label = s.title or s.url
                            print(f"  • {label}")
                    if result.follow_up:
                        print("\nPerguntas para aprofundar:")
                        for i, q in enumerate(result.follow_up, 1):
                            print(f"  {i}. {q}")
                        print("  (digite 'aprofundar' para mais conclusões/busca)")

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(''.join(tokens))} chars)"
                    )
            except Exception as e:
                stop_status.set()
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{error_msg}")
                if self.logger:
                    self.logger.error(error_msg)

    _STATUS_MESSAGES = (
        "{agent} está analisando sua resposta...",
        "{agent} está consultando a base de conhecimento...",
        "{agent} está processando sua pergunta...",
        "{agent} está buscando a melhor resposta...",
    )

    def _status_loop(self, stop_event: threading.Event) -> None:
        """Exibe mensagens de status rotativas enquanto a IA gera a resposta,
        mantendo o terminal limpo (sem logs)."""
        msgs = [m.format(agent=self.agent_name) for m in self._STATUS_MESSAGES]
        i = 0
        try:
            while True:
                if stop_event.is_set():
                    break
                sys.stdout.write(f"\r{msgs[i % len(msgs)]}   ")
                sys.stdout.flush()
                if stop_event.wait(2.5):
                    break
                i += 1
        finally:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
