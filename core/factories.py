"""Fábricas de objetos do Watson — centraliza construção para evitar duplicação.

Antes cada entrypoint (app.py, api.py, index.py, watch.py, reset_app.py) repetia
a montagem de embeddings, retriever, indexer, loader, chatbot etc. com os mesmos
parâmetros do Config. Aqui a construção é única; mudanças de wiring (ex.: novo
parâmetro) precisam ser feitas em um só lugar.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.config import Config
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
from ingestion.splitter import DocumentSplitter
from llm.ollama_client import OllamaClient
from metrics.store import MetricsStore
from rag.analyst import Analyst
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.reranker import Reranker as RagReranker
from rag.retriever import Retriever


def ensure_directories(cfg: Config) -> None:
    """Cria os diretórios de dados/log necessários."""
    Path(cfg.vector_db_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.documents_dir).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)


def build_metrics(cfg: Config, logger: logging.Logger = None) -> MetricsStore:
    return MetricsStore(db_path=cfg.metrics_db, logger=logger)


def build_embedding_generator(cfg: Config, logger: logging.Logger = None) -> EmbeddingGenerator:
    return EmbeddingGenerator(
        model_name=cfg.embedding_model,
        device=cfg.embedding_device,
        batch_size=cfg.embedding_batch_size,
        normalize=cfg.embedding_normalize,
        cache_path=cfg.embedding_cache_path,
        logger=logger,
    )


def build_retriever(
    cfg: Config,
    embedding_generator: EmbeddingGenerator,
    logger: logging.Logger = None,
) -> Retriever:
    return Retriever(
        embedding_generator=embedding_generator,
        chroma_persist_dir=cfg.vector_db_dir,
        top_k=cfg.top_k,
        similarity_threshold=cfg.similarity_threshold,
        use_mmr=cfg.use_mmr,
        mmr_fetch_k=cfg.mmr_fetch_k,
        mmr_lambda=cfg.mmr_lambda,
        logger=logger,
    )


def build_ollama(cfg: Config, metrics: MetricsStore, logger: logging.Logger = None) -> OllamaClient:
    return OllamaClient(
        model=cfg.ollama_model,
        base_url=cfg.ollama_base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        request_timeout=cfg.ollama_timeout,
        logger=logger,
        metrics=metrics,
    )


def build_reranker(cfg: Config, logger: logging.Logger = None):
    return (
        RagReranker(model_name=cfg.reranker_model, device=cfg.embedding_device, logger=logger)
        if cfg.use_reranker
        else None
    )


def build_analyst(
    cfg: Config,
    retriever: Retriever,
    ollama_client: OllamaClient,
    logger: logging.Logger = None,
):
    return (
        Analyst(
            retriever=retriever,
            ollama_client=ollama_client,
            logger=logger,
            max_followups=cfg.analyst_max_followups,
        )
        if cfg.enable_analyst
        else None
    )


def build_chatbot(cfg: Config, logger: logging.Logger = None) -> ChatBot:
    metrics = build_metrics(cfg, logger)
    emb_gen = build_embedding_generator(cfg, logger)
    retriever = build_retriever(cfg, emb_gen, logger)
    ollama_client = build_ollama(cfg, metrics, logger)
    reranker = build_reranker(cfg, logger)
    analyst = build_analyst(cfg, retriever, ollama_client, logger)
    return ChatBot(
        retriever=retriever,
        prompt_builder=PromptBuilder(),
        ollama_client=ollama_client,
        reranker=reranker,
        logger=logger,
        enable_reasoning=cfg.enable_reasoning,
        analyst=analyst,
        agent_name=cfg.agent_name,
        metrics=metrics,
        reasoning_top_k=cfg.reasoning_top_k,
        reasoning_temperature=cfg.reasoning_temperature,
        reasoning_max_tokens=cfg.reasoning_max_tokens,
        enable_query_expansion=cfg.enable_query_expansion,
        query_expansion_variants=cfg.query_expansion_variants,
        enable_reranker_reasoning=cfg.enable_reranker_reasoning,
    )


def build_loader(cfg: Config, logger: logging.Logger = None) -> DocumentLoader:
    return DocumentLoader(
        logger=logger,
        ocr_lang=cfg.ocr_lang,
        ocr_dpi=cfg.ocr_dpi,
        ocr_min_text_chars=cfg.ocr_min_text_chars,
        tesseract_cmd=cfg.tesseract_cmd,
        image_dir=cfg.image_dir,
        vision_model=cfg.vision_model,
        vision_base_url=cfg.ollama_base_url,
        ollama_base_url=cfg.ollama_base_url,
    )


def build_splitter(cfg: Config, logger: logging.Logger = None) -> DocumentSplitter:
    return DocumentSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        logger=logger,
    )


def build_indexer(cfg: Config, logger: logging.Logger = None):
    """Monta o pipeline de indexação.

    Retorna (embedding_generator, splitter, indexer) — os dois primeiros são
    úteis para preload/close, mas quem precisa só do indexer pode fazer
    `_, _, indexer = build_indexer(cfg, logger)`.
    """
    emb_gen = build_embedding_generator(cfg, logger)
    splitter = build_splitter(cfg, logger)
    indexer = DocumentIndexer(
        embedding_generator=emb_gen,
        splitter=splitter,
        chroma_persist_dir=cfg.vector_db_dir,
        batch_size=cfg.index_batch_size,
        logger=logger,
        metrics=build_metrics(cfg, logger),
    )
    return emb_gen, splitter, indexer


def preload_models(chatbot: ChatBot, logger: logging.Logger = None) -> None:
    """Pré-carrega modelos (embeddings + reranker) para evitar latência na 1ª pergunta."""
    try:
        emb_gen = chatbot.retriever.embedding_generator
        emb_gen.get_embeddings()
    except Exception as e:
        if logger:
            logger.warning(f"Embedding preload skipped: {e}")
    try:
        reranker = getattr(chatbot, "_rag_reranker", None)
        if reranker is not None:
            reranker._load_model()
    except Exception as e:
        if logger:
            logger.warning(f"Reranker preload skipped: {e}")