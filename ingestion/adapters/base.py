"""Base para Source Adapters.

Cada fonte (PDF, DOCX, CSV, XLSX, imagem, banco, texto) tem uma estratégia
própria de extração. Nenhuma lógica específica de formato deve vazar para o
DocumentLoader genérico (§6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Set

from ingestion.models import LoadedDocument


class SourceAdapter(ABC):
    """Interface mínima que todo adapter de origem deve implementar."""

    source_type: str = "unknown"
    supported_extensions: Set[str] = set()

    @abstractmethod
    def extract(self, filepath: Path) -> LoadedDocument:
        """Extrai o conteúdo estruturado de uma fonte.

        Deve preencher pelo menos `content` e os campos ricos
        (pages/sections/tables/images/metadata). Campos padrão do arquivo
        (filepath, filename, file_type, modified_at, file_size) são
        preenchidos pelo loader.
        """
        raise NotImplementedError

    def discover(self, directory: Path) -> List[Path]:
        """Descobre arquivos suportados dentro de um diretório (recursivo)."""
        if not directory.exists():
            return []
        return sorted(
            p for p in directory.rglob("*")
            if p.is_file() and p.suffix.lower() in self.supported_extensions
        )

    def get_metadata(self, filepath: Path) -> Dict:
        """Metadados específicos da fonte (sem conteúdo)."""
        stat = filepath.stat()
        return {
            "filename": filepath.name,
            "file_size": stat.st_size,
            "modified_at": _iso_from_mtime(stat.st_mtime),
        }


def _iso_from_mtime(mtime: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(mtime).isoformat()
