"""Utilidades compartilhadas de OCR (Tesseract).

O valor de `tesseract_cmd` (config/param) representa o **diretório** que contém
o executável do Tesseract (ex.: `libs/tesseract`), não o caminho completo do
`.exe`. A resolução anexa `tesseract.exe` automaticamente.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytesseract


def _project_root() -> Path:
    # Este arquivo está dentro de <raiz>/ingestion/adapters/.
    return Path(__file__).resolve().parent.parent.parent


def resolve_tesseract_cmd(tesseract_dir: str = "") -> str:
    """Resolve o caminho completo do `tesseract.exe`.

    Ordem de prioridade:
    1. `tesseract_dir` informado (pode ser diretório OU o .exe direto).
    2. Variável de ambiente `TESSERACT_CMD`.
    3. Padrão: `<raiz>/libs/tesseract`.

    Retorna o caminho completo do `tesseract.exe`. Se não for encontrado,
    retorna "" (o pytesseract usa o binário do PATH).
    """
    candidates: list = []
    if tesseract_dir:
        candidates.append(tesseract_dir)
    env = os.getenv("TESSERACT_CMD", "")
    if env:
        candidates.append(env)
    candidates.append(str(_project_root() / "libs" / "tesseract"))

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():  # já é o executável
            return str(path)
        exe = path / "tesseract.exe"
        if exe.is_file():
            return str(exe)
    return ""


def configure_tesseract(tesseract_dir: str = "") -> str:
    """Configura o Tesseract no pytesseract e retorna o caminho usado."""
    resolved = resolve_tesseract_cmd(tesseract_dir)
    if resolved:
        pytesseract.pytesseract.tesseract_cmd = resolved
    return resolved


def verify_tesseract() -> None:
    """Valida se o Tesseract está funcionando."""
    configure_tesseract()
    try:
        version = pytesseract.get_tesseract_version()
        print(f"Tesseract: {pytesseract.pytesseract.tesseract_cmd}")
        print(f"Versão: {version}")
    except Exception as exc:
        raise RuntimeError(
            "O tesseract.exe não pôde ser executado."
        ) from exc