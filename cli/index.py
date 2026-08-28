import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, config
from core.factories import build_indexer, build_loader, ensure_directories
from ingestion.drive_sync import GoogleDriveSync
from ingestion.loader import LoadedDocument
from utils.logger import setup_logger


def run_index(cfg: Config, logger, sync_drive: bool = True) -> int:
    """Executa a indexação completa (Drive + documentos).

    Retorna o número de chunks indexados. `sync_drive=False` pula a
    sincronização do Google Drive (útil quando já foi feita).
    """
    logger.info("Starting indexing")
    print("Iniciando indexacao...")

    all_documents: List[LoadedDocument] = []

    if sync_drive and cfg.google_drive_folder_id:
        try:
            logger.info(
                f"Syncing Google Drive folder: {cfg.google_drive_folder_id}"
            )
            print("Sincronizando Google Drive...")
            drive_sync = GoogleDriveSync(
                folder_id=cfg.google_drive_folder_id,
                dest_dir=cfg.google_drive_dest_dir,
                logger=logger,
                timeout=cfg.google_drive_sync_timeout,
            )
            result = drive_sync.sync()
            logger.info(f"Google Drive sync: {result.as_dict()}")
            print(
                f"  Google Drive: {result.downloaded} baixados, "
                f"{result.skipped} ignorados, {result.failed} falhas"
            )
        except Exception as e:
            logger.error(f"Google Drive sync failed: {e}")
            print(f"  Google Drive: ERRO - {e}")

    loader = build_loader(cfg, logger)
    logger.info(f"Scanning documents in: {cfg.documents_dir}")
    file_docs = loader.load(cfg.documents_dir)
    logger.info(f"Found {len(file_docs)} file documents")
    all_documents.extend(file_docs)
    print(f"  Documentos: {len(file_docs)} arquivos encontrados")

    if not all_documents:
        logger.warning("No documents found to index")
        print("Nenhum documento encontrado para indexar.")
        return 0

    _, _, indexer = build_indexer(cfg, logger)

    has_pending, pending_list, stale_set = (
        indexer.has_pending_changes(all_documents)
    )

    if not has_pending:
        logger.info("All documents are up to date, nothing to index")
        print("Todos os documentos estao atualizados, nada a indexar.")
        return 0

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
    return chunks_added


def main() -> None:
    cfg = config
    ensure_directories(cfg)

    logger = setup_logger(
        name="ai_agent_indexer",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    try:
        run_index(cfg, logger, sync_drive=False)
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
