import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str = "ai_agent",
    log_level: str = "INFO",
    log_file: str = "logs/ai_agent.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Rotating file handler: 10 MB per file, keep 5 backups
    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
        logging.Formatter("%(levelname)-8s | %(message)s")
    )
    logger.addHandler(console_handler)

    return logger