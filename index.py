import sys
from pathlib import Path

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
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

    logger.info("Starting document indexing")

    try:
        loader = DocumentLoader(logger=logger)
        splitter = DocumentSplitter(
            chunk_size=cfg.chunk_size,
            chunk_overlap=cfg.chunk_overlap,
            logger=logger,
        )
        embedding_generator = EmbeddingGenerator(
            model_name=cfg.embedding_model
        )

        logger.info(f"Scanning documents in: {cfg.documents_dir}")
        documents = loader.load(cfg.documents_dir)
        logger.info(f"Found {len(documents)} documents")

        if not documents:
            logger.warning("No documents found to index")
            return

        indexer = DocumentIndexer(
            embedding_generator=embedding_generator,
            splitter=splitter,
            chroma_persist_dir=cfg.vector_db_dir,
            batch_size=cfg.index_batch_size,
            logger=logger,
        )

        has_pending, pending_list, stale_set = (
            indexer.has_pending_changes(documents)
        )

        if not has_pending:
            logger.info("All documents are up to date, nothing to index")
            return

        logger.info(
            f"Pending: {len(pending_list)} new/changed, "
            f"{len(stale_set)} to remove"
        )

        chunks_added = indexer.index(documents)
        logger.info(f"Indexing done: {chunks_added} chunks indexed")

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
