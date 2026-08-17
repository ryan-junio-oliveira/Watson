"""Chunking específico por tipo de fonte (§23, §24, §28).

Substitui o `RecursiveCharacterTextSplitter` uniforme por uma estratégia de
chunking semântico baseado em blocos:

- **PDF/DOCX/Markdown**: blocos por heading (seções), tabelas e texto.
  Procedimentos técnicos permanecem semanticamente completos.
- **CSV/XLSX**: cada tabela é um bloco, preservando a estrutura tabular.
- **Banco/imagem**: bloco único (registro/documento curto).
- **Blocos maiores que `chunk_size`**: split recursivo respeitando tamanho/overlap.

Cada chunk carrega metadata rica seguindo o `ChunkContract` (§4/§24) além das
chaves legadas (`source`, `filename`, `file_type`, ...) usadas pelo indexer e
retriever atuais.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.contracts import ChunkContract
from ingestion.loader import LoadedDocument
from ingestion.models import sha256_text

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
PAGE_MARKER_RE = re.compile(r"^\[Página\s+(\d+)\]$")
OCR_MARKER_RE = re.compile(r"^\[OCR\]$")
ERROR_CODE_RE = re.compile(
    r"\b(?:ERR|ERROR|E|ER|COD(?:E|IGO))[-\s]?\d{2,4}\b", re.IGNORECASE
)
MARKDOWN_EMPHASIS_RE = re.compile(r"[*_`#]")

PARSER_VERSION = "1.1"
CHUNKING_VERSION = "2.0"


@dataclass
class Block:
    """Unidade de conteúdo usada para montar chunks semanticamente."""

    kind: str  # heading | text | table
    text: str
    level: int = 0
    section: str = ""
    page: Optional[int] = None


def clean_heading(text: str) -> str:
    """Remove marcadores markdown de um heading para metadata limpa."""
    return MARKDOWN_EMPHASIS_RE.sub("", text).strip()


def detect_error_codes(text: str) -> List[str]:
    """Detecta códigos de erro (ex.: E123, ERR-456, ERROR 789)."""
    found = ERROR_CODE_RE.findall(text)
    return sorted(set(found))


class DocumentSplitter:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: Optional[int] = None,
        parser_version: str = PARSER_VERSION,
        chunking_version: str = CHUNKING_VERSION,
        logger: Optional[logging.Logger] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size or max(200, chunk_size // 4)
        self.parser_version = parser_version
        self.chunking_version = chunking_version
        self.logger = logger

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def split(self, documents: List[LoadedDocument]) -> List[Document]:
        chunks: List[Document] = []
        for doc in documents:
            chunks.extend(self._split_document(doc))

        if self.logger:
            self.logger.info(
                f"Split {len(documents)} documents into {len(chunks)} chunks"
            )
        return chunks

    # ------------------------------------------------------------------ #
    # Extração de blocos por tipo de fonte
    # ------------------------------------------------------------------ #

    def _split_document(self, doc: LoadedDocument) -> List[Document]:
        blocks = self._extract_blocks(doc)
        if not blocks:
            blocks = [Block(kind="text", text=doc.content)]

        items = self._assemble_chunks(blocks)
        items = self._merge_small_chunks(items)
        return [
            self._build_chunk_document(doc, item, index, len(items))
            for index, item in enumerate(items)
        ]

    def _extract_blocks(self, doc: LoadedDocument) -> List[Block]:
        if doc.source_type in ("csv", "xlsx"):
            return self._blocks_from_tables(doc)
        if doc.source_type == "pdf":
            blocks: List[Block] = []
            for page in doc.pages:
                blocks.extend(self._parse_content_lines(page.text, page.number))
            return blocks
        if doc.source_type in ("database", "image"):
            return [Block(kind="text", text=doc.content)]
        return self._parse_content_lines(doc.content, None)

    def _blocks_from_tables(self, doc: LoadedDocument) -> List[Block]:
        blocks: List[Block] = []
        for table in doc.tables:
            if table.section:
                blocks.append(
                    Block(kind="heading", text=f"# {table.section}", level=1,
                          section=table.section, page=table.page)
                )
            if table.markdown:
                blocks.append(
                    Block(kind="table", text=table.markdown,
                          section=table.section, page=table.page)
                )
        return blocks

    def _parse_content_lines(self, text: str, page: Optional[int]) -> List[Block]:
        blocks: List[Block] = []
        buf: List[str] = []
        table_lines: List[str] = []

        def flush_buf() -> None:
            if buf:
                content = "\n".join(buf).strip()
                if content:
                    blocks.append(Block(kind="text", text=content, page=page))
                buf.clear()

        def flush_table() -> None:
            if table_lines:
                blocks.append(
                    Block(kind="table", text="\n".join(table_lines), page=page)
                )
                table_lines.clear()

        for raw in text.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if PAGE_MARKER_RE.match(stripped) or OCR_MARKER_RE.match(stripped):
                flush_buf()
                flush_table()
                continue
            m = HEADING_RE.match(stripped)
            if m:
                flush_buf()
                flush_table()
                heading_text = m.group(2).strip()
                blocks.append(
                    Block(
                        kind="heading",
                        text=stripped,
                        level=len(m.group(1)),
                        section=heading_text,
                        page=page,
                    )
                )
                continue
            if TABLE_ROW_RE.match(stripped):
                flush_buf()
                table_lines.append(line)
                continue
            flush_table()
            buf.append(line)

        flush_buf()
        flush_table()
        return blocks

    # ------------------------------------------------------------------ #
    # Montagem de chunks
    # ------------------------------------------------------------------ #

    def _assemble_chunks(self, blocks: List[Block]) -> List[Dict]:
        assembled: List[Dict] = []
        section = ""
        subsection = ""
        current: Dict = self._new_item(section, subsection)

        def flush() -> None:
            if current["chars"]:
                assembled.append(current)

        for block in blocks:
            block_len = len(block.text) + 2
            if block.kind == "heading":
                if current["chars"] >= self.min_chunk_size:
                    flush()
                    current = self._new_item(section, subsection)
                heading_clean = clean_heading(block.text)
                if block.level <= 2:
                    section = heading_clean
                    subsection = ""
                else:
                    subsection = heading_clean
                current["section"] = section
                current["subsection"] = subsection
                current["text"].append(block.text)
                current["chars"] += block_len
            else:
                if block.section and not section:
                    section = block.section
                    current["section"] = section
                if current["chars"] > 0 and current["chars"] + block_len > self.chunk_size:
                    flush()
                    current = self._new_item(section, subsection)
                current["text"].append(block.text)
                current["chars"] += block_len

            if block.page is not None:
                if current["page_start"] is None:
                    current["page_start"] = block.page
                current["page_end"] = block.page

        flush()

        result: List[Dict] = []
        for item in assembled:
            text = "\n\n".join(item["text"]).strip()
            if not text:
                continue
            if len(text) > self.chunk_size:
                result.extend(self._split_oversized(item, text))
            else:
                result.append({**item, "text": text})
        return result

    def _new_item(self, section: str, subsection: str) -> Dict:
        return {
            "text": [],
            "chars": 0,
            "page_start": None,
            "page_end": None,
            "section": section,
            "subsection": subsection,
        }

    def _split_oversized(self, item: Dict, text: str) -> List[Dict]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ".", " ", ""],
        )
        pieces = splitter.split_text(text)
        return [
            {**item, "text": piece}
            for piece in pieces
            if piece and piece.strip()
        ]

    def _merge_small_chunks(self, items: List[Dict]) -> List[Dict]:
        merged: List[Dict] = []
        for item in items:
            if merged:
                prev = merged[-1]
                if (
                    len(item["text"]) < self.min_chunk_size
                    and len(prev["text"]) + len(item["text"]) <= self.chunk_size
                ):
                    prev["text"] = prev["text"] + "\n\n" + item["text"]
                    prev["chars"] = len(prev["text"])
                    if item["page_start"] is not None:
                        prev["page_start"] = prev["page_start"] or item["page_start"]
                        prev["page_end"] = item["page_end"] or prev["page_end"]
                    continue
            merged.append(item)
        return merged

    def _build_chunk_document(
        self, doc: LoadedDocument, item: Dict, index: int, total: int
    ) -> Document:
        contract = ChunkContract(
            chunk_id=f"chunk_{doc.document_id}_{index + 1}",
            document_id=doc.document_id,
            content=item["text"],
            source_type=doc.source_type,
            section=item["section"],
            subsection=item["subsection"],
            page_start=item["page_start"],
            page_end=item["page_end"],
            error_codes=detect_error_codes(item["text"]),
            content_hash=sha256_text(item["text"]),
            source_id=doc.source_key,
            filename=doc.filename,
            parser_version=self.parser_version,
            chunking_version=self.chunking_version,
        )
        metadata = contract.to_metadata()
        # Chaves legadas usadas pelo indexer/retriever atuais
        metadata["source"] = doc.filepath
        metadata["file_type"] = doc.file_type
        metadata["modified_at"] = doc.modified_at
        metadata["file_size"] = doc.file_size
        metadata["chunk_index"] = index + 1
        metadata["total_chunks"] = total
        return Document(page_content=item["text"], metadata=metadata)
