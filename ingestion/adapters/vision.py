"""Análise de imagens via modelo de visão (Ollama) (§10).

Gera uma descrição estruturada e classifica a imagem técnica
(decorativa/técnica/diagrama/tabela/screenshot/fotografia/fluxograma).
Totalmente opcional: se não houver modelo de visão configurado ou o Ollama
estiver indisponível, retorna None (a classificação heurística é usada).
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Optional

CATEGORIES = (
    "decorative", "technical", "diagram", "table", "screenshot",
    "photograph", "flowchart",
)

_PROMPT = (
    "Classifique esta imagem como exatamente uma destas categorias: "
    f"{', '.join(CATEGORIES)}. "
    "Depois descreva brevemente o que ela mostra (máx 40 palavras), "
    "destacando texto legível, números, códigos de erro, diagramas ou etapas. "
    "Responda no formato: CATEGORIA: <categoria> | DESCRICAO: <descrição>"
)


class VisionAnalyzer:
    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434",
        timeout: int = 90,
        logger: Optional[logging.Logger] = None,
    ):
        self.model = model or ""
        self.base_url = base_url
        self.timeout = timeout
        self.logger = logger
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.model)

    def _get_client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.base_url, timeout=self.timeout)
        return self._client

    @staticmethod
    def _encode_image(image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze(self, image_path: str) -> Optional[dict]:
        """Retorna {"category", "description"} ou None se indisponível."""
        if not self.available or not image_path or not Path(image_path).exists():
            return None
        try:
            client = self._get_client()
            # Reduz imagem para evitar estouro de contexto (default 4096)
            # 4148 tokens > 4096 causa exceed_context_size_error - aumentamos num_ctx e reduzimos imagem
            resized_path = self._maybe_resize_image(image_path)
            target = resized_path or image_path
            encoded = self._encode_image(target)
            # num_ctx adaptativo: moondream (1.8B) eh leve com 4096; modelos pesados precisam 8192+ para imagem 300dpi
            ctx = 4096 if "moondream" in self.model.lower() else 8192
            response = client.generate(
                model=self.model,
                prompt=_PROMPT,
                images=[encoded],
                options={"temperature": 0.2, "num_predict": 200, "num_ctx": ctx},
            )
            raw = response.get("response", "")
            return self._parse(raw)
        except Exception as e:  # pragma: no cover
            if self.logger:
                self.logger.warning(f"Vision analysis failed: {e}")
            return None
        finally:
            # Limpa arquivo temporario de resize se criado
            try:
                if "resized_path" in locals() and resized_path and Path(resized_path).exists() and resized_path != image_path:
                    Path(resized_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _maybe_resize_image(self, image_path: str, max_size: int = 1024) -> Optional[str]:
        """Redimensiona imagem grande para max_size mantendo aspect ratio. Retorna path temporario ou None."""
        try:
            from PIL import Image as PILImage
            import tempfile

            with PILImage.open(image_path) as img:
                w, h = img.size
                if max(w, h) <= max_size:
                    return None
                # thumbnail mantem aspect
                img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
                # Converte RGBA -> RGB se necessario para JPEG
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp_path = tmp.name
                tmp.close()
                img.save(tmp_path, "JPEG", quality=85)
                return tmp_path
        except Exception:
            return None

    @staticmethod
    def _parse(raw: str) -> Optional[dict]:
        category_match = re.search(
            r"CATEGORIA\s*:\s*([a-zA-Z_]+)", raw, re.IGNORECASE
        )
        category = (
            category_match.group(1).strip().lower()
            if category_match else ""
        )
        if not category:
            category = next((c for c in CATEGORIES if c in raw.lower()), "")
        if not category:
            return None

        description_match = re.search(
            r"DESCRICAO\s*:\s*(.+)", raw, re.IGNORECASE | re.DOTALL
        )
        description = (
            description_match.group(1).strip()
            if description_match else ""
        )
        return {"category": category, "description": description}