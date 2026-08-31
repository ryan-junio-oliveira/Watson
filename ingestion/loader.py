"""DocumentLoader genérico: descobre e despacha para Source Adapters.

Nenhuma lógica específica de formato fica aqui — cada fonte é processada pelo
seu adapter (§6). O loader apenas descobre arquivos, preenche os campos padrão
do arquivo (path, mtime, size) e preserva a API legada (load/_load_single).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ingestion.adapters.registry import AdapterRegistry, build_default_registry
from ingestion.identity import infer_identity
from ingestion.models import LoadedDocument

__all__ = ["DocumentLoader", "LoadedDocument", "build_default_registry"]


class DocumentLoader:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        registry: Optional[AdapterRegistry] = None,
        ocr_lang: str = "por+eng",
        ocr_dpi: int = 300,
        ocr_min_text_chars: int = 20,
        tesseract_cmd: str = "",
        image_dir: str = "",
        vision_model: str = "",
        vision_base_url: str = "",
        ollama_base_url: str = "",
    ):
        self.logger = logger
        # Vision base URL cai no ollama base se não especificado
        _v_base = vision_base_url or ollama_base_url or "http://localhost:11434"
        self.registry = registry or build_default_registry(
            logger=logger,
            ocr_lang=ocr_lang,
            ocr_dpi=ocr_dpi,
            ocr_min_text_chars=ocr_min_text_chars,
            tesseract_cmd=tesseract_cmd,
            image_dir=image_dir,
            vision_model=vision_model,
            vision_base_url=_v_base,
            ollama_base_url=_v_base,
        )
        self.SUPPORTED_EXTENSIONS = self.registry.supported_extensions
        self._infer_identity = infer_identity

    def load(self, directory: str) -> List[LoadedDocument]:
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        documents: List[LoadedDocument] = []
        for filepath in sorted(dir_path.rglob("*")):
            if not filepath.is_file():
                continue
            ext = filepath.suffix.lower()
            if ext not in self.registry.supported_extensions:
                self._log_warning(f"Unsupported file type skipped: {filepath}")
                continue

            try:
                doc = self._load_single(filepath)
                documents.append(doc)
                self._log_info(f"Loaded document: {filepath.name}")
            except Exception as e:
                self._log_error(f"Failed to load {filepath}: {e}")
                continue

        self._log_info(f"Loaded {len(documents)} documents from {directory}")
        return documents

    def _load_single(self, filepath: Path) -> LoadedDocument:
        ext = filepath.suffix.lower()
        adapter = self.registry.get_by_extension(ext)
        if adapter is None:
            raise ValueError(f"Unsupported file type: {ext}")

        doc = adapter.extract(filepath)

        stat = filepath.stat()
        doc.filepath = str(filepath.absolute())
        doc.filename = filepath.name
        doc.file_type = ext
        doc.modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        doc.file_size = stat.st_size
        doc.source_id = doc.filepath

        # Identidade inferida do nome do arquivo (§24/§16)
        manufacturer, model = infer_identity(filepath.name)
        doc.metadata.setdefault("manufacturer", manufacturer)
        doc.metadata.setdefault("model", model)
        return doc

    def _log_info(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def _log_warning(self, message: str) -> None:
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str) -> None:
        if self.logger:
            self.logger.error(message)
