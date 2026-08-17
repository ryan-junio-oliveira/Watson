"""Modelos de domínio da pipeline de indexação.

Representa a etapa intermediária rica entre a extração da fonte e o chunking.
O objetivo é **não** reduzir a fonte a uma string antes que toda a estrutura
(páginas, seções, tabelas, imagens) tenha sido preservada.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def sha256_text(content: str) -> str:
    """Hash SHA-256 estável do conteúdo textual (UTF-8)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_file(filepath: str, chunk_size: int = 65536) -> str:
    """Hash SHA-256 do conteúdo binário de um arquivo."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_document_id(source_type: str, source_id: str) -> str:
    """Gera um ID de documento estável e determinístico a partir da origem."""
    raw = f"{source_type}::{source_id}"
    return "doc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def compute_source_id(source_type: str, source_id: str) -> str:
    """Gera um ID de fonte estável (usado pelo retrieval e versionamento)."""
    raw = f"{source_type}::{source_id}"
    return "src_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class Page:
    """Página de um documento, preservando texto (nativo ou OCR)."""

    number: int
    text: str = ""
    ocr: bool = False


@dataclass
class Section:
    """Seção detectada a partir de headings/estrutura do documento."""

    heading: str = ""
    level: int = 1
    page: Optional[int] = None
    content: str = ""


@dataclass
class Table:
    """Tabela extraída da fonte, preservando estrutura tabular."""

    page: Optional[int] = None
    section: str = ""
    markdown: str = ""
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)


@dataclass
class ImageRef:
    """Referência a uma imagem dentro do documento (não o conteúdo binário)."""

    image_id: str = ""
    page: Optional[int] = None
    section: str = ""
    storage_path: str = ""
    kind: str = "unknown"
    caption: str = ""
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class LoadedDocument:
    """Documento carregado de uma fonte, preservando estrutura.

    Os 6 primeiros campos são mantidos por compatibilidade com o pipeline
    legado (splitter/indexer consomem `content`, `filepath`, etc.).
    Os campos ricos são preenchidos pelos adapters de origem.
    """

    content: str
    filepath: str
    filename: str
    file_type: str
    modified_at: str
    file_size: int

    source_type: str = ""
    source_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    pages: List[Page] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    images: List[ImageRef] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.source_type:
            self.source_type = self.file_type.lstrip(".") or "unknown"
        if not self.source_id:
            self.source_id = self.filepath
        if not self.content_hash:
            self.content_hash = sha256_text(self.content)

    @property
    def document_id(self) -> str:
        return compute_document_id(self.source_type, self.source_id)

    @property
    def source_key(self) -> str:
        """Chave única da fonte (persistida no manifest/controle)."""
        return compute_source_id(self.source_type, self.source_id)
