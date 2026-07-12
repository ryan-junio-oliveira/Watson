import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.indexer import DocumentIndexer
from ingestion.loader import LoadedDocument


class TestDocumentIndexer:
    @pytest.fixture
    def mock_embedding_generator(self):
        generator = MagicMock()
        generator.get_embeddings.return_value = MagicMock()
        return generator

    @pytest.fixture
    def mock_splitter(self):
        splitter = MagicMock()
        splitter.split.return_value = []
        return splitter

    @pytest.fixture
    def sample_doc(self, tmp_path: Path) -> LoadedDocument:
        filepath = tmp_path / "test.txt"
        filepath.write_text("Conteúdo de teste para hash.")
        return LoadedDocument(
            content="Conteúdo de teste para hash.",
            filepath=str(filepath),
            filename="test.txt",
            file_type=".txt",
            modified_at="2024-01-01T00:00:00",
            file_size=28,
        )

    def test_compute_hash(self, tmp_path: Path):
        filepath = tmp_path / "hash_test.txt"
        filepath.write_text("conteúdo")
        indexer = DocumentIndexer(
            embedding_generator=MagicMock(),
            splitter=MagicMock(),
            chroma_persist_dir=str(tmp_path),
        )
        h1 = indexer._compute_file_hash(str(filepath))
        h2 = indexer._compute_file_hash(str(filepath))
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_content(self, tmp_path: Path):
        filepath = tmp_path / "hash_test.txt"
        filepath.write_text("conteúdo")
        indexer = DocumentIndexer(
            embedding_generator=MagicMock(),
            splitter=MagicMock(),
            chroma_persist_dir=str(tmp_path),
        )
        h1 = indexer._compute_file_hash(str(filepath))
        filepath.write_text("conteúdo modificado")
        h2 = indexer._compute_file_hash(str(filepath))
        assert h1 != h2

    def test_empty_control_file(self, tmp_path: Path):
        indexer = DocumentIndexer(
            embedding_generator=MagicMock(),
            splitter=MagicMock(),
            chroma_persist_dir=str(tmp_path),
        )
        data = indexer._load_control_data()
        assert data == {}

    def test_save_and_load_control_file(self, tmp_path: Path):
        indexer = DocumentIndexer(
            embedding_generator=MagicMock(),
            splitter=MagicMock(),
            chroma_persist_dir=str(tmp_path),
        )
        test_data = {
            "/path/doc.txt": {
                "hash": "abc123",
                "filename": "doc.txt",
                "modified_at": "2024-01-01T00:00:00",
                "chunk_count": 5,
            }
        }
        indexer._save_control_data(test_data)
        loaded = indexer._load_control_data()
        assert loaded == test_data

    def test_skip_unchanged_document(
        self, tmp_path: Path, mock_embedding_generator, mock_splitter, sample_doc
    ):
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()

        indexer = DocumentIndexer(
            embedding_generator=mock_embedding_generator,
            splitter=mock_splitter,
            chroma_persist_dir=str(chroma_dir),
        )

        file_hash = indexer._compute_file_hash(sample_doc.filepath)
        control_data = {
            sample_doc.filepath: {
                "hash": file_hash,
                "filename": "test.txt",
                "modified_at": "2024-01-01T00:00:00",
                "chunk_count": 3,
            }
        }
        indexer._save_control_data(control_data)

        with patch.object(indexer.splitter, "split") as mock_split:
            chunks = indexer.index([sample_doc])
            mock_split.assert_not_called()

        assert chunks == 0

    def test_skip_unchanged_with_zero_chunks(
        self, tmp_path: Path, mock_embedding_generator, mock_splitter, sample_doc
    ):
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()

        indexer = DocumentIndexer(
            embedding_generator=mock_embedding_generator,
            splitter=mock_splitter,
            chroma_persist_dir=str(chroma_dir),
        )

        control_data = {
            sample_doc.filepath: {
                "hash": "abc",
                "filename": "test.txt",
                "modified_at": sample_doc.modified_at,
                "chunk_count": 0,
            }
        }
        indexer._save_control_data(control_data)

        with patch.object(indexer.splitter, "split") as mock_split:
            chunks = indexer.index([sample_doc])
            mock_split.assert_not_called()

        assert chunks == 0

    def test_has_pending_changes_detects_stale(
        self, tmp_path: Path, mock_embedding_generator, mock_splitter
    ):
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()

        indexer = DocumentIndexer(
            embedding_generator=mock_embedding_generator,
            splitter=mock_splitter,
            chroma_persist_dir=str(chroma_dir),
        )

        stale_path = "/tmp/stale_doc.txt"
        control_data = {
            stale_path: {
                "hash": "abc",
                "filename": "stale_doc.txt",
                "modified_at": "2024-01-01T00:00:00",
                "chunk_count": 3,
            }
        }
        indexer._save_control_data(control_data)

        needs_indexing, pending, stale = indexer.has_pending_changes([])

        assert needs_indexing is True
        assert stale_path in stale

    def test_has_pending_changes_skips_unchanged(
        self, tmp_path: Path, mock_embedding_generator, mock_splitter, sample_doc
    ):
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()

        indexer = DocumentIndexer(
            embedding_generator=mock_embedding_generator,
            splitter=mock_splitter,
            chroma_persist_dir=str(chroma_dir),
        )

        file_hash = indexer._compute_file_hash(sample_doc.filepath)
        control_data = {
            sample_doc.filepath: {
                "hash": file_hash,
                "filename": "test.txt",
                "modified_at": sample_doc.modified_at,
                "chunk_count": 3,
            }
        }
        indexer._save_control_data(control_data)

        needs_indexing, pending, stale = indexer.has_pending_changes(
            [sample_doc]
        )

        assert needs_indexing is False
        assert len(pending) == 0

    def test_has_pending_changes_detects_new(
        self, tmp_path: Path, mock_embedding_generator, mock_splitter, sample_doc
    ):
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()

        indexer = DocumentIndexer(
            embedding_generator=mock_embedding_generator,
            splitter=mock_splitter,
            chroma_persist_dir=str(chroma_dir),
        )

        needs_indexing, pending, stale = indexer.has_pending_changes(
            [sample_doc]
        )

        assert needs_indexing is True
        assert len(pending) == 1
        assert pending[0] == sample_doc.filepath
