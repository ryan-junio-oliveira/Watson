import sys
from pathlib import Path

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from llm.ollama_client import OllamaClient
from rag.chatbot import ChatBot
from rag.planner import IntentClassifier
from rag.prompt import PromptBuilder
from rag.reranker import Reranker as RagReranker
from rag.retriever import Retriever
from rag.validator import ConfidenceScorer, FactValidator
from search.chunker import Chunker
from search.cleaner import ContentCleaner
from search.extractor import ContentExtractor
from search.fetcher import PageFetcher
from search.google_provider import GoogleProvider
from search.reranker import Reranker as SearchReranker
from utils.logger import setup_logger


def ensure_directories(cfg: Config) -> None:
    Path(cfg.vector_db_dir).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)


def main() -> None:
    cfg = config
    ensure_directories(cfg)

    logger = setup_logger(
        name="ai_agent",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    logger.info("Starting RAG Chat")

    try:
        embedding_generator = EmbeddingGenerator(
            model_name=cfg.embedding_model,
            device=cfg.embedding_device,
        )

        retriever = Retriever(
            embedding_generator=embedding_generator,
            chroma_persist_dir=cfg.vector_db_dir,
            top_k=cfg.top_k,
            similarity_threshold=cfg.similarity_threshold,
            use_mmr=cfg.use_mmr,
            mmr_fetch_k=cfg.mmr_fetch_k,
            mmr_lambda=cfg.mmr_lambda,
            logger=logger,
        )
        prompt_builder = PromptBuilder()
        ollama_client = OllamaClient(
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            request_timeout=cfg.ollama_timeout,
            logger=logger,
        )
        rag_reranker = (
            RagReranker(
                model_name=cfg.reranker_model,
                device=cfg.embedding_device,
                logger=logger,
            )
            if cfg.use_reranker
            else None
        )
        fetcher = PageFetcher(
            timeout=cfg.fetch_timeout,
            max_size=cfg.fetch_max_size,
            max_retries=cfg.fetch_retries,
            logger=logger,
        )
        extractor = ContentExtractor(logger=logger)
        cleaner = ContentCleaner(logger=logger)
        chunker = Chunker(
            chunk_size=cfg.web_chunk_size,
            chunk_overlap=cfg.web_chunk_overlap,
            logger=logger,
        )
        search_reranker = SearchReranker(
            model_name=cfg.reranker_model,
            device=cfg.embedding_device,
            logger=logger,
        )
        search_provider = GoogleProvider(logger=logger)
        intent_classifier = (
            IntentClassifier(ollama_client=ollama_client, logger=logger)
            if cfg.enable_planner
            else None
        )
        fact_validator = (
            FactValidator(ollama_client=ollama_client, logger=logger)
            if cfg.enable_validator
            else None
        )
        if hasattr(ConfidenceScorer, 'MIN_CONFIDENCE'):
            ConfidenceScorer.MIN_CONFIDENCE = cfg.min_confidence

        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=prompt_builder,
            ollama_client=ollama_client,
            reranker=rag_reranker,
            intent_classifier=intent_classifier,
            fact_validator=fact_validator,
            logger=logger,
            fetcher=fetcher,
            extractor=extractor,
            cleaner=cleaner,
            chunker=chunker,
            search_reranker=search_reranker,
            search_provider=search_provider,
            max_pages_per_query=cfg.fetch_max_pages,
            max_chunks_per_query=cfg.web_search_max_results * 6,
        )
        chatbot.chat_loop()

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
