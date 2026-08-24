from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ingestion.indexer import DocumentIndexer, compute_metadata_hash
from ingestion.loader import LoadedDocument


class FakeVectorStore:
    def __init__(self):
        self.chunks = {}  # chunk_id -> (content, metadata)

    def add(self, documents, vectors):
        for d in documents:
            self.chunks[d.metadata["chunk_id"]] = d.page_content

    def delete_by_document(self, document_id):
        self.chunks = {
            k: v for k, v in self.chunks.items()
            if not k.startswith(f"chunk_{document_id}_")
        }

    def delete_by_source(self, source_id):
        pass

    def delete_by_path(self, filepath):
        pass

    def count(self):
        return len(self.chunks)

    def clear(self):
        n = len(self.chunks)
        self.chunks.clear()
        return n


@pytest.fixture
def fake_store():
    return FakeVectorStore()


@pytest.fixture
def sample_doc(tmp_path: Path) -> LoadedDocument:
    return LoadedDocument(
        content="# Seção\n\nConteúdo do documento para indexar.",
        filepath=str(tmp_path / "doc.txt"),
        filename="doc.txt",
        file_type=".txt",
        modified_at="2024-01-01T00:00:00",
        file_size=100,
        source_type="text",
    )


def build_indexer(tmp_path, fake_store, splitter=None, embedding=None):
    if splitter is None:
        splitter = MagicMock()
        splitter.split.return_value = []
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"
    if embedding is None:
        embedding = MagicMock()
        embedding.get_embeddings.return_value = MagicMock()
        embedding.embed_documents.return_value = []
        embedding.embedding_model = "test-model"
        embedding.embedding_version = "test-model-8"
    return DocumentIndexer(
        embedding_generator=embedding,
        splitter=splitter,
        chroma_persist_dir=str(tmp_path),
        vector_store=fake_store,
        manifest_path=str(tmp_path / "manifest.json"),
    )


class TestNeedsReindex:
    def test_no_entry_requires_reindex(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        assert indexer.needs_reindex(sample_doc, None) is True

    def test_same_content_and_versions_no_reindex(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = {
            "status": "completed",
            "content_hash": sample_doc.content_hash,
            "metadata_hash": compute_metadata_hash(sample_doc),
            "parser_version": indexer.pipeline.parser_version,
            "chunking_version": indexer.pipeline.chunking_version,
            "embedding_model": indexer.pipeline.embedding_model,
            "embedding_version": indexer.pipeline.embedding_version,
        }
        assert indexer.needs_reindex(sample_doc, entry) is False

    def test_content_change_triggers(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = {
            "status": "completed",
            "content_hash": "other_hash",
            "metadata_hash": compute_metadata_hash(sample_doc),
            "parser_version": indexer.pipeline.parser_version,
            "chunking_version": indexer.pipeline.chunking_version,
            "embedding_model": indexer.pipeline.embedding_model,
            "embedding_version": indexer.pipeline.embedding_version,
        }
        assert indexer.needs_reindex(sample_doc, entry) is True

    def test_version_change_triggers(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = {
            "status": "completed",
            "content_hash": sample_doc.content_hash,
            "metadata_hash": compute_metadata_hash(sample_doc),
            "parser_version": "0.9",
            "chunking_version": indexer.pipeline.chunking_version,
            "embedding_model": indexer.pipeline.embedding_model,
            "embedding_version": indexer.pipeline.embedding_version,
        }
        assert indexer.needs_reindex(sample_doc, entry) is True

    def test_embedding_version_change_triggers(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = {
            "status": "completed",
            "content_hash": sample_doc.content_hash,
            "metadata_hash": compute_metadata_hash(sample_doc),
            "parser_version": indexer.pipeline.parser_version,
            "chunking_version": indexer.pipeline.chunking_version,
            "embedding_model": indexer.pipeline.embedding_model,
            "embedding_version": "old-model-384",
        }
        assert indexer.needs_reindex(sample_doc, entry) is True

    def test_failed_status_requires_retry(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = {"status": "failed", "content_hash": sample_doc.content_hash}
        assert indexer.needs_reindex(sample_doc, entry) is True


class TestHasPendingChanges:
    def test_new_document_is_pending(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        has_pending, pending, stale = indexer.has_pending_changes([sample_doc])
        assert has_pending is True
        assert len(pending) == 1
        assert pending[0].document_id == sample_doc.document_id
        assert stale == set()

    def test_unchanged_document_not_pending(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        entry = indexer._manifest_entry(sample_doc, {
            "chunks_created": 0, "chunks_indexed": 0, "pages": 0, "ocr_pages": 0,
        })
        indexer.manifest.upsert(sample_doc.document_id, entry)
        has_pending, pending, stale = indexer.has_pending_changes([sample_doc])
        assert has_pending is False
        assert pending == []

    def test_stale_detected(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        other = LoadedDocument(
            content="x", filepath="/gone.txt", filename="gone.txt",
            file_type=".txt", modified_at="t", file_size=1,
        )
        entry = indexer._manifest_entry(other, {
            "chunks_created": 1, "chunks_indexed": 1, "pages": 0, "ocr_pages": 0,
        })
        indexer.manifest.upsert(other.document_id, entry)
        has_pending, pending, stale = indexer.has_pending_changes([sample_doc])
        assert has_pending is True
        assert other.document_id in stale


class TestIndex:
    def test_indexes_pending_and_commits_manifest(self, tmp_path, fake_store, sample_doc):
        splitter = MagicMock()
        from langchain_core.documents import Document

        splitter.split.return_value = [
            Document(page_content="Conteúdo da parte 1 para indexação de teste.", metadata={"chunk_id": f"chunk_{sample_doc.document_id}_1"}),
            Document(page_content="Conteúdo da parte 2 para indexação de teste.", metadata={"chunk_id": f"chunk_{sample_doc.document_id}_2"}),
        ]
        embedding = MagicMock()
        embedding.get_embeddings.return_value = MagicMock()
        embedding.embed_documents.return_value = [[0.1] * 4, [0.2] * 4]
        embedding.embedding_model = "test-model"
        embedding.embedding_version = "test-model-8"
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"

        indexer = build_indexer(tmp_path, fake_store, splitter, embedding)
        total = indexer.index([sample_doc])

        assert total == 2
        assert len(fake_store.chunks) == 2
        entry = indexer.manifest.get(sample_doc.document_id)
        assert entry["status"] == "completed"
        assert entry["chunks"] == 2
        assert entry["content_hash"] == sample_doc.content_hash

        # segunda execução: nada a fazer
        assert indexer.index([sample_doc]) == 0

    def test_stale_removed_from_index_and_manifest(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        other = LoadedDocument(
            content="x", filepath="/gone.txt", filename="gone.txt",
            file_type=".txt", modified_at="t", file_size=1,
        )
        entry = indexer._manifest_entry(other, {
            "chunks_created": 1, "chunks_indexed": 1, "pages": 0, "ocr_pages": 0,
        })
        indexer.manifest.upsert(other.document_id, entry)
        fake_store.chunks[f"chunk_{other.document_id}_1"] = "velho"

        indexer.index([sample_doc])
        assert indexer.manifest.get(other.document_id) is None

    def test_error_in_one_doc_does_not_stop_others(self, tmp_path, fake_store):
        good = LoadedDocument(
            content="bom", filepath="/good.txt", filename="good.txt",
            file_type=".txt", modified_at="t", file_size=1,
        )
        bad = LoadedDocument(
            content="ruim", filepath="/bad.txt", filename="bad.txt",
            file_type=".txt", modified_at="t", file_size=1,
        )
        embedding = MagicMock()
        embedding.get_embeddings.return_value = MagicMock()
        embedding.embed_documents.side_effect = [RuntimeError("embedding falhou"), []]
        embedding.embedding_model = "test-model"
        embedding.embedding_version = "test-model-8"
        splitter = MagicMock()
        splitter.split.return_value = []
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"

        indexer = build_indexer(tmp_path, fake_store, splitter, embedding)
        total = indexer.index([good, bad])
        assert total == 0
        # good falhou no embedding → sem manifest
        assert indexer.manifest.get(good.document_id) is None
        # bad processado normalmente → manifest presente
        assert indexer.manifest.get(bad.document_id) is not None

    def test_reindex_all_forces(self, tmp_path, fake_store, sample_doc):
        splitter = MagicMock()
        splitter.split.return_value = []
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"
        indexer = build_indexer(tmp_path, fake_store, splitter)
        indexer.manifest.upsert(sample_doc.document_id, {
            "status": "completed",
            "content_hash": sample_doc.content_hash,
        })
        total = indexer.reindex_all([sample_doc])
        assert total == 0  # 0 chunks, mas reprocessado
        assert indexer.manifest.get(sample_doc.document_id)["status"] == "completed"

    def test_progress_callback_reports_done_and_total(self, tmp_path, fake_store, sample_doc):
        splitter = MagicMock()
        from langchain_core.documents import Document

        splitter.split.return_value = [
            Document(page_content="Conteúdo de teste para o callback de progresso.", metadata={"chunk_id": f"chunk_{sample_doc.document_id}_1"}),
        ]
        embedding = MagicMock()
        embedding.get_embeddings.return_value = MagicMock()
        embedding.embed_documents.return_value = [[0.1] * 4]
        embedding.embedding_model = "test-model"
        embedding.embedding_version = "test-model-8"
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"

        calls: list[tuple] = []
        indexer = build_indexer(tmp_path, fake_store, splitter, embedding)
        indexer.progress_callback = lambda done, total, name: calls.append((done, total, name))

        indexer.index([sample_doc])

        assert calls == [(1, 1, sample_doc.filename)]

    def test_progress_callback_noop_when_nothing_pending(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        indexer.manifest.upsert(sample_doc.document_id, {
            "status": "completed",
            "content_hash": sample_doc.content_hash,
            "metadata_hash": compute_metadata_hash(sample_doc),
            "source_id": sample_doc.source_key,
            "parser_version": "1.0",
            "chunking_version": "2.0",
            "embedding_model": "test-model",
            "embedding_version": "test-model-8",
        })
        calls: list[tuple] = []
        indexer.progress_callback = lambda done, total, name: calls.append((done, total, name))

        assert indexer.index([sample_doc]) == 0
        assert calls == []

    def test_delete_document(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        fake_store.chunks[f"chunk_{sample_doc.document_id}_1"] = "x"
        indexer.manifest.upsert(sample_doc.document_id, {"status": "completed"})
        ok = indexer.delete_document(sample_doc)
        assert ok is True
        assert indexer.manifest.get(sample_doc.document_id) is None
        assert fake_store.count() == 0

    def test_reindex_source_by_manufacturer_and_model(self, tmp_path, fake_store):
        hp = LoadedDocument(
            content="conteudo hp", filepath="/hp.pdf", filename="HP_E52645.pdf",
            file_type=".pdf", modified_at="t", file_size=1,
            metadata={"manufacturer": "HP", "model": "E52645"},
        )
        epson = LoadedDocument(
            content="conteudo epson", filepath="/ep.pdf", filename="Epson_L380.pdf",
            file_type=".pdf", modified_at="t", file_size=1,
            metadata={"manufacturer": "EPSON", "model": "L380"},
        )
        txt = LoadedDocument(
            content="notas", filepath="/notas.txt", filename="notas.txt",
            file_type=".txt", modified_at="t", file_size=1,
            metadata={"manufacturer": "", "model": ""},
        )
        splitter = MagicMock()
        splitter.split.return_value = []
        splitter.parser_version = "1.0"
        splitter.chunking_version = "2.0"
        embedding = MagicMock()
        embedding.get_embeddings.return_value = MagicMock()
        embedding.embed_documents.return_value = []
        embedding.embedding_model = "m"
        embedding.embedding_version = "v"

        indexer = build_indexer(tmp_path, fake_store, splitter, embedding)
        total = indexer.reindex_source([hp, epson, txt], manufacturer="HP", model="E52645")
        assert indexer.manifest.get(hp.document_id) is not None
        assert indexer.manifest.get(epson.document_id) is None
        assert indexer.manifest.get(txt.document_id) is None

        # por tipo
        total2 = indexer.reindex_source([hp, epson, txt], source_type="txt")
        assert indexer.manifest.get(txt.document_id) is not None


class TestManifestEntry:
    def test_entry_has_versions_and_stats(self, tmp_path, fake_store, sample_doc):
        indexer = build_indexer(tmp_path, fake_store)
        stats = {
            "chunks_created": 3, "pages": 2, "ocr_pages": 1,
            "chunks_indexed": 3, "embeddings_generated": 3,
            "chunks_rejected": 0, "chunks_duplicate": 0,
        }
        entry = indexer._manifest_entry(sample_doc, stats)
        assert entry["document_id"] == sample_doc.document_id
        assert entry["parser_version"] == indexer.pipeline.parser_version
        assert entry["chunking_version"] == indexer.pipeline.chunking_version
        assert entry["embedding_model"] == indexer.pipeline.embedding_model
        assert entry["embedding_version"] == indexer.pipeline.embedding_version
        assert entry["chunks"] == 3
        assert entry["status"] == "completed"
        assert entry["indexed_at"]


class TestCompatHashes:
    def test_compute_file_hash(self, tmp_path):
        indexer = build_indexer(tmp_path, FakeVectorStore())
        f = tmp_path / "h.txt"
        f.write_text("conteúdo")
        h1 = indexer._compute_file_hash(str(f))
        assert len(h1) == 64
        f.write_text("outro")
        assert indexer._compute_file_hash(str(f)) != h1

    def test_compute_metadata_hash(self, sample_doc):
        h1 = compute_metadata_hash(sample_doc)
        assert len(h1) == 64
        renamed = LoadedDocument(
            content=sample_doc.content, filepath="/novo.txt", filename="novo.txt",
            file_type=".txt", modified_at="t", file_size=100,
        )
        assert compute_metadata_hash(renamed) != h1