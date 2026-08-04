import json
import os
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import quote_plus

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
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
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
    vector_db_dir: str = field(
        default_factory=lambda: os.getenv("VECTOR_DB_DIR", "database/chroma")
    )
    embedding_device: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_DEVICE", "cpu")
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    log_file: str = field(
        default_factory=lambda: os.getenv("LOG_FILE", "logs/ai_agent.log")
    )

    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", ""))
    db_port: str = field(default_factory=lambda: os.getenv("DB_PORT", "3306"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", ""))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", ""))
    db_connection_string: Optional[str] = field(default=None)
    db_tables: Optional[List[str]] = field(default=None)

    enable_web_search: bool = field(
        default_factory=lambda: os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"
    )
    web_search_max_results: int = field(
        default_factory=lambda: int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    )
    search_provider: str = field(
        default_factory=lambda: os.getenv("SEARCH_PROVIDER", "google")
    )
    fetch_timeout: int = field(
        default_factory=lambda: int(os.getenv("FETCH_TIMEOUT", "10"))
    )
    fetch_max_size: int = field(
        default_factory=lambda: int(os.getenv("FETCH_MAX_SIZE", "1048576"))
    )
    fetch_max_pages: int = field(
        default_factory=lambda: int(os.getenv("FETCH_MAX_PAGES", "3"))
    )
    fetch_retries: int = field(
        default_factory=lambda: int(os.getenv("FETCH_RETRIES", "1"))
    )
    web_chunk_size: int = field(
        default_factory=lambda: int(os.getenv("WEB_CHUNK_SIZE", "1000"))
    )
    web_chunk_overlap: int = field(
        default_factory=lambda: int(os.getenv("WEB_CHUNK_OVERLAP", "200"))
    )
    enable_planner: bool = field(
        default_factory=lambda: os.getenv("ENABLE_PLANNER", "true").lower() == "true"
    )

    api_host: str = field(
        default_factory=lambda: os.getenv("API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.getenv("API_PORT", "9000"))
    )

    def __post_init__(self):
        raw = os.getenv("DB_CONNECTION_STRING")
        if raw:
            self.db_connection_string = raw
        elif self.db_user and self.db_host and self.db_name:
            encoded_password = quote_plus(self.db_password)
            self.db_connection_string = (
                f"mysql+pymysql://{self.db_user}:{encoded_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )

        tables_env = os.getenv("DB_TABLES")
        if tables_env:
            try:
                self.db_tables = json.loads(tables_env)
            except json.JSONDecodeError:
                self.db_tables = [t.strip() for t in tables_env.split(",") if t.strip()]


config = Config()
