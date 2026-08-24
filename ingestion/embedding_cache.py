"""Cache de embeddings persistente (§21).

Chave lógica: `content_hash` + `embedding_model` + `embedding_version`.
Se ambos o conteúdo e o modelo forem iguais, o embedding é reutilizado —
nunca é gerado de novo para conteúdo inalterado.

Armazenamento: SQLite (stdlib), vetores serializados com `struct` (float32).
"""

from __future__ import annotations

import sqlite3
import struct
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CacheKey = Tuple[str, str, str]


class EmbeddingCache:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                content_hash TEXT NOT NULL,
                model        TEXT NOT NULL,
                version      TEXT NOT NULL,
                dim          INTEGER NOT NULL,
                vector       BLOB NOT NULL,
                PRIMARY KEY (content_hash, model, version)
            )
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------ #

    def _row_key(self, content_hash: str, model: str, version: str) -> CacheKey:
        return (content_hash, model, version)

    @staticmethod
    def _serialize(vector: List[float], dim: int) -> bytes:
        return struct.pack(f"<{dim}f", *vector)

    @staticmethod
    def _deserialize(blob: bytes, dim: int) -> List[float]:
        return list(struct.unpack(f"<{dim}f", blob))

    # ------------------------------------------------------------------ #

    def get(
        self, content_hash: str, model: str, version: str
    ) -> Optional[List[float]]:
        row = self._row_key(content_hash, model, version)
        with self._lock:
            cur = self._conn.execute(
                "SELECT vector, dim FROM embeddings "
                "WHERE content_hash=? AND model=? AND version=?",
                row,
            )
            found = cur.fetchone()
        if found is None:
            return None
        return self._deserialize(found[0], found[1])

    def get_many(
        self, hashes: Iterable[str], model: str, version: str
    ) -> Dict[str, Optional[List[float]]]:
        """Busca em lote. Retorna {hash: vetor ou None para miss}."""
        unique = set(hashes)
        result: Dict[str, Optional[List[float]]] = {}
        with self._lock:
            for h in unique:
                cur = self._conn.execute(
                    "SELECT vector, dim FROM embeddings "
                    "WHERE content_hash=? AND model=? AND version=?",
                    (h, model, version),
                )
                found = cur.fetchone()
                result[h] = (
                    self._deserialize(found[0], found[1]) if found else None
                )
        return result

    def set_many(
        self, entries: Iterable[Tuple[str, str, str, int, List[float]]]
    ) -> int:
        """Insere/atualiza em lote.

        Cada entrada: (content_hash, model, version, dim, vector).
        """
        rows = [
            (h, model, version, dim, self._serialize(vector, dim))
            for h, model, version, dim, vector in entries
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO embeddings "
                "(content_hash, model, version, dim, vector) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        return len(rows)

    def count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM embeddings")
            return int(cur.fetchone()[0])

    def clear(self) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM embeddings")
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
