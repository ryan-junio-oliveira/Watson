"""Sync do Google Drive + indexação direto via CLI (sem limite de 300s do PHP).

Fluxo:
1. Sincroniza as pastas selecionadas do Google Drive para `documents/drive`.
2. Indexa todos os documentos (Drive + locais + banco) nos vetores.

Uso: `python drive_index.py [--sync-only]`
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import config
from ingestion.drive_sync import GoogleDriveSync
from index import ensure_directories, run_index
from utils.logger import setup_logger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincroniza o Google Drive e indexa os documentos."
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Apenas sincroniza o Drive (sem indexar).",
    )
    args = parser.parse_args()

    cfg = config
    ensure_directories(cfg)

    logger = setup_logger(
        name="ai_agent_drive_index",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    if not cfg.google_drive_folder_id:
        logger.error(
            "GOOGLE_DRIVE_FOLDER_ID not configured. Add it to .env first."
        )
        print("ERRO: GOOGLE_DRIVE_FOLDER_ID nao configurado no .env.")
        sys.exit(1)

    print(f"== Google Drive sync (raiz {cfg.google_drive_folder_id}) ==")
    logger.info(f"Starting Drive sync: {cfg.google_drive_folder_id}")
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id,
        dest_dir=cfg.google_drive_dest_dir,
        logger=logger,
        timeout=cfg.google_drive_sync_timeout,
    )

    selection = drive.load_selection()
    if selection:
        print(
            f"  Pastas selecionadas: {len(selection)} "
            f"({', '.join(s.path or s.folder_id for s in selection[:5])}"
            f"{'...' if len(selection) > 5 else ''})"
        )
    else:
        print("  Selecao vazia -> sincronizando a pasta raiz inteira.")

    result = drive.sync()
    print(
        f"  Drive: {result.downloaded} baixados, {result.skipped} ignorados, "
        f"{result.failed} falhas, {result.removed} removidos "
        f"({result.bytes_downloaded / 1024 / 1024:.1f} MB)"
    )
    if result.errors:
        for err in result.errors[:20]:
            print(f"  ! {err}")
    logger.info(f"Drive sync done: {result.as_dict()}")

    if args.sync_only:
        print("\nSync concluido. Para indexar: python drive_index.py")
        return

    print("\n== Indexando documentos ==")
    run_index(cfg, logger, sync_drive=False)


if __name__ == "__main__":
    main()