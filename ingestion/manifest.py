"""Fonte de verdade da indexação: o Indexing Manifest (§27, §29).

O vector store é apenas o índice para retrieval. O manifesto registra por
documento: hashes, versões da pipeline, status e estatísticas de processamento.
Permite reindex, delete, auditoria, versionamento e migração sem depender
exclusivamente do Chroma.

Persistência: JSON com escrita atômica (arquivo temporário + rename).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.contracts import IndexingManifest


class ManifestStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        # Callers already hold self._lock (lock não-reentrante).
        dir_path = self.path.parent
        fd, tmp = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # ------------------------------------------------------------------ #

    def get(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._data.get(document_id)
            return dict(entry) if entry else None

    def upsert(self, document_id: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._data[document_id] = entry
            self._save()

    def upsert_many(self, entries: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            self._data.update(entries)
            self._save()

    def remove(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            removed = self._data.pop(document_id, None)
            if removed is not None:
                self._save()
            return removed

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}

    def entries(self) -> List[Dict[str, Any]]:
        return [dict(v) for v in self.all().values()]

    def find_by_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        for entry in self.all().values():
            if entry.get("source_id") == source_id:
                return entry
        return None

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def to_manifest(self, document_id: str) -> Optional[IndexingManifest]:
        entry = self.get(document_id)
        return IndexingManifest.from_dict(entry) if entry else None

    def clear(self) -> int:
        with self._lock:
            n = len(self._data)
            self._data = {}
            self._save()
            return n
