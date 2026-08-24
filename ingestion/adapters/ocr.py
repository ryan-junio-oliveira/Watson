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
    """Procura o binário do Tesseract dentro de um diretório, por plataforma.

    No Linux/macOS o `tesseract.exe` (formato Windows) é ignorado para evitar
    o erro "Exec format error" quando o executável do Windows está presente
    (ex.: em `libs/tesseract` copiado do projeto Windows).
    """
    if IS_WINDOWS:
        exe = directory / "tesseract.exe"
        return exe if exe.is_file() else None
    binary = directory / "tesseract"
    if binary.is_file():
        return binary
    return None


def resolve_tesseract_cmd(tesseract_dir: str = "") -> str:
    """Resolve o caminho completo do executável do Tesseract.

    Linux/macOS: prioriza o binário do PATH (`/usr/bin/tesseract`); o diretório
    `libs/tesseract` é ignorado (contém o `.exe` do Windows).

    Windows: usa `tesseract_dir`/`TESSERACT_CMD` ou `libs/tesseract/tesseract.exe`.

    Retorna o caminho completo do executável. Se não for encontrado,
    retorna "" (o pytesseract usa o binário do PATH).
    """
    if IS_WINDOWS:
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

    # Linux/macOS: binário no PATH (padrão de instalação via apt/dnf/pacman)
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