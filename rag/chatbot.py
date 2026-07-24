import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer
from rag.planner import IntentClassifier, Plan
from rag.prompt import PromptBuilder
from rag.retriever import Retriever
from rag.validator import ConfidenceScorer, FactValidator, ValidationResult
from search.chunker import Chunker
from search.cleaner import ContentCleaner
from search.extractor import ContentExtractor
from search.fetcher import PageFetcher
from search.google_provider import GoogleProvider
from search.provider import SearchProvider, SearchResult
from search.reranker import Reranker as SearchReranker


@dataclass
class ChatResult:
    answer: str
    confidence: float
    verdict: str
    issues: List[str] = field(default_factory=list)
    sources: str = ""
    evidence_count: int = 0


class ChatBot:
    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        ollama_client: OllamaClient,
        reranker: Optional[Retriever] = None,
        web_search: Optional = None,
        intent_classifier: Optional[IntentClassifier] = None,
        fact_validator: Optional[FactValidator] = None,
        logger: Optional[logging.Logger] = None,
        fetcher: Optional[PageFetcher] = None,
        extractor: Optional[ContentExtractor] = None,
        cleaner: Optional[ContentCleaner] = None,
        chunker: Optional[Chunker] = None,
        search_reranker: Optional[SearchReranker] = None,
        search_provider: Optional[SearchProvider] = None,
        max_pages_per_query: int = 3,
        max_chunks_per_query: int = 30,
    ):
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.ollama_client = ollama_client
        self._rag_reranker = reranker
        self._intent_classifier = intent_classifier
        self.fact_validator = fact_validator
        self.logger = logger
        self.max_pages = max_pages_per_query
        self._fetcher = fetcher
        self._extractor = extractor
        self._cleaner = cleaner
        self._chunker = chunker
        self._search_reranker = search_reranker
        self._search_provider = search_provider
        self._enable_web_search = search_provider is not None or web_search is not None
        self._max_chunks = max_chunks_per_query
        self.aggregator = EvidenceAggregator(logger=logger)

    def _retrieve_rag(self, question: str) -> List[Evidence]:
        docs: List[Document] = self.retriever.retrieve(question)
        if self._rag_reranker and docs:
            from rag.reranker import Reranker as RagReranker
            docs = RagReranker.rerank(
                self._rag_reranker, question, docs, top_k=len(docs)
            )
        return [EvidenceNormalizer.from_chroma_document(d) for d in docs]

    def _ensure_search_provider(self) -> None:
        if self._search_provider is None:
            if not self._enable_web_search:
                return
            from search.google_provider import GoogleProvider
            self._search_provider = GoogleProvider(logger=self.logger)

    def _ensure_fetcher(self) -> None:
        if self._fetcher is None:
            self._fetcher = PageFetcher(logger=self.logger)

    def _ensure_extractor(self) -> None:
        if self._extractor is None:
            self._extractor = ContentExtractor(logger=self.logger)

    def _ensure_cleaner(self) -> None:
        if self._cleaner is None:
            self._cleaner = ContentCleaner(logger=self.logger)

    def _ensure_chunker(self) -> None:
        if self._chunker is None:
            self._chunker = Chunker(logger=self.logger)

    def _ensure_search_reranker(self) -> None:
        if self._search_reranker is None:
            self._search_reranker = SearchReranker(logger=self.logger)

    def _search_web(self, question: str) -> List[SearchResult]:
        if self.logger:
            self.logger.info(f"Searching web: '{question[:60]}'")
        from search.ddgs_provider import DDGSProvider
        results = DDGSProvider(logger=self.logger).search(
            question, self.max_pages * 3
        )
        if not results:
            results = self._search_provider.search(question, self.max_pages * 3)
            if self.logger:
                self.logger.info(
                    f"Google fallback returned {len(results)} results"
                )
        deduped: Dict[str, SearchResult] = {}
        for r in results:
            if r.url not in deduped:
                deduped[r.url] = r
        return list(deduped.values())[: self.max_pages]

    def _fetch_and_extract(
        self, results: List[SearchResult]
    ) -> List[Evidence]:
        self._ensure_fetcher()
        self._ensure_extractor()
        self._ensure_cleaner()
        self._ensure_chunker()
        fetched: List[Evidence] = []
        for sr in results:
            if self.logger:
                self.logger.info(f"Fetching: {sr.url[:80]}")
            fetch_result = self._fetcher.fetch(sr.url)
            if fetch_result is None or fetch_result.status_code != 200:
                continue
            raw_text = self._extractor.extract_from_fetch(fetch_result)
            if not raw_text:
                if self.logger:
                    self.logger.info(f"No content extracted from {sr.url[:60]}")
                continue
            cleaned = self._cleaner.clean(raw_text)
            if len(cleaned) < 50:
                if self.logger:
                    self.logger.info(
                        f"Content too short ({len(cleaned)} chars), skipping {sr.url[:60]}"
                    )
                continue
            chunks = self._chunker.chunk(cleaned)
            for i, chunk in enumerate(chunks):
                ev = EvidenceNormalizer.from_extracted_content(
                    url=sr.url,
                    title=sr.title,
                    content=chunk,
                    provider=f"web:{sr.source}",
                    score=0.7,
                )
                ev.metadata["chunk_index"] = i
                ev.metadata["total_chunks"] = len(chunks)
                fetched.append(ev)
            if self.logger:
                self.logger.info(
                    f"Extracted {len(cleaned)} chars, {len(chunks)} chunks from {sr.url[:60]}"
                )
        return fetched

    def _handle_rag(self, question: str) -> List[Evidence]:
        if self.logger:
            self.logger.info("Retrieving from local documents")
        return self._retrieve_rag(question)

    def _handle_web(self, question: str) -> List[Evidence]:
        self._ensure_search_provider()
        if self._search_provider is None:
            if self.logger:
                self.logger.info("Web search not configured, skipping")
            return []
        if self.logger:
            self.logger.info("Searching the internet")
        results = self._search_web(question)
        if not results:
            return []
        evidence = self._fetch_and_extract(results)
        if not evidence:
            return []
        if len(evidence) > self._max_chunks:
            if self.logger:
                self.logger.info(f"Truncating {len(evidence)} chunks to {self._max_chunks}")
            evidence = evidence[:self._max_chunks]
        self._ensure_search_reranker()
        if self.logger:
            self.logger.info(f"Reranking {len(evidence)} web evidence chunks")
        evidence = self._search_reranker.rerank(question, evidence, top_k=5)
        return evidence

    def _collect_evidence(self, question: str, plan: Plan) -> List[Evidence]:
        rag_evidence: List[Evidence] = []
        web_evidence: List[Evidence] = []

        if plan.need_rag:
            rag_evidence = self._handle_rag(question)

        if plan.need_web:
            web_evidence = self._handle_web(question)

        if not plan.need_rag and not plan.need_web:
            if self.logger:
                self.logger.info("Plan says no source; trying web as fallback")
            web_evidence = self._handle_web(question)

        if not rag_evidence and not web_evidence:
            if self.logger:
                self.logger.info("No evidence from plan, trying web fallback")
            web_evidence = self._handle_web(question)

        all_evidence = self.aggregator.collect(
            rag_evidence=rag_evidence, web_evidence=web_evidence
        )
        return self.aggregator.rank(all_evidence)

    def _no_evidence_result(self) -> ChatResult:
        return ChatResult(
            answer=(
                "Não encontrei informações suficientes nos documentos "
                "indexados nem na internet para responder a esta pergunta. "
                "Tente reformular a pergunta ou fornecer mais detalhes."
            ),
            confidence=0.0,
            verdict="inconsistent",
            issues=["Nenhuma evidência encontrada"],
            sources="",
            evidence_count=0,
        )

    def _call_llm(self, prompt: str) -> str:
        answer = self.ollama_client.ask(prompt)
        return self.ollama_client._strip_thinking(answer)

    def _classify(self, question: str) -> Plan:
        if self._intent_classifier:
            try:
                return self._intent_classifier.classify(question)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Classification failed: {e}")
        return Plan(need_rag=True, need_web=True)

    def _validate(
        self, answer: str, evidence: List[Evidence]
    ) -> ValidationResult:
        if self.fact_validator:
            try:
                return self.fact_validator.validate(answer, evidence)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Validation failed: {e}")
        return ValidationResult(
            overall_verdict="unknown", overall_confidence=0.5
        )

    def _process(self, question: str, history_context: str = "") -> ChatResult:
        plan = self._classify(question)
        evidence = self._collect_evidence(question, plan)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found")
            return self._no_evidence_result()

        prompt = (
            self.prompt_builder.build_with_history(
                question, evidence, history_context
            )
            if history_context
            else self.prompt_builder.build(question, evidence)
        )

        answer_clean = self._call_llm(prompt)
        validation = self._validate(answer_clean, evidence)
        confidence = ConfidenceScorer.calculate(validation, evidence)
        sources = self.aggregator.sources_text(evidence)

        if self.logger:
            self.logger.info(
                f"ChatResult: confidence={confidence:.2f}, "
                f"verdict={validation.overall_verdict}, "
                f"evidence={len(evidence)}, issues={len(validation.issues)}"
            )

        return ChatResult(
            answer=answer_clean,
            confidence=confidence,
            verdict=validation.overall_verdict,
            issues=validation.issues,
            sources=sources,
            evidence_count=len(evidence),
        )

    def ask(self, question: str) -> ChatResult:
        return self._process(question)

    def ask_with_context(
        self, question: str, history_context: str = ""
    ) -> ChatResult:
        return self._process(question, history_context)

    def _stream_evidence(
        self, question: str, prompt: str, evidence: List[Evidence]
    ) -> Generator[str, None, ChatResult]:
        full_answer: List[str] = []
        for token in self.ollama_client.ask_stream(prompt):
            full_answer.append(token)
            yield token

        answer_clean = "".join(full_answer)
        validation = self._validate(answer_clean, evidence)
        confidence = ConfidenceScorer.calculate(validation, evidence)
        sources = self.aggregator.sources_text(evidence)

        result = ChatResult(
            answer=answer_clean,
            confidence=confidence,
            verdict=validation.overall_verdict,
            issues=validation.issues,
            sources=sources,
            evidence_count=len(evidence),
        )

        if self.logger:
            self.logger.info(
                f"Stream result: confidence={confidence:.2f}, "
                f"verdict={validation.overall_verdict}, "
                f"evidence={len(evidence)}, issues={len(validation.issues)}"
            )

        return result

    def ask_stream(
        self, question: str
    ) -> Generator[str, None, ChatResult]:
        plan = self._classify(question)
        evidence = self._collect_evidence(question, plan)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found, returning no-evidence response")
            return self._no_evidence_result()

        prompt = self.prompt_builder.build(question, evidence)
        result = yield from self._stream_evidence(question, prompt, evidence)
        return result

    def ask_stream_with_history(
        self, question: str, history_context: str = ""
    ) -> Generator[str, None, ChatResult]:
        plan = self._classify(question)
        evidence = self._collect_evidence(question, plan)

        if not evidence:
            if self.logger:
                self.logger.info("No evidence found, returning no-evidence response")
            return self._no_evidence_result()

        prompt = self.prompt_builder.build_with_history(
            question, evidence, history_context
        )
        result = yield from self._stream_evidence(question, prompt, evidence)
        return result

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

                answer_parts: List[str] = []
                print()
                gen = self.ask_stream(question)
                try:
                    while True:
                        token = next(gen)
                        print(token, end="", flush=True)
                        answer_parts.append(token)
                except StopIteration as e:
                    result = e.value
                print()

                if result:
                    print(
                        f"\n[Confiança: {result.confidence:.0%} | "
                        f"Veredito: {result.verdict}"
                        f"{' | Avisos: ' + '; '.join(result.issues) if result.issues else ''}]"
                    )

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(''.join(answer_parts))} chars)"
                    )
            except Exception as e:
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{error_msg}")
                if self.logger:
                    self.logger.error(error_msg)
