import asyncio
import logging
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, config as app_config
from core.factories import build_chatbot, build_indexer, preload_models
from ingestion.drive_sync import (
    GoogleDriveSync,
    SelectedFolder as _SelectedFolder,
)
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
from ingestion.splitter import DocumentSplitter
from llm.ollama_client import OllamaClient
from presentation.formatter import ApiFormatter
from rag.chatbot import ChatBot
from rag.response import Mode
from rag.retriever import Retriever
from utils.logger import setup_logger


class ChatRequest(BaseModel):
    question: str = Field(
        ..., description="Pergunta do usuário", examples=["Como corrigir o erro E123 na impressora E52645?"]
    )
    history: Optional[List[dict]] = Field(
        None, description="Histórico da conversa para contexto",
        examples=[[{"role": "user", "content": "Olá"}, {"role": "assistant", "content": "Olá! Como posso ajudar?"}]]
    )
    mode: Mode = Field(
        Mode.auto,
        description="Modo de consulta. `auto` e `rag` respondem com base nos documentos indexados (RAG). `web` busca na internet com fontes citadas (título + URL). "
                    "Modos: auto | rag | web.",
        examples=["auto", "rag", "web"],
    )
    analyze: bool = Field(
        False,
        description="Se true, roda a análise proativa (reflexão sobre a própria "
                    "resposta, conclusões e perguntas de acompanhamento) e busca "
                    "mais informação no acervo. Respostas chegam em "
                    "`follow_up`, `conclusions` e `additional_info`.",
        examples=[True],
    )


class SourceItem(BaseModel):
    title: str = Field(..., description="Título da fonte", examples=["HP LASER JET E52645.pdf"])
    url: str = Field("", description="URL da fonte (vazio para documentos internos)")
    provider: Optional[str] = Field(None, description="Provedor da fonte", examples=["rag"])
    page: Optional[int] = Field(None, description="Número da página onde o trecho foi encontrado", examples=[142])
    section: Optional[str] = Field(None, description="Seção do documento (headings)", examples=["Troubleshooting"])
    manufacturer: Optional[str] = Field(None, description="Fabricante inferido do documento", examples=["HP"])
    model: Optional[str] = Field(None, description="Modelo do equipamento", examples=["E52645"])
    error_codes: Optional[List[str]] = Field(None, description="Códigos de erro detectados no trecho", examples=[["E123"]])


class ChatMetadata(BaseModel):
    provider: Optional[str] = Field(None, description="Provedor da resposta (rag)", examples=["rag"])
    evidence_count: int = Field(0, description="Quantidade de evidências utilizadas")
    execution_time_ms: int = Field(0, description="Tempo de execução em milissegundos")
    verdict: str = Field("ok", description="Status da resposta", examples=["ok"])
    issues: Optional[List[str]] = Field(None, description="Problemas encontrados internamente")


class ChatSuccessResponse(BaseModel):
    success: bool = Field(True, description="Indica se a requisição foi bem-sucedida")
    answer: str = Field(..., description="Resposta gerada pelo Watson", examples=["Existem 5 servidores cadastrados."])
    confidence: float = Field(0.0, description="Nível de confiança na resposta (0.0 a 1.0)")
    sources: List[SourceItem] = Field(default_factory=list, description="Documentos utilizados como fonte")
    metadata: ChatMetadata = Field(default_factory=ChatMetadata, description="Metadados da execução")
    follow_up: Optional[List[str]] = Field(
        None, description="Perguntas de acompanhamento (análise proativa, `analyze=true`)",
        examples=[["Quer saber a previsão de manutenção?"]],
    )
    conclusions: Optional[List[str]] = Field(
        None, description="Conclusões da análise proativa sobre a própria resposta",
        examples=[["O volume está acima do recomendado pelo manual."]],
    )
    additional_info: Optional[List[str]] = Field(
        None, description="Informação adicional buscada no acervo indexado",
        examples=[["O manual também cita a troca do kit de fusão nesse volume."]],
    )


class ChatErrorDetail(BaseModel):
    code: str = Field(..., description="Código do erro", examples=["INTERNAL_ERROR"])
    message: str = Field(..., description="Mensagem de erro", examples=["O serviço não respondeu"])


class ChatErrorResponse(BaseModel):
    success: bool = False
    error: ChatErrorDetail = Field(..., description="Detalhes do erro")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Mensagem de erro")


class IndexResponse(BaseModel):
    status: str = Field(..., description="Status da operação", examples=["ok"])
    documents_indexed: int = Field(0, description="Quantidade de documentos indexados")
    total_chunks: int = Field(0, description="Total de chunks processados")


class ClearResponse(BaseModel):
    status: str = Field(..., description="Status da operação", examples=["ok"])
    documents_removed: int = Field(0, description="Quantidade de arquivos de documento removidos")
    vectorstore_files_removed: int = Field(0, description="Quantidade de arquivos do banco vetorial removidos")


class DocUploadResponse(BaseModel):
    status: str = Field(..., description="Status do upload", examples=["ok"])
    filename: str = Field(..., description="Nome do arquivo enviado", examples=["manual.pdf"])
    size: int = Field(..., description="Tamanho do arquivo em bytes")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Status geral da API", examples=["ok"])
    documents_dir: str = Field(..., description="Diretório de documentos")
    chroma_dir: str = Field(..., description="Diretório do banco vetorial ChromaDB")
    ollama_model: str = Field(..., description="Modelo Ollama em uso")


class ReadyResponse(BaseModel):
    status: str = Field(..., description="ok | degraded | not_ready", examples=["ok"])
    checks: Dict[str, str] = Field(..., description="Resultado por subsistema")
    documents: int = Field(..., description="Documentos no manifest")
    chunks: int = Field(..., description="Chunks indexados")
    stale: int = Field(..., description="Documentos stale (no manifest mas não no disco)")


class DriveItem(BaseModel):
    id: str = Field(..., description="ID da pasta ou arquivo no Google Drive")
    name: str = Field(..., description="Nome do item")
    type: str = Field(..., description="`folder` ou `file`")
    modified: Optional[str] = Field(None, description="Data de última modificação")


class DriveFolderRequest(BaseModel):
    folder_id: str = Field(..., description="ID da pasta no Google Drive")


class SelectedFolderRequest(BaseModel):
    folder_id: str = Field(..., description="ID da pasta selecionada")
    path: str = Field("", description="Caminho relativo preservado (ex.: MANUAIS/HP)")


class DriveSelectionResponse(BaseModel):
    folders: List[SelectedFolderRequest] = Field(
        default_factory=list, description="Pastas selecionadas para indexação"
    )
    selected: int = Field(0, description="Quantidade de pastas selecionadas")


class DriveSelectionSaveRequest(BaseModel):
    folders: List[SelectedFolderRequest] = Field(
        ..., description="Nova lista de pastas selecionadas"
    )


class DriveSyncResponse(BaseModel):
    status: str = Field(..., description="Status do sync", examples=["ok"])
    files_remote: int = Field(0, description="Arquivos encontrados no Drive")
    folders: int = Field(0, description="Pastas percorridas")
    downloaded: int = Field(0, description="Arquivos baixados")
    skipped: int = Field(0, description="Arquivos ignorados (não suportados ou já atuais)")
    failed: int = Field(0, description="Falhas")
    removed: int = Field(0, description="Arquivos removidos localmente")
    bytes_downloaded: int = Field(0, description="Bytes baixados")
    errors: List[str] = Field(default_factory=list, description="Erros ocorridos")


class DriveClearResponse(BaseModel):
    status: str = Field(..., description="Status da operação", examples=["ok"])
    removed: int = Field(0, description="Quantidade de arquivos removidos")


class ModelListResponse(BaseModel):
    models: List[str] = Field(..., description="Lista de modelos disponíveis no Ollama")


# ------------------------------------------------------------------ #
# Métricas — response models (Swagger tipado)
# ------------------------------------------------------------------ #


class MetricsSummaryResponse(BaseModel):
    llm_calls: int = Field(0, description="Total de chamadas LLM no período")
    llm_success: int = Field(0, description="Chamadas LLM com sucesso")
    llm_errors: int = Field(0, description="Chamadas LLM com erro")
    total_prompt_tokens: int = Field(0, description="Soma de tokens de entrada")
    total_completion_tokens: int = Field(0, description="Soma de tokens de saída")
    total_tokens: int = Field(0, description="Soma total de tokens")
    avg_eval_duration_ms: Optional[float] = Field(None, description="Média de eval_duration_ms (ms)")
    requests: int = Field(0, description="Total de requisições de chat no período")
    request_success: int = Field(0, description="Requisições com sucesso")
    request_errors: int = Field(0, description="Requisições com erro")
    avg_execution_ms: Optional[float] = Field(None, description="Média de execution_ms (ms)")
    documents_indexed: int = Field(0, description="Documentos no manifest (último snapshot)")
    chunks_indexed: int = Field(0, description="Chunks no manifest (último snapshot)")


class TokenBucket(BaseModel):
    ts: float = Field(..., description="Timestamp do bucket (início da hora, epoch seconds)")
    input_tokens: int = Field(0, description="Tokens de entrada no bucket")
    output_tokens: int = Field(0, description="Tokens de saída no bucket")
    calls: int = Field(0, description="Quantidade de chamadas no bucket")


class TokenSeriesResponse(BaseModel):
    hours: float = Field(..., description="Janela solicitada em horas", examples=[24])
    series: List[TokenBucket] = Field(default_factory=list, description="Série por bucket de 1h")


class RequestBucket(BaseModel):
    ts: float = Field(..., description="Timestamp do bucket (início da hora)")
    requests: int = Field(0, description="Total de requisições no bucket")
    success: int = Field(0, description="Requisições com sucesso no bucket")


class RequestSeriesResponse(BaseModel):
    hours: float = Field(..., description="Janela solicitada em horas")
    series: List[RequestBucket] = Field(default_factory=list, description="Série por bucket de 1h")


class ModelBucket(BaseModel):
    model: str = Field(..., description="Nome do modelo", examples=["gemma3:4b"])
    calls: int = Field(0, description="Chamadas no período")
    input_tokens: int = Field(0, description="Tokens de entrada")
    output_tokens: int = Field(0, description="Tokens de saída")


class ModelsMetricsResponse(BaseModel):
    models: List[ModelBucket] = Field(default_factory=list, description="Agregação por modelo")


class LlmCallItem(BaseModel):
    ts: float = Field(..., description="Timestamp epoch seconds")
    model: str = Field(..., description="Modelo usado")
    kind: str = Field("generate", description="generate | stream")
    prompt_tokens: int = Field(0, description="Tokens de entrada")
    completion_tokens: int = Field(0, description="Tokens de saída")
    eval_duration_ms: float = Field(0, description="Duração de eval em ms")
    success: int = Field(1, description="1=ok, 0=erro")
    error: Optional[str] = Field(None, description="Mensagem de erro se houver")


class LlmCallsResponse(BaseModel):
    calls: List[LlmCallItem] = Field(default_factory=list, description="Últimas chamadas LLM (ordem decrescente)")


class RequestLogItem(BaseModel):
    ts: float = Field(..., description="Timestamp")
    endpoint: str = Field("chat", description="Endpoint")
    question: Optional[str] = Field(None, description="Pergunta do usuário")
    mode: Optional[str] = Field(None, description="Modo usado")
    provider: str = Field("rag", description="Provider")
    evidence_count: int = Field(0, description="Evidências retornadas")
    execution_ms: float = Field(0, description="Tempo de execução em ms")
    analyze: int = Field(0, description="1 se analyze=true")
    success: int = Field(1, description="1=ok, 0=erro")
    error: Optional[str] = Field(None, description="Erro se houver")


class RequestLogResponse(BaseModel):
    requests: List[RequestLogItem] = Field(default_factory=list, description="Últimas requisições")


class DocumentHistoryItem(BaseModel):
    ts: float = Field(..., description="Timestamp do snapshot")
    documents: int = Field(0, description="Documentos indexados")
    chunks: int = Field(0, description="Chunks indexados")
    by_type: Dict[str, Dict[str, int]] = Field(default_factory=dict, description="Por tipo de fonte")


class DocumentHistoryResponse(BaseModel):
    history: List[DocumentHistoryItem] = Field(default_factory=list, description="Histórico de snapshots")


class IndexEventItem(BaseModel):
    ts: float = Field(..., description="Timestamp")
    documents_processed: int = Field(0, description="Documentos processados")
    chunks_indexed: int = Field(0, description="Chunks indexados")
    error: Optional[str] = Field(None, description="Erro se houver")


class IndexEventsResponse(BaseModel):
    events: List[IndexEventItem] = Field(default_factory=list, description="Eventos recentes")


class AuthErrorResponse(BaseModel):
    success: bool = Field(False, description="Sempre false em erro de auth")
    detail: str = Field(..., description="Mensagem", examples=["Token de API inválido ou ausente."])

    model_config = {"json_schema_extra": {"example": {"success": False, "detail": "Token de API inválido ou ausente."}}}


class RateLimitErrorResponse(BaseModel):
    success: bool = Field(False, description="Sempre false em rate limit")
    detail: str = Field(..., description="Mensagem", examples=["Rate limit excedido. Tente novamente em 12s."])
    error: ChatErrorDetail = Field(..., description="Detalhe com code RATE_LIMIT_EXCEEDED")


logger: logging.Logger = None
chatbot: ChatBot = None
embedding_generator: EmbeddingGenerator = None
splitter: DocumentSplitter = None
indexer: DocumentIndexer = None
retriever: Retriever = None
ollama_client: OllamaClient = None
cfg: Config = None
api_formatter: ApiFormatter = None


# ------------------------------------------------------------------ #
# Indexação assíncrona (jobs em segundo plano)
# ------------------------------------------------------------------ #

_index_jobs: Dict[str, dict] = {}
_index_jobs_lock = threading.Lock()
_index_exec_lock = threading.Lock()
_JOBS_FILE = Path("database/index_jobs.json")


def _persist_jobs() -> None:
    """Persiste _index_jobs em disco de forma atômica (tmp + replace)."""
    try:
        _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        import tempfile as _tmp
        import os as _os

        # Snapshot sob lock
        with _index_jobs_lock:
            data = dict(_index_jobs)
        fd, tmp_path = _tmp.mkstemp(dir=str(_JOBS_FILE.parent), suffix=".tmp")
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(data, f, indent=2, ensure_ascii=False)
            _os.replace(tmp_path, _JOBS_FILE)
        except Exception:
            if _os.path.exists(tmp_path):
                _os.remove(tmp_path)
            raise
    except Exception:
        # Persistência é best-effort — não quebra o job se falhar
        pass


def _load_persisted_jobs() -> None:
    """Carrega jobs persistidos (se existirem) na memória."""
    try:
        if not _JOBS_FILE.exists():
            return
        import json as _json
        import time as _time

        raw = _json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        now = _time.time()
        # Descarta jobs com mais de 24h para não ressuscitar lixo
        filtered = {
            k: v for k, v in raw.items()
            if isinstance(v, dict) and (now - float(v.get("created_at", now)) < 86400)
        }
        # Jobs que estavam "running" quando o processo caiu viram "error"
        for v in filtered.values():
            if v.get("status") == "running":
                v["status"] = "error"
                v["error"] = "Processo reiniciado durante a indexação"
        with _index_jobs_lock:
            # Não sobrescreve jobs já em memória (processo já tem estado mais recente)
            for k, v in filtered.items():
                if k not in _index_jobs:
                    _index_jobs[k] = v
    except Exception:
        pass


class _IndexJobCancelled(Exception):
    """Sinaliza que um job de indexação foi cancelado pelo usuário."""


def _start_index_job(
    index_documents: bool,
    sync_drive: bool = False,
) -> str:
    """Inicia a indexação em uma thread de fundo e retorna o job_id.

    O resultado fica disponível em `GET /api/index/status/{job_id}`.
    """
    with _index_jobs_lock:
        running = [
            jid for jid, j in _index_jobs.items()
            if j.get("status") == "running"
        ]
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma indexação em andamento (job {running[0]}).",
        )

    job_id = uuid.uuid4().hex[:12]
    with _index_jobs_lock:
        _index_jobs[job_id] = {
            "status": "running",
            "result": None,
            "error": None,
            "created_at": __import__("time").time(),
            "progress": 0,
            "total": 0,
            "message": "",
            "cancel_requested": False,
        }
    _persist_jobs()

    def _update_job(**fields: object) -> None:
        with _index_jobs_lock:
            if job_id in _index_jobs:
                _index_jobs[job_id].update(fields)
                if _index_jobs[job_id].get("cancel_requested"):
                    raise _IndexJobCancelled(job_id)
        # Persiste progresso de forma best-effort (fora do lock para não bloquear)
        _persist_jobs()

    def _worker():
        try:
            with _index_exec_lock:
                # Usa new_event_loop dedicado em vez de asyncio.run (evita
                # "event loop is closed" quando a thread não é a main thread)
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(
                        _run_index(
                            index_documents,
                            sync_drive,
                            on_progress=_update_job,
                        )
                    )
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            with _index_jobs_lock:
                _index_jobs[job_id] = {
                    "status": "done",
                    "result": result.model_dump(),
                    "error": None,
                    "progress": _index_jobs[job_id].get("progress", 0),
                    "total": _index_jobs[job_id].get("total", 0),
                    "message": _index_jobs[job_id].get("message", ""),
                    "created_at": _index_jobs[job_id].get("created_at", __import__("time").time()),
                }
            _persist_jobs()
        except _IndexJobCancelled:
            logger.info(f"Background index job {job_id} cancelled")
            with _index_jobs_lock:
                _index_jobs[job_id] = {
                    "status": "cancelled",
                    "result": None,
                    "error": None,
                    "progress": _index_jobs[job_id].get("progress", 0),
                    "total": _index_jobs[job_id].get("total", 0),
                    "message": _index_jobs[job_id].get("message", ""),
                    "created_at": _index_jobs[job_id].get("created_at", __import__("time").time()),
                }
            _persist_jobs()
        except Exception as e:
            logger.exception(f"Background index job {job_id} failed: {e}")
            with _index_jobs_lock:
                _index_jobs[job_id] = {
                    "status": "error",
                    "result": None,
                    "error": str(e),
                    "progress": _index_jobs[job_id].get("progress", 0),
                    "total": _index_jobs[job_id].get("total", 0),
                    "message": _index_jobs[job_id].get("message", ""),
                    "created_at": _index_jobs[job_id].get("created_at", __import__("time").time()),
                }
            _persist_jobs()

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def _get_index_job(job_id: str) -> Optional[dict]:
    _load_persisted_jobs()
    with _index_jobs_lock:
        job = _index_jobs.get(job_id)
        return dict(job) if job else None


def _prune_index_jobs(max_age_seconds: int = 3600) -> None:
    """Remove jobs antigos para não vazar memória (chamado a cada novo job)."""
    import time

    _load_persisted_jobs()
    now = time.time()
    pruned = False
    with _index_jobs_lock:
        for jid in list(_index_jobs.keys()):
            ts = _index_jobs[jid].get("created_at", 0)
            if now - ts > max_age_seconds:
                _index_jobs.pop(jid, None)
                pruned = True
    if pruned:
        _persist_jobs()


def _preload_models(_chatbot: ChatBot, _emb_gen, _logger) -> None:
    preload_models(_chatbot, _logger)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global logger, chatbot, embedding_generator, splitter, indexer, retriever, ollama_client, cfg, api_formatter

    cfg = app_config

    Path(cfg.vector_db_dir).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)

    logger = setup_logger(
        name="watson_api",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    logger.info("Starting Watson API server")
    _load_persisted_jobs()

    chatbot = build_chatbot(cfg, logger)
    embedding_generator, splitter, indexer = build_indexer(cfg, logger)

    logger.info("Preloading models...")
    try:
        _preload_models(chatbot, embedding_generator, logger)
        logger.info("Models loaded successfully")
    except Exception as e:
        logger.warning(f"Model preload skipped (tests/dev): {e}")

    api_formatter = ApiFormatter()

    yield

    logger.info("Shutting down Watson API server")


app = FastAPI(
    title="Watson RAG API",
    description="""
    API de Retrieval-Augmented Generation (RAG) para indexação de documentos e
    imagens, com consultas inteligentes via LLM (Ollama).

    ## Arquitetura (Knowledge Ingestion & Indexing Pipeline)
    O Watson transforma fontes de conhecimento em uma base pesquisável:

    1. **Ingestão** — adapters por fonte (PDF com OCR seletivo, DOCX, CSV, XLSX,
       TXT, imagens), extraindo estrutura (páginas, seções,
       tabelas, imagens).
    2. **Indexação** — chunking semântico por tipo, deduplicação, quality gate,
       embeddings multilíngues (padrão `intfloat/multilingual-e5-base`) com
       cache, e gravação em um índice vetorial (Chroma).
    3. **Manifesto** — cada documento é registrado com hashes, versões de
       parser/chunking/embedding e status, permitindo indexação incremental e
       reindexação controlada (§versionamento).
    4. **Recuperação** — busca vetorial com metadata rica (fabricante, modelo,
       seção, página, códigos de erro) e rerank opcional.
    5. **Geração** — LLM sintetiza a resposta com base nas evidências.

    ## Funcionalidades
    - **Chat**: perguntas sobre documentos indexados (RAG).
    - **Streaming (SSE)**: tokens da resposta em tempo real + metadados finais.
    - **Indexação**: `POST /api/index` e `POST /api/index/documents` (incremental por hash/versão).
    - **Indexação assíncrona**: `POST /api/index/async` + `GET /api/index/status/{job_id}` + `POST /api/index/cancel/{job_id}`.
    - **Upload**: envie novos documentos (PDF, TXT, DOCX, XLSX, CSV, imagens) via `POST /api/documents/upload`.
    - **Reindexação**: incremental por hash/versão; limpeza via `POST /api/clear*` (`/clear`, `/clear/documents`, `/clear/vectorstore`, `/drive/clear`).
    - **OCR seletivo**: Tesseract aplicado apenas em páginas sem texto nativo.
    - **Saúde**: status da API e dependências (`/api/health`, `/api/health/ready`).
    - **Métricas**: séries e logs em `/api/metrics/*` (dashboard em `/dashboard`).
    - **Autenticação**: quando `API_AUTH_TOKEN` configurado, exige `X-API-Token` ou `Authorization: Bearer` (exceto `/api/health*` e `/docs`).
    - **Rate limiting**: `429` com `Retry-After` em `/api/chat` e `/api/chat/stream` (config `API_RATE_LIMIT`/`API_RATE_WINDOW`).

    ## Formato de Resposta
    Todas as respostas seguem um contrato estável:
    ```json
    {
      "success": true,
      "answer": "texto da resposta",
      "confidence": 0.94,
      "sources": [
        {
          "title": "HP LASER JET E52645.pdf",
          "provider": "rag",
          "page": 142,
          "section": "Troubleshooting",
          "manufacturer": "HP",
          "model": "E52645",
          "error_codes": ["E123"]
        }
      ],
      "metadata": {
        "provider": "rag",
        "evidence_count": 3,
        "execution_time_ms": 814,
        "verdict": "ok"
      }
    }
    ```

    ## Streaming (SSE)
    O endpoint `POST /api/chat/stream` envia eventos:
    1. `data: {"content": "<token>"}` — cada token da resposta (JSON preserva
       newlines e formatação markdown);
    2. `data: [DONE]` — fim do texto;
    3. `data: {...}` — metadados finais (confidence, sources ricas, metadata).

    Diagnósticos internos **nunca** são expostos na resposta.
    """,
    version="0.0.1",
    contact={
        "name": "Watson Team",
        "url": "http://localhost:9000",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Chat", "description": "Perguntas RAG com streaming SSE opcional"},
        {"name": "Indexação", "description": "Indexação síncrona e assíncrona (jobs)"},
        {"name": "Documentos", "description": "Upload de documentos para indexação"},
        {"name": "Google Drive", "description": "Listagem, seleção e sync do Drive"},
        {"name": "Monitoramento", "description": "Health e readiness"},
        {"name": "Métricas", "description": "Séries temporais, logs e histórico (usado pelo dashboard)"},
        {"name": "Manutenção", "description": "Limpeza de documentos, vetores e métricas"},
        {"name": "Modelos", "description": "Modelos Ollama disponíveis"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Swagger: esquemas de segurança documentados (middleware real em require_api_token/rate_limit)
from fastapi.security import APIKeyHeader, HTTPBearer

_api_key_header = APIKeyHeader(name="X-API-Token", auto_error=False, description="Token configurado em API_AUTH_TOKEN")
_bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT", description="Alternativa: Authorization: Bearer <token>")

_COMMON_AUTH_RESPONSES = {
    401: {"description": "Token de API inválido ou ausente (quando API_AUTH_TOKEN configurado)", "model": AuthErrorResponse},
    429: {
        "description": "Rate limit excedido — tente após Retry-After (apenas /api/chat e /api/chat/stream)",
        "model": RateLimitErrorResponse,
        "headers": {
            "Retry-After": {"description": "Segundos até liberar", "schema": {"type": "integer"}},
            "X-RateLimit-Limit": {"description": "Limite da janela", "schema": {"type": "integer"}},
            "X-RateLimit-Remaining": {"description": "Restante na janela", "schema": {"type": "integer"}},
            "X-RateLimit-Reset": {"description": "Epoch de reset", "schema": {"type": "integer"}},
        },
    },
}
# Endpoints isentos de auth (health/docs) não recebem 401
_AUTH_EXEMPT = {"/api/health", "/api/health/ready"}


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())[:8]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Exige o header `X-API-Token` (ou `Authorization: Bearer`) em todos os
    endpoints `/api/*`, exceto health/docs. Desativado se `API_AUTH_TOKEN`
    estiver vazio (configuração local de desenvolvimento)."""
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/health"):
        return await call_next(request)

    token = getattr(app_config, "api_auth_token", "") or ""
    if not token:
        return await call_next(request)

    header_token = request.headers.get("x-api-token", "")
    if not header_token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            header_token = auth[7:].strip()

    if header_token != token:
        return JSONResponse(
            status_code=401,
            content={"success": False, "detail": "Token de API inválido ou ausente."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)


# ------------------------------------------------------------------ #
# Rate limiting (token bucket per IP) — protege /api/chat contra abuso
# ------------------------------------------------------------------ #

_rate_limit_store: Dict[str, List[float]] = {}
_rate_limit_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Limita requisições por IP para endpoints sensíveis.

    Usa janela deslizante em memória (sem dependência externa). Configurável
    via `API_RATE_LIMIT` / `API_RATE_WINDOW` / `API_RATE_ENABLED`.
    Só atua em `/api/chat` e `/api/chat/stream`; demais endpoints liberados.
    """
    path = request.url.path
    # Só limita chat — health/metrics/index não devem ser throttled
    if not path.startswith("/api/chat"):
        return await call_next(request)

    if not getattr(app_config, "api_rate_enabled", True):
        return await call_next(request)

    limit = int(getattr(app_config, "api_rate_limit", 30))
    window = int(getattr(app_config, "api_rate_window", 60))
    if limit <= 0 or window <= 0:
        return await call_next(request)

    # IP do cliente (respeita X-Forwarded-For quando atrás de proxy)
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    import time as _time

    now = _time.time()
    with _rate_limit_lock:
        timestamps = _rate_limit_store.get(client_ip, [])
        # Remove timestamps fora da janela
        timestamps = [t for t in timestamps if now - t < window]
        if len(timestamps) >= limit:
            retry_after = int(window - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "detail": f"Rate limit excedido. Tente novamente em {retry_after}s.",
                    "error": {"code": "RATE_LIMIT_EXCEEDED", "message": f"Limite de {limit} req/{window}s"},
                },
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)
        _rate_limit_store[client_ip] = timestamps

        # Evita vazamento de memória: limpa IPs ociosos (mantém só janela)
        if len(_rate_limit_store) > 1000:
            for ip in list(_rate_limit_store.keys()):
                ts = _rate_limit_store[ip]
                if not ts or now - ts[-1] > window * 2:
                    _rate_limit_store.pop(ip, None)

    response = await call_next(request)
    # Informa limites nos headers (útil para clientes)
    try:
        remaining = max(0, limit - len(timestamps))
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + window))
    except Exception:
        pass
    return response


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["Monitoramento"],
    summary="Verificar status da API",
    description="Sempre retorna 200. Campo `status` indica `ok` ou `degraded` (Ollama indisponível). Isento de autenticação.",
    response_description="Status atual da API e seus componentes",
    responses={
        200: {"description": "API funcionando (ok ou degraded)", "model": HealthResponse},
    },
)
async def health():
    global cfg, ollama_client
    ollama_status = "unknown"
    try:
        local_client = ollama_client or OllamaClient(
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
            request_timeout=5,
        )
        local_client.list_models()
        ollama_status = "ok"
    except Exception:
        ollama_status = "unavailable"

    overall = "ok" if ollama_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        documents_dir=cfg.documents_dir,
        chroma_dir=cfg.vector_db_dir,
        ollama_model=cfg.ollama_model,
    )


@app.get(
    "/api/health/ready",
    response_model=ReadyResponse,
    tags=["Monitoramento"],
    summary="Readiness probe (k8s/docker)",
    description="Retorna 200 com `status: ok | degraded` e `checks` por subsistema (vector_db_dir, manifest, ollama, metrics_db, embedding_cache). Isento de autenticação. `stale` indica docs no manifest sem arquivo no disco.",
    response_description="Detalha subsistemas: vector_db, manifest, ollama, metrics",
)
async def ready():
    global cfg, ollama_client, embedding_generator
    checks: Dict[str, str] = {}
    # vector_db dir
    try:
        p = Path(cfg.vector_db_dir)
        checks["vector_db_dir"] = "ok" if p.exists() else "missing"
    except Exception as e:
        checks["vector_db_dir"] = f"error: {e}"

    # chroma count
    chroma_docs = 0
    chroma_chunks = 0
    try:
        # Usa indexer manifest como fonte de verdade
        from pathlib import Path as _P

        manifest_path = str(_P(cfg.vector_db_dir) / "index_manifest.json")
        from ingestion.manifest import ManifestStore

        ms = ManifestStore(manifest_path)
        entries = ms.entries()
        chroma_docs = len(entries)
        chroma_chunks = sum(int(e.get("chunks", 0) or 0) for e in entries)
        checks["manifest"] = "ok" if chroma_docs >= 0 else "empty"
        # stale: source não existe mais no disco
        stale = 0
        for e in entries:
            src = e.get("source") or ""
            if src and not Path(src).exists():
                # Também checa se arquivo foi movido para drive dest que não existe
                stale += 1
        checks["stale_docs"] = str(stale)
    except Exception as e:
        checks["manifest"] = f"error: {e}"
        stale = 0
        chroma_chunks = 0
        chroma_docs = 0

    # ollama
    try:
        local_client = ollama_client or OllamaClient(
            model=cfg.ollama_model, base_url=cfg.ollama_base_url, request_timeout=5
        )
        local_client.list_models()
        checks["ollama"] = "ok"
    except Exception as e:
        checks["ollama"] = f"unavailable: {e}"

    # metrics db
    try:
        from metrics.store import MetricsStore

        ms2 = MetricsStore(db_path=cfg.metrics_db)
        # simples query
        ms2.summary()
        checks["metrics_db"] = "ok"
    except Exception as e:
        checks["metrics_db"] = f"error: {e}"

    # embeddings cache
    try:
        checks["embedding_cache"] = "ok" if Path(cfg.embedding_cache_path).parent.exists() else "missing_parent"
    except Exception as e:
        checks["embedding_cache"] = f"error: {e}"

    # Overall
    degraded = any(v.startswith("error") or v.startswith("unavailable") or v == "missing" for v in checks.values())
    # stale >20 é warning mas não not_ready
    status = "degraded" if degraded else "ok"
    return ReadyResponse(
        status=status,
        checks=checks,
        documents=chroma_docs,
        chunks=chroma_chunks,
        stale=stale if "stale" in locals() else 0,
    )


@app.get(
    "/api/models",
    response_model=ModelListResponse,
    tags=["Modelos"],
    summary="Listar modelos Ollama disponíveis",
    response_description="Lista de nomes dos modelos disponíveis",
    responses={
        200: {"description": "Modelos listados com sucesso", "model": ModelListResponse},
        401: {"description": "Token de API inválido ou ausente (quando API_AUTH_TOKEN configurado)", "model": AuthErrorResponse},
    },
)
async def list_models():
    global ollama_client
    try:
        local_client = ollama_client or OllamaClient(
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
            request_timeout=cfg.ollama_timeout,
        )
        models = local_client.list_models()
        return ModelListResponse(models=models)
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        return ModelListResponse(models=[cfg.ollama_model])


@app.post(
    "/api/chat",
    response_model=ChatSuccessResponse,
    tags=["Chat"],
    summary="Fazer uma pergunta ao Watson",
    description="Responde usando RAG. Exige `X-API-Token` ou `Authorization: Bearer` quando `API_AUTH_TOKEN` configurado. Rate limited (padrão 30 req/60s por IP) — retorna 429 com `Retry-After` e headers `X-RateLimit-*`.",
    response_description="Resposta gerada com sucesso no formato padronizado",
    responses={
        200: {"description": "Resposta gerada com sucesso", "model": ChatSuccessResponse},
        400: {"description": "Pergunta inválida ou vazia", "model": ErrorResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        429: {"description": "Rate limit excedido", "model": RateLimitErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ChatErrorResponse},
        503: {"description": "Chatbot não foi inicializado", "model": ErrorResponse},
    },
)
async def chat(request: ChatRequest, req: Request):
    """Responde uma pergunta usando RAG (documentos indexados).

    Retorna `answer`, `confidence`, `sources` (com metadata rica: fabricante,
    modelo, seção, página e códigos de erro) e `metadata` de execução.
    """
    global chatbot, logger, api_formatter
    request_id = getattr(req.state, "request_id", "unknown")

    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        if request.history:
            context = ""
            for msg in request.history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                context += f"{role}: {content}\n"
            result = chatbot.ask_with_context(
                question, context, mode=request.mode, analyze=request.analyze
            )
        else:
            result = chatbot.ask(
                question, mode=request.mode, analyze=request.analyze
            )

        logger.info(
            f"[{request_id}] Chat completed: {len(result.answer)} chars, "
            f"confidence={result.confidence:.2f}, verdict={result.verdict}, "
            f"time={result.execution_time:.2f}s"
        )

        return api_formatter.format(result)

    except Exception as e:
        logger.exception(f"[{request_id}] Chat error: {e}")
        return JSONResponse(
            status_code=500,
            content=api_formatter.format_error(
                code="INTERNAL_ERROR",
                message=str(e),
            ),
        )


@app.post(
    "/api/chat/stream",
    tags=["Chat"],
    summary="Fazer uma pergunta ao Watson com resposta em streaming (SSE)",
    description="SSE em `text/event-stream`. Rate limited e autenticado como `/api/chat`.",
    response_description="Stream de eventos SSE com tokens JSON da resposta + metadados finais",
    responses={
        200: {
            "description": (
                "Stream de eventos SSE:\n"
                "1. `data: {\"content\": \"<token>\"}` — cada token da resposta "
                "(JSON preserva newlines/ markdown);\n"
                "2. `data: [DONE]` — fim do texto;\n"
                "3. `data: {...}` — metadados finais com sources ricas "
                "(confidence, sources, metadata)."
            ),
        },
        400: {"description": "Pergunta inválida ou vazia", "model": ErrorResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        422: {"description": "Validation Error", "model": ErrorResponse},
        429: {"description": "Rate limit excedido", "model": RateLimitErrorResponse},
        503: {"description": "Chatbot não foi inicializado", "model": ErrorResponse},
    },
)
async def chat_stream(request: ChatRequest, req: Request):
    """Envia uma pergunta e recebe a resposta em tempo real via SSE.

    Formato dos eventos:
    - Tokens: `data: {"content": "<token>"}\\n\\n` (JSON — preserva quebras de
      linha, espaços e formatação markdown).
    - `[DONE]` sinaliza o fim do texto.
    - Último evento: JSON com `confidence`, `sources` (metadata rica:
      fabricante, modelo, seção, página, códigos de erro) e `metadata`.
    """
    global chatbot, logger, api_formatter
    request_id = getattr(req.state, "request_id", "unknown")

    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            import json as _json

            result = None
            context = ""
            if request.history:
                for msg in request.history:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    context += f"{role}: {content}\n"
            gen = (
                chatbot.ask_stream_with_history(
                    question, context, mode=request.mode, analyze=request.analyze
                )
                if request.history
                else chatbot.ask_stream(
                    question, mode=request.mode, analyze=request.analyze
                )
            )
            try:
                while True:
                    token = next(gen)
                    # Envia cada token como JSON ({"content": ...}) para que
                    # newlines/ espaços do markdown sejam preservados com
                    # segurança pelo consumidor (o delimitador SSE \n\n não
                    # colide com o conteúdo).
                    yield f"data: {_json.dumps({'content': token})}\n\n"
            except StopIteration as e:
                result = e.value

            yield "data: [DONE]\n\n"

            if result:
                import json
                meta = api_formatter.format_stream_metadata(result)
                yield f"data: {json.dumps(meta)}\n\n"

            logger.info(
                f"[{request_id}] Stream completed: "
                f"confidence={result.confidence if result else 'N/A'}, "
                f"verdict={result.verdict if result else 'N/A'}"
            )
        except Exception as e:
            logger.exception(f"[{request_id}] Stream error: {e}")
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get(
    "/api/drive/folder/{folder_id}",
    response_model=List[DriveItem],
    tags=["Google Drive"],
    summary="Listar itens de uma pasta do Google Drive",
    description="Lista pastas/arquivos de uma pasta pública. Requer `API_AUTH_TOKEN` se configurado.",
    response_description="Lista de pastas e arquivos da pasta",
    responses={
        200: {"description": "Itens listados", "model": List[DriveItem]},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        404: {"description": "Pasta não encontrada", "model": ErrorResponse},
    },
)
async def drive_folder(folder_id: str, req: Request):
    """Lista os itens (pastas e arquivos) de uma pasta pública do Drive."""
    global logger, cfg
    try:
        drive = GoogleDriveSync(
            folder_id=folder_id,
            dest_dir=cfg.google_drive_dest_dir,
            logger=logger,
            timeout=cfg.google_drive_sync_timeout,
        )
        entries = drive.list_folder(folder_id)
        return [
            DriveItem(
                id=e.entry_id,
                name=e.name,
                type="folder" if e.is_folder else "file",
                modified=e.modified or None,
            )
            for e in entries
        ]
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Folder listing failed: {e}")


@app.get(
    "/api/drive/selection",
    response_model=DriveSelectionResponse,
    tags=["Google Drive"],
    summary="Obter a seleção de pastas para indexação",
    description="Retorna pastas selecionadas para sync/indexação. Requer auth se configurado.",
    response_description="Pastas atualmente selecionadas",
    responses={
        200: {"description": "Seleção atual", "model": DriveSelectionResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def drive_selection_get(req: Request):
    """Retorna quais subpastas do Drive estão selecionadas para indexação."""
    global cfg
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id or "",
        dest_dir=cfg.google_drive_dest_dir,
        timeout=cfg.google_drive_sync_timeout,
    )
    selection = drive.load_selection()
    return DriveSelectionResponse(
        folders=[
            SelectedFolderRequest(folder_id=s.folder_id, path=s.path)
            for s in selection
        ],
        selected=len(selection),
    )


@app.post(
    "/api/drive/selection",
    response_model=DriveSelectionResponse,
    tags=["Google Drive"],
    summary="Salvar a seleção de pastas para indexação",
    description="Salva pastas para sync. Enviar `{\"folders\": []}` usa pasta raiz inteira. Requer auth se configurado.",
    response_description="Seleção salva",
    responses={
        200: {"description": "Seleção salva", "model": DriveSelectionResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def drive_selection_save(payload: DriveSelectionSaveRequest, req: Request):
    """Salva quais subpastas do Drive serão sincronizadas/indexadas.

    Enviar lista vazia (`{"folders": []}`) faz o sync usar a pasta raiz
    inteira.
    """
    global cfg
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id or "",
        dest_dir=cfg.google_drive_dest_dir,
        timeout=cfg.google_drive_sync_timeout,
    )
    selection = [
        SelectedFolderRequest(folder_id=f.folder_id, path=f.path)
        for f in payload.folders
    ]
    drive.save_selection(
        [
            _SelectedFolder(folder_id=f.folder_id, path=f.path)
            for f in selection
        ]
    )
    return DriveSelectionResponse(folders=selection, selected=len(selection))


@app.post(
    "/api/drive/sync",
    response_model=DriveSyncResponse,
    tags=["Google Drive"],
    summary="Sincronizar arquivos selecionados do Google Drive",
    description="Baixa arquivos das pastas selecionadas. Retorna 400 se `GOOGLE_DRIVE_FOLDER_ID` não configurado. Requer auth se configurado.",
    response_description="Relatório do sync",
    responses={
        200: {"description": "Relatório do sync", "model": DriveSyncResponse},
        400: {"description": "Google Drive não configurado", "model": ErrorResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def drive_sync(req: Request):
    """Baixa os arquivos das pastas selecionadas para o diretório local,
    respeitando a seleção salva em `/api/drive/selection`."""
    global logger, cfg
    if not cfg.google_drive_folder_id:
        raise HTTPException(
            status_code=400,
            detail="Google Drive not configured. Set GOOGLE_DRIVE_FOLDER_ID.",
        )
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id,
        dest_dir=cfg.google_drive_dest_dir,
        logger=logger,
        timeout=cfg.google_drive_sync_timeout,
    )
    result = drive.sync()
    return DriveSyncResponse(
        status="ok",
        files_remote=result.files_remote,
        folders=result.folders,
        downloaded=result.downloaded,
        skipped=result.skipped,
        failed=result.failed,
        removed=result.removed,
        bytes_downloaded=result.bytes_downloaded,
        errors=result.errors,
    )


@app.post(
    "/api/drive/clear",
    response_model=DriveClearResponse,
    tags=["Google Drive"],
    summary="Remover arquivos sincronizados do Google Drive",
    description="Apaga arquivos do `GOOGLE_DRIVE_DEST_DIR` e limpa seleção. Requer auth se configurado.",
    response_description="Quantidade de arquivos removidos",
    responses={
        200: {"description": "Arquivos removidos", "model": DriveClearResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def drive_clear(req: Request):
    """Apaga os arquivos sincronizados (e a seleção) do diretório local.

    Use com cuidado: após isso, `POST /api/index` detectará os documentos
    como stale e os removerá do índice.
    """
    global logger, cfg
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id or "",
        dest_dir=cfg.google_drive_dest_dir,
        logger=logger,
        timeout=cfg.google_drive_sync_timeout,
    )
    removed = 0
    dest = Path(cfg.google_drive_dest_dir)
    if dest.exists():
        for item in dest.rglob("*"):
            if item.is_file():
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    pass
    drive.save_selection([])
    return DriveClearResponse(status="ok", removed=removed)


@app.post(
    "/api/index",
    response_model=IndexResponse,
    tags=["Indexação"],
    summary="Indexar documentos",
    description="Indexa de forma incremental (hash/versão). Bloqueante — para background use `POST /api/index/async`. Requer auth se configurado.",
    response_description="Resultado da indexação incluindo documentos e chunks processados",
    responses={
        200: {"description": "Indexação concluída", "model": IndexResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        500: {"description": "Erro na indexação", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_all():
    """Indexa documentos de forma incremental (por hash/versão).

    Processa apenas documentos alterados ou novos.
    """
    return await _run_index(index_documents=True)


@app.post(
    "/api/index/documents",
    response_model=IndexResponse,
    tags=["Indexação"],
    summary="Indexar apenas documentos",
    description="Atalho para `POST /api/index` (documentos com OCR seletivo, incremental). Requer auth se configurado.",
    response_description="Resultado da indexação de documentos",
    responses={
        200: {"description": "Indexação concluída", "model": IndexResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        500: {"description": "Erro na indexação", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_documents():
    """Indexa apenas documentos (PDF, DOCX, CSV, XLSX, TXT, imagens) do
    diretório configurado, com OCR seletivo e incremental por hash."""
    return await _run_index(index_documents=True)


class IndexJobRequest(BaseModel):
    mode: str = Field(
        "all", description="O que indexar: all | documents",
        examples=["documents"],
    )
    sync_drive: bool = Field(
        False,
        description="Se true, sincroniza o Google Drive antes de indexar "
        "(use apenas quando quiser baixar o Drive junto)",
    )


class IndexJobResponse(BaseModel):
    status: str = Field(..., description="Status da operação", examples=["started"])
    job_id: str = Field(..., description="ID do job para consulta de status")


class IndexJobStatus(BaseModel):
    job_id: str = Field(..., description="ID do job")
    status: str = Field(
        ..., description="running | done | error | cancelled",
        examples=["running"],
    )
    result: Optional[IndexResponse] = Field(None, description="Resultado (quando done)")
    error: Optional[str] = Field(None, description="Mensagem de erro (quando error)")
    progress: int = Field(0, description="Documentos processados até agora")
    total: int = Field(0, description="Total de documentos pendentes")
    message: str = Field("", description="Documento/fase atual")


@app.post(
    "/api/index/async",
    response_model=IndexJobResponse,
    tags=["Indexação"],
    summary="Iniciar indexação em segundo plano",
    description="Retorna `job_id` imediatamente. Consulte `GET /api/index/status/{job_id}`. Body: `{\"mode\": \"all|documents\", \"sync_drive\": false}`. Retorna 409 se já há job em andamento.",
    response_description="Retorna o job_id imediatamente; consulte o status via GET /api/index/status/{job_id}",
    responses={
        200: {"description": "Job iniciado", "model": IndexJobResponse},
        400: {"description": "Modo inválido (mode deve ser all|documents)", "model": ErrorResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        409: {"description": "Já existe indexação em andamento", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_async(payload: IndexJobRequest):
    """Inicia a indexação em segundo plano e retorna na hora.

    Não bloqueia a requisição — a UI fica livre enquanto o job roda.
    Use `GET /api/index/status/{job_id}` para acompanhar o progresso.
    """
    global indexer, logger

    if not indexer:
        raise HTTPException(status_code=503, detail="Indexer not initialized")

    mode = payload.mode or "all"
    if mode not in {"all", "documents"}:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

    _prune_index_jobs()

    job_id = _start_index_job(
        index_documents=mode in {"all", "documents"},
        sync_drive=payload.sync_drive,
    )
    logger.info(f"Background index job started: {job_id} ({mode})")
    return IndexJobResponse(status="started", job_id=job_id)


@app.get(
    "/api/index/status/{job_id}",
    response_model=IndexJobStatus,
    tags=["Indexação"],
    summary="Consultar status de um job de indexação",
    description="`status: running | done | error | cancelled`. Requer auth se configurado.",
    response_description="Status atual do job (running, done ou error)",
    responses={
        200: {"description": "Status do job", "model": IndexJobStatus},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        404: {"description": "Job não encontrado", "model": ErrorResponse},
    },
)
async def index_status(job_id: str):
    """Consulta o status de um job iniciado via `POST /api/index/async`."""
    job = _get_index_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return IndexJobStatus(
        job_id=job_id,
        status=job["status"],
        result=IndexResponse(**job["result"]) if job.get("result") else None,
        error=job.get("error"),
        progress=job.get("progress", 0),
        total=job.get("total", 0),
        message=job.get("message", ""),
    )


class IndexCancelResponse(BaseModel):
    status: str = Field(..., description="Status da operação", examples=["cancelling"])
    job_id: str = Field(..., description="ID do job a cancelar")


@app.post(
    "/api/index/cancel/{job_id}",
    response_model=IndexCancelResponse,
    tags=["Indexação"],
    summary="Cancelar um job de indexação em andamento",
    description="Marca `cancel_requested` — a thread verifica entre documentos. Requer auth se configurado.",
    response_description="Solicita o cancelamento cooperativo do job",
    responses={
        200: {"description": "Cancelamento solicitado", "model": IndexCancelResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        404: {"description": "Job não encontrado", "model": ErrorResponse},
        409: {"description": "Job não está em andamento", "model": ErrorResponse},
    },
)
async def index_cancel(job_id: str):
    """Marca o job para cancelamento. A thread verifica o flag entre
    documentos e para de forma cooperativa (status vira `cancelled`)."""
    job = _get_index_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.get("status") != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' não está em andamento (status={job.get('status')})",
        )

    with _index_jobs_lock:
        if job_id in _index_jobs:
            _index_jobs[job_id]["cancel_requested"] = True
    _persist_jobs()

    logger.info(f"Cancel requested for index job {job_id}")
    return IndexCancelResponse(status="cancelling", job_id=job_id)


async def _run_index(
    index_documents: bool,
    sync_drive: bool = False,
    on_progress: Optional[Callable[..., None]] = None,
) -> IndexResponse:
    global indexer, embedding_generator, splitter, logger, cfg

    if not indexer:
        raise HTTPException(status_code=503, detail="Indexer not initialized")

    total_chunks = 0
    docs_indexed = 0

    if index_documents:
        try:
            if on_progress:
                on_progress(message="Sincronizando Google Drive...")
            if sync_drive and cfg.google_drive_folder_id:
                try:
                    drive_sync = GoogleDriveSync(
                        folder_id=cfg.google_drive_folder_id,
                        dest_dir=cfg.google_drive_dest_dir,
                        logger=logger,
                        timeout=cfg.google_drive_sync_timeout,
                    )
                    result = drive_sync.sync()
                    logger.info(f"Google Drive sync: {result.as_dict()}")
                except Exception as e:
                    logger.exception(f"Google Drive sync error: {e}")

            loader = DocumentLoader(
                logger=logger,
                ocr_lang=cfg.ocr_lang,
                ocr_dpi=cfg.ocr_dpi,
                ocr_min_text_chars=cfg.ocr_min_text_chars,
                tesseract_cmd=cfg.tesseract_cmd,
                image_dir=cfg.image_dir,
                vision_model=cfg.vision_model,
                vision_base_url=cfg.ollama_base_url,
                ollama_base_url=cfg.ollama_base_url,
            )
            if on_progress:
                on_progress(message="Carregando documentos...")
            documents = loader.load(cfg.documents_dir)
            if on_progress:
                on_progress(message=f"{len(documents)} documentos carregados")

            if documents:
                has_pending, pending_list, stale_set = (
                    indexer.has_pending_changes(documents)
                )
                if has_pending:
                    prev_callback = getattr(indexer, "progress_callback", None)
                    indexer.progress_callback = (
                        lambda done, total, name, _c=on_progress: (
                            _c(progress=done, total=total, message=name)
                            if _c
                            else None
                        )
                    )
                    try:
                        chunks = indexer.index(documents)
                    finally:
                        indexer.progress_callback = prev_callback
                    total_chunks += chunks
                    docs_indexed = len(pending_list)
                    logger.info(f"Indexed {chunks} chunks from {len(pending_list)} documents")
                else:
                    logger.info("All documents are up to date")
        except Exception as e:
            logger.exception(f"Document indexing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return IndexResponse(
        status="ok",
        documents_indexed=docs_indexed,
        total_chunks=total_chunks,
    )


@app.post(
    "/api/documents/upload",
    response_model=DocUploadResponse,
    tags=["Documentos"],
    summary="Fazer upload de documento",
    description="Envia para `DOCUMENTS_DIR` (máx. 50MB). Nome sanitizado, 409 se já existe. Depois `POST /api/index`. Requer auth se configurado.",
    response_description="Resultado do upload com nome e tamanho do arquivo",
    responses={
        200: {"description": "Upload realizado com sucesso", "model": DocUploadResponse},
        400: {"description": "Nenhum arquivo enviado / nome inválido", "model": ErrorResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        409: {"description": "Arquivo já existe", "model": ErrorResponse},
        413: {"description": "Arquivo excede 50MB", "model": ErrorResponse},
        500: {"description": "Erro ao salvar", "model": ErrorResponse},
    },
)
async def upload_document(file: UploadFile = File(..., description="Arquivo a ser enviado (PDF, DOCX, TXT, MD, CSV, XLSX, XLS, JPG, PNG, BMP, TIFF)")):
    """Envia um documento para o diretório de indexação (máx. 50 MB).

    Depois de enviado, execute `POST /api/index` para indexá-lo. Nomes de
    arquivo são sanitizados; envio duplicado retorna 409.
    """
    global logger, cfg

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = re.sub(r'[^\w\.\-]', '_', Path(file.filename).name)
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    docs_dir = Path(cfg.documents_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    filepath = docs_dir / filename

    if filepath.exists():
        raise HTTPException(
            status_code=409,
            detail=f"File '{filename}' already exists",
        )

    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({len(content)} bytes). Maximum is {MAX_UPLOAD_SIZE} bytes.",
            )
        filepath.write_bytes(content)
        logger.info(f"Uploaded document: {filename} ({len(content)} bytes)")
        return DocUploadResponse(status="ok", filename=filename, size=len(content))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/clear",
    response_model=ClearResponse,
    tags=["Manutenção"],
    summary="Limpar toda a memória (documentos + banco vetorial)",
    description="Remove arquivos de `DOCUMENTS_DIR` e vetores do Chroma; também limpa métricas. Requer auth se configurado.",
    response_description="Resultado da limpeza",
    responses={
        200: {"description": "Memória limpa com sucesso", "model": ClearResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        500: {"description": "Erro na limpeza", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def clear_all():
    return await _run_clear(clear_docs=True, clear_vectorstore=True)


@app.post(
    "/api/clear/documents",
    response_model=ClearResponse,
    tags=["Manutenção"],
    summary="Limpar apenas documentos",
    description="Remove só arquivos de `DOCUMENTS_DIR`. Requer auth se configurado.",
    response_description="Resultado da limpeza de documentos",
    responses={
        200: {"description": "Documentos removidos", "model": ClearResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        500: {"description": "Erro na limpeza", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def clear_documents():
    return await _run_clear(clear_docs=True, clear_vectorstore=False)


@app.post(
    "/api/clear/vectorstore",
    response_model=ClearResponse,
    tags=["Manutenção"],
    summary="Limpar apenas banco vetorial",
    description="Remove vetores e limpa métricas (`metrics.db`). Requer auth se configurado.",
    response_description="Resultado da limpeza do banco vetorial",
    responses={
        200: {"description": "Banco vetorial limpo", "model": ClearResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
        500: {"description": "Erro na limpeza", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def clear_vectorstore():
    return await _run_clear(clear_docs=False, clear_vectorstore=True)


async def _run_clear(clear_docs: bool, clear_vectorstore: bool) -> ClearResponse:
    global indexer, logger, cfg

    if not indexer:
        raise HTTPException(status_code=503, detail="Indexer not initialized")

    docs_removed = 0
    vec_removed = 0

    try:
        if clear_vectorstore:
            vec_removed = indexer.clear_vectorstore()
        if clear_docs:
            docs_removed = indexer.clear_documents(cfg.documents_dir)
        # Limpar a "memória" (vetores) também zera as métricas registradas,
        # já que os dados de origem foram apagados.
        if clear_vectorstore:
            try:
                from metrics.store import MetricsStore
                MetricsStore(db_path=cfg.metrics_db, logger=logger).clear()
            except Exception as e:
                logger.warning(f"Metrics clear failed: {e}")
        logger.info(f"Clear completed: {docs_removed} docs, {vec_removed} vectorstore files")
        return ClearResponse(
            status="ok",
            documents_removed=docs_removed,
            vectorstore_files_removed=vec_removed,
        )
    except Exception as e:
        logger.exception(f"Clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
# Métricas e Dashboard
# ------------------------------------------------------------------ #

def _get_metrics_store():
    from metrics.store import MetricsStore
    return MetricsStore(db_path=cfg.metrics_db, logger=logger)


@app.get(
    "/api/metrics/summary",
    response_model=MetricsSummaryResponse,
    tags=["Métricas"],
    summary="Resumo das métricas do Watson",
    description="Agregado no intervalo `hours` (0 = todo histórico). Usado pelos KPIs do dashboard.",
    response_description="Resumo agregado",
    responses={
        200: {"description": "Resumo agregado", "model": MetricsSummaryResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_summary(hours: Optional[float] = 24.0):
    store = _get_metrics_store()
    since = None
    if hours:
        import time
        since = time.time() - hours * 3600
    return store.summary(since_ts=since)


@app.get(
    "/api/metrics/tokens",
    response_model=TokenSeriesResponse,
    tags=["Métricas"],
    summary="Série temporal de tokens (input/output)",
    description="Buckets de 1h com `input_tokens/output_tokens/calls`. Usado no gráfico Tokens do dashboard.",
    response_description="Série por hora",
    responses={
        200: {"description": "Série por hora", "model": TokenSeriesResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_tokens(hours: float = 24.0):
    store = _get_metrics_store()
    return {"hours": hours, "series": store.token_series(hours)}


@app.get(
    "/api/metrics/requests",
    response_model=RequestSeriesResponse,
    tags=["Métricas"],
    summary="Série temporal de requisições de chat",
    description="Buckets de 1h com `requests/success`. Usado no gráfico Requisições do dashboard.",
    response_description="Série por hora",
    responses={
        200: {"description": "Série por hora", "model": RequestSeriesResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_requests(hours: float = 24.0):
    store = _get_metrics_store()
    return {"hours": hours, "series": store.request_series(hours)}


@app.get(
    "/api/metrics/models",
    response_model=ModelsMetricsResponse,
    tags=["Métricas"],
    summary="Tokens por modelo",
    description="Agregação por modelo no intervalo `hours`. Usado no gráfico Tokens por Modelo.",
    response_description="Agregação por modelo",
    responses={
        200: {"description": "Agregação por modelo", "model": ModelsMetricsResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_models(hours: float = 24.0):
    store = _get_metrics_store()
    return {"models": store.by_model(hours)}


@app.get(
    "/api/metrics/llm-calls",
    response_model=LlmCallsResponse,
    tags=["Métricas"],
    summary="Últimas chamadas ao LLM",
    description="Últimas `limit` chamadas ao Ollama (tokens, duração, sucesso). Tabela do dashboard.",
    response_description="Lista decrescente por id",
    responses={
        200: {"description": "Últimas chamadas", "model": LlmCallsResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_llm_calls(limit: int = 50):
    store = _get_metrics_store()
    return {"calls": store.recent_llm_calls(limit)}


@app.get(
    "/api/metrics/requests-log",
    response_model=RequestLogResponse,
    tags=["Métricas"],
    summary="Últimas requisições de chat",
    description="Últimas `limit` requisições de chat (pergunta, evidências, tempo). Tabela do dashboard.",
    response_description="Lista decrescente por id",
    responses={
        200: {"description": "Últimas requisições", "model": RequestLogResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_requests_log(limit: int = 50):
    store = _get_metrics_store()
    return {"requests": store.recent_requests(limit)}


@app.get(
    "/api/metrics/documents",
    response_model=DocumentHistoryResponse,
    tags=["Métricas"],
    summary="Histórico de dados indexados",
    description="Snapshots de `documents/chunks/by_type`. Usado no gráfico Documentos Indexados.",
    response_description="Histórico de snapshots",
    responses={
        200: {"description": "Histórico de snapshots", "model": DocumentHistoryResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_documents():
    store = _get_metrics_store()
    return {"history": store.document_history()}


@app.get(
    "/api/metrics/index-events",
    response_model=IndexEventsResponse,
    tags=["Métricas"],
    summary="Eventos recentes de indexação",
    description="Últimos `limit` eventos de indexação (docs/chunks/erro). Tabela do dashboard.",
    response_description="Eventos recentes",
    responses={
        200: {"description": "Eventos recentes", "model": IndexEventsResponse},
        401: {"description": "Token de API inválido ou ausente", "model": AuthErrorResponse},
    },
)
async def metrics_index_events(limit: int = 50):
    store = _get_metrics_store()
    return {"events": store.recent_index_events(limit)}


def _custom_openapi():
    """Injeta securitySchemes (X-API-Token / Bearer) no OpenAPI — o middleware real valida, o Swagger só documenta."""
    from fastapi.openapi.utils import get_openapi

    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
        {
            "ApiToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Token",
                "description": "Token configurado em API_AUTH_TOKEN. Alternativa: Authorization: Bearer <token>. Isento em /api/health*, /docs, /redoc, /dashboard.",
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Mesmo token de API_AUTH_TOKEN via Authorization: Bearer",
            },
        }
    )
    # Aplica security global apenas em paths /api/* não isentos
    for path, methods in openapi_schema.get("paths", {}).items():
        if not path.startswith("/api/") or path in ("/api/health", "/api/health/ready"):
            continue
        for method in methods.values():
            if isinstance(method, dict) and "security" not in method:
                method["security"] = [{"ApiToken": []}, {"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[assignment]


@app.get("/", include_in_schema=False)
async def chat_page():
    # Rota raiz serve o Chat (interface premium). Funciona tanto em dev (cli/api.py) quanto em prod (api:app)
    candidates = [
        Path(__file__).resolve().parent.parent / "presentation" / "chat.html",
        Path(__file__).resolve().parent / "presentation" / "chat.html",
        Path("presentation/chat.html").resolve(),
        Path(__file__).resolve().parent.parent / "presentation" / "dashboard.html",
    ]
    for p in candidates:
        if p.exists():
            return FileResponse(str(p), media_type="text/html", headers={"Cache-Control": "no-store"})
    # último recurso: tenta via FileResponse direto do disco
    raise HTTPException(status_code=404, detail="Chat interface not found. Verifique presentation/chat.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    # Suporta tanto cli/api.py (cli/presentation) quanto raiz (presentation)
    p = Path(__file__).parent / "presentation" / "dashboard.html"
    if not p.exists():
        p = Path(__file__).resolve().parent.parent / "presentation" / "dashboard.html"
    return FileResponse(p)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=cfg.api_host, port=cfg.api_port)
