from pathlib import Path
from typing import Generator

import pytest

from ingestion.loader import LoadedDocument


@pytest.fixture
def sample_text() -> str:
    return (
        "Este é um documento de exemplo para testes.\n"
        "Ele contém múltiplas linhas de texto.\n"
        "O objetivo é verificar o funcionamento do loader.\n"
        "Aqui está uma informação importante: o céu é azul.\n"
        "E outra: a grama é verde.\n"
    )


@pytest.fixture
def tmp_text_file(tmp_path: Path, sample_text: str) -> Path:
    filepath = tmp_path / "test.txt"
    filepath.write_text(sample_text, encoding="utf-8")
    return filepath


@pytest.fixture
def tmp_md_file(tmp_path: Path, sample_text: str) -> Path:
    filepath = tmp_path / "test.md"
    filepath.write_text(f"# Documento de Teste\n\n{sample_text}", encoding="utf-8")
    return filepath


@pytest.fixture
def loaded_text_doc(tmp_text_file: Path) -> LoadedDocument:
    from ingestion.loader import DocumentLoader

    loader = DocumentLoader()
    return loader._load_single(tmp_text_file)


@pytest.fixture
def tmp_documents_dir(tmp_path: Path) -> Path:
    dir_path = tmp_path / "docs"
    dir_path.mkdir()
    return dir_path
