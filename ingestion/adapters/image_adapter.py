"""Adapter de imagem: OCR + classificação + descrição via visão (§10).

Fluxo:
1. OCR (Tesseract) para extrair texto.
2. Classificação: visão (se modelo configurado) ou heurística local.
3. Descrição estruturada via visão quando disponível (imagens técnicas).
4. `LoadedDocument` com metadata rica e `ImageRef` com storage_path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
import pytesseract

from ingestion.adapters.base import SourceAdapter
from ingestion.adapters.ocr import configure_tesseract
from ingestion.adapters.vision import VisionAnalyzer
from ingestion.models import ImageRef, LoadedDocument, sha256_text


class ImageAdapter(SourceAdapter):
    source_type = "image"
    supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

    def __init__(
        self,
        ocr_lang: str = "por+eng",
        tesseract_cmd: str = "",
        vision_model: str = "",
        vision_base_url: str = "http://localhost:11434",
        logger: Optional[logging.Logger] = None,
    ):
        self.ocr_lang = ocr_lang
        self.tesseract_cmd = tesseract_cmd
        self.logger = logger
        self.vision = VisionAnalyzer(
            model=vision_model, base_url=vision_base_url, logger=logger
        )
        configure_tesseract(tesseract_cmd)

    def extract(self, filepath: Path) -> LoadedDocument:
        image = PILImage.open(str(filepath))
        width, height = image.size
        image_format = image.format or "unknown"

        # Filtra idioma para tessdata disponível (HyperViewer só tem por)
        try:
            from ingestion.adapters.ocr import _filter_available_langs
            from pathlib import Path as _P
            import pytesseract as _pt

            _tessdata = None
            _cmd = getattr(_pt.pytesseract, "tesseract_cmd", "")
            if _cmd:
                _tessdata = _P(_cmd).parent / "tessdata"
            ocr_lang_eff = _filter_available_langs(self.ocr_lang, _tessdata) if _tessdata else self.ocr_lang
        except Exception:
            ocr_lang_eff = self.ocr_lang
        text = ""
        # Skipa OCR para imagens muito pequenas ou com aspecto extremo (mesmo erro pixScaleAreaMap)
        if width < 50 or height < 50 or (width * height) < 10000 or (width / height < 0.05 if height else False) or (height / width < 0.05 if width else False):
            if self.logger:
                self.logger.info(f"Skipping OCR for small/thin image '{filepath.name}': {width}x{height}")
        else:
            try:
                import contextlib
                import io as _io

                with contextlib.redirect_stderr(_io.StringIO()):
                    text = pytesseract.image_to_string(image, lang=ocr_lang_eff).strip()
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Image OCR failed for '{filepath.name}': {e} (lang={ocr_lang_eff})")

        # Só chama vision para imagens com tamanho razoável
        vision = None
        if width >= 100 and height >= 100 and (width * height) >= 10000:
            vision = self.vision.analyze(str(filepath))
        else:
            vision = None
        kind = self._classify(width, height, text, vision)

        description = ""
        if vision and vision.get("description"):
            description = vision["description"]

        content_parts = []
        if text:
            content_parts.append(text)
        if description:
            content_parts.append(f"[Descrição da imagem: {description}]")
        content = "\n\n".join(content_parts) or (
            f"[Imagem sem texto detectado: {filepath.name}]"
        )

        return LoadedDocument(
            content=content,
            filepath=str(filepath),
            filename=filepath.name,
            file_type=filepath.suffix.lower(),
            modified_at="",
            file_size=0,
            source_type=self.source_type,
            source_id=str(filepath),
            metadata={
                "image_format": image_format,
                "image_width": width,
                "image_height": height,
                "image_kind": kind,
                "ocr_chars": len(text),
                "vision_category": (vision or {}).get("category", ""),
            },
            images=[
                ImageRef(
                    image_id="img_main",
                    kind=kind,
                    storage_path=str(filepath),
                    width=width,
                    height=height,
                    caption=description,
                )
            ],
            content_hash=sha256_text(text),
        )

    @staticmethod
    def _classify(width: int, height: int, text: str, vision=None) -> str:
        if vision and vision.get("category"):
            return vision["category"]
        if text:
            return "screenshot"
        if width >= 800 or height >= 600:
            return "photograph"
        return "decorative"