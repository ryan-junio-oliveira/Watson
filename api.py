import logging
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

from config import Config, config as app_config
from ingestion.db_loader import DatabaseLoader
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
from ingestion.splitter import DocumentSplitter
from llm.ollama_client import OllamaClient
from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.reranker import Reranker
from rag.retriever import Retriever
from utils.logger import setup_logger


class ChatRequest(BaseModel):
    question: str = Field(
        ..., description="Pergunta do usuário", examples=["Quais servidores estão cadastrados?"]
    )
    history: Optional[List[dict]] = Field(
        None, description="Histórico da conversa para contexto",
        examples=[[{"role": "user", "content": "Olá"}, {"role": "assistant", "content": "Olá! Como posso ajudar?"}]]
    )
    model: Optional[str] = Field(None, description="Modelo Ollama a ser usado", examples=["qwen3:8b"])


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Resposta gerada pelo Watson", examples=["Existem 5 servidores cadastrados."])


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


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Mensagem de erro")


logger: logging.Logger = None
chatbot: ChatBot = None
embedding_generator: EmbeddingGenerator = None
splitter: DocumentSplitter = None
indexer: DocumentIndexer = None
retriever: Retriever = None
ollama_client: OllamaClient = None
cfg: Config = None


def build_chatbot(cfg: Config, _logger: logging.Logger) -> ChatBot:
    _embedding_generator = EmbeddingGenerator(model_name=cfg.embedding_model, device=cfg.embedding_device)
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
    _reranker = (
        Reranker(
            model_name=cfg.reranker_model,
            device=cfg.embedding_device,
            logger=_logger,
        )
        if cfg.use_reranker
        else None
    )
    return ChatBot(
        retriever=_retriever,
        prompt_builder=_prompt_builder,
        ollama_client=_ollama_client,
        reranker=_reranker,
        logger=_logger,
    )


def build_indexer(cfg: Config, _logger: logging.Logger):
    _embedding_generator = EmbeddingGenerator(model_name=cfg.embedding_model, device=cfg.embedding_device)
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
    global logger, chatbot, embedding_generator, splitter, indexer, retriever, ollama_client, cfg

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

    yield

    logger.info("Shutting down Watson API server")


app = FastAPI(
    title="Watson RAG API",
    description="""
    API de Retrieval-Augmented Generation (RAG) para indexação de documentos e
    consultas inteligentes com modelos LLM via Ollama.

    ## Funcionalidades
    - **Chat**: Faça perguntas sobre documentos indexados
    - **Indexação**: Indexe documentos (PDF, TXT, DOCX, etc.) e dados de banco MySQL
    - **Upload**: Envie novos documentos para indexação
    - **Saúde**: Monitore o status da API e componentes
    """,
    version="1.0.0",
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


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["Monitoramento"],
    summary="Verificar status da API",
    response_description="Status atual da API e seus componentes",
    responses={
        200: {"description": "API funcionando normalmente", "model": HealthResponse},
    },
)
async def health():
    """Retorna o status da API, incluindo diretórios configurados e modelo Ollama."""
    global cfg
    return HealthResponse(
        status="ok",
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
    """Lista todos os modelos disponíveis no servidor Ollama.

    Em caso de falha de conexão, retorna apenas o modelo configurado como fallback.
    """
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
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Fazer uma pergunta ao Watson",
    response_description="Resposta gerada pelo modelo LLM com base nos documentos indexados",
    responses={
        200: {"description": "Resposta gerada com sucesso", "model": ChatResponse},
        400: {"description": "Pergunta inválida ou vazia", "model": ErrorResponse},
        503: {"description": "Chatbot não foi inicializado", "model": ErrorResponse},
    },
)
async def chat(request: ChatRequest):
    """Envia uma pergunta para o Watson e obtém uma resposta baseada nos documentos indexados.

    Opcionalmente, envie `history` com o histórico da conversa para manter contexto.
    """
    global chatbot, logger

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
            answer = chatbot.ask_with_context(question, context)
        else:
            answer = chatbot.ask(question)

        return ChatResponse(answer=answer)
    except Exception as e:
        logger.exception(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """Indexa **documentos** e **banco de dados** simultaneamente.

    Apenas arquivos novos ou modificados desde a última indexação são processados.
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
    """Indexa **apenas documentos** (PDF, TXT, DOCX, etc.) do diretório configurado."""
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
    """Indexa **apenas o banco de dados MySQL** conectado.

    Requer `DB_CONNECTION_STRING` configurado no `.env`.
    """
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
            loader = DocumentLoader(logger=logger)
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
async def upload_document(file: UploadFile = File(..., description="Arquivo a ser enviado (PDF, TXT, DOCX, etc.)")):
    """Faz upload de um documento para o diretório de documentos.

    Após o upload, execute `/api/index/documents` para indexá-lo.
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
    """Remove **todos** os documentos e limpa o banco vetorial ChromaDB.

    Após executar, será necessário reindexar os documentos com `/api/index/documents`.
    """
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
    """Remove **apenas os arquivos de documentos** do diretório.

    O banco vetorial permanece intacto (chunks órfãos).
    """
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
    """Remove **apenas o banco vetorial ChromaDB**.

    Os arquivos de documentos permanecem no diretório.
    """
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
