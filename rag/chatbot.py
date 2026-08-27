import logging
import os
import re
import sys
import threading
import time
from typing import Generator, List, Optional

# Cores ANSI para terminal — diferencia pergunta/resposta/status à primeira vista
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_BLUE = "\033[94m"
ANSI_MAGENTA = "\033[95m"
ANSI_CYAN = "\033[96m"
ANSI_WHITE = "\033[97m"


def _enable_ansi_on_windows() -> None:
    if os.name == "nt":
        try:
            os.system("color")
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

from langchain_core.documents import Document

from llm.ollama_client import OllamaClient
from metrics.store import MetricsStore
from rag.analyst import Analyst
from rag.calculator import Calculator
from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer
from rag.prompt import PromptBuilder
from rag.query_expander import QueryExpander, reciprocal_rank_fusion
from rag.reasoning import ReasoningEngine
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
        reasoning_top_k: Optional[int] = None,
        reasoning_temperature: Optional[float] = None,
        reasoning_max_tokens: Optional[int] = None,
        enable_query_expansion: Optional[bool] = None,
        query_expansion_variants: int = 3,
        enable_reranker_reasoning: Optional[bool] = None,
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

        # Reasoning engine — tenta ler do config global se não passado explicitamente
        try:
            from config import config as _cfg
            _rtk = reasoning_top_k if reasoning_top_k is not None else getattr(_cfg, "reasoning_top_k", 12)
            _rt = reasoning_temperature if reasoning_temperature is not None else getattr(_cfg, "reasoning_temperature", 0.2)
            _rmt = reasoning_max_tokens if reasoning_max_tokens is not None else getattr(_cfg, "reasoning_max_tokens", 3072)
            _eqe = enable_query_expansion if enable_query_expansion is not None else getattr(_cfg, "enable_query_expansion", True)
            _qev = getattr(_cfg, "query_expansion_variants", query_expansion_variants)
            _err = enable_reranker_reasoning if enable_reranker_reasoning is not None else getattr(_cfg, "enable_reranker_reasoning", True)
        except Exception:
            _rtk, _rt, _rmt, _eqe, _qev, _err = 12, 0.2, 3072, True, query_expansion_variants, True

        self.reasoning_engine = ReasoningEngine(
            base_top_k=retriever.top_k,
            base_temperature=ollama_client.temperature,
            base_max_tokens=ollama_client.max_tokens,
            reasoning_top_k=_rtk,
            reasoning_temperature=_rt,
            reasoning_max_tokens=_rmt,
        )
        self.query_expander = QueryExpander(max_variants=_qev) if _eqe else None
        self._enable_query_expansion = bool(_eqe)
        self._enable_reranker_reasoning = bool(_err)

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
        """Detecta pedido EXPLÍCITO de resposta completa (TOP_K ampliado):
        'todos', 'completo', 'mais informações', etc. Perguntas de listagem
        genéricas ('quais sao ...') NÃO disparam a expansão total, para não
        inchar o prompt e demorar demais em CPU."""
        q = question.lower()
        return any(h in q for h in self._FULL_CONTEXT_HINTS)

    # Saudações e conversa trivial — não devem disparar RAG
    _GREETING_EXACT = {
        "bom dia", "boa tarde", "boa noite", "boa madrugada",
        "olá", "ola", "oi", "oie", "hey", "hello", "eae", "opa",
        "tudo bem", "tudo bom", "como vai", "como vai voce", "como vai você",
        "tudo joia", "tudo ótimo", "tudo otimo", "beleza", "fala",
        "obrigado", "obrigada", "valeu", "thanks", "tchau", "ate mais", "até mais",
    }
    _GREETING_TOKENS = {
        "bom", "dia", "boa", "tarde", "noite", "madrugada",
        "olá", "ola", "oi", "oie", "hey", "hello", "eae", "opa",
        "tudo", "bem", "bom", "vai", "você", "voce", "joia", "ótimo", "otimo",
        "beleza", "fala", "obrigado", "obrigada", "valeu", "thanks",
        "tchau", "até", "ate", "mais", "watson", "como",
    }
    _GREETING_RE = re.compile(
        r"^\s*(bom dia|boa tarde|boa noite|boa madrugada|olá|ola|oi|oie|hey|hello|eae|opa|tudo bem|tudo bom|como vai|tudo joia|beleza|fala|obrigado|obrigada|valeu|thanks|tchau|até mais|ate mais)"
        r"(\s*[, ]\s*watson)?\s*[!?.]*\s*$",
        re.IGNORECASE,
    )
    # Palavras que indicam pergunta real — se aparecerem, NÃO é só saudação
    _QUESTION_HINTS = (
        "qual", "quais", "como", "quanto", "quantos", "quantas", "onde", "quando",
        "por que", "porque", "explique", "liste", "mostre", "erro", "código", "codigo",
        "manual", "impressora", "modelo", "?", "!", # "!" para evitar falso positivo em "bom dia!"
    )

    def _is_greeting(self, question: str) -> bool:
        """Detecta saudação pura (sem pedido de informação).

        'bom dia' -> True
        'bom dia watson' -> True
        'bom dia, como corrigir erro E123?' -> False (tem pergunta real)
        """
        if not question or not question.strip():
            return False
        q = question.strip().lower()
        # Remove múltiplos espaços e pontuação para comparação
        q_clean = re.sub(r"[^\w\s]", "", q).strip()
        q_clean = re.sub(r"\s+", " ", q_clean)

        # Se contém hint de pergunta real, não é saudação
        has_question_hint = any(
            h in q
            for h in (
                "qual", "quais", "como corrigir", "como fazer", "como resolver",
                "quanto", "quantos", "quantas", "onde", "quando",
                "erro", "código", "codigo", "impressora", "manual", "modelo",
                "documento", "planilha", "tabela",
            )
        )
        if has_question_hint and len(q_clean.split()) > 3:
            return False
        if "?" in question and has_question_hint:
            return False

        # Match exato após limpeza
        if q_clean in self._GREETING_EXACT:
            return True
        if self._GREETING_RE.match(q):
            return True
        # Todos os tokens são de saudação e poucos tokens (até 6 para "bom dia watson tudo bem")
        tokens = q_clean.split()
        if 1 <= len(tokens) <= 6 and all(t in self._GREETING_TOKENS for t in tokens):
            return True
        return False

    def _greeting_response(self, start: float) -> AgentResponse:
        """Resposta determinística para saudação — sem RAG, sem LLM."""
        answer = self._greeting()
        return AgentResponse(
            answer=answer,
            evidences=[],
            confidence=1.0,
            verdict="ok",
            metadata={"provider": "greeting", "evidence_count": 0, "greeting": True},
            execution_time=time.time() - start,
        )

    def _retrieve_rag(self, question: str) -> List[Evidence]:
        # Plano de raciocínio decide top_k, multi-query e rerank
        try:
            plan = self.reasoning_engine.plan(question)
        except Exception:
            plan = None

        full = self._wants_full_context(question)
        # full-context tem prioridade (listagem completa)
        if full:
            top_k = (plan.top_k * 2 if plan else self.retriever.top_k * 4)
            docs = self.retriever.retrieve(question, k=top_k)
            # Rerank se disponível
            if self._rag_reranker and docs:
                from rag.reranker import Reranker as RagReranker
                docs = RagReranker.rerank(self._rag_reranker, question, docs, top_k=len(docs))
            evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]
            # Boost de evidências para queries analíticas
            if plan:
                for ev in evidence:
                    boost = self.reasoning_engine.evidence_boost(ev.content, question)
                    if boost:
                        ev.score = min(1.0, ev.score + boost)
                        ev.metadata["relevance_score"] = ev.score
            evidence = self._expand_document_context(evidence)
            return evidence

        # Caminho com reasoning + multi-query RRF
        if self._enable_query_expansion and plan and plan.needs_multi_query and self.query_expander:
            try:
                expanded = self.query_expander.expand(question)
                # Limita a 2 variantes para não estourar latência em CPU
                variants = expanded.variants[:2] if len(expanded.variants) > 1 else [question]
                per_k = max(3, (plan.top_k // len(variants)) if plan else self.retriever.top_k)
                ranked_lists: List[List[Document]] = []
                for v in variants:
                    docs_v = self.retriever.retrieve(v, k=per_k)
                    if docs_v:
                        ranked_lists.append(docs_v)
                if len(ranked_lists) > 1:
                    docs = reciprocal_rank_fusion(ranked_lists, top_n=plan.top_k if plan else per_k * len(variants))
                    if self.logger:
                        self.logger.info(f"RRF fusion: {len(variants)} variants -> {len(docs)} docs (intent={expanded.intent})")
                elif ranked_lists:
                    docs = ranked_lists[0]
                else:
                    docs = []
                # Rerank se plano pedir e reranker habilitado para reasoning
                should_rerank = (plan.use_reranker if plan else self._is_analytical(question)) and self._rag_reranker and docs and self._enable_reranker_reasoning
                if should_rerank:
                    from rag.reranker import Reranker as RagReranker
                    docs = RagReranker.rerank(self._rag_reranker, question, docs, top_k=len(docs))
                evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]
                if plan:
                    for ev in evidence:
                        boost = self.reasoning_engine.evidence_boost(ev.content, question)
                        if boost:
                            ev.score = min(1.0, ev.score + boost)
                            ev.metadata["relevance_score"] = ev.score
                # Fallback iterativo: se pouca evidência e precisa raciocinar, tenta query sem stopwords
                if plan and plan.needs_cot and len(evidence) < 2:
                    stripped = re.sub(r"\b(por que|porque|explique|analise|comparar|variação|percentual)\b", "", question, flags=re.IGNORECASE).strip()
                    if stripped and stripped != question:
                        extra = self.retriever.retrieve(stripped, k=3)
                        for d in extra:
                            ev = EvidenceNormalizer.from_chroma_document(d)
                            if ev.chunk_id not in {e.chunk_id for e in evidence}:
                                evidence.append(ev)
                                if len(evidence) >= (plan.top_k if plan else 8):
                                    break
                return evidence
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Multi-query retrieval failed, fallback single: {e}")

        # Fallback single-query (compatível com comportamento antigo)
        if plan:
            top_k = plan.top_k
        elif self._is_analytical(question):
            top_k = self.retriever.top_k * 2
        else:
            top_k = None
        docs: List[Document] = self.retriever.retrieve(question, k=top_k)
        # Rerank adaptativo: só se habilitado para reasoning
        should_rerank = False
        if self._rag_reranker and docs and self._enable_reranker_reasoning:
            if plan and plan.use_reranker:
                should_rerank = True
            elif self._is_analytical(question):
                should_rerank = True
        if should_rerank:
            from rag.reranker import Reranker as RagReranker
            docs = RagReranker.rerank(self._rag_reranker, question, docs, top_k=len(docs))
        evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]
        if plan:
            for ev in evidence:
                boost = self.reasoning_engine.evidence_boost(ev.content, question)
                if boost:
                    ev.score = min(1.0, ev.score + boost)
                    ev.metadata["relevance_score"] = ev.score
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

    def _call_llm(
        self,
        prompt: str,
        reasoning: Optional[bool] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        kwargs: dict = {}
        if reasoning is not None:
            kwargs["think"] = reasoning
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        answer = self.ollama_client.ask(prompt, **kwargs)
        return self.ollama_client._strip_thinking(answer)

    def _should_reason(self, question: str) -> bool:
        """Habilita raciocínio (think) para perguntas analíticas, se configurado
        e o modelo suportar. Usa ReasoningEngine para decisão mais precisa."""
        if not self.ollama_client.supports_thinking():
            return False
        # Se reasoning global desabilitado, só permite se plano indicar necessidade forte
        try:
            plan = self.reasoning_engine.plan(question)
            if plan.needs_cot:
                # Se modelo suporta thinking, permite mesmo com enable_reasoning=False
                # para queries que exigem CoT, mas respeita flag se não for crítico
                return True if plan.intent in {"percent_change", "difference", "compare", "trend", "reasoning"} else self.enable_reasoning
        except Exception:
            pass
        if not self.enable_reasoning:
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

    def _call_llm_stream(
        self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None, reasoning: Optional[bool] = None,
    ) -> Generator[str, None, str]:
        full_answer: List[str] = []
        kwargs: dict = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if reasoning is not None:
            kwargs["think"] = reasoning
        try:
            for token in self.ollama_client.ask_stream(prompt, **kwargs):
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

    def _deepen_answer(
        self, question: str, resp: AgentResponse, focus: str = ""
    ) -> str:
        """Gera um detalhamento mais profundo da resposta, baseado nas evidências.

        Usado por 'aprofundar: <foco>' — expande a narrativa sem inventar:
        se a evidência for insuficiente para o foco, o modelo diz o que falta.
        """
        evidence_text = "\n\n".join(
            f"[{e.title or e.source}]\n{e.content}"
            for e in (resp.evidences or [])[:8]
        )
        if not evidence_text:
            evidence_text = "(sem evidências disponíveis)"
        focus_line = f"FOCO DO DETALHAMENTO: {focus}" if focus else ""
        prompt = (
            "Você é o Watson, um analista sênior.\n"
            f"Pergunta original: {question}\n"
            f"Resposta anterior (resumida):\n{resp.answer}\n\n"
            "Agora produza uma versão MUITO MAIS DETALHADA dessa resposta, "
            "explorando cada aspecto com mais profundidade. IMPORTANTE:\n"
            "- NÃO invente fatos, números ou nomes que não estejam nas evidências.\n"
            "- Se a evidência não tiver informação para aprofundar o foco, diga explicitamente o que falta.\n"
            f"- {focus_line}\n\n"
            "Evidências disponíveis:\n"
            f"{evidence_text}\n\n"
            "Detalhamento:"
        )
        try:
            detailed = self.ollama_client.ask(
                prompt,
                temperature=0.3,
                max_tokens=getattr(self.reasoning_engine, "reasoning_max_tokens", 3072),
            )
            return self.ollama_client._strip_thinking(detailed).strip()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Deepen failed: {e}")
            return ""

    def _make_plan(self, question: str):
        """Plano de raciocínio para a pergunta — (plan, hint, reasoning_needed)."""
        try:
            plan = self.reasoning_engine.plan(question)
        except Exception:
            plan = None
        reasoning_needed = bool(plan and plan.needs_cot)
        hint = plan.reasoning_hint if plan else ""
        return plan, hint, reasoning_needed

    def _apply_relevance_filter(
        self, question: str, evidence: List[Evidence]
    ) -> List[Evidence]:
        """Filtro de relevância: evita usar imagem irrelevante para pergunta factual."""
        if not evidence:
            return evidence
        try:
            max_score = max(getattr(e, "score", 0) or 0 for e in evidence)
            is_image_only = all((e.metadata.get("source_type", "") == "image") for e in evidence)
            ql = question.lower()
            is_image_question = any(kw in ql for kw in (
                "imagem", "foto", "figura", "print", "screenshot",
                "imagem fornecida", "anexe", "descreva", "o que tem", "o que há",
            ))
            evidence_text = " ".join((e.content or "").lower() for e in evidence)
            content_overlap = False
            if is_image_only and not is_image_question:
                q_keywords = [kw for kw in ("champions", "pote", "pot ", "time", "grupo", "liga") if kw in ql]
                if q_keywords and any(kw in evidence_text for kw in q_keywords):
                    is_image_question = True
                    content_overlap = True
            thr = self.retriever.similarity_threshold if self.retriever.similarity_threshold is not None else 0.25
            if is_image_question:
                evidence = [e for e in evidence if e.metadata.get("source_type", "") == "image"]
            elif max_score < thr and is_image_only and not is_image_question:
                if self.logger:
                    self.logger.info(f"Evidence filtered: image-only low relevance (max={max_score:.2f} < {thr}) for non-image question")
                evidence = []
            elif max_score < 0.15 and not content_overlap:
                if self.logger:
                    self.logger.info(f"Evidence filtered: max relevance {max_score:.2f} too low")
                evidence = []
        except Exception:
            pass
        return evidence

    def _prepare_evidence(self, question: str) -> List[Evidence]:
        """Pipeline comum de evidências: retrieve -> dedup -> rank -> filtro -> cálculo."""
        evidence = self._retrieve_rag(question)
        evidence = self.aggregator.collect(rag_evidence=evidence)
        evidence = self.aggregator.rank(evidence)
        evidence = self._apply_relevance_filter(question, evidence)
        evidence = self._inject_computed_facts(question, evidence)
        return evidence

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
            # Saudações não devem disparar RAG — resposta direta e leve
            if self._is_greeting(question):
                if self.logger:
                    self.logger.info(f"Greeting detected: {question!r} -> no retrieval")
                resp = self._greeting_response(start)
                self._record_request(question, mode, provider, resp, start, analyze)
                return resp

            plan, hint, reasoning_needed = self._make_plan(question)
            evidence = self._prepare_evidence(question)

            if not evidence:
                if self.logger:
                    self.logger.info("No evidence found in indexed documents")
                prompt = self.prompt_builder.build(question, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint)
                answer = self._call_llm(
                    prompt,
                    reasoning=self._should_reason(question),
                    temperature=plan.temperature if plan else None,
                    max_tokens=plan.max_tokens if plan else None,
                )
                resp = self._build_response(answer, [], start)
                resp.metadata["fallback"] = "no_documents"
                if plan:
                    resp.metadata["reasoning_intent"] = plan.intent
                    resp.metadata["reasoning_cot"] = reasoning_needed
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, provider, resp, start, analyze)
                return resp

            prompt = (
                self.prompt_builder.build_with_history(
                    question, evidence, history_context, mode=mode,
                    reasoning=reasoning_needed, reasoning_hint=hint,
                )
                if history_context
                else self.prompt_builder.build(question, evidence, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint)
            )

            answer_clean = self._call_llm(
                prompt,
                reasoning=self._should_reason(question),
                temperature=plan.temperature if plan else None,
                max_tokens=plan.max_tokens if plan else None,
            )
            result = self._build_response(answer_clean, evidence, start)
            if plan:
                result.metadata["reasoning_intent"] = plan.intent
                result.metadata["reasoning_cot"] = reasoning_needed
                result.metadata["reasoning_top_k"] = plan.top_k

            if self.logger:
                self.logger.info(
                    f"AgentResponse: evidence={len(evidence)}, "
                    f"time={result.execution_time:.2f}s, intent={plan.intent if plan else 'unknown'}, cot={reasoning_needed}"
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
        plan=None,
    ) -> Generator[str, None, AgentResponse]:
        start = time.time()
        if plan is None:
            plan = self._make_plan(question)[0]
        hint = plan.reasoning_hint if plan else ""
        reasoning_needed = bool(plan and plan.needs_cot)
        prompt = (
            self.prompt_builder.build_with_history(
                question, None, history_context, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint
            )
            if history_context
            else self.prompt_builder.build(question, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint)
        )
        full_answer = yield from self._call_llm_stream(
            prompt,
            temperature=plan.temperature if plan else None,
            max_tokens=plan.max_tokens if plan else None,
            reasoning=self._should_reason(question),
        )
        resp = self._build_response(full_answer, [], start)
        resp.metadata["fallback"] = "no_documents"
        if plan:
            resp.metadata["reasoning_intent"] = plan.intent
        return resp

    def _greeting_stream(self, start: float) -> Generator[str, None, AgentResponse]:
        """Stream para saudação — yield único para evitar glitch com status spinner."""
        resp = self._greeting_response(start)
        yield resp.answer
        return resp

    def _ask_stream_inner(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        """Core único de streaming — usado por ask_stream e ask_stream_with_history."""
        if self.logger:
            self.logger.info(f"Question: {question}")

        start = time.time()
        try:
            if self._is_greeting(question):
                if self.logger:
                    self.logger.info(f"Greeting detected (stream): {question!r}")
                resp = yield from self._greeting_stream(start)
                self._record_request(question, mode, "greeting", resp, start, analyze)
                return resp

            plan, hint, reasoning_needed = self._make_plan(question)
            evidence = self._prepare_evidence(question)

            if not evidence:
                if self.logger:
                    self.logger.info("No evidence found in indexed documents")
                resp = yield from self._stream_no_evidence(question, history_context, mode, plan)
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, "rag", resp, start, analyze)
                return resp

            prompt = (
                self.prompt_builder.build_with_history(
                    question, evidence, history_context, mode=mode,
                    reasoning=reasoning_needed, reasoning_hint=hint,
                )
                if history_context
                else self.prompt_builder.build(question, evidence, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint)
            )
            result = yield from self._stream_evidence(prompt, evidence)
            if plan:
                result.metadata["reasoning_intent"] = plan.intent
                result.metadata["reasoning_cot"] = reasoning_needed
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

    def ask_stream(
        self,
        question: str,
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        return self._ask_stream_inner(question, "", mode, analyze)

    def ask_stream_with_history(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        return self._ask_stream_inner(question, history_context, mode, analyze)

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
        return f"Olá, {periodo}! Sou o {self.agent_name}. Como posso ajudar hoje?"

    def chat_loop(self) -> None:
        _enable_ansi_on_windows()
        print(f"\n{ANSI_CYAN}{ANSI_BOLD}=== Watson RAG ==={ANSI_RESET}")
        print(f"{ANSI_GREEN}{self._greeting()}{ANSI_RESET}")
        print(f"{ANSI_DIM}Digite 'exit' ou 'quit' para sair.{ANSI_RESET}\n")

        last_question: Optional[str] = None
        last_result: Optional[AgentResponse] = None
        analyze_mode = False  # espelha API analyze=true — quando ligado, toda pergunta já vem com análise proativa
        history: List[dict] = []  # memória de conversa (como ChatGPT/Gemini/Claude)

        # Dicas padronizadas no formato "comando: pergunta" — amarelo para o comando, dim para o resto
        print(f"{ANSI_DIM}{ANSI_BOLD}Como perguntar (tipo: pergunta):{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}fato:{ANSI_RESET}{ANSI_DIM}      qual o erro E123 da impressora HP E52645?{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}lista:{ANSI_RESET}{ANSI_DIM}     quais são os modelos disponíveis?{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}conta:{ANSI_RESET}{ANSI_DIM}     quantos % a mais em fevereiro vs janeiro?{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}comparar:{ANSI_RESET}{ANSI_DIM}  compare os dois planos de pagamento{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}imagem:{ANSI_RESET}{ANSI_DIM}    o que tem nessa imagem?{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}passos:{ANSI_RESET}{ANSI_DIM}    como trocar o toner passo a passo?{ANSI_RESET}")
        print()
        print(f"{ANSI_DIM}{ANSI_BOLD}Comandos (comando: valor) -> o que faz:{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}analisar: on{ANSI_RESET}{ANSI_DIM}       -> liga a análise automática em toda pergunta{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}analisar: off{ANSI_RESET}{ANSI_DIM}       -> desliga a análise automática{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}analisar: <pergunta>{ANSI_RESET}{ANSI_DIM} -> análise só nessa pergunta{ANSI_RESET}")
        print(f"{ANSI_DIM}      ex: {ANSI_YELLOW}analisar: como pagar a moto em 6 meses?{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}aprofundar:{ANSI_RESET}{ANSI_DIM}       -> detalha mais a última resposta (ex: {ANSI_YELLOW}aprofundar: detalhe a história{ANSI_RESET}){ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}esquecer:{ANSI_RESET}{ANSI_DIM}        -> limpa a memória da conversa{ANSI_RESET}")
        print(f"{ANSI_DIM}  • {ANSI_YELLOW}exit:{ANSI_RESET}{ANSI_DIM}            -> sai do chat{ANSI_RESET}")
        print()

        while True:
            try:
                # Prompt e texto digitado em amarelo/negrito — bem distinto de resposta (branco) e status (azul claro)
                sys.stdout.write(f"{ANSI_YELLOW}{ANSI_BOLD}> {ANSI_YELLOW}")
                sys.stdout.flush()
                question = input().strip()
                sys.stdout.write(ANSI_RESET)
                sys.stdout.flush()
                # Reimprime a pergunta com cor para garantir histórico colorido
                if question:
                    sys.stdout.write(f"\033[F\033[2K{ANSI_YELLOW}{ANSI_BOLD}> {question}{ANSI_RESET}\n")
                    sys.stdout.flush()
            except (EOFError, KeyboardInterrupt):
                sys.stdout.write(ANSI_RESET + "\n")
                print(f"{ANSI_DIM}Encerrando...{ANSI_RESET}")
                break

            if not question:
                continue

            if question.lower() in ("exit", "quit", "sair", "encerrar", "parar"):
                print(f"{ANSI_DIM}Encerrando...{ANSI_RESET}")
                break

            # --- Modo analisar (espelha API analyze=true) ---
            qlow = question.lower().strip()
            # Flag por pergunta: "analisar: ..." ou "... --analisar"
            analyze_this = False
            if qlow.startswith("analisar:"):
                analyze_this = True
                question = question[len("analisar:"):].strip()
                qlow = question.lower().strip()
            elif qlow.endswith("--analisar"):
                analyze_this = True
                question = question[: -len("--analisar")].strip()
                qlow = question.lower().strip()
            elif qlow.endswith("/analisar"):
                analyze_this = True
                question = question[: -len("/analisar")].strip()
                qlow = question.lower().strip()

            # Toggle persistente: "analisar on/off"
            if qlow in ("analisar on", "analisar ligado", "modo analisar on", "analisar: on"):
                analyze_mode = True
                print(f"{ANSI_GREEN}Modo analisar ativado — próximas respostas virão com conclusões e perguntas de acompanhamento (como API analyze=true).{ANSI_RESET}")
                continue
            if qlow in ("analisar off", "analisar desligado", "modo analisar off", "analisar: off"):
                analyze_mode = False
                print(f"{ANSI_DIM}Modo analisar desativado.{ANSI_RESET}")
                continue
            if qlow in ("analisar", "analise"):
                print(f"{ANSI_YELLOW}Modo analisar está {'ligado' if analyze_mode else 'desligado'}. Use 'analisar on/off' ou 'analisar: sua pergunta' para análise única.{ANSI_RESET}")
                if self.analyst is None:
                    print(f"{ANSI_DIM}(Analista desabilitado — ative ENABLE_ANALYST=true e reinicie){ANSI_RESET}")
                continue

            # Limpar memória de conversa
            if qlow in ("esquecer", "limpar contexto", "limpar memória", "limpar memoria", "novo contexto", "novo"):
                history.clear()
                print(f"{ANSI_DIM}Memória da conversa limpa. Novas perguntas não usarão contexto anterior.{ANSI_RESET}")
                continue

            if qlow in ("aprofundar", "aprofundar análise") or qlow.startswith("aprofundar"):
                # Extrai foco: 'aprofundar: detalhe' -> foco='detalhe'
                focus = ""
                if ":" in qlow:
                    focus = question.split(":", 1)[1].strip()
                elif qlow.startswith("aprofundar ") and qlow != "aprofundar análise":
                    focus = question.split(" ", 1)[1].strip()
                # Focos genéricos = detalhar a resposta INTEIRA (não um ponto específico)
                if focus and focus.lower().lstrip("!?. ") in (
                    "detalhe", "detalhar", "detalhes", "mais", "mais detalhe",
                    "expandir", "expand", "aprofundar", "história", "historia",
                    "melhor", "responda", "continue", "resposta anterior",
                ):
                    focus = ""
                if last_result is not None and last_question:
                    # 1) Detalhamento narrativo (LLM + evidências) — pega a resposta anterior e detalha mais
                    print(f"\n{ANSI_YELLOW}[Aprofundando...]{ANSI_RESET}", flush=True)
                    detailed = self._deepen_answer(last_question, last_result, focus)
                    if detailed:
                        print(f"\n{ANSI_WHITE}{ANSI_BOLD}Detalhamento:{ANSI_RESET}")
                        print(f"{ANSI_WHITE}{detailed}{ANSI_RESET}")
                    # 2) Análise proativa (conclusões/perguntas/informação adicional)
                    result = self._run_analyst(last_question, last_result)
                    print(f"{ANSI_MAGENTA}{self._format_analyst(result)}{ANSI_RESET}")
                else:
                    print(f"\n{ANSI_YELLOW}Nenhuma resposta anterior para aprofundar. Faça uma pergunta primeiro.{ANSI_RESET}")
                continue

            last_question = question
            last_result = None
            should_analyze = analyze_this or analyze_mode
            if should_analyze and self.analyst is None:
                print(f"{ANSI_YELLOW}[Aviso] Analyst desabilitado (ENABLE_ANALYST=false) — resposta virá sem análise.{ANSI_RESET}")
                should_analyze = False

            stop_status = threading.Event()
            status_thread = threading.Thread(
                target=self._status_loop, args=(stop_status,), daemon=True
            )
            status_thread.start()

            try:
                print()
                # Memória de conversa: envia últimas 8 mensagens como contexto (como ChatGPT/Gemini/Claude)
                history_context = "\n".join(
                    f"{m['role']}: {m['content']}" for m in history[-8:]
                )
                # Não passa analyze para o stream aqui — análise roda depois com status próprio
                gen = self.ask_stream_with_history(
                    question, history_context
                ) if history_context else self.ask_stream(question)
                tokens: List[str] = []
                started = False
                try:
                    while True:
                        token = next(gen)
                        if not started:
                            stop_status.set()
                            try:
                                status_thread.join(timeout=0.3)
                            except Exception:
                                pass
                            started = True
                            # Limpa a linha do status ANTES do primeiro token
                            sys.stdout.write("\r\033[K")
                            sys.stdout.flush()
                            # Inicia cor da resposta (branco brilhante/verde)
                            sys.stdout.write(ANSI_WHITE + ANSI_BOLD)
                            sys.stdout.flush()
                        # Resposta em branco/brilhante — bem distinta da pergunta (ciano) e status (amarelo)
                        sys.stdout.write(token)
                        sys.stdout.flush()
                        tokens.append(token)
                except StopIteration as e:
                    result = e.value
                # Reseta cor e garante quebra de linha
                sys.stdout.write(ANSI_RESET + "\n")
                sys.stdout.flush()
                stop_status.set()
                try:
                    status_thread.join(timeout=0.2)
                except Exception:
                    pass

                if result:
                    # Fase de análise (se pedida) — com feedback visual para não parecer travado
                    if should_analyze and self.analyst is not None:
                        an_status = threading.Event()
                        an_thread = threading.Thread(
                            target=self._analyst_status_loop, args=(an_status,), daemon=True
                        )
                        an_thread.start()
                        try:
                            result = self._run_analyst(question, result)
                        finally:
                            an_status.set()
                            try:
                                an_thread.join(timeout=0.3)
                            except Exception:
                                pass
                            sys.stdout.write("\r\033[K" + ANSI_RESET)
                            sys.stdout.flush()

                    last_result = result
                    if result.sources:
                        print(f"\n{ANSI_DIM}{ANSI_BOLD}Sources{ANSI_RESET}")
                        print(f"{ANSI_DIM}-------{ANSI_RESET}")
                        for s in result.sources:
                            label = s.title or s.url
                            print(f"{ANSI_DIM}  • {label}{ANSI_RESET}")
                    # Modo analisar (API analyze=true) mostra análise completa; modo normal só follow-up
                    if should_analyze and (result.conclusions or result.follow_up or result.additional_info):
                        print(f"\n{ANSI_MAGENTA}{self._format_analyst(result)}{ANSI_RESET}")
                    elif result.follow_up:
                        print(f"\n{ANSI_MAGENTA}{ANSI_BOLD}Perguntas para aprofundar:{ANSI_RESET}")
                        for i, q in enumerate(result.follow_up, 1):
                            print(f"{ANSI_MAGENTA}  {i}. {q}{ANSI_RESET}")
                        print(f"{ANSI_DIM}  (digite 'aprofundar' para mais conclusões/busca){ANSI_RESET}")

                    # Guarda na memória da conversa
                    history.append({"role": "user", "content": question})
                    history.append({"role": "assistant", "content": result.answer})
                    if len(history) > 24:  # cap para não estourar contexto
                        history = history[-24:]

                if self.logger:
                    self.logger.info(
                        f"Answer provided ({len(''.join(tokens))} chars)"
                    )
            except Exception as e:
                stop_status.set()
                sys.stdout.write(ANSI_RESET)
                error_msg = f"Erro ao processar pergunta: {e}"
                print(f"\n{ANSI_RED}{error_msg}{ANSI_RESET}")
                if self.logger:
                    self.logger.error(error_msg)

    _STATUS_MESSAGES = (
        "{agent} está analisando sua resposta...",
        "{agent} está consultando a base de conhecimento...",
        "{agent} está processando sua pergunta...",
        "{agent} está buscando a melhor resposta...",
    )

    def _status_loop(self, stop_event: threading.Event) -> None:
        """Exibe mensagens de status rotativas (azul bem claro) enquanto a IA gera a resposta."""
        msgs = [m.format(agent=self.agent_name) for m in self._STATUS_MESSAGES]
        i = 0
        try:
            while True:
                if stop_event.is_set():
                    break
                sys.stdout.write(f"\r{ANSI_CYAN}{msgs[i % len(msgs)]}   {ANSI_RESET}")
                sys.stdout.flush()
                if stop_event.wait(2.5):
                    break
                i += 1
        finally:
            sys.stdout.write("\r\033[K" + ANSI_RESET)
            sys.stdout.flush()

    def _analyst_status_loop(self, stop_event: threading.Event) -> None:
        """Status da fase de análise proativa (evita parecer travado durante 2-3 chamadas ao LLM)."""
        msgs = [
            f"{self.agent_name} está aprofundando a análise...",
            f"{self.agent_name} está refletindo sobre a resposta...",
            f"{self.agent_name} está buscando informação adicional...",
        ]
        i = 0
        try:
            while True:
                if stop_event.is_set():
                    break
                sys.stdout.write(f"\r{ANSI_CYAN}{msgs[i % len(msgs)]}   {ANSI_RESET}")
                sys.stdout.flush()
                if stop_event.wait(1.8):
                    break
                i += 1
        finally:
            sys.stdout.write("\r\033[K" + ANSI_RESET)
            sys.stdout.flush()
