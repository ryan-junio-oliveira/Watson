import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from langchain_chroma import Chroma
from tqdm import tqdm

from ingestion.embeddings import EmbeddingGenerator
from ingestion.loader import LoadedDocument
from ingestion.splitter import DocumentSplitter


class DocumentIndexer:
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        splitter: DocumentSplitter,
        chroma_persist_dir: str,
        batch_size: int = 100,
        logger: Optional[logging.Logger] = None,
    ):
        self.embedding_generator = embedding_generator
        self.splitter = splitter
        self.chroma_persist_dir = chroma_persist_dir
        self.batch_size = batch_size
        self.logger = logger
        self.control_file = Path(chroma_persist_dir) / "index_control.json"

    def has_pending_changes(
        self, documents: List[LoadedDocument]
    ) -> Tuple[bool, List[str], Set[str]]:
        control_data = self._load_control_data()
        needs_indexing: List[str] = []
        all_current = {doc.filepath for doc in documents}

        for doc in documents:
            existing = control_data.get(doc.filepath)
            if existing is None:
                needs_indexing.append(doc.filepath)
                continue
            quick_match = existing.get("modified_at") == doc.modified_at
            if quick_match:
                continue
            needs_indexing.append(doc.filepath)

        stale_paths = [
            path for path in control_data if path not in all_current
        ]

        return bool(needs_indexing or stale_paths), needs_indexing, set(stale_paths)

    def index(self, documents: List[LoadedDocument]) -> int:
        control_data = self._load_control_data()
        current_paths = {doc.filepath for doc in documents}

        stale_paths = [
            path for path in control_data if path not in current_paths
        ]

        docs_to_process = []
        for doc in documents:
            existing = control_data.get(doc.filepath)
            if existing is None:
                docs_to_process.append(doc)
                continue
            quick_match = existing.get("modified_at") == doc.modified_at
            if quick_match:
                continue
            docs_to_process.append(doc)

        if not docs_to_process and not stale_paths:
            if self.logger:
                self.logger.info(
                    "All documents are up to date, skipping indexing"
                )
            return 0

        if self.logger:
            self.logger.info(
                f"Indexing {len(docs_to_process)} documents "
                f"({len(stale_paths)} to remove)"
            )

        embeddings = self.embedding_generator.get_embeddings()
        vector_store = Chroma(
            persist_directory=self.chroma_persist_dir,
            embedding_function=embeddings,
            collection_name="documents",
        )

        for path in stale_paths:
            try:
                vector_store.delete(where={"source": path})
                if self.logger:
                    self.logger.info(
                        f"Removed stale document: "
                        f"{control_data[path]['filename']}"
                    )
                del control_data[path]
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Failed to remove stale document {path}: {e}"
                    )

        chunk_buffer: List = []
        indexed_count = 0
        total_chunks = 0
        start_time = time.time()

        progress = tqdm(
            docs_to_process, desc="Indexing documents", unit="doc"
        )
        for doc in progress:
            file_hash = self._compute_hash_for_doc(doc)
            existing = control_data.get(doc.filepath)

            if existing:
                try:
                    vector_store.delete(where={"source": doc.filepath})
                except Exception:
                    pass

            chunks = self.splitter.split([doc])
            for chunk in chunks:
                chunk.metadata["file_hash"] = file_hash

            chunk_buffer.extend(chunks)
            indexed_count += 1
            total_chunks += len(chunks)

            control_data[doc.filepath] = {
                "hash": file_hash,
                "filename": doc.filename,
                "modified_at": doc.modified_at,
                "chunk_count": len(chunks),
                "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            if self.logger:
                self.logger.info(
                    f"Indexed: {doc.filename} ({len(chunks)} chunks)"
                )

            if len(chunk_buffer) >= self.batch_size:
                vector_store.add_documents(chunk_buffer)
                chunk_buffer = []

        if chunk_buffer:
            vector_store.add_documents(chunk_buffer)

        self._save_control_data(control_data)

        elapsed = time.time() - start_time
        if self.logger:
            docs_per_sec = indexed_count / elapsed if elapsed > 0 else 0
            self.logger.info(
                f"Indexing complete: {indexed_count} processed, "
                f"{total_chunks} chunks in {elapsed:.1f}s "
                f"({docs_per_sec:.1f} docs/s)"
            )

        return total_chunks

    def _compute_file_hash(self, filepath: str, content: str = "") -> str:
        hasher = hashlib.sha256()
        if filepath.startswith("db://") or not Path(filepath).exists():
            hasher.update(content.encode("utf-8"))
        else:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
        return hasher.hexdigest()

    def _compute_hash_for_doc(self, doc: LoadedDocument) -> str:
        return self._compute_file_hash(doc.filepath, doc.content)

    def clear_vectorstore(self) -> int:
        """Remove todos os dados do banco vetorial ChromaDB."""
        removed = 0
        chroma_dir = Path(self.chroma_persist_dir)
        if chroma_dir.exists():
            for item in chroma_dir.iterdir():
                if item.name == "index_control.json":
                    continue
                if item.is_dir():
                    for sub in item.iterdir():
                        sub.unlink()
                        removed += 1
                    item.rmdir()
                else:
                    item.unlink()
                    removed += 1
        control = {}
        self._save_control_data(control)
        if self.logger:
            self.logger.info(f"Vector store cleared: {removed} files removed")
        return removed

    def clear_documents(self, documents_dir: str) -> int:
        """Remove todos os arquivos do diretório de documentos (recursivamente)."""
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
        """Remove tudo: documentos + vector store."""
        docs = self.clear_documents(documents_dir)
        vec = self.clear_vectorstore()
        return {"documents_removed": docs, "vectorstore_files_removed": vec}

    def _load_control_data(self) -> Dict:
        if self.control_file.exists():
            with open(self.control_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_control_data(self, data: Dict) -> None:
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.control_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
