import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
        default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", "120"))
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

    db_connection_string: Optional[str] = field(
        default_factory=lambda: os.getenv("DB_CONNECTION_STRING")
    )
    db_tables: Optional[List[str]] = field(default=None)

    api_host: str = field(
        default_factory=lambda: os.getenv("API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.getenv("API_PORT", "8000"))
    )

    def __post_init__(self):
        tables_env = os.getenv("DB_TABLES")
        if tables_env:
            try:
                self.db_tables = json.loads(tables_env)
            except json.JSONDecodeError:
                self.db_tables = [t.strip() for t in tables_env.split(",") if t.strip()]


config = Config()
