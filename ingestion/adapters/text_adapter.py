"""Adapter para texto puro (TXT) e Markdown (MD)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from ingestion.adapters.base import SourceAdapter
from ingestion.models import LoadedDocument, Section, sha256_text

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class TextAdapter(SourceAdapter):
    source_type = "text"
    supported_extensions = {".txt", ".md", ".markdown"}

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger

    def extract(self, filepath: Path) -> LoadedDocument:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        sections: list = []
        if filepath.suffix.lower() in (".md", ".markdown"):
            for line in content.splitlines():
                m = _HEADING_RE.match(line.strip())
                if m:
                    sections.append(
                        Section(
                            heading=m.group(2).strip(),
                            level=len(m.group(1)),
                        )
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
            metadata={"chars": len(content)},
            sections=sections,
            content_hash=sha256_text(content),
        )
