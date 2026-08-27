"""Reset total da aplicação: banco vetorial + documentos indexados.

Remove o banco vetorial (ChromaDB), o manifesto de indexação, os documentos
locais e a seleção do Google Drive, restaurando a aplicação ao estado inicial.

Uso:
    python reset_app.py            -> pede confirmação
    python reset_app.py --yes      -> executa sem pedir confirmação (start.sh / start.bat)
    python reset_app.py --no-docs  -> mantém os documentos, limpa só o vetorial
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from config import config
from ingestion.drive_sync import GoogleDriveSync
from utils.logger import setup_logger


def _confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [s/N]: ").strip().lower() in {"s", "sim", "y", "yes"}
    except EOFError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset total: banco vetorial + documentos indexados."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Executa sem pedir confirmação.",
    )
    parser.add_argument(
        "--no-docs",
        action="store_true",
        help="Mantém os documentos; limpa apenas o banco vetorial.",
    )
    args = parser.parse_args()

    cfg = config
    logger = setup_logger(
        name="ai_agent_reset",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )

    vector_db = Path(cfg.vector_db_dir)
    manifest_path = vector_db / "index_manifest.json"
    docs_dir = Path(cfg.documents_dir)
    drive_dir = Path(cfg.google_drive_dest_dir)
    selection_path = drive_dir / ".drive_selection.json"
    embedding_cache = Path(cfg.embedding_cache_path)
    image_dir = Path(cfg.image_dir)
    metrics_db = Path(cfg.metrics_db)

    print("== Reset total do Watson ==")
    print(f"  Banco vetorial : {vector_db}")
    print(f"  Manifesto      : {manifest_path}")
    print(f"  Cache emb.     : {embedding_cache}")
    print(f"  Imagens OCR    : {image_dir}")
    print(f"  Métricas       : {metrics_db}")
    if not args.no_docs:
        print(f"  Documentos     : {docs_dir}")
        print(f"  Google Drive   : {drive_dir} (inclui seleção)")
    print()

    if not args.yes:
        if not _confirm("Tem certeza que deseja apagar tudo?"):
            print("Cancelado.")
            return

    removed = {"chunks": 0, "manifest": 0, "docs": 0, "drive": 0, "cache": 0, "images": 0, "metrics": 0}

    # 1) Banco vetorial + manifesto (reutiliza o indexer quando possível)
    embeddings = None
    indexer = None
    try:
        from ingestion.embeddings import EmbeddingGenerator
        from ingestion.indexer import DocumentIndexer
        from ingestion.splitter import DocumentSplitter

        embeddings = EmbeddingGenerator(
            model_name=cfg.embedding_model,
            device=cfg.embedding_device,
            batch_size=cfg.embedding_batch_size,
            normalize=cfg.embedding_normalize,
            cache_path=cfg.embedding_cache_path,
            logger=logger,
        )
        indexer = DocumentIndexer(
            embedding_generator=embeddings,
            splitter=DocumentSplitter(
                chunk_size=cfg.chunk_size,
                chunk_overlap=cfg.chunk_overlap,
                logger=logger,
            ),
            chroma_persist_dir=cfg.vector_db_dir,
            batch_size=cfg.index_batch_size,
            logger=logger,
        )
        removed["chunks"] = indexer.clear_vectorstore()
    except Exception as e:
        logger.warning(f"Falha ao limpar via indexer, apagando diretório: {e}")
        if vector_db.exists():
            shutil.rmtree(vector_db, ignore_errors=True)

    # Garante que conexões SQLite sejam fechadas antes de tentar apagar (Windows trava arquivo aberto)
    if embeddings is not None:
        try:
            cache_obj = getattr(embeddings, "_cache", None) or getattr(embeddings, "_embedding_cache", None)
            if cache_obj is not None and hasattr(cache_obj, "close"):
                cache_obj.close()
        except Exception:
            pass
        # Força GC para liberar handle no Windows
        try:
            import gc

            gc.collect()
        except Exception:
            pass

    def _safe_unlink(p: Path, label: str) -> bool:
        if not p.exists():
            return False
        for attempt in range(3):
            try:
                p.unlink()
                return True
            except PermissionError as e:
                logger.warning(f"{label} em uso (tentativa {attempt+1}/3): {e}")
                time.sleep(0.5 * (attempt + 1))
                # Tenta fechar novamente se ainda houver handle
                if embeddings is not None:
                    try:
                        c = getattr(embeddings, "_cache", None)
                        if c:
                            c.close()
                    except Exception:
                        pass
                try:
                    import gc

                    gc.collect()
                except Exception:
                    pass
            except FileNotFoundError:
                return False
            except Exception as e:
                logger.warning(f"Falha ao remover {label}: {e}")
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
                return False
        # Última tentativa: renomeia e agenda remoção
        try:
            tmp = p.with_suffix(p.suffix + ".old")
            p.rename(tmp)
            logger.warning(f"{label} renomeado para {tmp} (será removido no próximo reinício)")
            return True
        except Exception as e:
            logger.warning(f"Não foi possível remover {label} (feche a API/watcher e tente novamente): {e}")
            print(f"[AVISO] {label} está em uso — feche a API (opção 1) e rode o reset novamente.")
            return False

    # 2) Caches regeneráveis: cache de embeddings, imagens OCR e métricas
    if _safe_unlink(embedding_cache, "Cache de embeddings"):
        removed["cache"] = 1
    if _safe_unlink(metrics_db, "Métricas"):
        removed["metrics"] = 1
    if image_dir.exists():
        for item in image_dir.rglob("*"):
            if item.is_file():
                removed["images"] += 1
        shutil.rmtree(image_dir, ignore_errors=True)

    # 3) Documentos locais: remove a pasta inteira (sem deixar lixo)
    if not args.no_docs and docs_dir.exists():
        for item in docs_dir.rglob("*"):
            if item.is_file():
                removed["docs"] += 1
        shutil.rmtree(docs_dir, ignore_errors=True)

    # 4) Google Drive sincronizado + seleção (se fora de documents/)
    if not args.no_docs:
        inside_docs = drive_dir.resolve().is_relative_to(docs_dir.resolve())
        if not inside_docs:
            if drive_dir.exists():
                for item in drive_dir.rglob("*"):
                    if item.is_file():
                        removed["drive"] += 1
                shutil.rmtree(drive_dir, ignore_errors=True)
            try:
                GoogleDriveSync(
                    folder_id=cfg.google_drive_folder_id or "",
                    dest_dir=cfg.google_drive_dest_dir,
                    logger=logger,
                    timeout=cfg.google_drive_sync_timeout,
                ).save_selection([])
            except Exception as e:
                logger.warning(f"Falha ao limpar seleção do Drive: {e}")
            if selection_path.exists():
                selection_path.unlink()

    print()
    print("Reset concluído:")
    print(f"  Banco vetorial: {removed['chunks']} chunks removidos")
    print(f"  Manifesto     : limpo")
    print(f"  Cache emb.    : {removed['cache']} arquivo removido")
    print(f"  Imagens OCR   : {removed['images']} arquivos removidos")
    print(f"  Métricas      : {removed['metrics']} arquivo removido")
    if not args.no_docs:
        print(f"  Documentos    : pasta {docs_dir} removida inteira "
              f"({removed['docs']} arquivos)")
        print(f"  Google Drive  : {removed['drive']} arquivos removidos")
        print(f"  Seleção Drive : limpa")
    print()
    print("Para reindexar tudo do zero: opção 4 (Drive + Index) do start.sh / start.bat.")


if __name__ == "__main__":
    main()