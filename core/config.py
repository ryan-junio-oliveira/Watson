import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma3:4b")
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
    google_drive_workers: int = field(
        default_factory=lambda: max(1, int(os.getenv("GOOGLE_DRIVE_WORKERS", "8")))
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
        default_factory=lambda: int(os.getenv("OCR_DPI", "200"))
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
    dedup_cross_doc: bool = field(
        default_factory=lambda: os.getenv("DEDUP_CROSS_DOC", "true").lower() == "true"
    )
    dedup_persist_path: str = field(
        default_factory=lambda: os.getenv("DEDUP_PERSIST_PATH", "database/dedup.json")
    )
    quality_min_chars: int = field(
        default_factory=lambda: int(os.getenv("QUALITY_MIN_CHARS", "20"))
    )
    quality_min_chars_table: int = field(
        default_factory=lambda: int(os.getenv("QUALITY_MIN_CHARS_TABLE", "10"))
    )
    quality_min_chars_image: int = field(
        default_factory=lambda: int(os.getenv("QUALITY_MIN_CHARS_IMAGE", "30"))
    )
    quality_table_min_pipes: int = field(
        default_factory=lambda: int(os.getenv("QUALITY_TABLE_MIN_PIPES", "4"))
    )
    quality_ocr_threshold: float = field(
        default_factory=lambda: float(os.getenv("QUALITY_OCR_THRESHOLD", "0.6"))
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
    # Reasoning avançado
    reasoning_top_k: int = field(
        default_factory=lambda: int(os.getenv("REASONING_TOP_K", "12"))
    )
    reasoning_temperature: float = field(
        default_factory=lambda: float(os.getenv("REASONING_TEMPERATURE", "0.2"))
    )
    reasoning_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("REASONING_MAX_TOKENS", "3072"))
    )
    enable_query_expansion: bool = field(
        default_factory=lambda: os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
    )
    query_expansion_variants: int = field(
        default_factory=lambda: int(os.getenv("QUERY_EXPANSION_VARIANTS", "3"))
    )
    enable_reranker_reasoning: bool = field(
        default_factory=lambda: os.getenv("ENABLE_RERANKER_REASONING", "true").lower() == "true"
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
    api_rate_limit: int = field(
        default_factory=lambda: int(os.getenv("API_RATE_LIMIT", "30"))
    )
    api_rate_window: int = field(
        default_factory=lambda: int(os.getenv("API_RATE_WINDOW", "60"))
    )
    api_rate_enabled: bool = field(
        default_factory=lambda: os.getenv("API_RATE_ENABLED", "true").lower() == "true"
    )

    web_search_enabled: bool = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
    )
    web_search_provider: str = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo")
    )
    web_search_api_key: str = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_API_KEY", "").strip()
    )
    web_search_max_results: int = field(
        default_factory=lambda: int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    )
    web_search_timeout: int = field(
        default_factory=lambda: int(os.getenv("WEB_SEARCH_TIMEOUT", "15"))
    )
    # Tavily (quando provider=tavily)
    tavily_search_depth: str = field(
        default_factory=lambda: os.getenv("TAVILY_SEARCH_DEPTH", "basic")
    )
    web_search_trusted_domains: str = field(
        default_factory=lambda: os.getenv(
            "WEB_SEARCH_TRUSTED_DOMAINS",
            "g1.globo.com,uol.com.br,folha.uol.com.br,estadao.com.br,terra.com.br,veja.abril.com.br,cnnbrasil.com,cnn.com,bbc.com,band.uol.com.br,jovempan.com.br,sbt.com.br,record.r7.com,correiobraziliense.com.br,metropoles.com,gazetadopovo.com.br,exame.com,infomoney.com.br",
        )
    )


config = Config()
