import sys
from pathlib import Path

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from llm.ollama_client import OllamaClient
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.reranker import Reranker as RagReranker
from rag.retriever import Retriever
from tools.sql_tool import SqlQueryTool
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

        sql_tool = (
            SqlQueryTool(
                connection_string=cfg.db_connection_string,
                tables=cfg.db_tables,
                max_rows=cfg.db_max_rows_per_query,
                logger=logger,
            )
            if cfg.db_connection_string
            else None
        )

        embedding_generator.get_embeddings()
        if rag_reranker is not None:
            rag_reranker._load_model()
        logger.info("Models preloaded successfully")

        stt = None
        tts = None
        if cfg.voice_enabled:
            try:
                from voice.stt import SpeechToText
                from voice.tts import TextToSpeech

                stt = SpeechToText(
                    model_name=cfg.voice_stt_model,
                    language=cfg.voice_language,
                    device=cfg.voice_stt_device,
                    logger=logger,
                )
                tts = TextToSpeech(
                    voice=cfg.voice_name,
                    rate=cfg.voice_rate,
                    volume=cfg.voice_volume,
                    output_dir=cfg.voice_output_dir,
                    logger=logger,
                )
                logger.info("Voice mode enabled (STT + TTS)")
            except Exception as e:
                logger.warning(f"Voice modules unavailable, falling back to text: {e}")

        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=prompt_builder,
            ollama_client=ollama_client,
            reranker=rag_reranker,
            sql_tool=sql_tool,
            logger=logger,
            stt=stt,
            tts=tts,
        )
        chatbot.chat_loop(use_voice=cfg.voice_enabled)

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
