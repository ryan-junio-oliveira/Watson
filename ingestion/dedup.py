"""Deduplicação de chunks (§22).

- **Duplicata exata intra-documento**: mesmo `content_hash` repetido no mesmo
  documento (ex.: cabeçalho/rodapé repetido, tabela duplicada) → o chunk é
  **rejeitado** (é ruído dentro do próprio documento).
- **Duplicata exata entre documentos**: mesmo conteúdo em documentos diferentes
  com contexto distinto (ex.: a mesma lista de códigos de erro reproduzida em
  dois manuais) → o chunk é **mantido** (contexto importa), mas marcado com
  `duplicate_of` e contabilizado — nunca removemos conteúdo legítimo por engano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set


@dataclass
class DedupResult:
    keep: bool
    reason: str = ""
    duplicate_of: str = ""


class Deduplicator:
    def __init__(self, persist_path: str = "", cross_doc_persist: bool = False):
        # content_hash -> (document_id, chunk_id) da primeira ocorrência
        self._seen: Dict[str, tuple] = {}
        self._seen_documents: Set[str] = set()
        self.intra_document_duplicates = 0
        self.cross_document_duplicates = 0
        self.persist_path = persist_path
        self.cross_doc_persist = cross_doc_persist
        if self.cross_doc_persist and self.persist_path:
            self._load_persisted()

    def _load_persisted(self) -> None:
        try:
            from pathlib import Path
            import json

            p = Path(self.persist_path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                # formato: {hash: [doc_id, chunk_id]}
                for h, v in data.items():
                    if isinstance(v, list) and len(v) >= 2:
                        self._seen[h] = (str(v[0]), str(v[1]))
        except Exception:
            pass

    def _persist(self) -> None:
        if not (self.cross_doc_persist and self.persist_path):
            return
        try:
            from pathlib import Path
            import json
            import tempfile
            import os

            p = Path(self.persist_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({k: list(v) for k, v in self._seen.items()}, f, ensure_ascii=False)
                os.replace(tmp, p)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception:
            pass

    def check(
        self,
        content_hash: str,
        document_id: str,
        chunk_id: str,
    ) -> DedupResult:
        if not content_hash:
            return DedupResult(keep=True)

        if content_hash in self._seen:
            first_doc, first_chunk = self._seen[content_hash]
            if first_doc == document_id:
                self.intra_document_duplicates += 1
                return DedupResult(
                    keep=False,
                    reason="duplicate_intra_document",
                    duplicate_of=first_chunk,
                )
            self.cross_document_duplicates += 1
            return DedupResult(
                keep=True,
                reason="duplicate_cross_document",
                duplicate_of=first_chunk,
            )

        self._seen[content_hash] = (document_id, chunk_id)
        if self.cross_doc_persist:
            self._persist()
        return DedupResult(keep=True)

    def reset(self, hard: bool = False) -> None:
        """Reset intra-run. Se cross_doc_persist=True, mantém _seen entre runs salvo hard=True."""
        if self.cross_doc_persist and not hard:
            # Mantém _seen global para dedup cross-run, só zera contadores
            self.intra_document_duplicates = 0
            self.cross_document_duplicates = 0
            return
        self._seen.clear()
        self._seen_documents.clear()
        self.intra_document_duplicates = 0
        self.cross_document_duplicates = 0

    @property
    def totals(self) -> Dict[str, int]:
        return {
            "intra_document_duplicates": self.intra_document_duplicates,
            "cross_document_duplicates": self.cross_document_duplicates,
        }
