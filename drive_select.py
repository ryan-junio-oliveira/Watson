"""Seleção de pastas do Google Drive para indexação (modo CLI).

Navega pela árvore do Drive e salva a seleção persistida (`.drive_selection.json`),
o mesmo arquivo usado pela API `/api/drive/selection` e pelo sync.

Comandos no prompt:
    <n>       - entra na pasta de número n
    ..        - volta para a pasta anterior
    marcar    - inclui a pasta atual na seleção
    desmarcar - remove a pasta atual da seleção
    lista     - mostra a seleção atual
    limpar    - esvazia a seleção (sincroniza a raiz inteira)
    salvar    - persiste a seleção e sai
    sair      - sai sem salvar

Uso: `python drive_select.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

from config import config
from ingestion.drive_sync import DriveEntry, GoogleDriveSync, SelectedFolder
from utils.logger import setup_logger

HELP = (
    "\n<n> entra na pasta  |  .. volta  |  marcar/desmarcar  |  "
    "lista  |  limpar  |  salvar  |  sair"
)


def _print_entries(entries: list) -> None:
    folders = [e for e in entries if e.is_folder]
    files = [e for e in entries if not e.is_folder]
    if folders:
        print("  Pastas:")
        for i, e in enumerate(folders, 1):
            print(f"    [{i:>3}] {e.name}")
    if files:
        print("  Arquivos:")
        for i, e in enumerate(files, 1):
            print(f"    (   ) {e.name}")
    if not entries:
        print("  (vazia)")


def main() -> None:
    cfg = config
    if not cfg.google_drive_folder_id:
        print("ERRO: GOOGLE_DRIVE_FOLDER_ID nao configurado no .env.")
        sys.exit(1)

    logger = setup_logger(
        name="ai_agent_drive_select",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )
    drive = GoogleDriveSync(
        folder_id=cfg.google_drive_folder_id,
        dest_dir=cfg.google_drive_dest_dir,
        logger=logger,
        timeout=cfg.google_drive_sync_timeout,
    )

    selection = drive.load_selection()
    selected_ids = {s.folder_id for s in selection}

    stack: list[tuple[str, str]] = []  # (folder_id, path)
    current_id = cfg.google_drive_folder_id
    current_path = ""

    print("== Seleção de pastas do Google Drive ==")
    print(f"Raiz: {cfg.google_drive_folder_id}")
    print(HELP)
    print()

    while True:
        if stack:
            print(f"\nPasta atual: {current_path}")
        marker = " [SELECIONADA]" if current_id in selected_ids else ""
        print(f"-> {current_path or '(raiz)'}{marker}")

        try:
            entries = drive.list_folder(current_id)
        except Exception as e:
            print(f"  ERRO ao listar: {e}")
            if stack:
                current_id, current_path = stack.pop()
                continue
            break

        _print_entries(entries)
        folders = [e for e in entries if e.is_folder]

        try:
            cmd = input("\n>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue

        if cmd == "sair":
            print("Saindo sem salvar.")
            break

        if cmd == "salvar":
            drive.save_selection(
                [s for s in selection if s.folder_id in selected_ids]
            )
            print(f"Seleção salva: {len(selected_ids)} pasta(s).")
            break

        if cmd == "lista":
            if not selection:
                print("  (vazio - sincroniza a raiz inteira)")
            for s in selection:
                tag = "  [x]" if s.folder_id in selected_ids else "  [ ]"
                print(f"{tag} {s.path or s.folder_id}")
            continue

        if cmd == "limpar":
            selected_ids.clear()
            selection.clear()
            print("  Seleção esvaziada.")
            continue

        if cmd == "marcar":
            if current_id not in selected_ids:
                selected_ids.add(current_id)
                selection.append(SelectedFolder(folder_id=current_id, path=current_path))
                print(f"  Marcada: {current_path or '(raiz)'}")
            else:
                print("  Já está marcada.")
            continue

        if cmd == "desmarcar":
            if current_id in selected_ids:
                selected_ids.discard(current_id)
                selection = [
                    s for s in selection
                    if s.folder_id != current_id
                ]
                print(f"  Desmarcada: {current_path or '(raiz)'}")
            else:
                print("  Não está marcada.")
            continue

        if cmd == "..":
            if stack:
                current_id, current_path = stack.pop()
            else:
                print("  Já está na raiz.")
            continue

        if cmd.isdigit():
            idx = int(cmd)
            if 1 <= idx <= len(folders):
                target = folders[idx - 1]
                stack.append((current_id, current_path))
                current_id = target.entry_id
                current_path = f"{current_path}/{target.name}".strip("/")
            else:
                print("  Número inválido.")
            continue

        if cmd in {"help", "?"}:
            print(HELP)
            continue

        print(f"  Comando desconhecido: {cmd}")


if __name__ == "__main__":
    main()