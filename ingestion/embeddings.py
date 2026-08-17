"""Geração de embeddings multilíngues, versionada e com cache (§20, §21).

- **Modelo**: configurável (padrão `intfloat/multilingual-e5-base` — multilíngue,
  768 dims, adequado a manuais PT/EN e terminologia técnica).
- **Prefixo E5**: modelos da família e5 exigem prefixo `query:`/`passage:`;
  detectado automaticamente.
- **Normalização**: embeddings normalizados por padrão (compatível com cosine).
- **Versionamento**: `embedding_version` deriva do modelo + dimensão — muda
  quando o modelo troca, sinalizando reindexação necessária (stage 4).
- **Cache**: documentos já embarcados com o mesmo (content_hash, model, version)
  são reutilizados — nunca re-embarcados.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ingestion.embedding_cache import EmbeddingCache

_E5_MODEL_HINTS = ("e5", "multilingual-e5")


class EmbeddingGenerator:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        device: str = "cpu",
        batch_size: int = 32,
        normalize: bool = True,
        cache_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.normalize = normalize
        self.logger = logger
        self._model = None
        self._dimension: Optional[int] = None
        self._embeddings_wrapper: Optional[_LangChainCompatibleEmbeddings] = None
        self._cache = EmbeddingCache(cache_path) if cache_path else None

        self.query_prefix, self.document_prefix = self._detect_prefixes(model_name)

    # ------------------------------------------------------------------ #
    # Propriedades de versionamento
    # ------------------------------------------------------------------ #

    @property
    def embedding_model(self) -> str:
        return self.model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            model = self._load_model()
            getter = getattr(
                model, "get_embedding_dimension", None
            ) or getattr(model, "get_sentence_embedding_dimension")
            self._dimension = getter()
        return self._dimension

    @property
    def embedding_version(self) -> str:
        basename = self.model_name.rstrip("/").split("/")[-1]
        return f"{basename}-{self.dimension}"

    @property
    def version(self) -> str:
        return self.embedding_version

    def get_model_info(self) -> Dict:
        return {
            "model": self.embedding_model,
            "version": self.embedding_version,
            "dimension": self.dimension,
            "device": self.device,
            "batch_size": self.batch_size,
            "normalize": self.normalize,
            "query_prefix": self.query_prefix,
            "document_prefix": self.document_prefix,
        }

    # ------------------------------------------------------------------ #
    # Interface compatível com LangChain / Chroma
    # ------------------------------------------------------------------ #

    def get_embeddings(self) -> _LangChainCompatibleEmbeddings:
        if self._embeddings_wrapper is None:
            self._embeddings_wrapper = _LangChainCompatibleEmbeddings(self)
        return self._embeddings_wrapper

    # ------------------------------------------------------------------ #
    # API pública de embedding
    # ------------------------------------------------------------------ #

    def embed_query(self, text: str) -> List[float]:
        """Embedding de uma consulta (usa prefixo de query; sem cache)."""
        prefixed = f"{self.query_prefix}{text}"
        vector = self._encode([prefixed])[0]
        return [float(v) for v in vector]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embedding de documentos com cache por (content_hash, model, version).

        A chave de cache usa o hash do texto **bruto** (idêntico ao
        `content_hash` que o splitter grava no chunk), garantindo consistência
        com o manifest e a lógica de incremental indexing.
        """
        if not texts:
            return []
        prefixed = [f"{self.document_prefix}{t}" for t in texts]
        hashes = [self._hash_for(t) for t in texts]

        if self._cache is not None:
            cached = self._cache.get_many(hashes, self.embedding_model, self.embedding_version)
        else:
            cached = {}

        missing_idx = [i for i, h in enumerate(hashes) if cached.get(h) is None]

        vectors: List[List[float]] = [None] * len(texts)  # type: ignore[list-item]
        for i, h in enumerate(hashes):
            if cached.get(h) is not None:
                vectors[i] = list(cached[h])

        if missing_idx:
            missing_texts = [prefixed[i] for i in missing_idx]
            encoded = self._encode(missing_texts)
            new_entries = [
                (hashes[i], self.embedding_model, self.embedding_version,
                 self.dimension, [float(v) for v in vec])
                for i, vec in zip(missing_idx, encoded)
            ]
            if self._cache is not None:
                self._cache.set_many(new_entries)
            for i, vec in zip(missing_idx, encoded):
                vectors[i] = [float(v) for v in vec]

        return vectors  # type: ignore[return-value]

    def embed_texts(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        if is_query:
            return [self.embed_query(t) for t in texts]
        return self.embed_documents(texts)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _load_model(self):
        if self._model is None:
            if self.logger:
                self.logger.info(f"Loading embedding model: {self.model_name}")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def _encode(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
        )
        return embeddings.tolist()

    @staticmethod
    def _hash_for(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _detect_prefixes(model_name: str) -> tuple:
        low = model_name.lower()
        if any(hint in low for hint in _E5_MODEL_HINTS):
            return "query: ", "passage: "
        return "", ""


class _LangChainCompatibleEmbeddings:
    """Wraps o generator na interface esperada por Chroma/LangChain."""

    def __init__(self, generator: EmbeddingGenerator):
        self.generator = generator

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.generator.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.generator.embed_query(text)

    @property
    def model_name(self) -> str:
        return self.generator.embedding_model
