"""Adapter de CSV: preserva estrutura tabular como tabela + representação textual."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from ingestion.adapters.base import SourceAdapter
from ingestion.models import LoadedDocument, Table, sha256_text


class CsvAdapter(SourceAdapter):
    source_type = "csv"
    supported_extensions = {".csv"}

    def __init__(self, max_rows: int = 5000, logger: Optional[logging.Logger] = None):
        self.max_rows = max_rows
        self.logger = logger

    def extract(self, filepath: Path) -> LoadedDocument:
        with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows: list = []
            for i, row in enumerate(reader):
                if i >= self.max_rows:
                    break
                rows.append([cell for cell in row])

        headers = rows[0] if rows else []
        data_rows = rows[1:] if rows else []

        text_lines = []
        for row in rows:
            text_lines.append(" | ".join(row))
        content = "\n".join(text_lines)

        return LoadedDocument(
            content=content,
            filepath=str(filepath),
            filename=filepath.name,
            file_type=".csv",
            modified_at="",
            file_size=0,
            source_type=self.source_type,
            source_id=str(filepath),
            metadata={"rows": len(data_rows), "columns": len(headers)},
            tables=[
                Table(
                    headers=headers,
                    rows=data_rows,
                    markdown=_to_markdown(headers, data_rows),
                )
            ],
            content_hash=sha256_text(content),
        )


def _to_markdown(headers, rows):
    lines = []
    if headers:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
