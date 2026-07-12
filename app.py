import sys
from pathlib import Path

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from llm.ollama_client import OllamaClient
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
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
    )

    logger.info("Starting RAG Chat")

    try:
        embedding_generator = EmbeddingGenerator(
            model_name=cfg.embedding_model
        )

        retriever = Retriever(
            embedding_generator=embedding_generator,
            chroma_persist_dir=cfg.vector_db_dir,
            top_k=cfg.top_k,
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

        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=prompt_builder,
            ollama_client=ollama_client,
            logger=logger,
        )
        chatbot.chat_loop()

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
