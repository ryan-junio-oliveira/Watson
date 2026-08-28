import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, config
from core.factories import build_chatbot, ensure_directories, preload_models
from utils.logger import setup_logger


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
        chatbot = build_chatbot(cfg, logger)
        preload_models(chatbot, logger)
        logger.info("Models preloaded successfully")

        chatbot.chat_loop()

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
