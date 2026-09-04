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
from rag.semantic_cache import SemanticCache


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
        web_search: Optional[object] = None,
        query_rewriter: Optional[object] = None,
        analyst_ollama_client: Optional[OllamaClient] = None,
        semantic_cache: Optional[SemanticCache] = None,
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
            from core.config import config as _cfg
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
        self.web_search = web_search
        self.query_rewriter = query_rewriter
        self._last_rewritten = None  # para expor em metadata/debug
        self.analyst_ollama_client = analyst_ollama_client or ollama_client
        self._profiles = {
            "flash": {"top_k": 5, "enable_query_rewriter": False, "use_reranker": False, "enable_analyst": False, "enable_reasoning": False},
            "pro": {"top_k": 12, "enable_query_rewriter": True, "use_reranker": True, "enable_analyst": True, "enable_reasoning": True},
        }
        # Semantic cache — tenta ler do config global se não passado
        if semantic_cache is not None:
            self.semantic_cache = semantic_cache
        else:
            try:
                from core.config import config as _cfg_cache
                if getattr(_cfg_cache, "cache_enabled", True):
                    self.semantic_cache = SemanticCache(max_size=getattr(_cfg_cache, "cache_max_size", 100), ttl_seconds=getattr(_cfg_cache, "cache_ttl_seconds", 3600))
                else:
                    self.semantic_cache = None
            except Exception:
                self.semantic_cache = SemanticCache(max_size=100, ttl_seconds=3600)

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

    def _retrieve_rag(self, question: str, profile: str = "") -> List[Evidence]:
        # Plano de raciocínio decide top_k, multi-query e rerank — perfil Watson (flash/plus/pro) pode sobrescrever
        try:
            plan = self.reasoning_engine.plan(question)
        except Exception:
            plan = None
        # Aplica overrides de perfil por request (se enviado via select no prompt)
        p = (profile or "").strip().lower()
        if p in self._profiles:
            prof = self._profiles[p]
            if plan:
                # Sobrescreve top_k do plano com o do perfil
                try:
                    plan.top_k = int(prof.get("top_k", plan.top_k))
                except Exception:
                    pass

        # --- Query Understanding Layer (LLM rewriter) — antes de tudo ---
        rewritten = None
        if getattr(self, "query_rewriter", None):
            try:
                rewritten = self.query_rewriter.rewrite(question)
                self._last_rewritten = rewritten
                if self.logger:
                    self.logger.info(
                        f"Rewriter: normalized='{rewritten.normalized_query[:80]}' | {len(rewritten.expanded_queries)} vars | entities={rewritten.entities} intent={rewritten.intent}"
                    )
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Rewriter failed, fallback: {e}")
                rewritten = None
                self._last_rewritten = None

        full = self._wants_full_context(question)
        # full-context tem prioridade (listagem completa)
        if full:
            # Usa normalized do rewriter se houver, preserva termos técnicos
            q_full = rewritten.normalized_query if rewritten and rewritten.normalized_query else question
            top_k = (plan.top_k * 2 if plan else self.retriever.top_k * 4)
            docs = self.retriever.retrieve(q_full, k=top_k)
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

        # Caminho com rewriter (prioritário) — 5 queries especializadas preservando termos técnicos
        if rewritten and rewritten.expanded_queries:
            try:
                variants = rewritten.all_queries()  # normalized + 5 expandidas
                # Limita para não estourar latência; usa todas do rewriter (até 6)
                per_k = max(3, (plan.top_k // len(variants)) if plan and plan.top_k else self.retriever.top_k)
                ranked_lists: List[List[Document]] = []
                for v in variants[:5]:
                    docs_v = self.retriever.retrieve(v, k=per_k)
                    if docs_v:
                        ranked_lists.append(docs_v)
                if len(ranked_lists) > 1:
                    docs = reciprocal_rank_fusion(ranked_lists, top_n=plan.top_k if plan else per_k * len(variants))
                    if self.logger:
                        self.logger.info(f"Rewriter RRF: {len(variants)} vars -> {len(docs)} docs (intent={rewritten.intent} entities={rewritten.entities})")
                elif ranked_lists:
                    docs = ranked_lists[0]
                else:
                    docs = []
                # Boost por entidades (manufacturer/model) se detectadas
                if rewritten.entities:
                    for ev in [EvidenceNormalizer.from_chroma_document(d) for d in docs]:
                        # Placeholder para boost por entidade será aplicado abaixo após conversão
                        pass
                should_rerank = (plan.use_reranker if plan else self._is_analytical(question)) and self._rag_reranker and docs and self._enable_reranker_reasoning
                # Sempre reranka quando rewriter foi usado e reranker disponível — melhora híbrido
                if should_rerank or (self._rag_reranker and docs and rewritten.intent in ("troubleshooting", "procedural")):
                    from rag.reranker import Reranker as RagReranker
                    docs = RagReranker.rerank(self._rag_reranker, question, docs, top_k=len(docs))
                evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]
                # Boost por entidades + reasoning
                if rewritten.entities:
                    man = (rewritten.entities.get("manufacturer") or "").lower()
                    mod = (rewritten.entities.get("model") or "").lower()
                    for ev in evidence:
                        txt = (ev.content or "").lower()
                        boost = 0.0
                        if man and man in txt:
                            boost += 0.08
                        if mod and any(tok in txt for tok in mod.split() if len(tok) >= 3):
                            boost += 0.12
                        if boost:
                            ev.score = min(1.0, ev.score + boost)
                            ev.metadata["entity_boost"] = boost
                if plan:
                    for ev in evidence:
                        b = self.reasoning_engine.evidence_boost(ev.content, question)
                        if b:
                            ev.score = min(1.0, ev.score + b)
                            ev.metadata["relevance_score"] = ev.score
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
                    self.logger.warning(f"Rewriter RRF failed, fallback: {e}")

        # Caminho com reasoning + multi-query RRF (fallback determinístico antigo)
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

        # Fallback single-query (compatível com comportamento antigo) — com over-fetch para rerank (Pro 2×)
        if plan:
            top_k = plan.top_k
        elif self._is_analytical(question):
            top_k = self.retriever.top_k * 2
        else:
            top_k = None
        # Over-fetch para Pro/reranker: busca 25-30 candidatos e reranka para top_k (melhor recall)
        fetch_k = top_k
        should_rerank = False
        if self._rag_reranker and self._enable_reranker_reasoning:
            if plan and plan.use_reranker:
                should_rerank = True
            elif self._is_analytical(question):
                should_rerank = True
        if should_rerank and top_k is not None:
            fetch_k = max(top_k * 3, 24)  # Pro: 12 → 36, Flash nunca entra aqui (use_reranker False)
            fetch_k = min(fetch_k, 50)
        docs: List[Document] = self.retriever.retrieve(question, k=fetch_k)
        if should_rerank and docs:
            from rag.reranker import Reranker as RagReranker
            docs = RagReranker.rerank(self._rag_reranker, question, docs, top_k=top_k or len(docs))
            # Compressão extrativa leve: mantém top_k já filtrado (30-80% tokens a menos vs over-fetch)
            if len(docs) > (top_k or 0) and top_k:
                docs = docs[:top_k]
        evidence = [EvidenceNormalizer.from_chroma_document(d) for d in docs]
        if plan:
            for ev in evidence:
                boost = self.reasoning_engine.evidence_boost(ev.content, question)
                if boost:
                    ev.score = min(1.0, ev.score + boost)
                    ev.metadata["relevance_score"] = ev.score
        return evidence

    def _expand_parent_context(self, evidence: List[Evidence], max_extra: int = 6) -> List[Evidence]:
        """Parent-child: para Pro, busca chunks vizinhos do mesmo documento para dar contexto completo (late chunking query-time).
        Search em child (400) mas devolve parent (800/1600) — sem reindex."""
        if not evidence or not self._rag_reranker:
            return evidence
        # Só para Pro (reranker ativo) — Pro já paga over-fetch, expandir mais 6 não pesa
        ranked = sorted(evidence, key=lambda e: e.score, reverse=True)
        sources: list = []
        seen: set = set()
        for ev in ranked:
            source = ev.metadata.get("source", "") or ev.source or ""
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
            if len(sources) >= 1:
                break
        if not sources:
            return evidence
        exclude = {ev.metadata.get("chunk_id", "") for ev in evidence}
        extra_docs = []
        for source in sources:
            try:
                related = self.retriever.retrieve_all_from_source(source, exclude_ids=exclude)
                extra_docs.extend(related[: max_extra])
            except Exception:
                pass
        if not extra_docs:
            return evidence
        extra = [EvidenceNormalizer.from_chroma_document(d) for d in extra_docs]
        if self.logger:
            self.logger.info(f"Parent-child expand (Pro): +{len(extra)} chunks de {sources[0].split('/')[-1]}")
        return evidence + extra

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

    def _choose_llm(self, analyze: bool = False) -> OllamaClient:
        if analyze and getattr(self, "analyst_ollama_client", None) and self.analyst_ollama_client is not self.ollama_client:
            return self.analyst_ollama_client
        return self.ollama_client

    def _call_llm(
        self,
        prompt: str,
        reasoning: Optional[bool] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        analyze: bool = False,
    ) -> str:
        client = self._choose_llm(analyze)
        kwargs: dict = {}
        # Em modo analisar, força think se cliente suporta (modelo inteligente)
        if analyze and client.supports_thinking():
            kwargs["think"] = True
        elif reasoning is not None:
            kwargs["think"] = reasoning
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            answer = client.ask(prompt, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            # Fallback se modelo inteligente não baixado (ex: qwen3:8b ainda não existe) → usa gemma
            if analyze and client is not self.ollama_client and ("not found" in msg or "model" in msg and "not" in msg):
                if self.logger:
                    self.logger.warning(f"Analyst model {client.model} não encontrado, fallback para {self.ollama_client.model}: {e}")
                # Tenta sem think no modelo principal
                kwargs.pop("think", None)
                answer = self.ollama_client.ask(prompt, **kwargs)
                return self.ollama_client._strip_thinking(answer)
            raise
        return client._strip_thinking(answer)

    def _strip_inline_sources(self, text: str) -> str:
        """Remove qualquer URL ou menção a fonte inline que o LLM tenha gerado — sanitização final.
        Chips abaixo já exibem as fontes; URLs no corpo poluem e violam a regra do WEB prompt."""
        import re
        if not text:
            return text
        # Remove markdown links [texto](https://...)
        text = re.sub(r'\[([^\]]+)\]\s*\(\s*https?://[^\)]+\s*\)', r'\1', text)
        # Remove URLs soltas
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)
        # Remove linhas tipo "Fonte: https..." ou "fonte https..." que sobraram
        text = re.sub(r'(?m)^\s*Fonte\s*:?.*https.*$', '', text)
        text = re.sub(r'(?m)^\s*fonte\s*:?.*https.*$', '', text)
        # Remove "A fonte https..." inline residual
        text = re.sub(r'\b[Aa]\s+fonte\s+https?://\S+', '', text)
        # Remove linha Fontes: ... gerada para RAG (agora chips bonitos abaixo fazem isso, igual web)
        text = re.sub(r'(?m)^\s*Fontes\s*:\s*.*$', '', text)
        text = re.sub(r'(?m)^\s*###\s*Fontes.*$', '', text)
        # Limpa parênteses vazios ou com só espaços que sobraram: "texto ()"
        text = re.sub(r'\(\s*\)', '', text)
        # Remove linhas que viraram só "Fonte:" ou "Fontes:"
        text = re.sub(r'(?m)^\s*Fontes?\s*:?\s*$', '', text)
        # Colapsa espaços duplos e linhas vazias excessivas
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove espaços antes de pontuação
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        return text.strip()

    def _should_reason(self, question: str, analyze: bool = False) -> bool:
        """Habilita raciocínio (think) para perguntas analíticas, se configurado
        e o modelo suportar. Usa ReasoningEngine para decisão mais precisa."""
        client = self._choose_llm(analyze)
        if not client.supports_thinking():
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
        self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None, reasoning: Optional[bool] = None, analyze: bool = False,
    ) -> Generator[str, None, str]:
        client = self._choose_llm(analyze)
        full_answer: List[str] = []
        kwargs: dict = {}
        if analyze and client.supports_thinking():
            kwargs["think"] = True
        elif reasoning is not None:
            kwargs["think"] = reasoning
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            for token in client.ask_stream(prompt, **kwargs):
                full_answer.append(token)
                yield token
        except Exception as e:
            msg = str(e).lower()
            if analyze and client is not self.ollama_client and ("not found" in msg or "model" in msg and "not" in msg):
                if self.logger:
                    self.logger.warning(f"Analyst stream model {client.model} não encontrado, fallback para {self.ollama_client.model}")
                kwargs.pop("think", None)
                try:
                    for token in self.ollama_client.ask_stream(prompt, **kwargs):
                        full_answer.append(token)
                        yield token
                    return "".join(full_answer)
                except Exception as e2:
                    if self.logger:
                        self.logger.warning(f"Fallback stream falhou: {e2}")
                    raise e2
            if self.logger:
                self.logger.warning(f"Stream interrupted: {e}")
        return "".join(full_answer)

    def _build_response(
        self,
        answer: str,
        evidences: List[Evidence],
        start_time: float,
        provider: str = "rag",
    ) -> AgentResponse:
        elapsed = time.time() - start_time
        return AgentResponse(
            answer=answer,
            evidences=evidences,
            confidence=1.0 if evidences else 0.5,
            verdict="ok",
            metadata={
                "provider": provider,
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

    def _prepare_evidence(self, question: str, profile: str = "") -> List[Evidence]:
        """Pipeline comum de evidências: retrieve -> dedup -> rank -> filtro -> cálculo."""
        evidence = self._retrieve_rag(question, profile=profile)
        evidence = self.aggregator.collect(rag_evidence=evidence)
        evidence = self.aggregator.rank(evidence)
        evidence = self._apply_relevance_filter(question, evidence)
        # Parent-child query-time para Pro: expande com vizinhos do mesmo doc (sem reindex, late chunking)
        if profile == "pro" and evidence and getattr(self, "_rag_reranker", None):
            try:
                evidence = self._expand_parent_context(evidence, max_extra=6)
            except Exception:
                pass
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

    def _prepare_web_evidence(self, question: str) -> List[Evidence]:
        """Busca na web (modo web isolado) — retorna evidences com provider=web e url obrigatório."""
        if not self.web_search:
            if self.logger:
                self.logger.warning("Web search requested but provider not configured")
            return []
        try:
            from core.config import config as _cfg

            if not getattr(_cfg, "web_search_enabled", True):
                if self.logger:
                    self.logger.info("Web search disabled (WEB_SEARCH_ENABLED=false)")
                return []
        except Exception:
            pass
        try:
            evidences = self.web_search.search(question)
            if self.logger:
                self.logger.info(f"Web search: {len(evidences)} evidences for '{question[:60]}'")
            return evidences
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Web search failed: {e}")
            return []

    def _process(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
    ) -> AgentResponse:
        start = time.time()
        # provider reflete o modo real (auto/rag → rag, web → web) — auto faz fallback inteligente
        provider = "web" if mode == Mode.web else "rag"

        if self.logger:
            self.logger.info(f"Question: {question} [mode={mode}] profile={profile} analyze={analyze}")

        try:
            # Saudações não devem disparar RAG/web — resposta direta e leve
            if self._is_greeting(question):
                if self.logger:
                    self.logger.info(f"Greeting detected: {question!r} -> no retrieval")
                resp = self._greeting_response(start)
                self._record_request(question, mode, provider, resp, start, analyze, profile=profile)
                return resp

            # Cache semântico — hit <50ms (Sprint 1)
            if getattr(self, "semantic_cache", None):
                from rag.semantic_cache import _cache_key as _ck
                _key_dbg = _ck(question, str(mode), profile, analyze)
                if self.logger:
                    self.logger.info(f"Cache GET key={_key_dbg[:8]} q='{question[:30]}' mode={mode} profile={profile} analyze={analyze} size={len(self.semantic_cache._store)}")
                cached = self.semantic_cache.get(question, str(mode), profile, analyze)
                if cached:
                    ans, meta, srcs, conf = cached
                    # Reconstrói evidências mínimas a partir de sources cacheadas (se houver)
                    from rag.evidence import Evidence as _Ev
                    cached_evs = []
                    for s in srcs:
                        try:
                            cached_evs.append(_Ev(provider=s.get("provider","rag"), source=s.get("title",""), title=s.get("title",""), url=s.get("url",""), content="", metadata=s))
                        except Exception:
                            pass
                    resp = AgentResponse(answer=ans, evidences=cached_evs, confidence=conf, verdict=meta.get("verdict","ok"), metadata={**meta, "cached": True, "cache_hit": True, "profile": profile or meta.get("profile","flash")}, execution_time=time.time() - start)
                    # Restaura sources completas se cache tinha
                    try:
                        resp.metadata["evidence_count"] = len(srcs)
                    except Exception:
                        pass
                    if self.logger:
                        self.logger.info(f"Cache HIT para '{question[:60]}' profile={profile} mode={mode} — {time.time()-start:.3f}s key={_key_dbg[:8]}")
                    self._record_request(question, mode, provider, resp, start, analyze, profile=profile)
                    return resp
                elif self.logger:
                    self.logger.info(f"Cache MISS key={_key_dbg[:8]} q='{question[:30]}' mode={mode} profile={profile}")

            plan, hint, reasoning_needed = self._make_plan(question)
            self._last_rewritten = None
            if not style:
                if profile == "flash":
                    style = "concise"
                elif profile == "pro":
                    style = "analyst"
            # Auto-routing: tenta RAG primeiro, se vazio e web habilitado faz fallback para web
            if mode == Mode.auto:
                evidence = self._prepare_evidence(question, profile=profile)
                if not evidence and self.web_search:
                    try:
                        from core.config import config as _cfg_auto
                        if getattr(_cfg_auto, "web_search_enabled", True):
                            if self.logger:
                                self.logger.info(f"Auto-routing: RAG vazio para '{question[:60]}', fallback para web")
                            web_ev = self._prepare_web_evidence(question)
                            if web_ev:
                                evidence = web_ev
                                mode = Mode.web
                                provider = "web"
                    except Exception:
                        pass
            elif mode == Mode.web:
                evidence = self._prepare_web_evidence(question)
            else:
                evidence = self._prepare_evidence(question, profile=profile)

            if not evidence:
                if self.logger:
                    self.logger.info(f"No evidence found (mode={mode}) profile={profile}")
                web_hint = ""
                if mode == Mode.web:
                    web_hint = (
                        "MODO WEB ATIVO: Responda DIRETAMENTE à pergunta de forma precisa e factual, com base NAS EVIDÊNCIAS DA WEB "
                        "(título, URL e conteúdo). NÃO apenas comente as fontes — SINTETIZE: defina, compare, explique princípios, "
                        "implementação, vantagens/desvantagens e casos de uso quando a pergunta exigir. Não inclua links inline — as fontes serão exibidas como chips clicáveis abaixo. "
                        "Se a evidência for insuficiente, diga o que falta. Responda em português, direto ao ponto, como no modo RAG. "
                        + (hint + " " if hint else "")
                    )
                    prompt = self.prompt_builder.build(question, mode=mode, reasoning=reasoning_needed, reasoning_hint=web_hint.strip(), style=style, custom_instructions=custom_instructions)
                else:
                    prompt = self.prompt_builder.build(question, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint, style=style, custom_instructions=custom_instructions)
                answer = self._call_llm(
                    prompt,
                    reasoning=self._should_reason(question, analyze=analyze),
                    temperature=plan.temperature if plan else None,
                    max_tokens=plan.max_tokens if plan else None,
                    analyze=analyze,
                )
                if style == "concise":
                    import re as _re2
                    has_list2 = bool(_re2.search(r'^\s*\d+[\.\)]\s', answer, flags=_re2.MULTILINE))
                    if not has_list2:
                        _sents2 = _re2.split(r'(?<=[.!?])\s+', answer.strip())
                        if len(_sents2) > 12:
                            answer = ' '.join(_sents2[:12]).strip()
                resp = self._build_response(answer, [], start, provider=provider)
                resp.metadata["fallback"] = "no_documents"
                if plan:
                    resp.metadata["reasoning_intent"] = plan.intent
                    resp.metadata["reasoning_cot"] = reasoning_needed
                if style:
                    resp.metadata["style"] = style
                if custom_instructions:
                    resp.metadata["custom_instructions"] = True
                # Expõe rewriter mesmo sem evidências para debug
                if getattr(self, "_last_rewritten", None):
                    resp.metadata["rewritten"] = self._last_rewritten.to_dict()
                    resp.metadata["expanded_queries"] = self._last_rewritten.expanded_queries
                    resp.metadata["rewriter_intent"] = self._last_rewritten.intent
                if analyze:
                    resp = self._run_analyst(question, resp)
                # Cache semântico — guarda (se não for greeting/fallback vazio)
                if getattr(self, "semantic_cache", None):
                    try:
                        cache_mode = original_mode if "original_mode" in locals() else mode
                        self.semantic_cache.set(question, str(cache_mode), profile, analyze, resp.answer, resp.metadata, [s.to_dict() for s in resp.sources], resp.confidence)
                    except Exception:
                        pass
                self._record_request(question, mode, provider, resp, start, analyze, profile=profile)
                return resp

            web_hint = ""
            if mode == Mode.web:
                web_hint = (
                    "MODO WEB ATIVO: Responda DIRETAMENTE à pergunta de forma precisa e factual, com base NAS EVIDÊNCIAS DA WEB "
                    "(título, URL e conteúdo). NÃO apenas comente as fontes — SINTETIZE: defina, compare, explique princípios, "
                    "implementação, vantagens/desvantagens e casos de uso quando a pergunta exigir. Não inclua links inline — as fontes serão exibidas como chips clicáveis abaixo. "
                    "Se a evidência for insuficiente, diga o que falta. Responda em português, direto ao ponto, como no modo RAG. "
                    + (hint + " " if hint else "")
                )
            effective_hint = web_hint.strip() if mode == Mode.web else hint
            prompt = (
                self.prompt_builder.build_with_history(
                    question, evidence, history_context, mode=mode,
                    reasoning=reasoning_needed or analyze, reasoning_hint=effective_hint, style=style, custom_instructions=custom_instructions,
                )
                if history_context
                else self.prompt_builder.build(question, evidence, mode=mode, reasoning=reasoning_needed or analyze, reasoning_hint=effective_hint, style=style, custom_instructions=custom_instructions)
            )

            answer_clean = self._call_llm(
                prompt,
                reasoning=self._should_reason(question, analyze=analyze),
                temperature=plan.temperature if plan else None,
                max_tokens=plan.max_tokens if plan else None,
                analyze=analyze,
            )
            # Sanitiza: remove URLs inline que o LLM insiste em gerar (chips já exibem fontes)
            answer_clean = self._strip_inline_sources(answer_clean)
            # Enforce conciso humano Flash: até 12 frases ou 10 passos (1.5× mais inteligente)
            if style == "concise":
                import re as _re
                has_list = bool(_re.search(r'^\s*\d+[\.\)]\s', answer_clean, flags=_re.MULTILINE))
                if has_list:
                    lines = answer_clean.strip().split('\n')
                    if len([l for l in lines if _re.match(r'^\s*\d+[\.\)]\s', l)]) > 10:
                        pass
                else:
                    _sents = _re.split(r'(?<=[.!?])\s+', answer_clean.strip())
                    if len(_sents) > 12:
                        answer_clean = ' '.join(_sents[:12]).strip()
            result = self._build_response(answer_clean, evidence, start, provider=provider)
            # Guardrail de confiança — Sprint 1: marca baixa confiança para UI exibir aviso
            # Se evidência fraca ou pouca, não inventa: verdict low_confidence + guardrail flag
            try:
                max_score = max((getattr(e, "score", 0) or 0) for e in evidence) if evidence else 0
                if len(evidence) == 0 or max_score < 0.3 or result.confidence < 0.6:
                    # Só marca se não for saudação e não for fallback já tratado
                    if not result.metadata.get("greeting"):
                        result.metadata["guardrail"] = "low_confidence"
                        if result.verdict == "ok":
                            result.verdict = "low_confidence"
                        result.metadata["guardrail_detail"] = f"evidência fraca (max_score={max_score:.2f}, evidences={len(evidence)})"
                        # Adiciona grounding visual hint: páginas/fontes já estão em sources, frontend pode destacar
                        if evidence:
                            result.metadata["grounding_pages"] = list({getattr(e, "page_start", None) or e.metadata.get("page") for e in evidence if getattr(e, "page_start", None) or e.metadata.get("page")})[:3]
            except Exception:
                pass
            if plan:
                result.metadata["reasoning_intent"] = plan.intent
                result.metadata["reasoning_cot"] = reasoning_needed
                result.metadata["reasoning_top_k"] = plan.top_k
            if style:
                result.metadata["style"] = style
            if custom_instructions:
                result.metadata["custom_instructions"] = True
            if getattr(self, "_last_rewritten", None):
                result.metadata["rewritten"] = self._last_rewritten.to_dict()
                result.metadata["expanded_queries"] = self._last_rewritten.expanded_queries
                result.metadata["rewriter_intent"] = self._last_rewritten.intent
                result.metadata["rewriter_entities"] = self._last_rewritten.entities

            if self.logger:
                self.logger.info(
                    f"AgentResponse: evidence={len(evidence)}, "
                    f"time={result.execution_time:.2f}s, intent={plan.intent if plan else 'unknown'}, cot={reasoning_needed}, style={style or 'default'}"
                )

            if analyze:
                result = self._run_analyst(question, result)

            if getattr(self, "semantic_cache", None):
                try:
                    cache_mode = original_mode if "original_mode" in locals() else mode
                    # Guarda sob modo original e final (para hit em auto e web)
                    self.semantic_cache.set(question, str(cache_mode), profile, analyze, result.answer, result.metadata, [s.to_dict() for s in result.sources], result.confidence)
                    if str(cache_mode) != str(mode):
                        self.semantic_cache.set(question, str(mode), profile, analyze, result.answer, result.metadata, [s.to_dict() for s in result.sources], result.confidence)
                except Exception:
                    pass
            self._record_request(question, mode, provider, result, start, analyze, profile=profile)
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
        profile: str = "",
    ) -> None:
        try:
            # profile e cache_hit para observabilidade por perfil (Sprint 1)
            prof = profile or resp.metadata.get("profile") or getattr(self, "watson_profile", "") or "flash"
            # tenta pegar profile do cache/metadata
            if not prof or prof == "flash":
                # fallback para config global se vazio
                try:
                    from core.config import config as _cfg_prof
                    prof = getattr(_cfg_prof, "watson_profile", "flash") or "flash"
                    # se request tinha profile explícito, usa ele
                    if profile and profile.strip():
                        prof = profile.strip().lower()
                except Exception:
                    pass
            # alias plus -> flash
            if prof in ("plus", "core", "balanced"):
                prof = "flash"
            cache_hit = bool(resp.metadata.get("cached") or resp.metadata.get("cache_hit"))
            self.metrics.record_request(
                question=question, mode=str(mode), provider=provider,
                evidence_count=len(resp.evidences),
                execution_ms=resp.execution_time * 1000,
                analyze=analyze, success=True,
                profile=prof, cache_hit=cache_hit,
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Metrics request record failed: {e}")

    def ask(
        self,
        question: str,
        mode: Mode = Mode.auto,
        analyze: bool = False,
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
    ) -> AgentResponse:
        return self._process(question, mode=mode, analyze=analyze, style=style, custom_instructions=custom_instructions, profile=profile)

    def ask_with_context(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
    ) -> AgentResponse:
        return self._process(question, history_context, mode, analyze=analyze, style=style, custom_instructions=custom_instructions, profile=profile)

    def _stream_evidence(
        self, prompt: str, evidence: List[Evidence], provider: str = "rag", analyze: bool = False, style: str = ""
    ) -> Generator[str, None, AgentResponse]:
        start = time.time()
        full_answer: List[str] = []
        client = self._choose_llm(analyze)
        try:
            kwargs = {"think": True} if analyze and client.supports_thinking() else {}
            for token in client.ask_stream(prompt, **kwargs):
                full_answer.append(token)
                yield token
        except Exception as e:
            msg = str(e).lower()
            if analyze and client is not self.ollama_client and ("not found" in msg or "model" in msg and "not" in msg):
                if self.logger:
                    self.logger.warning(f"Stream evidence model {client.model} não encontrado, fallback para {self.ollama_client.model}")
                try:
                    for token in self.ollama_client.ask_stream(prompt):
                        full_answer.append(token)
                        yield token
                except Exception as e2:
                    if self.logger:
                        self.logger.warning(f"Fallback stream evidence falhou: {e2}")
                    raise e2
            elif self.logger:
                self.logger.warning(f"Stream interrupted: {e}")

        answer_clean = self._strip_inline_sources("".join(full_answer))
        if style == "concise":
            import re as _re3
            _sents3 = _re3.split(r'(?<=[.!?])\s+', answer_clean.strip())
            if len(_sents3) > 6:
                answer_clean = ' '.join(_sents3[:6]).strip()
        result = self._build_response(answer_clean, evidence, start, provider=provider)

        if self.logger:
            self.logger.info(f"Stream result: time={result.execution_time:.2f}s")

        return result

    def _stream_no_evidence(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        plan=None,
        style: str = "",
        custom_instructions: str = "",
        analyze: bool = False,
    ) -> Generator[str, None, AgentResponse]:
        start = time.time()
        if plan is None:
            plan = self._make_plan(question)[0]
        hint = plan.reasoning_hint if plan else ""
        reasoning_needed = bool(plan and plan.needs_cot)
        if mode == Mode.web and hint is not None:
            hint = (
                "MODO WEB ATIVO: Responda DIRETAMENTE à pergunta de forma precisa e factual, com base NAS EVIDÊNCIAS DA WEB "
                "(título, URL e conteúdo). NÃO apenas comente as fontes — SINTETIZE: defina, compare, explique princípios, "
                "implementação, vantagens/desvantagens e casos de uso quando a pergunta exigir. Não inclua links inline — as fontes serão exibidas como chips clicáveis abaixo. "
                "Se a evidência for insuficiente, diga o que falta. Responda em português, direto ao ponto, como no modo RAG. " + (hint or "")
            )
        prompt = (
            self.prompt_builder.build_with_history(
                question, None, history_context, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint, style=style, custom_instructions=custom_instructions
            )
            if history_context
            else self.prompt_builder.build(question, mode=mode, reasoning=reasoning_needed, reasoning_hint=hint, style=style, custom_instructions=custom_instructions)
        )
        full_answer = yield from self._call_llm_stream(
            prompt,
            temperature=plan.temperature if plan else None,
            max_tokens=plan.max_tokens if plan else None,
            reasoning=self._should_reason(question, analyze=analyze),
            analyze=analyze,
        )
        provider = "web" if mode == Mode.web else "rag"
        resp = self._build_response(full_answer, [], start, provider=provider)
        resp.metadata["fallback"] = "no_documents"
        if plan:
            resp.metadata["reasoning_intent"] = plan.intent
        if style:
            resp.metadata["style"] = style
        if custom_instructions:
            resp.metadata["custom_instructions"] = True
        if getattr(self, "_last_rewritten", None):
            resp.metadata["rewritten"] = self._last_rewritten.to_dict()
            resp.metadata["expanded_queries"] = self._last_rewritten.expanded_queries
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
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
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
                self._record_request(question, mode, "greeting", resp, start, analyze, profile=profile)
                return resp

            plan, hint, reasoning_needed = self._make_plan(question)
            self._last_rewritten = None
            if not style:
                if profile == "flash":
                    style = "concise"
                elif profile == "pro":
                    style = "analyst"
            # Auto-routing para stream também
            if mode == Mode.auto:
                evidence = self._prepare_evidence(question, profile=profile)
                if not evidence and self.web_search:
                    try:
                        from core.config import config as _cfg_auto
                        if getattr(_cfg_auto, "web_search_enabled", True):
                            web_ev = self._prepare_web_evidence(question)
                            if web_ev:
                                evidence = web_ev
                                mode = Mode.web
                    except Exception:
                        pass
            elif mode == Mode.web:
                evidence = self._prepare_web_evidence(question)
            else:
                evidence = self._prepare_evidence(question, profile=profile)

            if not evidence:
                if self.logger:
                    self.logger.info(f"No evidence found (stream, mode={mode}) profile={profile}")
                resp = yield from self._stream_no_evidence(question, history_context, mode, plan, style=style, custom_instructions=custom_instructions, analyze=analyze)
                provider = "web" if mode == Mode.web else "rag"
                if getattr(self, "_last_rewritten", None):
                    resp.metadata["rewritten"] = self._last_rewritten.to_dict()
                    resp.metadata["expanded_queries"] = self._last_rewritten.expanded_queries
                if analyze:
                    resp = self._run_analyst(question, resp)
                self._record_request(question, mode, provider, resp, start, analyze, profile=profile)
                return resp

            if mode == Mode.web:
                hint = (
                    "MODO WEB ATIVO: Responda DIRETAMENTE à pergunta de forma precisa e factual, com base NAS EVIDÊNCIAS DA WEB "
                    "(título, URL e conteúdo). NÃO apenas comente as fontes — SINTETIZE: defina, compare, explique princípios, "
                    "implementação, vantagens/desvantagens e casos de uso quando a pergunta exigir. Não inclua links inline — as fontes serão exibidas como chips clicáveis abaixo. "
                    "Se a evidência for insuficiente, diga o que falta. Responda em português, direto ao ponto, como no modo RAG. " + (hint or "")
                )
            prompt = (
                self.prompt_builder.build_with_history(
                    question, evidence, history_context, mode=mode,
                    reasoning=reasoning_needed or analyze, reasoning_hint=hint, style=style, custom_instructions=custom_instructions,
                )
                if history_context
                else self.prompt_builder.build(question, evidence, mode=mode, reasoning=reasoning_needed or analyze, reasoning_hint=hint, style=style, custom_instructions=custom_instructions)
            )
            provider = "web" if mode == Mode.web else "rag"
            result = yield from self._stream_evidence(prompt, evidence, provider=provider, analyze=analyze, style=style)
            if plan:
                result.metadata["reasoning_intent"] = plan.intent
                result.metadata["reasoning_cot"] = reasoning_needed or analyze
            if style:
                result.metadata["style"] = style
            if custom_instructions:
                result.metadata["custom_instructions"] = True
            if getattr(self, "_last_rewritten", None):
                result.metadata["rewritten"] = self._last_rewritten.to_dict()
                result.metadata["expanded_queries"] = self._last_rewritten.expanded_queries
                result.metadata["rewriter_intent"] = self._last_rewritten.intent
                result.metadata["rewriter_entities"] = self._last_rewritten.entities
            if analyze:
                result = self._run_analyst(question, result)
            self._record_request(question, mode, provider, result, start, analyze, profile=profile)
            return result
        except Exception as e:
            provider = "web" if mode == Mode.web else "rag"
            self.metrics.record_request(
                question=question, mode=str(mode), provider=provider,
                execution_ms=(time.time() - start) * 1000,
                analyze=analyze, success=False, error=str(e),
            )
            raise

    def ask_stream(
        self,
        question: str,
        mode: Mode = Mode.auto,
        analyze: bool = False,
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
    ) -> Generator[str, None, AgentResponse]:
        return self._ask_stream_inner(question, "", mode, analyze, style=style, custom_instructions=custom_instructions, profile=profile)

    def ask_stream_with_history(
        self,
        question: str,
        history_context: str = "",
        mode: Mode = Mode.auto,
        analyze: bool = False,
        style: str = "",
        custom_instructions: str = "",
        profile: str = "",
    ) -> Generator[str, None, AgentResponse]:
        return self._ask_stream_inner(question, history_context, mode, analyze, style=style, custom_instructions=custom_instructions, profile=profile)

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
        # Perfil Watson (igual API e DokViewerManager): flash rápido vs pro 2×
        try:
            from core.config import config as _cfg_prof
            current_profile = (_cfg_prof.watson_profile or "flash").lower()
        except Exception:
            current_profile = "flash"
        if current_profile not in ("flash", "pro"):
            current_profile = "flash"
        def _profile_info(p: str) -> str:
            return "Flash 6/800/1536" if p == "flash" else "Pro 12/1600/3072 2× (qwen3:8b think)"
        print(f"{ANSI_WHITE}{ANSI_BOLD}Perfil atual:{ANSI_RESET} {ANSI_YELLOW}{current_profile}{ANSI_RESET} ({_profile_info(current_profile)}) — troque com {ANSI_YELLOW}flash{ANSI_RESET}/{ANSI_YELLOW}pro{ANSI_RESET} ou {ANSI_YELLOW}perfil: flash{ANSI_RESET}")

        # Dicas padronizadas — cores legíveis (sem DIM apagado), exemplos de impressora/suprimento
        print(f"{ANSI_WHITE}{ANSI_BOLD}Como perguntar (tipo: pergunta):{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}fato:{ANSI_RESET}{ANSI_WHITE}      qual o erro E123 da impressora HP Modelo-X?{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}lista:{ANSI_RESET}{ANSI_WHITE}     quais são os toners compatíveis com Brother DCP-L2540?{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}conta:{ANSI_RESET}{ANSI_WHITE}     quantos % a mais em fevereiro vs janeiro?{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}comparar:{ANSI_RESET}{ANSI_WHITE}  compare Brother DCP-L2540 vs Impressora M404{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}imagem:{ANSI_RESET}{ANSI_WHITE}    o que tem nessa imagem de erro da impressora?{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}passos:{ANSI_RESET}{ANSI_WHITE}    como trocar o toner da Kyocera M2040 passo a passo?{ANSI_RESET}")
        print()
        print(f"{ANSI_WHITE}{ANSI_BOLD}Comandos (comando: valor) -> o que faz:{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}flash / pro{ANSI_RESET}{ANSI_WHITE}          -> troca perfil ({_profile_info('flash')} vs {_profile_info('pro')}){ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}perfil: flash/pro{ANSI_RESET}{ANSI_WHITE}    -> idem (ex: {ANSI_YELLOW}perfil: pro{ANSI_RESET}){ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}analisar: on{ANSI_RESET}{ANSI_WHITE}       -> liga a análise automática em toda pergunta{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}analisar: off{ANSI_RESET}{ANSI_WHITE}       -> desliga a análise automática{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}analisar: <pergunta>{ANSI_RESET}{ANSI_WHITE} -> análise só nessa pergunta{ANSI_RESET}")
        print(f"{ANSI_WHITE}      ex: {ANSI_YELLOW}analisar: por que a impressora está com falha de fusor?{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}aprofundar:{ANSI_RESET}{ANSI_WHITE}       -> detalha mais a última resposta (ex: {ANSI_YELLOW}aprofundar: detalhe o erro C7990{ANSI_RESET}){ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}esquecer:{ANSI_RESET}{ANSI_WHITE}        -> limpa a memória da conversa{ANSI_RESET}")
        print(f"{ANSI_WHITE}  • {ANSI_YELLOW}exit:{ANSI_RESET}{ANSI_WHITE}            -> sai do chat{ANSI_RESET}")
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

            # --- Troca de perfil Flash/Pro (igual API e DokViewerManager) ---
            if qlow in ("flash", "perfil: flash", "perfil flash", "profile: flash", "profile flash", "modo flash"):
                current_profile = "flash"
                try:
                    from core.config import config as _cfg_upd
                    _cfg_upd.watson_profile = "flash"
                    # Reaplica perfil sem reiniciar (mesma lógica de __post_init__)
                    _cfg_upd.__post_init__()
                except Exception:
                    pass
                print(f"{ANSI_GREEN}Perfil Flash ativado — {_profile_info('flash')} (rápido, TOP_K 6){ANSI_RESET}")
                continue
            if qlow in ("pro", "perfil: pro", "perfil pro", "profile: pro", "profile pro", "modo pro"):
                current_profile = "pro"
                try:
                    from core.config import config as _cfg_upd
                    _cfg_upd.watson_profile = "pro"
                    _cfg_upd.__post_init__()
                except Exception:
                    pass
                print(f"{ANSI_GREEN}Perfil Pro ativado — {_profile_info('pro')} (2× Flash, TOP_K 12){ANSI_RESET}")
                continue
            if qlow in ("perfil", "profile", "modo"):
                print(f"{ANSI_YELLOW}Perfil atual: {current_profile} ({_profile_info(current_profile)}). Use 'flash' ou 'pro'.{ANSI_RESET}")
                continue
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
                # Perfil por pergunta (igual API: CLI flash/pro muda config em tempo real)
                from core.config import config as _cfg_q
                profile_for_q = _cfg_q.watson_profile  # já atualizado por flash/pro
                # Não passa analyze para o stream aqui — análise roda depois com status próprio
                gen = self.ask_stream_with_history(
                    question, history_context, profile=profile_for_q
                ) if history_context else self.ask_stream(question, profile=profile_for_q)
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
