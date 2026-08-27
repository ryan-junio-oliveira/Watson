"""Indexador com manifesto, incremental por hash, versionamento e atomicidade
(§14, §15, §16, §17, §18, §27).

Fluxo:
1. `has_pending_changes` decide o que reindexar comparando o `IndexingManifest`
   (content_hash + metadata_hash + versões de parser/chunking/embedding).
2. `index` processa apenas os pendentes e remove os obsoletos.
3. Por documento: split → embeddings (com cache) → **swap atômico** no vector
   store (só após os embeddings terem sucesso) → commit do manifest.
   Falha em um documento não destrói a versão anterior nem impede os demais.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

from ingestion.contracts import PipelineVersion
from ingestion.dedup import Deduplicator
from ingestion.loader import LoadedDocument
from ingestion.manifest import ManifestStore
from ingestion.quality import QualityGate
from ingestion.vector_store import ChromaVectorStore, VectorStore
from metrics.store import MetricsStore


def compute_metadata_hash(doc: LoadedDocument) -> str:
    """Hash da identidade/metadata do documento (não do conteúdo)."""
    meta = json.dumps(
        {
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "source_type": doc.source_type,
        },
        sort_keys=True,
    )
    return hashlib.sha256(meta.encode("utf-8")).hexdigest()


class DocumentIndexer:
    def __init__(
        self,
        embedding_generator,
        splitter,
        chroma_persist_dir: str,
        batch_size: int = 100,
        vector_store: Optional[VectorStore] = None,
        manifest_path: Optional[str] = None,
        quality_gate: Optional[QualityGate] = None,
        deduplicator: Optional[Deduplicator] = None,
        logger: Optional[logging.Logger] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        metrics: Optional[MetricsStore] = None,
    ):
        self.embedding_generator = embedding_generator
        self.splitter = splitter
        self.chroma_persist_dir = chroma_persist_dir
        self.batch_size = batch_size
        self.logger = logger
        self.metrics = metrics or MetricsStore(logger=logger)
        self.progress_callback = progress_callback

        embeddings = embedding_generator.get_embeddings()
        self.vector_store = vector_store or ChromaVectorStore(
            persist_directory=chroma_persist_dir,
            embedding_function=embeddings,
            logger=logger,
        )

        self.manifest_path = manifest_path or str(
            Path(chroma_persist_dir) / "index_manifest.json"
        )
        self.manifest = ManifestStore(self.manifest_path)

        # QualityGate por tipo — lê de config se não injetado (permite testes mockarem)
        if quality_gate is not None:
            self.quality_gate = quality_gate
        else:
            try:
                from config import config as _cfg

                self.quality_gate = QualityGate(
                    min_chars=getattr(_cfg, "quality_min_chars", 20),
                    min_chars_table=getattr(_cfg, "quality_min_chars_table", 10),
                    min_chars_image=getattr(_cfg, "quality_min_chars_image", 30),
                    table_min_pipes=getattr(_cfg, "quality_table_min_pipes", 4),
                    ocr_conf_threshold=getattr(_cfg, "quality_ocr_threshold", 0.6),
                )
            except Exception:
                self.quality_gate = QualityGate()

        # Deduplicator — cross-doc persistido opcional via DEDUP_PERSIST_PATH
        if deduplicator is not None:
            self.deduplicator = deduplicator
        else:
            try:
                from config import config as _cfg

                if getattr(_cfg, "dedup_cross_doc", False):
                    self.deduplicator = Deduplicator(
                        persist_path=getattr(_cfg, "dedup_persist_path", "database/dedup.json"),
                        cross_doc_persist=True,
                    )
                else:
                    self.deduplicator = Deduplicator()
            except Exception:
                self.deduplicator = Deduplicator()

        self._pipeline: Optional[PipelineVersion] = None

    @property
    def pipeline(self) -> PipelineVersion:
        """Versões da pipeline, calculadas sob demanda (evita carregar o modelo
        de embeddings apenas para inspecionar versão na construção)."""
        if self._pipeline is None:
            self._pipeline = PipelineVersion(
                parser_version=getattr(self.splitter, "parser_version", "1.0"),
                chunking_version=getattr(self.splitter, "chunking_version", "2.0"),
                embedding_model=self.embedding_generator.embedding_model,
                embedding_version=self.embedding_generator.embedding_version,
            )
        return self._pipeline

    # ------------------------------------------------------------------ #
    # Decisão incremental (§14, §15)
    # ------------------------------------------------------------------ #

    def needs_reindex(
        self, doc: LoadedDocument, entry: Optional[Dict]
    ) -> bool:
        if entry is None:
            return True
        if entry.get("status") != "completed":
            return True
        if entry.get("content_hash") != doc.content_hash:
            return True
        if entry.get("metadata_hash") != compute_metadata_hash(doc):
            return True
        if entry.get("parser_version") != self.pipeline.parser_version:
            return True
        if entry.get("chunking_version") != self.pipeline.chunking_version:
            return True
        if entry.get("embedding_model") != self.pipeline.embedding_model:
            return True
        if entry.get("embedding_version") != self.pipeline.embedding_version:
            return True
        return False

    def has_pending_changes(
        self, documents: List[LoadedDocument]
    ) -> Tuple[bool, List[LoadedDocument], Set[str]]:
        pending: List[LoadedDocument] = [
            doc for doc in documents
            if self.needs_reindex(doc, self.manifest.get(doc.document_id))
        ]
        current_sources = {doc.source_key for doc in documents}
        stale = {
            entry["document_id"]
            for entry in self.manifest.entries()
            if entry.get("source_id") not in current_sources
        }
        return bool(pending or stale), pending, stale

    # ------------------------------------------------------------------ #
    # Indexação
    # ------------------------------------------------------------------ #

    def index(self, documents: List[LoadedDocument]) -> int:
        has_pending, pending, stale = self.has_pending_changes(documents)
        if not has_pending:
            if self.logger:
                self.logger.info("All documents are up to date, skipping")
            return 0

        if self.logger:
            self.logger.info(
                f"Indexing {len(pending)} documents "
                f"({len(stale)} to remove)"
            )

        self.deduplicator.reset()

        total_chunks = 0
        errors: List[Tuple[str, str]] = []

        progress = tqdm(pending, desc="Indexing documents", unit="doc")
        for i, doc in enumerate(progress):
            try:
                stats = self._process_document(doc)
                total_chunks += stats["chunks_indexed"]
                self._log_document_summary(doc, stats)
            except Exception as e:
                errors.append((doc.filename, str(e)))
                if self.logger:
                    self.logger.error(f"Failed to index {doc.filename}: {e}")
            if self.progress_callback:
                self.progress_callback(i + 1, len(pending), doc.filename)

        for document_id in stale:
            entry = self.manifest.get(document_id)
            if not entry:
                continue
            try:
                self.vector_store.delete_by_source(entry.get("source_id", ""))
                self.vector_store.delete_by_path(entry.get("source", ""))
                self.manifest.remove(document_id)
                if self.logger:
                    self.logger.info(
                        f"Removed stale document: {entry.get('filename')}"
                    )
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to remove stale document {document_id}: {e}"
                    )

        if errors and self.logger:
            self.logger.error(f"{len(errors)} documents failed: {errors}")

        try:
            self.metrics.record_index_event(
                documents_processed=len(pending),
                chunks_indexed=total_chunks,
                error=("; ".join(f"{n}: {e}" for n, e in errors) if errors else None),
            )
            self.record_indexed_snapshot()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Metrics index record failed: {e}")

        return total_chunks

    def record_indexed_snapshot(self) -> None:
        """Registra o snapshot atual de documentos/chunks indexados (por tipo)."""
        try:
            entries = self.manifest.entries()
            total_docs = 0
            total_chunks = 0
            by_type: Dict[str, Dict[str, int]] = {}
            for e in entries:
                st = e.get("source_type", "unknown")
                d = by_type.setdefault(st, {"documents": 0, "chunks": 0})
                d["documents"] += 1
                d["chunks"] += e.get("chunks", 0)
                total_docs += 1
                total_chunks += e.get("chunks", 0)
            self.metrics.record_documents(
                documents=total_docs, chunks=total_chunks, by_type=by_type
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Metrics snapshot failed: {e}")

    def _process_document(self, doc: LoadedDocument) -> Dict:
        """Processa um documento de forma atômica e registra no manifest.

        Ordem segura: split → quality gate → dedup → embeddings (com cache) →
        só então swap no vector store (delete da versão antiga + add da nova)
        → commit do manifest. Se qualquer etapa falhar, a versão anterior
        permanece no índice.
        """
        chunks = self.splitter.split([doc])

        # Quality gate (§25)
        accepted: List = []
        rejected = 0
        for chunk in chunks:
            score = self.quality_gate.assess(chunk, doc)
            if not score.accepted:
                rejected += 1
                continue
            accepted.append(chunk)

        # Deduplicação (§22)
        kept: List = []
        duplicates = 0
        for chunk in accepted:
            result = self.deduplicator.check(
                chunk.metadata.get("content_hash", ""),
                doc.document_id,
                chunk.metadata.get("chunk_id", ""),
            )
            if not result.keep:
                duplicates += 1
                continue
            if result.duplicate_of:
                chunk.metadata["duplicate_of"] = result.duplicate_of
            chunk.metadata["file_hash"] = doc.content_hash
            kept.append(chunk)

        vectors = self.embedding_generator.embed_documents(
            [c.page_content for c in kept]
        )

        self.vector_store.delete_by_document(doc.document_id)
        self._add_batched(kept, vectors)

        stats = self._build_stats(
            doc, created=len(chunks), rejected=rejected,
            duplicates=duplicates, indexed=len(kept),
        )
        entry = self._manifest_entry(doc, stats)
        self.manifest.upsert(doc.document_id, entry)
        return stats

    def _add_batched(self, chunks, vectors) -> None:
        for i in range(0, len(chunks), self.batch_size):
            batch_docs = chunks[i : i + self.batch_size]
            batch_vecs = vectors[i : i + self.batch_size]
            if batch_docs:
                self.vector_store.add(batch_docs, batch_vecs)

    def _build_stats(
        self,
        doc: LoadedDocument,
        created: int,
        rejected: int,
        duplicates: int,
        indexed: int,
    ) -> Dict:
        return {
            "chunks_created": created,
            "chunks_indexed": indexed,
            "embeddings_generated": indexed,
            "chunks_rejected": rejected,
            "chunks_duplicate": duplicates,
            "cross_document_duplicates": self.deduplicator.cross_document_duplicates,
            "pages": len(doc.pages),
            "ocr_pages": sum(1 for p in doc.pages if p.ocr),
        }

    def _collect_image_hashes(self, doc: LoadedDocument) -> Dict[str, str]:
        """Hash de imagens para evitar re-Vision/re-OCR desnecessário."""
        out: Dict[str, str] = {}
        for img in getattr(doc, "images", []) or []:
            try:
                p = Path(getattr(img, "storage_path", "") or "")
                if p.exists() and p.is_file():
                    import hashlib

                    h = hashlib.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            h.update(chunk)
                    out[getattr(img, "image_id", str(p))] = h.hexdigest()[:16]
                else:
                    out[getattr(img, "image_id", "")] = ""
            except Exception:
                out[getattr(img, "image_id", "")] = ""
        return out

    def _manifest_entry(self, doc: LoadedDocument, stats: Dict) -> Dict:
        return {
            "document_id": doc.document_id,
            "source_id": doc.source_key,
            "source": doc.filepath,
            "source_type": doc.source_type,
            "filename": doc.filename,
            "content_hash": doc.content_hash,
            "metadata_hash": compute_metadata_hash(doc),
            "manufacturer": doc.metadata.get("manufacturer", ""),
            "model": doc.metadata.get("model", ""),
            "parser_version": self.pipeline.parser_version,
            "chunking_version": self.pipeline.chunking_version,
            "embedding_model": self.pipeline.embedding_model,
            "embedding_version": self.pipeline.embedding_version,
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "chunks": stats["chunks_indexed"],
            "pages": stats["pages"],
            "ocr_pages": stats["ocr_pages"],
            "image_hashes": self._collect_image_hashes(doc),
            "status": "completed",
            "error": None,
            "stats": stats,
        }

    def _log_document_summary(self, doc: LoadedDocument, stats: Dict) -> None:
        """Observabilidade por documento (§26)."""
        if not self.logger:
            return
        ocr_pages = stats["ocr_pages"]
        text_pages = stats["pages"] - ocr_pages
        self.logger.info(
            f"Document: {doc.filename}\n"
            f"  Pages: {stats['pages']} | Text pages: {text_pages} | "
            f"OCR pages: {ocr_pages}\n"
            f"  Chunks created: {stats['chunks_created']} | "
            f"Rejected: {stats['chunks_rejected']} | "
            f"Duplicates: {stats['chunks_duplicate']} | "
            f"Cross-doc dup: {stats['cross_document_duplicates']}\n"
            f"  Embeddings: {stats['embeddings_generated']} | "
            f"Indexed: {stats['chunks_indexed']}"
        )

    def summary(self) -> Dict:
        """Relatório agregado do manifesto (§26) — facilmente consultável."""
        entries = self.manifest.entries()
        totals = {
            "documents": len(entries),
            "chunks": sum(e.get("chunks", 0) for e in entries),
            "pages": sum(e.get("pages", 0) for e in entries),
            "ocr_pages": sum(e.get("ocr_pages", 0) for e in entries),
            "status": {
                s: sum(1 for e in entries if e.get("status") == s)
                for s in {e.get("status", "unknown") for e in entries}
            },
            "by_source_type": {},
        }
        for e in entries:
            st = e.get("source_type", "unknown")
            totals["by_source_type"].setdefault(st, {"documents": 0, "chunks": 0})
            totals["by_source_type"][st]["documents"] += 1
            totals["by_source_type"][st]["chunks"] += e.get("chunks", 0)
        return totals

    # ------------------------------------------------------------------ #
    # Controle de reindexação (§16)
    # ------------------------------------------------------------------ #

    def index_document(self, doc: LoadedDocument) -> int:
        """Indexa (ou reindexa) um único documento incondicionalmente."""
        self.deduplicator.reset()
        stats = self._process_document(doc)
        self._log_document_summary(doc, stats)
        return stats["chunks_indexed"]

    def reindex_document(self, doc: LoadedDocument) -> int:
        return self.index_document(doc)

    def delete_document(self, doc: LoadedDocument) -> bool:
        """Remove um documento do índice e do manifest."""
        try:
            self.vector_store.delete_by_document(doc.document_id)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to delete {doc.filename}: {e}")
        return self.manifest.remove(doc.document_id) is not None

    def delete_by_source_id(self, source_id: str) -> bool:
        entry = self.manifest.find_by_source(source_id)
        self.vector_store.delete_by_source(source_id)
        if entry:
            return self.manifest.remove(entry["document_id"]) is not None
        return False

    def reindex_source_type(
        self, documents: List[LoadedDocument], source_type: str
    ) -> int:
        return self.reindex_source(documents, source_type=source_type)

    def reindex_source(
        self,
        documents: List[LoadedDocument],
        source_type: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        filename_contains: Optional[str] = None,
    ) -> int:
        """Reindexa apenas um subconjunto de fontes (§16).

        Filtra por tipo de fonte, fabricante, modelo ou padrão de nome de
        arquivo (ex.: "somente PDFs", "somente HP", "somente E52645").
        """
        filtered = documents
        if source_type:
            filtered = [d for d in filtered if d.source_type == source_type]
        if manufacturer:
            filtered = [
                d for d in filtered
                if (d.metadata.get("manufacturer") or "").lower()
                == manufacturer.lower()
            ]
        if model:
            filtered = [
                d for d in filtered
                if (d.metadata.get("model") or "").lower() == model.lower()
            ]
        if filename_contains:
            filtered = [
                d for d in filtered if filename_contains.lower() in d.filename.lower()
            ]
        return self.index(filtered)

    def reindex_changed(self, documents: List[LoadedDocument]) -> int:
        return self.index(documents)

    def reindex_all(self, documents: List[LoadedDocument]) -> int:
        """Força reindexação completa (ignora o manifest)."""
        for doc in documents:
            self.manifest.remove(doc.document_id)
        return self.index(documents)

    # ------------------------------------------------------------------ #
    # Limpeza
    # ------------------------------------------------------------------ #

    def clear_vectorstore(self) -> int:
        """Remove todos os dados do vector store e do manifest."""
        removed = self.vector_store.clear()
        self.manifest.clear()
        if self.logger:
            self.logger.info(f"Vector store cleared: {removed} chunks removed")
        return removed

    def clear_documents(self, documents_dir: str) -> int:
        """Remove todos os arquivos do diretório de documentos (recursivo)."""
        removed = 0
        docs_path = Path(documents_dir)
        if docs_path.exists():
            for item in docs_path.rglob("*"):
                if item.is_file():
                    item.unlink()
                    removed += 1
        if self.logger:
            self.logger.info(f"Documents cleared: {removed} files removed")
        return removed

    def clear_all(self, documents_dir: str) -> dict:
        docs = self.clear_documents(documents_dir)
        vec = self.clear_vectorstore()
        return {"documents_removed": docs, "vectorstore_chunks_removed": vec}

    # ------------------------------------------------------------------ #
    # Compatibilidade (hashes)
    # ------------------------------------------------------------------ #

    def _compute_file_hash(self, filepath: str, content: str = "") -> str:
        hasher = hashlib.sha256()
        if not Path(filepath).exists():
            hasher.update(content.encode("utf-8"))
        else:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
        return hasher.hexdigest()

    def _compute_hash_for_doc(self, doc: LoadedDocument) -> str:
        return self._compute_file_hash(doc.filepath, doc.content)
