"""Watcher de documentos — reindexação automática.

Monitora o diretório `documents/` (incluindo `documents/drive`) e executa a
indexação incremental sempre que houver arquivos novos, alterados ou removidos.

Não usa `watchdog`: faz um polling leve (hash de arquivos) a cada N segundos,
comparando com o último estado conhecido. Ideal para rodar junto com a API.

Uso:
    python watch.py [--interval 30]
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

from config import Config, config
from ingestion.embeddings import EmbeddingGenerator
from ingestion.indexer import DocumentIndexer
from ingestion.loader import DocumentLoader
from ingestion.splitter import DocumentSplitter
from utils.logger import setup_logger

# Extensões consideradas documentos (mesma regra do DocumentLoader).
SUPPORTED_EXTS = {
    ".pdf", ".txt", ".md", ".doc", ".docx", ".csv", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
}

STATE_FILE = "logs/.watch_state.json"


def ensure_directories(cfg: Config) -> None:
    Path(cfg.documents_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.vector_db_dir).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)


def snapshot(cfg: Config) -> Dict[str, Tuple[int, str]]:
    """Gera um estado dos arquivos: {caminho_relativo: (tamanho, hash_mtime)}.

    O hash usa size+mtime+nome (rápido, sem ler o conteúdo) para detectar
    mudanças de forma leve a cada poll.
    """
    state: Dict[str, Tuple[int, str]] = {}
    base = Path(cfg.documents_dir)

    if not base.exists():
        return state

    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        rel = str(path.relative_to(base)).replace("\\", "/")
        stat = path.stat()
        state[rel] = (stat.st_size, str(stat.st_mtime))

    return state


def load_state(cfg: Config) -> Dict[str, Tuple[int, str]]:
    import json

    path = Path(STATE_FILE)
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Formato: {"version": 1, "files": {rel: [size, mtime]}}
        return {k: (int(v[0]), str(v[1])) for k, v in raw.get("files", {}).items()}
    except Exception:
        return {}


def save_state(cfg: Config, state: Dict[str, Tuple[int, str]]) -> None:
    import json

    path = Path(STATE_FILE)
    payload = {"version": 1, "files": {k: [s, m] for k, (s, m) in state.items()}}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_once(cfg: Config, logger) -> int:
    """Executa a indexação incremental dos documentos locais.

    Retorna o número de chunks indexados.
    """
    embedding_generator = EmbeddingGenerator(
        model_name=cfg.embedding_model,
        device=cfg.embedding_device,
        batch_size=cfg.embedding_batch_size,
        normalize=cfg.embedding_normalize,
        cache_path=cfg.embedding_cache_path,
        logger=logger,
    )
    loader = DocumentLoader(
        logger=logger,
        ocr_lang=cfg.ocr_lang,
        ocr_dpi=cfg.ocr_dpi,
        ocr_min_text_chars=cfg.ocr_min_text_chars,
        tesseract_cmd=cfg.tesseract_cmd,
        image_dir=cfg.image_dir,
        vision_model=cfg.vision_model,
    )
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

    documents = loader.load(cfg.documents_dir)
    if not documents:
        logger.info("No documents found, nothing to index")
        return 0

    has_pending, pending_list, stale_set = indexer.has_pending_changes(documents)
    if not has_pending:
        logger.info("All documents up to date, nothing to index")
        return 0

    logger.info(
        f"Pending: {len(pending_list)} new/changed, {len(stale_set)} to remove"
    )
    print(
        f"[watch] {len(pending_list)} novos/alterados, "
        f"{len(stale_set)} removidos -> indexando..."
    )
    chunks = indexer.index(documents)
    logger.info(f"Indexing complete: {chunks} chunks")
    print(f"[watch] Indexacao concluida: {chunks} chunks.")
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Watcher de documentos do Watson")
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Intervalo de verificação em segundos (padrão: 30)",
    )
    args = parser.parse_args()

    cfg = config
    ensure_directories(cfg)

    logger = setup_logger(
        name="watson_watch",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    interval = max(5, args.interval)
    logger.info(f"Watcher iniciado (intervalo={interval}s, dir={cfg.documents_dir})")
    print(f"[watch] Monitorando {cfg.documents_dir} a cada {interval}s...")
    print("[watch] Pressione Ctrl+C para parar.")

    last_state = load_state(cfg)
    idle_cycles = 0

    try:
        while True:
            current = snapshot(cfg)
            changed = current != last_state

            if changed:
                print("[watch] Mudanca detectada nos documentos.")
                try:
                    run_once(cfg, logger)
                except Exception as e:
                    logger.exception(f"Watcher index failed: {e}")
                    print(f"[watch] Erro na indexacao: {e}")
                last_state = current
                save_state(cfg, current)
                idle_cycles = 0
            else:
                idle_cycles += 1

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[watch] Encerrando watcher.")
        logger.info("Watcher stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()