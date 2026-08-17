"""Inferência leve de identidade (fabricante/modelo) a partir do nome do arquivo
(§24, §16). Permite reindexação/filtragem por marca/modelo sem metadados externos.
"""

from __future__ import annotations

import re
from typing import Tuple

MANUFACTURERS = (
    "HP", "CANON", "EPSON", "BROTHER", "XEROX", "SAMSUNG", "KYOCERA",
    "LEXMARK", "RICOH", "KONICA", "MINOLTA", "SHARP", "DELL", "FUJITSU",
    "PANASONIC", "TOSHIBA", "OKI", "OLIVETTI", "ZEBRA", "DOK", "LENOVO",
    "AOC", "BENQ", "LG", "PHILIPS",
)

# Padrões de modelo comuns: E52645, MFC-7860DW, SC-1520, LaserJet Pro, P1102w...
_MODEL_PATTERNS = [
    re.compile(r"([A-Z]{1,3}[-]?\d{2,6}[A-Z]?(?:\s?[A-Z]{1,3})?)", re.IGNORECASE),
    re.compile(r"([A-Za-z]{2,}(?:Jet|MFC|SC-|Laser|DeskJet|WorkForce|Pixma|Bizhub|imageRUNNER|ecosys|Prologue|DocuPrint)[A-Za-z0-9 -]*)", re.IGNORECASE),
]

_SERIES_WORDS = {"series", "model", "manual", "service", "troubleshooting",
                 "guia", "guia", "manual", "manutenção", "manutencao",
                 "catalogo", "catálogo", "v0", "v1", "v2", "v3", "dok"}


def _clean_model(raw: str) -> str:
    return raw.strip().strip("-_ ")


def infer_identity(filename: str) -> Tuple[str, str]:
    """Retorna (manufacturer, model) inferidos do nome do arquivo."""
    stem = filename.rsplit(".", 1)[0]
    upper = stem.upper()

    manufacturer = ""
    for mfr in MANUFACTURERS:
        if mfr in upper:
            manufacturer = mfr
            break

    model = ""
    for pattern in _MODEL_PATTERNS:
        match = pattern.search(stem)
        if match:
            candidate = _clean_model(match.group(1))
            words = candidate.split()
            if words and words[0].lower() not in _SERIES_WORDS:
                model = candidate
                break
    return manufacturer, model