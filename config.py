import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:8b")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "2048"))
    )
    ollama_timeout: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", "300"))
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL", "intfloat/multilingual-e5-base"
        )
    )
    embedding_batch_size: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    )
    embedding_normalize: bool = field(
        default_factory=lambda: os.getenv("EMBEDDING_NORMALIZE", "true").lower() == "true"
    )
    embedding_cache_path: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_CACHE_PATH", "database/embedding_cache.sqlite3"
        )
    )
    chunk_size: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_SIZE", "1000"))
    )
    chunk_overlap: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "200"))
    )
    top_k: int = field(
        default_factory=lambda: int(os.getenv("TOP_K", "5"))
    )
    similarity_threshold: Optional[float] = field(
        default_factory=lambda: (
            float(v) if (v := os.getenv("SIMILARITY_THRESHOLD")) else None
        )
    )
    use_mmr: bool = field(
        default_factory=lambda: os.getenv("USE_MMR", "false").lower() == "true"
    )
    mmr_fetch_k: int = field(
        default_factory=lambda: int(os.getenv("MMR_FETCH_K", "20"))
    )
    mmr_lambda: float = field(
        default_factory=lambda: float(os.getenv("MMR_LAMBDA", "0.5"))
    )
    use_reranker: bool = field(
        default_factory=lambda: os.getenv("USE_RERANKER", "false").lower() == "true"
    )
    reranker_model: str = field(
        default_factory=lambda: os.getenv(
            "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
    )
    index_batch_size: int = field(
        default_factory=lambda: int(os.getenv("INDEX_BATCH_SIZE", "100"))
    )
    documents_dir: str = field(
        default_factory=lambda: os.getenv("DOCUMENTS_DIR", "documents")
    )
    google_drive_folder_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    )
    google_drive_dest_dir: str = field(
        default_factory=lambda: os.getenv("GOOGLE_DRIVE_DEST_DIR", "documents/drive")
    )
    google_drive_sync_timeout: int = field(
        default_factory=lambda: int(os.getenv("GOOGLE_DRIVE_SYNC_TIMEOUT", "60"))
    )
    vector_db_dir: str = field(
        default_factory=lambda: os.getenv("VECTOR_DB_DIR", "database/chroma")
    )
    embedding_device: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_DEVICE", "cpu")
    )
    ocr_lang: str = field(
        default_factory=lambda: os.getenv("OCR_LANG", "por+eng")
    )
    ocr_dpi: int = field(
        default_factory=lambda: int(os.getenv("OCR_DPI", "300"))
    )
    ocr_min_text_chars: int = field(
        default_factory=lambda: int(os.getenv("OCR_MIN_TEXT_CHARS", "20"))
    )
    tesseract_cmd: str = field(
        default_factory=lambda: os.getenv(
            "TESSERACT_CMD", "libs/tesseract"
        )
    )
    image_dir: str = field(
        default_factory=lambda: os.getenv("IMAGE_DIR", "database/images")
    )
    vision_model: str = field(
        default_factory=lambda: os.getenv("VISION_MODEL", "")
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    log_file: str = field(
        default_factory=lambda: os.getenv("LOG_FILE", "logs/ai_agent.log")
    )
    agent_name: str = field(
        default_factory=lambda: os.getenv("AGENT_NAME", "Watson")
    )
    metrics_db: str = field(
        default_factory=lambda: os.getenv("METRICS_DB", "database/metrics.db")
    )

    enable_reasoning: bool = field(
        default_factory=lambda: os.getenv("ENABLE_REASONING", "false").lower() == "true"
    )
    enable_analyst: bool = field(
        default_factory=lambda: os.getenv("ENABLE_ANALYST", "true").lower() == "true"
    )
    analyst_max_followups: int = field(
        default_factory=lambda: int(os.getenv("ANALYST_MAX_FOLLOWUPS", "3"))
    )

    api_host: str = field(
        default_factory=lambda: os.getenv("API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.getenv("API_PORT", "9000"))
    )
    api_auth_token: str = field(
        default_factory=lambda: os.getenv("API_AUTH_TOKEN", "").strip()
    )


config = Config()
