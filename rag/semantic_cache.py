"""Cache semântico simples — evita recomputar respostas idênticas/semelhantes.

Sprint 1: cache exato (normalizado) com TTL e LRU. Sprint 2 pode evoluir
para similaridade por embedding (cosine > threshold).

Armazena em memória; hit retorna <50ms vs 30-110s de LLM em CPU.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


def _normalize_q(q: str) -> str:
    import re
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    # remove pontuação leve
    q = re.sub(r"[^\w\sÀ-ÿ]", "", q)
    return q.strip()


def _cache_key(question: str, mode: str, profile: str, analyze: bool) -> str:
    norm = _normalize_q(question)
    raw = f"{norm}|{mode}|{profile}|{analyze}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class CacheEntry:
    answer: str
    metadata: Dict
    sources: list
    confidence: float
    created_at: float


class SemanticCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max(1, int(max_size))
        self.ttl = max(60, int(ttl_seconds))
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, question: str, mode: str, profile: str, analyze: bool) -> Optional[Tuple[str, Dict, list, float]]:
        key = _cache_key(question, mode, profile, analyze)
        entry = self._store.get(key)
        # Debug
        # print(f"CACHE GET key={key[:8]} q='{question[:20]}' mode={mode} profile={profile} analyze={analyze} -> {'HIT' if entry else 'MISS'} size={len(self._store)}")
        if not entry:
            self.misses += 1
            return None
        if time.time() - entry.created_at > self.ttl:
            # expirado
            self._store.pop(key, None)
            self.misses += 1
            return None
        # LRU: move para fim
        self._store.move_to_end(key)
        self.hits += 1
        return entry.answer, entry.metadata, entry.sources, entry.confidence

    def set(self, question: str, mode: str, profile: str, analyze: bool, answer: str, metadata: Dict, sources: list, confidence: float):
        key = _cache_key(question, mode, profile, analyze)
        # Evita cachear respostas vazias ou de saudação/fallback sem evidência
        if not answer or not answer.strip():
            return
        if metadata.get("greeting"):
            return
        if metadata.get("fallback") == "no_documents" and not sources:
            # não cacheia "não encontrei" — pode indexar depois
            return
        entry = CacheEntry(answer=answer, metadata=dict(metadata), sources=list(sources), confidence=confidence, created_at=time.time())
        self._store[key] = entry
        self._store.move_to_end(key)
        # LRU eviction
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def stats(self):
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total else 0
        return {"hits": self.hits, "misses": self.misses, "hit_rate": hit_rate, "size": len(self._store)}
