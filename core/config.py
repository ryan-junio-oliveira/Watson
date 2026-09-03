import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _get_float(key: str, default: float) -> float:
    v = os.getenv(key)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _get_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() == "true"


@dataclass
class Config:
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma3:4b")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    temperature: float = field(
        default_factory=lambda: _get_float("TEMPERATURE", 0.1)
    )
    max_tokens: int = field(
        default_factory=lambda: _get_int("MAX_TOKENS", 2048)
    )
    ollama_timeout: int = field(
        default_factory=lambda: _get_int("OLLAMA_TIMEOUT", 300)
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL", "intfloat/multilingual-e5-base"
        )
    )
    embedding_batch_size: int = field(
        default_factory=lambda: _get_int("EMBEDDING_BATCH_SIZE", 32)
    )
    embedding_normalize: bool = field(
        default_factory=lambda: _get_bool("EMBEDDING_NORMALIZE", True)
    )
    embedding_cache_path: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_CACHE_PATH", "database/embedding_cache.sqlite3"
        )
    )
    chunk_size: int = field(
        default_factory=lambda: _get_int("CHUNK_SIZE", 1000)
    )
    chunk_overlap: int = field(
        default_factory=lambda: _get_int("CHUNK_OVERLAP", 200)
    )
    top_k: int = field(
        default_factory=lambda: _get_int("TOP_K", 5)
    )
    similarity_threshold: Optional[float] = field(
        default_factory=lambda: (
            float(v) if (v := os.getenv("SIMILARITY_THRESHOLD")) and str(v).strip() else None
        )
    )
    use_mmr: bool = field(
        default_factory=lambda: _get_bool("USE_MMR", False)
    )
    mmr_fetch_k: int = field(
        default_factory=lambda: _get_int("MMR_FETCH_K", 20)
    )
    mmr_lambda: float = field(
        default_factory=lambda: _get_float("MMR_LAMBDA", 0.5)
    )
    use_reranker: bool = field(
        default_factory=lambda: _get_bool("USE_RERANKER", False)
    )
    reranker_model: str = field(
        default_factory=lambda: os.getenv(
            "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
    )
    index_batch_size: int = field(
        default_factory=lambda: _get_int("INDEX_BATCH_SIZE", 100)
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
        default_factory=lambda: _get_int("GOOGLE_DRIVE_SYNC_TIMEOUT", 60)
    )
    google_drive_workers: int = field(
        default_factory=lambda: max(1, _get_int("GOOGLE_DRIVE_WORKERS", 8))
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
        default_factory=lambda: _get_int("OCR_DPI", 200)
    )
    ocr_min_text_chars: int = field(
        default_factory=lambda: _get_int("OCR_MIN_TEXT_CHARS", 20)
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
        default_factory=lambda: _get_bool("DEDUP_CROSS_DOC", True)
    )
    dedup_persist_path: str = field(
        default_factory=lambda: os.getenv("DEDUP_PERSIST_PATH", "database/dedup.json")
    )
    quality_min_chars: int = field(
        default_factory=lambda: _get_int("QUALITY_MIN_CHARS", 20)
    )
    quality_min_chars_table: int = field(
        default_factory=lambda: _get_int("QUALITY_MIN_CHARS_TABLE", 10)
    )
    quality_min_chars_image: int = field(
        default_factory=lambda: _get_int("QUALITY_MIN_CHARS_IMAGE", 30)
    )
    quality_table_min_pipes: int = field(
        default_factory=lambda: _get_int("QUALITY_TABLE_MIN_PIPES", 4)
    )
    quality_ocr_threshold: float = field(
        default_factory=lambda: _get_float("QUALITY_OCR_THRESHOLD", 0.6)
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
        default_factory=lambda: _get_bool("ENABLE_REASONING", False)
    )
    enable_analyst: bool = field(
        default_factory=lambda: _get_bool("ENABLE_ANALYST", True)
    )
    analyst_max_followups: int = field(
        default_factory=lambda: _get_int("ANALYST_MAX_FOLLOWUPS", 0)
    )
    # Modelo inteligente para modo analisar — pensa sobre evidências
    analyst_model: str = field(
        default_factory=lambda: os.getenv("ANALYST_MODEL", "").strip()  # vazio = usa OLLAMA_MODEL
    )
    analyst_temperature: float = field(
        default_factory=lambda: _get_float("ANALYST_TEMPERATURE", 0.2)
    )
    analyst_max_tokens: int = field(
        default_factory=lambda: _get_int("ANALYST_MAX_TOKENS", 4096)
    )
    analyst_think: bool = field(
        default_factory=lambda: _get_bool("ANALYST_THINK", True)
    )
    # Reasoning avançado
    reasoning_top_k: int = field(
        default_factory=lambda: _get_int("REASONING_TOP_K", 12)
    )
    reasoning_temperature: float = field(
        default_factory=lambda: _get_float("REASONING_TEMPERATURE", 0.2)
    )
    reasoning_max_tokens: int = field(
        default_factory=lambda: _get_int("REASONING_MAX_TOKENS", 3072)
    )
    enable_query_expansion: bool = field(
        default_factory=lambda: _get_bool("ENABLE_QUERY_EXPANSION", True)
    )
    query_expansion_variants: int = field(
        default_factory=lambda: _get_int("QUERY_EXPANSION_VARIANTS", 3)
    )
    enable_reranker_reasoning: bool = field(
        default_factory=lambda: _get_bool("ENABLE_RERANKER_REASONING", True)
    )
    # Query Understanding Layer — LLM intermediário que enriquece consulta pobre
    enable_query_rewriter: bool = field(
        default_factory=lambda: _get_bool("ENABLE_QUERY_REWRITER", True)
    )
    query_rewriter_model: str = field(
        default_factory=lambda: os.getenv("QUERY_REWRITER_MODEL", "").strip()  # vazio = usa OLLAMA_MODEL
    )
    query_rewriter_max_expanded: int = field(
        default_factory=lambda: _get_int("QUERY_REWRITER_MAX_EXPANDED", 5)
    )

    api_host: str = field(
        default_factory=lambda: os.getenv("API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: _get_int("API_PORT", 9000)
    )
    api_auth_token: str = field(
        default_factory=lambda: os.getenv("API_AUTH_TOKEN", "").strip()
    )
    api_rate_limit: int = field(
        default_factory=lambda: _get_int("API_RATE_LIMIT", 30)
    )
    api_rate_window: int = field(
        default_factory=lambda: _get_int("API_RATE_WINDOW", 60)
    )
    api_rate_enabled: bool = field(
        default_factory=lambda: _get_bool("API_RATE_ENABLED", True)
    )

    web_search_enabled: bool = field(
        default_factory=lambda: _get_bool("WEB_SEARCH_ENABLED", True)
    )
    web_search_provider: str = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo")
    )
    web_search_api_key: str = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_API_KEY", "").strip()
    )
    # Google Custom Search
    google_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "").strip()
    )
    google_cx: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CX", "").strip()
    )
    serper_api_key: str = field(
        default_factory=lambda: os.getenv("SERPER_API_KEY", "").strip()
    )
    searxng_url: str = field(
        default_factory=lambda: os.getenv("SEARXNG_URL", "http://localhost:8080").strip()
    )
    web_search_max_results: int = field(
        default_factory=lambda: _get_int("WEB_SEARCH_MAX_RESULTS", 5)
    )
    web_search_timeout: int = field(
        default_factory=lambda: _get_int("WEB_SEARCH_TIMEOUT", 15)
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

    watson_profile: str = field(
        default_factory=lambda: (os.getenv("WATSON_PROFILE", "flash") or "flash").strip().lower()
    )

    def __post_init__(self):
        # Aplica presets de perfil — Flash (rápido) e Pro (analista profundo, pensa)
        # Flash é o default rápido; Pro liga tudo + qwen para máxima qualidade (plus removido por ser indistinguível)
        profiles = {
            "flash": {
                "top_k": 5,
                "chunk_size": 800,
                "chunk_overlap": 150,
                "enable_query_rewriter": False,
                "query_rewriter_max_expanded": 3,
                "use_reranker": False,
                "use_mmr": False,
                "enable_reasoning": False,
                "enable_analyst": False,
                "enable_query_expansion": False,
                "temperature": 0.1,
                "max_tokens": 2048,
                "reasoning_top_k": 8,
                "reasoning_max_tokens": 2048,
                "analyst_max_tokens": 2048,
                "index_batch_size": 100,
            },
            "pro": {
                "top_k": 12,
                "chunk_size": 1200,
                "chunk_overlap": 250,
                "enable_query_rewriter": True,
                "query_rewriter_max_expanded": 5,
                "use_reranker": True,
                "use_mmr": True,
                "enable_reasoning": True,
                "enable_analyst": True,
                "enable_query_expansion": True,
                "temperature": 0.2,
                "max_tokens": 4096,
                "reasoning_top_k": 12,
                "reasoning_temperature": 0.2,
                "reasoning_max_tokens": 4096,
                "analyst_max_tokens": 4096,
                "analyst_think": True,
                "index_batch_size": 50,
            },
        }
        # Compat: plus/balanced/core → flash (fallback)
        _alias = {"plus": "flash", "balanced": "flash", "core": "flash"}
        p = (self.watson_profile or "flash").strip().lower()
        p = _alias.get(p, p)
        if p == "custom":
            return
        if p not in profiles:
            p = "flash"
            self.watson_profile = p
        # Se perfil Pro e sem modelo analista definido, usa qwen3:8b (fallback para gemma se não baixado)
        if p == "pro" and not (os.getenv("ANALYST_MODEL") or "").strip():
            # Não sobrescreve se já tem OLLAMA_MODEL custom, mas sugere qwen para Pro
            if not os.getenv("OLLAMA_MODEL"):
                self.ollama_model = "qwen3:8b"
            self.analyst_model = self.analyst_model or "qwen3:8b"
        # Aplica overrides do perfil (flash/plus/pro) — sempre sobrescreve, a menos que WATSON_PROFILE=custom
        # Isso garante que selecionar Plus no prompt ou no .env realmente muda TOP_K etc, mesmo se .env tinha valor antigo
        overrides = profiles[p]
        for k, v in overrides.items():
            setattr(self, k, v)


config = Config()
