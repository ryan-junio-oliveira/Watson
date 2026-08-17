"""Contrato estável entre Indexer e Retriever/Chat.

Define o esquema de metadata que cada chunk carrega no vector store e o
versionamento da pipeline (§4, §15, §24). O Chat/API não deve conhecer
detalhes internos de parsing/embedding — apenas este contrato.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Chaves obrigatórias/esperadas do contrato de metadata por chunk (§24).
CHUNK_METADATA_KEYS: List[str] = [
    "chunk_id",
    "document_id",
    "source_id",
    "source_type",
    "manufacturer",
    "model",
    "device_type",
    "document_type",
    "section",
    "subsection",
    "page_start",
    "page_end",
    "error_codes",
    "version",
    "language",
    "source_priority",
    "content_hash",
    "parser_version",
    "chunking_version",
    "embedding_model",
    "embedding_version",
    "chunk_index",
    "total_chunks",
]

# Campos com valor "vazio" não devem ser persistidos para não poluir o índice.
_EMPTY_VALUES: tuple = ("", None, [], {})


def clean_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove campos vazios, normalizando o dict para persistência."""
    return {k: v for k, v in data.items() if v not in _EMPTY_VALUES}


@dataclass
class PipelineVersion:
    """Versão da pipeline que produziu um documento/chunk (§15).

    Se qualquer campo mudar, o conteúdo indexado pode ficar incompatível e
    precisa ser reindexado.
    """

    parser_version: str = "1.0"
    chunking_version: str = "1.0"
    embedding_model: str = ""
    embedding_version: str = ""

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)

    def signature(self) -> str:
        """Hash da combinação de versões — chave de decisão de reindexação."""
        return "|".join(
            [self.parser_version, self.chunking_version,
             self.embedding_model, self.embedding_version]
        )


@dataclass
class ChunkContract:
    """Chunk pronto para retrieval, segundo o contrato estável (§4)."""

    chunk_id: str
    document_id: str
    content: str
    source_type: str

    manufacturer: str = ""
    model: str = ""
    device_type: str = ""
    document_type: str = ""
    section: str = ""
    subsection: str = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    error_codes: List[str] = field(default_factory=list)
    version: str = ""
    language: str = ""
    source_priority: int = 100

    content_hash: str = ""
    source_id: str = ""
    filename: str = ""

    parser_version: str = ""
    chunking_version: str = ""
    embedding_model: str = ""
    embedding_version: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        """Serializa o contrato em metadata plana para o vector store."""
        data = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "device_type": self.device_type,
            "document_type": self.document_type,
            "section": self.section,
            "subsection": self.subsection,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "error_codes": self.error_codes,
            "version": self.version,
            "language": self.language,
            "source_priority": self.source_priority,
            "content_hash": self.content_hash,
            "filename": self.filename,
            "parser_version": self.parser_version,
            "chunking_version": self.chunking_version,
            "embedding_model": self.embedding_model,
            "embedding_version": self.embedding_version,
        }
        data.update(self.metadata)
        return clean_metadata(data)

    @classmethod
    def from_metadata(cls, metadata: Dict[str, Any], content: str = "") -> ChunkContract:
        """Reconstrói o contrato a partir de metadata persistida."""
        meta = metadata or {}
        return cls(
            chunk_id=str(meta.get("chunk_id", "")),
            document_id=str(meta.get("document_id", "")),
            content=content or str(meta.get("content", "")),
            source_type=str(meta.get("source_type", "unknown")),
            manufacturer=str(meta.get("manufacturer", "")),
            model=str(meta.get("model", "")),
            device_type=str(meta.get("device_type", "")),
            document_type=str(meta.get("document_type", "")),
            section=str(meta.get("section", "")),
            subsection=str(meta.get("subsection", "")),
            page_start=meta.get("page_start"),
            page_end=meta.get("page_end"),
            error_codes=list(meta.get("error_codes", [])),
            version=str(meta.get("version", "")),
            language=str(meta.get("language", "")),
            source_priority=int(meta.get("source_priority", 100)),
            content_hash=str(meta.get("content_hash", "")),
            source_id=str(meta.get("source_id", "")),
            filename=str(meta.get("filename", "")),
            parser_version=str(meta.get("parser_version", "")),
            chunking_version=str(meta.get("chunking_version", "")),
            embedding_model=str(meta.get("embedding_model", "")),
            embedding_version=str(meta.get("embedding_version", "")),
            metadata={k: v for k, v in meta.items()
                      if k not in CHUNK_METADATA_KEYS},
        )


@dataclass
class IndexingManifest:
    """Manifesto de indexação por documento (§27)."""

    document_id: str
    filename: str
    source_id: str
    source_type: str
    content_hash: str
    parser_version: str
    chunking_version: str
    embedding_model: str
    embedding_version: str
    indexed_at: str
    chunks: int
    status: str = "completed"
    pages: int = 0
    ocr_pages: int = 0
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IndexingManifest:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
