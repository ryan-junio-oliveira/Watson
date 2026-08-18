import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

from config import Config, config as app_config
from ingestion.db_loader import DatabaseLoader
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
from ingestion.splitter import DocumentSplitter
from llm.ollama_client import OllamaClient
from presentation.formatter import ApiFormatter
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.reranker import Reranker as RagReranker
from rag.response import Mode
from rag.retriever import Retriever
from tools.sql_tool import SqlQueryTool
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
        description="Modo de consulta. `auto` e `rag` são equivalentes: "
                    "ambos respondem com base nos documentos e dados indexados (RAG). "
                    "Modos: auto | rag.",
        examples=["auto", "rag"],
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
    db_indexed: int = Field(0, description="Quantidade de registros do banco indexados")
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
    db_configured: bool = Field(..., description="Se o banco MySQL está configurado")
    ollama_model: str = Field(..., description="Modelo Ollama em uso")


class ModelListResponse(BaseModel):
    models: List[str] = Field(..., description="Lista de modelos disponíveis no Ollama")


logger: logging.Logger = None
chatbot: ChatBot = None
embedding_generator: EmbeddingGenerator = None
splitter: DocumentSplitter = None
indexer: DocumentIndexer = None
retriever: Retriever = None
ollama_client: OllamaClient = None
cfg: Config = None
api_formatter: ApiFormatter = None


def _preload_models(_chatbot: ChatBot, _emb_gen, _logger) -> None:
    _emb_gen.get_embeddings()
    if _chatbot._rag_reranker is not None:
        _chatbot._rag_reranker._load_model()


def build_chatbot(cfg: Config, _logger: logging.Logger) -> ChatBot:
    _embedding_generator = EmbeddingGenerator(
        model_name=cfg.embedding_model,
        device=cfg.embedding_device,
        batch_size=cfg.embedding_batch_size,
        normalize=cfg.embedding_normalize,
        cache_path=cfg.embedding_cache_path,
        logger=_logger,
    )
    _retriever = Retriever(
        embedding_generator=_embedding_generator,
        chroma_persist_dir=cfg.vector_db_dir,
        top_k=cfg.top_k,
        similarity_threshold=cfg.similarity_threshold,
        use_mmr=cfg.use_mmr,
        mmr_fetch_k=cfg.mmr_fetch_k,
        mmr_lambda=cfg.mmr_lambda,
        logger=_logger,
    )
    _prompt_builder = PromptBuilder()
    _ollama_client = OllamaClient(
        model=cfg.ollama_model,
        base_url=cfg.ollama_base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        request_timeout=cfg.ollama_timeout,
        logger=_logger,
    )
    _rag_reranker = (
        RagReranker(
            model_name=cfg.reranker_model,
            device=cfg.embedding_device,
            logger=_logger,
        )
        if cfg.use_reranker
        else None
    )
    _sql_tool = (
        SqlQueryTool(
            connection_string=cfg.db_connection_string,
            tables=cfg.db_tables,
            max_rows=cfg.db_max_rows_per_query,
            logger=_logger,
        )
        if cfg.db_connection_string
        else None
    )
    return ChatBot(
        retriever=_retriever,
        prompt_builder=_prompt_builder,
        ollama_client=_ollama_client,
        reranker=_rag_reranker,
        sql_tool=_sql_tool,
        logger=_logger,
    )


def build_indexer(cfg: Config, _logger: logging.Logger):
    _embedding_generator = EmbeddingGenerator(
        model_name=cfg.embedding_model,
        device=cfg.embedding_device,
        batch_size=cfg.embedding_batch_size,
        normalize=cfg.embedding_normalize,
        cache_path=cfg.embedding_cache_path,
        logger=_logger,
    )
    _splitter = DocumentSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        logger=_logger,
    )
    _indexer = DocumentIndexer(
        embedding_generator=_embedding_generator,
        splitter=_splitter,
        chroma_persist_dir=cfg.vector_db_dir,
        batch_size=cfg.index_batch_size,
        logger=_logger,
    )
    return _embedding_generator, _splitter, _indexer


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

    chatbot = build_chatbot(cfg, logger)
    embedding_generator, splitter, indexer = build_indexer(cfg, logger)

    logger.info("Preloading models...")
    _preload_models(chatbot, embedding_generator, logger)
    logger.info("Models loaded successfully")

    api_formatter = ApiFormatter()

    yield

    logger.info("Shutting down Watson API server")


app = FastAPI(
    title="Watson RAG API",
    description="""
    API de Retrieval-Augmented Generation (RAG) para indexação de documentos,
    imagens e dados de banco, com consultas inteligentes via LLM (Ollama).

    ## Arquitetura (Knowledge Ingestion & Indexing Pipeline)
    O Watson transforma fontes de conhecimento em uma base pesquisável:

    1. **Ingestão** — adapters por fonte (PDF com OCR seletivo, DOCX, CSV, XLSX,
       TXT, imagens e banco de dados), extraindo estrutura (páginas, seções,
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
    - **Chat**: perguntas sobre documentos e banco indexados (RAG).
    - **Streaming (SSE)**: tokens da resposta em tempo real + metadados finais.
    - **Indexação**: `POST /api/index` (documentos + banco), com endpoints
      separados para documentos e banco; respeita `DB_MODE` (rag | sql | both).
    - **Upload**: envie novos documentos (PDF, TXT, DOCX, XLSX, CSV, imagens).
    - **Reindexação**: incremental por hash/versão; use `DELETE` de fontes via
      limpeza ou reindexação controlada.
    - **OCR seletivo**: Tesseract aplicado apenas em páginas sem texto nativo.
    - **Saúde**: status da API e dependências.

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
    version="3.0.0",
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())[:8]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["Monitoramento"],
    summary="Verificar status da API",
    response_description="Status atual da API e seus componentes",
    responses={
        200: {"description": "API funcionando normalmente", "model": HealthResponse},
        503: {"description": "Ollama ou dependências indisponíveis", "model": ErrorResponse},
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
        db_configured=bool(cfg.db_connection_string),
        ollama_model=cfg.ollama_model,
    )


@app.get(
    "/api/models",
    response_model=ModelListResponse,
    tags=["Modelos"],
    summary="Listar modelos Ollama disponíveis",
    response_description="Lista de nomes dos modelos disponíveis",
    responses={
        200: {"description": "Modelos listados com sucesso", "model": ModelListResponse},
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
    response_description="Resposta gerada com sucesso no formato padronizado",
    responses={
        200: {"description": "Resposta gerada com sucesso", "model": ChatSuccessResponse},
        400: {"description": "Pergunta inválida ou vazia", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ChatErrorResponse},
        503: {"description": "Chatbot não foi inicializado", "model": ErrorResponse},
    },
)
async def chat(request: ChatRequest, req: Request):
    """Responde uma pergunta usando RAG (documentos + banco indexados).

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
            result = chatbot.ask_with_context(question, context, mode=request.mode)
        else:
            result = chatbot.ask(question, mode=request.mode)

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
        400: {"description": "Pergunta inválida ou vazia"},
        503: {"description": "Chatbot não foi inicializado"},
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
                chatbot.ask_stream_with_history(question, context, mode=request.mode)
                if request.history
                else chatbot.ask_stream(question, mode=request.mode)
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


@app.post(
    "/api/index",
    response_model=IndexResponse,
    tags=["Indexação"],
    summary="Indexar documentos e banco de dados",
    response_description="Resultado da indexação incluindo documentos e chunks processados",
    responses={
        200: {"description": "Indexação concluída", "model": IndexResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_all():
    """Indexa documentos e banco de forma incremental (por hash/versão).

    Processa apenas documentos/registros alterados ou novos. Respeita
    `DB_MODE`: em `sql`, os dados do banco são consultados via SQL Tool e não
    são indexados em embeddings.
    """
    return await _run_index(index_documents=True, index_database=True)


@app.post(
    "/api/index/documents",
    response_model=IndexResponse,
    tags=["Indexação"],
    summary="Indexar apenas documentos",
    response_description="Resultado da indexação de documentos",
    responses={
        200: {"description": "Indexação concluída", "model": IndexResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_documents():
    """Indexa apenas documentos (PDF, DOCX, CSV, XLSX, TXT, imagens) do
    diretório configurado, com OCR seletivo e incremental por hash."""
    return await _run_index(index_documents=True, index_database=False)


@app.post(
    "/api/index/database",
    response_model=IndexResponse,
    tags=["Indexação"],
    summary="Indexar apenas banco de dados",
    response_description="Resultado da indexação do banco de dados",
    responses={
        200: {"description": "Indexação concluída", "model": IndexResponse},
        400: {"description": "Banco de dados não configurado", "model": ErrorResponse},
        503: {"description": "Indexador não foi inicializado", "model": ErrorResponse},
    },
)
async def index_database():
    """Indexa registros do banco (tabelas úteis configuradas) como conhecimento
    RAG. Em `DB_MODE=sql`, não indexa — dados são consultados via SQL Tool."""
    return await _run_index(index_documents=False, index_database=True)


async def _run_index(index_documents: bool, index_database: bool) -> IndexResponse:
    global indexer, embedding_generator, splitter, logger, cfg

    if not indexer:
        raise HTTPException(status_code=503, detail="Indexer not initialized")

    total_chunks = 0
    docs_indexed = 0
    db_indexed = 0

    if index_documents:
        try:
            loader = DocumentLoader(
                logger=logger,
                ocr_lang=cfg.ocr_lang,
                ocr_dpi=cfg.ocr_dpi,
                ocr_min_text_chars=cfg.ocr_min_text_chars,
                tesseract_cmd=cfg.tesseract_cmd,
                image_dir=cfg.image_dir,
                vision_model=cfg.vision_model,
            )
            documents = loader.load(cfg.documents_dir)

            if documents:
                has_pending, pending_list, stale_set = (
                    indexer.has_pending_changes(documents)
                )
                if has_pending:
                    chunks = indexer.index(documents)
                    total_chunks += chunks
                    docs_indexed = len(pending_list)
                    logger.info(f"Indexed {chunks} chunks from {len(pending_list)} documents")
                else:
                    logger.info("All documents are up to date")
        except Exception as e:
            logger.exception(f"Document indexing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if index_database:
        try:
            if not cfg.db_connection_string:
                raise HTTPException(
                    status_code=400,
                    detail="Database not configured. Set DB_CONNECTION_STRING in config.",
                )

            if cfg.db_mode == "sql":
                # §12: dados estruturados são consultados via SQL Tool,
                # não são transformados em embeddings.
                logger.info("DB_MODE=sql: skipping RAG indexing of database records")
                return IndexResponse(
                    status="ok",
                    documents_indexed=docs_indexed,
                    db_indexed=0,
                    total_chunks=total_chunks,
                )

            loader = DatabaseLoader(
                connection_string=cfg.db_connection_string,
                tables=cfg.db_tables,
                logger=logger,
            )
            db_documents = loader.load()

            if db_documents:
                chunks = indexer.index(db_documents)
                total_chunks += chunks
                db_indexed = len(db_documents)
                logger.info(f"Indexed {chunks} chunks from {len(db_documents)} database records")
            else:
                logger.info("No database records to index")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Database indexing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return IndexResponse(
        status="ok",
        documents_indexed=docs_indexed,
        db_indexed=db_indexed,
        total_chunks=total_chunks,
    )


@app.post(
    "/api/documents/upload",
    response_model=DocUploadResponse,
    tags=["Documentos"],
    summary="Fazer upload de documento",
    response_description="Resultado do upload com nome e tamanho do arquivo",
    responses={
        200: {"description": "Upload realizado com sucesso", "model": DocUploadResponse},
        400: {"description": "Nenhum arquivo enviado", "model": ErrorResponse},
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
    response_description="Resultado da limpeza",
    responses={
        200: {"description": "Memória limpa com sucesso", "model": ClearResponse},
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
    response_description="Resultado da limpeza de documentos",
    responses={
        200: {"description": "Documentos removidos", "model": ClearResponse},
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
    response_description="Resultado da limpeza do banco vetorial",
    responses={
        200: {"description": "Banco vetorial limpo", "model": ClearResponse},
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
        logger.info(f"Clear completed: {docs_removed} docs, {vec_removed} vectorstore files")
        return ClearResponse(
            status="ok",
            documents_removed=docs_removed,
            vectorstore_files_removed=vec_removed,
        )
    except Exception as e:
        logger.exception(f"Clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=cfg.api_host, port=cfg.api_port)
