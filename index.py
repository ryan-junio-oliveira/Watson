import sys
from pathlib import Path
from typing import List

from config import Config, config
from ingestion.db_loader import DatabaseLoader
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader, LoadedDocument
from ingestion.splitter import DocumentSplitter
from utils.logger import setup_logger


def ensure_directories(cfg: Config) -> None:
    Path(cfg.documents_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.vector_db_dir).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)


def main() -> None:
    cfg = config
    ensure_directories(cfg)

    logger = setup_logger(
        name="ai_agent_indexer",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    logger.info("Starting indexing")
    print("Iniciando indexacao...")

    try:
        embedding_generator = EmbeddingGenerator(
            model_name=cfg.embedding_model,
            device=cfg.embedding_device,
            batch_size=cfg.embedding_batch_size,
            normalize=cfg.embedding_normalize,
            cache_path=cfg.embedding_cache_path,
            logger=logger,
        )

        all_documents: List[LoadedDocument] = []

        loader = DocumentLoader(
            logger=logger,
            ocr_lang=cfg.ocr_lang,
            ocr_dpi=cfg.ocr_dpi,
            ocr_min_text_chars=cfg.ocr_min_text_chars,
            tesseract_cmd=cfg.tesseract_cmd,
            image_dir=cfg.image_dir,
            vision_model=cfg.vision_model,
        )
        logger.info(f"Scanning documents in: {cfg.documents_dir}")
        file_docs = loader.load(cfg.documents_dir)
        logger.info(f"Found {len(file_docs)} file documents")
        all_documents.extend(file_docs)
        print(f"  Documentos: {len(file_docs)} arquivos encontrados")

        if cfg.db_connection_string:
            try:
                db_loader = DatabaseLoader(
                    connection_string=cfg.db_connection_string,
                    tables=cfg.db_tables,
                    logger=logger,
                )
                logger.info("Loading data from database...")
                db_docs = db_loader.load()
                logger.info(f"Loaded {len(db_docs)} records from database")
                all_documents.extend(db_docs)
                print(f"  Banco de dados: {len(db_docs)} registros carregados")
            except Exception as e:
                logger.error(f"Database loading failed: {e}")
                print(f"  Banco de dados: ERRO - {e}")
        else:
            logger.info("No database configured, skipping database")
            print("  Banco de dados: nao configurado, pulando")

        if not all_documents:
            logger.warning("No documents found to index")
            print("Nenhum documento encontrado para indexar.")
            return

        splitter = DocumentSplitter(
            chunk_size=cfg.chunk_size,
            chunk_overlap=cfg.chunk_overlap,
            logger=logger,
        )

        indexer = DocumentIndexer(
            embedding_generator=embedding_generator,
            splitter=splitter,
            chroma_persist_dir=cfg.vector_db_dir,
            batch_size=cfg.index_batch_size,
            logger=logger,
        )

        has_pending, pending_list, stale_set = (
            indexer.has_pending_changes(all_documents)
        )

        if not has_pending:
            logger.info("All documents are up to date, nothing to index")
            print("Todos os documentos estao atualizados, nada a indexar.")
            return

        logger.info(
            f"Pending: {len(pending_list)} new/changed, "
            f"{len(stale_set)} to remove"
        )
        print(
            f"  Pendentes: {len(pending_list)} novos/alterados, "
            f"{len(stale_set)} para remover"
        )

        chunks_added = indexer.index(all_documents)
        logger.info(f"Indexing complete: {chunks_added} chunks indexed")
        print(f"Indexacao concluida: {chunks_added} chunks indexados.")

    except FileNotFoundError as e:
        logger.error(str(e))
        print(f"Erro: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
