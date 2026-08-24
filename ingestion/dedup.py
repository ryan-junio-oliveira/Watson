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
    def __init__(self):
        # content_hash -> (document_id, chunk_id) da primeira ocorrência
        self._seen: Dict[str, tuple] = {}
        self._seen_documents: Set[str] = set()
        self.intra_document_duplicates = 0
        self.cross_document_duplicates = 0

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
        return DedupResult(keep=True)

    def reset(self) -> None:
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
