"""Armazenamento de métricas do Watson (SQLite persistente).

Registra tudo que passa pelo sistema RAG:
- `llm_calls`: cada chamada ao Ollama (tokens input/output, modelo, duração, sucesso)
- `requests`: cada requisição de chat (pergunta, modo, evidências, tempo, erro)
- `documents`: snapshot dos dados indexados (documentos e chunks por tipo)
- `index_events`: eventos de indexação (docs/chunks processados, erros)

O SQLite é leve, sem dependências externas, e thread-safe (lock por escrita).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'generate',   -- generate | stream
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_duration_ms REAL DEFAULT 0,
    eval_duration_ms REAL DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_calls(ts);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    endpoint TEXT NOT NULL DEFAULT 'chat',
    question TEXT,
    mode TEXT,
    provider TEXT DEFAULT 'rag',
    evidence_count INTEGER DEFAULT 0,
    execution_ms REAL DEFAULT 0,
    analyze INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_req_ts ON requests(ts);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    documents INTEGER DEFAULT 0,
    chunks INTEGER DEFAULT 0,
    by_type TEXT DEFAULT '{}'   -- JSON {source_type: {documents, chunks}}
);
CREATE INDEX IF NOT EXISTS idx_docs_ts ON documents(ts);

CREATE TABLE IF NOT EXISTS index_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    documents_processed INTEGER DEFAULT 0,
    chunks_indexed INTEGER DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ie_ts ON index_events(ts);
"""


class MetricsStore:
    def __init__(self, db_path: str = "database/metrics.db", logger: Optional[logging.Logger] = None):
        self.db_path = str(db_path)
        self.logger = logger
        self._lock = threading.Lock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.executescript(_SCHEMA)
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Metrics DB init failed: {e}")

    # ------------------------------------------------------------------ #
    # Escritas
    # ------------------------------------------------------------------ #

    def record_llm_call(
        self,
        model: str,
        kind: str = "generate",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_duration_ms: float = 0.0,
        eval_duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "INSERT INTO llm_calls (ts, model, kind, prompt_tokens, "
                        "completion_tokens, total_duration_ms, eval_duration_ms, "
                        "success, error) VALUES (?,?,?,?,?,?,?,?,?)",
                        (time.time(), model, kind, int(prompt_tokens),
                         int(completion_tokens), float(total_duration_ms),
                         float(eval_duration_ms), 1 if success else 0, error),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"record_llm_call failed: {e}")

    def record_request(
        self,
        endpoint: str = "chat",
        question: Optional[str] = None,
        mode: Optional[str] = None,
        provider: str = "rag",
        evidence_count: int = 0,
        execution_ms: float = 0.0,
        analyze: bool = False,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "INSERT INTO requests (ts, endpoint, question, mode, "
                        "provider, evidence_count, execution_ms, analyze, "
                        "success, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (time.time(), endpoint, question, mode, provider,
                         int(evidence_count), float(execution_ms),
                         1 if analyze else 0, 1 if success else 0, error),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"record_request failed: {e}")

    def record_documents(
        self,
        documents: int = 0,
        chunks: int = 0,
        by_type: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "INSERT INTO documents (ts, documents, chunks, by_type) "
                        "VALUES (?,?,?,?)",
                        (time.time(), int(documents), int(chunks),
                         json.dumps(by_type or {})),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"record_documents failed: {e}")

    def record_index_event(
        self,
        documents_processed: int = 0,
        chunks_indexed: int = 0,
        error: Optional[str] = None,
    ) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "INSERT INTO index_events (ts, documents_processed, "
                        "chunks_indexed, error) VALUES (?,?,?,?)",
                        (time.time(), int(documents_processed),
                         int(chunks_indexed), error),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"record_index_event failed: {e}")

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #

    def summary(self, since_ts: Optional[float] = None) -> Dict[str, Any]:
        def _apply_filter(sql: str, args: tuple = ()) -> tuple:
            """Insere o filtro de tempo no SQL de forma correta: usa `AND ts >= ?`
            quando a query já tem WHERE, ou `WHERE ts >= ?` quando não tem."""
            if since_ts is None:
                return sql, args
            if " WHERE " in sql.upper():
                return f"{sql} AND ts >= ?", args + (since_ts,)
            return f"{sql} WHERE ts >= ?", args + (since_ts,)

        with self._lock:
            conn = self._connect()
            try:
                def one(sql: str, args: tuple = ()) -> Any:
                    sql2, args2 = _apply_filter(sql, args)
                    row = conn.execute(sql2, args2).fetchone()
                    return row[0] if row else 0

                return {
                    "llm_calls": one("SELECT COUNT(*) FROM llm_calls"),
                    "llm_success": one("SELECT COUNT(*) FROM llm_calls WHERE success=1"),
                    "llm_errors": one("SELECT COUNT(*) FROM llm_calls WHERE success=0"),
                    "total_prompt_tokens": one("SELECT COALESCE(SUM(prompt_tokens),0) FROM llm_calls"),
                    "total_completion_tokens": one("SELECT COALESCE(SUM(completion_tokens),0) FROM llm_calls"),
                    "total_tokens": one("SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) FROM llm_calls"),
                    "avg_eval_duration_ms": one("SELECT AVG(eval_duration_ms) FROM llm_calls WHERE success=1"),
                    "requests": one("SELECT COUNT(*) FROM requests"),
                    "request_success": one("SELECT COUNT(*) FROM requests WHERE success=1"),
                    "request_errors": one("SELECT COUNT(*) FROM requests WHERE success=0"),
                    "avg_execution_ms": one("SELECT AVG(execution_ms) FROM requests WHERE success=1"),
                    "documents_indexed": self._latest_scalar("documents", "documents"),
                    "chunks_indexed": self._latest_scalar("documents", "chunks"),
                }
            finally:
                conn.close()

    def _latest_scalar(self, table: str, column: str) -> Any:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT {column} FROM {table} ORDER BY ts DESC, id DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def token_series(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        """Série temporal (bucket de 1h) de tokens input/output."""
        since = time.time() - hours * 3600
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT (CAST(ts AS INTEGER)/3600)*3600 AS bucket, "
                    "SUM(prompt_tokens) AS inp, SUM(completion_tokens) AS out, "
                    "COUNT(*) AS calls "
                    "FROM llm_calls WHERE ts >= ? GROUP BY bucket ORDER BY bucket",
                    (since,),
                ).fetchall()
                return [
                    {"ts": r["bucket"], "input_tokens": r["inp"] or 0,
                     "output_tokens": r["out"] or 0, "calls": r["calls"] or 0}
                    for r in rows
                ]
            finally:
                conn.close()

    def request_series(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        since = time.time() - hours * 3600
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT (CAST(ts AS INTEGER)/3600)*3600 AS bucket, "
                    "COUNT(*) AS total, "
                    "SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS ok "
                    "FROM requests WHERE ts >= ? GROUP BY bucket ORDER BY bucket",
                    (since,),
                ).fetchall()
                return [
                    {"ts": r["bucket"], "requests": r["total"] or 0,
                     "success": r["ok"] or 0}
                    for r in rows
                ]
            finally:
                conn.close()

    def by_model(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        since = time.time() - hours * 3600
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT model, COUNT(*) AS calls, "
                    "SUM(prompt_tokens) AS inp, SUM(completion_tokens) AS out "
                    "FROM llm_calls WHERE ts >= ? GROUP BY model ORDER BY calls DESC",
                    (since,),
                ).fetchall()
                return [
                    {"model": r["model"], "calls": r["calls"] or 0,
                     "input_tokens": r["inp"] or 0, "output_tokens": r["out"] or 0}
                    for r in rows
                ]
            finally:
                conn.close()

    def recent_llm_calls(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT ts, model, kind, prompt_tokens, completion_tokens, "
                    "eval_duration_ms, success, error FROM llm_calls "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def recent_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT ts, endpoint, question, mode, provider, "
                    "evidence_count, execution_ms, analyze, success, error "
                    "FROM requests ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def document_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT ts, documents, chunks, by_type FROM documents "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["by_type"] = json.loads(d.get("by_type") or "{}")
                    except Exception:
                        d["by_type"] = {}
                    out.append(d)
                return list(reversed(out))
            finally:
                conn.close()

    def recent_index_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT ts, documents_processed, chunks_indexed, error "
                    "FROM index_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def prune(self, keep_hours: float = 30 * 24) -> None:
        """Remove registros mais antigos que `keep_hours` (evita crescimento)."""
        cutoff = time.time() - keep_hours * 3600
        with self._lock:
            conn = self._connect()
            try:
                for table in ("llm_calls", "requests", "documents", "index_events"):
                    conn.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))
                conn.commit()
            finally:
                conn.close()

    def clear(self) -> int:
        """Remove todos os registros de métricas. Retorna o total de linhas apagadas."""
        with self._lock:
            conn = self._connect()
            try:
                total = 0
                for table in ("llm_calls", "requests", "documents", "index_events"):
                    cur = conn.execute(f"DELETE FROM {table}")
                    total += cur.rowcount
                conn.commit()
                return total
            finally:
                conn.close()


metrics_store = MetricsStore()


def get_metrics_store(db_path: Optional[str] = None, logger: Optional[logging.Logger] = None) -> MetricsStore:
    """Retorna um MetricsStore com o path configurado (via env METRICS_DB)."""
    if db_path:
        return MetricsStore(db_path=db_path, logger=logger)
    from config import config
    return MetricsStore(db_path=config.metrics_db, logger=logger)