"""Adapter de PDF baseado em PyMuPDF + PyMuPDF4LLM com OCR seletivo (§8, §9).

Estratégia:
1. Abre o PDF com PyMuPDF e extrai texto nativo por página.
2. Avalia a qualidade do texto nativo de cada página (critério: densidade
   mínima de caracteres). Páginas sem camada textual aceitável são marcadas
   para OCR.
3. Usa PyMuPDF4LLM para gerar markdown rico (headings, tabelas, listas)
   nas páginas com texto nativo.
4. Páginas sem texto são OCRadas individualmente com Tesseract
   (render a 300 dpi via PyMuPDF — sem depender de pdf2image).
5. Constrói o LoadedDocument rico (pages/sections/tables/images).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.adapters.base import SourceAdapter
from ingestion.adapters.ocr import configure_tesseract
from ingestion.models import ImageRef, LoadedDocument, Page, Section, Table, sha256_text

try:
    import pymupdf4llm

    HAS_PYMUPDF4LLM = True
except ImportError:  # pragma: no cover
    HAS_PYMUPDF4LLM = False

try:
    import pymupdf
except ImportError:  # pragma: no cover - fallback para API antiga
    import fitz as pymupdf

try:
    import pytesseract
    from PIL import Image as PILImage

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


class PdfAdapter(SourceAdapter):
    source_type = "pdf"
    supported_extensions = {".pdf"}

    def __init__(
        self,
        ocr_lang: str = "por+eng",
        min_text_chars: int = 20,
        ocr_dpi: int = 300,
        tesseract_cmd: str = "",
        image_dir: str = "",
        logger: Optional[logging.Logger] = None,
    ):
        self.ocr_lang = ocr_lang
        self.min_text_chars = min_text_chars
        self.ocr_dpi = ocr_dpi
        self.tesseract_cmd = tesseract_cmd
        self.image_dir = image_dir
        self.logger = logger
        configure_tesseract(tesseract_cmd)

    def extract(self, filepath: Path) -> LoadedDocument:
        pdf = pymupdf.open(str(filepath))
        try:
            page_count = pdf.page_count
            native_texts = self._extract_native_text(pdf)
            ocr_needed = [
                i for i, text in enumerate(native_texts)
                if self._needs_ocr(text)
            ]

            if ocr_needed:
                if HAS_OCR:
                    for i in ocr_needed:
                        native_texts[i] = self._ocr_page(pdf, i)
                else:
                    self._log_warning(
                        f"OCR required for {len(ocr_needed)} pages of "
                        f"'{filepath.name}' but tesseract/PIL not available"
                    )

            markdown_pages = self._rich_markdown(filepath, pdf, ocr_needed)
            page_texts = [
                self._best_page_text(markdown_pages.get(i), native_texts[i])
                for i in range(page_count)
            ]
            pages = self._build_pages(page_texts, ocr_needed)
            sections = self._extract_sections(markdown_pages, pages)
            tables = self._extract_tables(markdown_pages, pages)
            images = self._extract_images(pdf, pages, filepath)

            content = self._merge_content(pages)

            return LoadedDocument(
                content=content,
                filepath=str(filepath),
                filename=filepath.name,
                file_type=".pdf",
                modified_at="",
                file_size=0,
                source_type=self.source_type,
                source_id=str(filepath),
                metadata={
                    "pages": page_count,
                    "text_pages": page_count - len(ocr_needed),
                    "ocr_pages": len(ocr_needed),
                    "has_ocr": bool(ocr_needed),
                },
                pages=pages,
                sections=sections,
                tables=tables,
                images=images,
                content_hash=sha256_text(content),
            )
        finally:
            pdf.close()

    # ------------------------------------------------------------------ #

    def _extract_native_text(self, pdf: Any) -> List[str]:
        texts: List[str] = []
        for page in pdf:
            texts.append(page.get_text("text") or "")
        return texts

    def _needs_ocr(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < self.min_text_chars:
            return True
        # Camada de texto presente mas com densidade alfanumérica muito baixa
        # (ex.: página com apenas números de página) é candidata a OCR.
        alnum = sum(c.isalnum() for c in stripped)
        ratio = alnum / len(stripped) if stripped else 0
        return ratio < 0.4

    def _ocr_page(self, pdf: Any, page_index: int) -> str:
        try:
            from io import BytesIO

            pix = pdf[page_index].get_pixmap(dpi=self.ocr_dpi)
            image = PILImage.open(BytesIO(pix.pil_tobytes("PNG")))
            text = pytesseract.image_to_string(image, lang=self.ocr_lang)
            text = text.strip()
            self._log_info(
                f"OCR page {page_index + 1}: {len(text)} chars extracted"
            )
            return text
        except Exception as e:  # pragma: no cover
            self._log_error(f"OCR failed for page {page_index + 1}: {e}")
            return ""

    def _log_info(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def _build_pages(
        self, native_texts: List[str], ocr_needed: List[int]
    ) -> List[Page]:
        ocr_set = set(ocr_needed)
        return [
            Page(number=i + 1, text=text, ocr=i in ocr_set)
            for i, text in enumerate(native_texts)
        ]

    @staticmethod
    def _best_page_text(markdown: Optional[str], native: str) -> str:
        """Escolhe o texto da página sem perder conteúdo.

        O markdown estruturado (PyMuPDF4LLM) é útil para headings/tabelas, mas
        pode descartar tokens associados a ícones/imagens (ex.: "ícone",
        "botão"). Se o markdown ficou muito menor que o texto nativo (sinal de
        conteúdo perdido), preservamos o texto nativo, que é completo.
        """
        native_stripped = (native or "").strip()
        markdown_stripped = (markdown or "").strip()
        if not markdown_stripped:
            return native_stripped
        if not native_stripped:
            return markdown_stripped
        # Se o markdown tem ao menos 80% do texto nativo, prefere a estrutura;
        # caso contrário, usa o nativo (mais completo).
        if len(markdown_stripped) >= 0.8 * len(native_stripped):
            return markdown_stripped
        return native_stripped

    def _rich_markdown(
        self, filepath: Path, pdf: Any, ocr_needed: List[int]
    ) -> Dict[int, str]:
        """Markdown rico por página (headings/tabelas) via PyMuPDF4LLM.

        Para páginas OCRadas o markdown do PyMuPDF4LLM não é útil (não há
        texto nativo); usamos o texto OCR já capturado.
        """
        result: Dict[int, str] = {}
        ocr_set = set(ocr_needed)
        if HAS_PYMUPDF4LLM:
            try:
                chunks = pymupdf4llm.to_markdown(
                    str(filepath), page_chunks=True, show_progress=False
                )
                for chunk in chunks:
                    meta = chunk.get("metadata", {}) or {}
                    # pymupdf4llm usa "page_number" (1-based)
                    page_num = meta.get("page_number", 0) - 1
                    if page_num >= 0 and page_num not in ocr_set:
                        result[page_num] = chunk.get("text", "")
            except Exception as e:
                self._log_error(
                    f"PyMuPDF4LLM markdown failed for '{filepath.name}': {e}"
                )
        return result

    def _extract_sections(
        self, markdown_pages: Dict[int, str], pages: List[Page]
    ) -> List[Section]:
        sections: List[Section] = []
        for page_num, md in sorted(markdown_pages.items()):
            for line in md.splitlines():
                m = _HEADING_RE.match(line.strip())
                if m:
                    sections.append(
                        Section(
                            heading=m.group(2).strip(),
                            level=len(m.group(1)),
                            page=page_num + 1,
                        )
                    )
        return sections

    def _extract_tables(
        self, markdown_pages: Dict[int, str], pages: List[Page]
    ) -> List[Table]:
        tables: List[Table] = []
        for page_num, md in sorted(markdown_pages.items()):
            lines = md.splitlines()
            i = 0
            while i < len(lines):
                stripped = lines[i].strip()
                if not _TABLE_ROW_RE.match(stripped):
                    i += 1
                    continue
                header = self._split_cells(lines[i])
                j = i + 1
                rows: List[List[str]] = []
                block_lines = [lines[i]]
                if j < len(lines) and _TABLE_ROW_RE.match(lines[j].strip()):
                    block_lines.append(lines[j])
                    j += 1
                while j < len(lines) and _TABLE_ROW_RE.match(lines[j].strip()):
                    cells = self._split_cells(lines[j])
                    if self._is_separator(cells):
                        block_lines.append(lines[j])
                        j += 1
                        continue
                    rows.append(cells)
                    block_lines.append(lines[j])
                    j += 1
                if header or rows:
                    tables.append(
                        Table(
                            page=page_num + 1,
                            markdown="\n".join(block_lines),
                            headers=header,
                            rows=rows,
                        )
                    )
                i = j
        return tables

    @staticmethod
    def _split_cells(line: str) -> List[str]:
        cells = [c.strip() for c in line.strip().split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        return cells

    @staticmethod
    def _is_separator(cells: List[str]) -> bool:
        if not cells:
            return False
        return all(set(c) <= {"-", ":", " "} for c in cells)

    def _extract_images(
        self, pdf: Any, pages: List[Page], filepath: Path
    ) -> List[ImageRef]:
        images: List[ImageRef] = []
        storage_root = Path(self.image_dir) if self.image_dir else None
        for page_index, page in enumerate(pdf):
            try:
                info = page.get_image_info(xrefs=True)
            except Exception:
                info = []
            for img in info:
                bbox = img.get("bbox", (0, 0, 0, 0))
                width = int(bbox[2] - bbox[0]) if len(bbox) >= 4 else 0
                height = int(bbox[3] - bbox[1]) if len(bbox) >= 4 else 0
                if width < 16 or height < 16:
                    continue
                xref = img.get("xref", 0)
                storage_path = ""
                if storage_root is not None and xref:
                    storage_path = self._save_image(pdf, xref, filepath, page_index + 1)
                images.append(
                    ImageRef(
                        image_id=f"img_{page_index + 1}_{xref}",
                        page=page_index + 1,
                        width=width,
                        height=height,
                        storage_path=storage_path,
                    )
                )
        return images

    def _save_image(
        self, pdf: Any, xref: int, filepath: Path, page_number: int
    ) -> str:
        """Persiste a imagem extraída em disco e retorna o caminho (§10)."""
        try:
            extracted = pdf.extract_image(xref)
            if not extracted:
                return ""
            ext = extracted.get("ext", "png")
            image_bytes = extracted.get("image")
            if not image_bytes:
                return ""
            doc_dir = Path(self.image_dir) / filepath.stem
            doc_dir.mkdir(parents=True, exist_ok=True)
            target = doc_dir / f"img_p{page_number}_x{xref}.{ext}"
            target.write_bytes(image_bytes)
            return str(target)
        except Exception as e:  # pragma: no cover
            self._log_warning(f"Failed to save image xref={xref}: {e}")
            return ""

    def _merge_content(self, pages: List[Page]) -> str:
        parts: List[str] = []
        for page in pages:
            text = page.text.strip()
            if text:
                marker = "[OCR]" if page.ocr else f"[Página {page.number}]"
                parts.append(f"{marker}\n{text}")
        return "\n\n".join(parts)

    def _log_warning(self, message: str) -> None:
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str) -> None:
        if self.logger:
            self.logger.error(message)
