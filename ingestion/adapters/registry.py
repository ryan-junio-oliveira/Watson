"""Registro de adapters: mapeia extensão/source_type → adapter (§6).

Permite registrar novos adapters (DB, APIs, novos formatos) sem alterar o
DocumentLoader nem o restante da pipeline.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from ingestion.adapters.base import SourceAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._by_extension: Dict[str, SourceAdapter] = {}
        self._by_source_type: Dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter, by_extension: bool = True) -> None:
        self._by_source_type[adapter.source_type] = adapter
        if by_extension:
            for ext in adapter.supported_extensions:
                self._by_extension[ext.lower()] = adapter

    def get_by_extension(self, extension: str) -> Optional[SourceAdapter]:
        return self._by_extension.get(extension.lower())

    def get_by_source_type(self, source_type: str) -> Optional[SourceAdapter]:
        return self._by_source_type.get(source_type)

    @property
    def supported_extensions(self) -> Set[str]:
        return set(self._by_extension.keys())

    @property
    def source_types(self) -> List[str]:
        return sorted(self._by_source_type.keys())

    def is_supported(self, extension: str) -> bool:
        return extension.lower() in self._by_extension


def build_default_registry(
    logger=None,
    ocr_lang: str = "por+eng",
    ocr_dpi: int = 300,
    ocr_min_text_chars: int = 20,
    tesseract_cmd: str = "",
    image_dir: str = "",
    vision_model: str = "",
    **kwargs,
) -> AdapterRegistry:
    """Monta o registro com os adapters nativos disponíveis."""
    from ingestion.adapters.csv_adapter import CsvAdapter
    from ingestion.adapters.docx_adapter import DocxAdapter
    from ingestion.adapters.image_adapter import ImageAdapter
    from ingestion.adapters.pdf_adapter import PdfAdapter
    from ingestion.adapters.text_adapter import TextAdapter
    from ingestion.adapters.xlsx_adapter import XlsxAdapter

    registry = AdapterRegistry()
    registry.register(
        PdfAdapter(
            logger=logger,
            ocr_lang=ocr_lang,
            min_text_chars=ocr_min_text_chars,
            ocr_dpi=ocr_dpi,
            tesseract_cmd=tesseract_cmd,
            image_dir=image_dir,
            vision_model=vision_model,
            vision_base_url=kwargs.get("vision_base_url", kwargs.get("ollama_base_url", "http://localhost:11434")),
        )
    )
    registry.register(DocxAdapter(logger=logger))
    registry.register(TextAdapter(logger=logger))
    registry.register(CsvAdapter(logger=logger))
    registry.register(XlsxAdapter(logger=logger))
    registry.register(
        ImageAdapter(
            logger=logger,
            ocr_lang=ocr_lang,
            tesseract_cmd=tesseract_cmd,
            vision_model=vision_model,
        )
    )
    return registry