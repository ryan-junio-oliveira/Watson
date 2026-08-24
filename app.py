import sys
from pathlib import Path

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from metrics.store import MetricsStore
from llm.ollama_client import OllamaClient
from rag.analyst import Analyst
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.reranker import Reranker as RagReranker
from rag.retriever import Retriever
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
        console=False,
    )

    logger.info("Starting Watson RAG")

    try:
        embedding_generator = EmbeddingGenerator(
            model_name=cfg.embedding_model,
            device=cfg.embedding_device,
            batch_size=cfg.embedding_batch_size,
            normalize=cfg.embedding_normalize,
            cache_path=cfg.embedding_cache_path,
            logger=logger,
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
        metrics = MetricsStore(db_path=cfg.metrics_db, logger=logger)
        ollama_client = OllamaClient(
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            request_timeout=cfg.ollama_timeout,
            logger=logger,
            metrics=metrics,
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

        analyst = (
            Analyst(
                retriever=retriever,
                ollama_client=ollama_client,
                logger=logger,
                max_followups=cfg.analyst_max_followups,
            )
            if cfg.enable_analyst
            else None
        )

        embedding_generator.get_embeddings()
        if rag_reranker is not None:
            rag_reranker._load_model()
        logger.info("Models preloaded successfully")

        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=prompt_builder,
            ollama_client=ollama_client,
            reranker=rag_reranker,
            logger=logger,
            enable_reasoning=cfg.enable_reasoning,
            analyst=analyst,
            agent_name=cfg.agent_name,
            metrics=metrics,
        )
        chatbot.chat_loop()

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
