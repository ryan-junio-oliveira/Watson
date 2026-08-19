"""Utilidades compartilhadas de OCR (Tesseract).

Suporte multiplataforma:

- **Windows**: o `tesseract_cmd` (config/param) representa o **diretório** que
  contém o executável (ex.: `libs/tesseract`) ou o caminho completo do
  `tesseract.exe`. A resolução anexa `tesseract.exe` automaticamente.
- **Linux/macOS**: o Tesseract normalmente está no PATH (`/usr/bin/tesseract`).
  Se `tesseract_cmd` for um diretório, tentamos o binário `tesseract` dentro
  dele; se nada for encontrado, usamos o binário do PATH (deixamos "").
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytesseract

IS_WINDOWS = sys.platform == "win32"


def _project_root() -> Path:
    # Este arquivo está dentro de <raiz>/ingestion/adapters/.
    return Path(__file__).resolve().parent.parent.parent


def _resolve_platform_binary(directory: Path) -> Path | None:
    """Procura o binário do Tesseract dentro de um diretório, por plataforma."""
    if IS_WINDOWS:
        exe = directory / "tesseract.exe"
        return exe if exe.is_file() else None
    for name in ("tesseract", "tesseract.exe"):
        binary = directory / name
        if binary.is_file():
            return binary
    return None


def resolve_tesseract_cmd(tesseract_dir: str = "") -> str:
    """Resolve o caminho completo do executável do Tesseract.

    Ordem de prioridade:
    1. `tesseract_dir` informado (pode ser diretório OU o executável direto).
    2. Variável de ambiente `TESSERACT_CMD`.
    3. Padrão: `<raiz>/libs/tesseract`.
    4. Binário do PATH (`shutil.which`), principalmente no Linux.

    Retorna o caminho completo do executável. Se não for encontrado,
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
        binary = _resolve_platform_binary(path)
        if binary is not None:
            return str(binary)

    # Fallback multiplataforma: binário no PATH (comum no Linux/macOS)
    which = shutil.which("tesseract")
    if which:
        return which
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
            "O executável do Tesseract não pôde ser executado. "
            "No Linux: sudo apt install tesseract-ocr tesseract-ocr-por "
            "tesseract-ocr-eng"
        ) from exc