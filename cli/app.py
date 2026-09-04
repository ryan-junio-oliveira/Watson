import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, config
from core.factories import build_chatbot, ensure_directories, preload_models
from utils.logger import setup_logger


def main() -> None:
    import argparse, os
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["flash", "pro"], help="Perfil Watson: flash (6/800/1536) vs pro (12/1600/3072 2×)")
    args, _ = ap.parse_known_args()
    if args.profile:
        os.environ["WATSON_PROFILE"] = args.profile
        # Força reload do config para aplicar perfil antes de build_chatbot
        from importlib import reload
        import core.config as cfg_mod
        reload(cfg_mod)
        from core.config import config as cfg_reloaded
        cfg = cfg_reloaded
    else:
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
