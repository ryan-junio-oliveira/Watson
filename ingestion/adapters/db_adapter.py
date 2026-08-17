"""Adapter de banco de dados (§6/§11).

Descobre o schema (tabelas, colunas, chaves primárias), filtra colunas
sensíveis e converte registros em `LoadedDocument` com identidade estável
(source_id = db://tabela/pk) — permitindo incremental indexing por registro.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text as sa_text

from ingestion.models import LoadedDocument, sha256_text

SENSITIVE_COLUMN_PATTERNS: Set[str] = {
    "password", "senha", "secret", "token", "recovery_codes",
    "two_factor", "remember_token", "api_key", "apikey",
}


class DatabaseAdapter:
    source_type = "database"

    def __init__(
        self,
        connection_string: str,
        tables: Optional[List[str]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.connection_string = connection_string
        self.tables = tables
        self.logger = logger
        self._schema_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Schema (descoberta) — §11
    # ------------------------------------------------------------------ #

    def get_schema(self) -> Dict[str, Any]:
        """Retorna {table: {"columns": [...], "pk": [...]}} (cacheado)."""
        if self._schema_cache is not None:
            return self._schema_cache

        from sqlalchemy import create_engine, inspect

        engine = create_engine(self.connection_string)
        try:
            inspector = inspect(engine)
            available = set(inspector.get_table_names())
            selected = self._select_tables(available, inspector)
            schema: Dict[str, Any] = {}
            for table in selected:
                columns = [
                    col["name"] for col in inspector.get_columns(table)
                ]
                pk = []
                try:
                    pk_constraint = inspector.get_pk_constraint(table)
                    if isinstance(pk_constraint, dict):
                        pk = pk_constraint.get("constrained_columns", []) or []
                except Exception:
                    pk = []
                safe = [c for c in columns if not self._is_sensitive(c)]
                schema[table] = {"columns": columns, "safe_columns": safe, "pk": pk}
            self._schema_cache = schema
            return schema
        finally:
            engine.dispose()

    def _select_tables(self, available: Set[str], inspector) -> List[str]:
        requested = self.tables
        if requested and "*" in requested:
            requested = None
        if not requested:
            return sorted(available)
        selected = []
        for t in requested:
            name = t.strip().strip('`"')
            if name in available:
                selected.append(name)
            else:
                self._log_error(
                    f"Table '{t}' not found in database. "
                    f"Available: {sorted(available)}"
                )
        return selected

    def _is_sensitive(self, column_name: str) -> bool:
        name_lower = column_name.lower()
        return any(p in name_lower for p in SENSITIVE_COLUMN_PATTERNS)

    def _quote_identifier(self, name: str) -> str:
        clean = name.strip().strip('`')
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", clean):
            raise ValueError(f"Invalid SQL identifier: {clean}")
        return f"`{clean}`"

    # ------------------------------------------------------------------ #
    # Extração de registros
    # ------------------------------------------------------------------ #

    def load(self) -> List[LoadedDocument]:
        schema = self.get_schema()
        documents: List[LoadedDocument] = []

        from sqlalchemy import create_engine

        engine = create_engine(self.connection_string)
        try:
            for table, info in schema.items():
                try:
                    documents.extend(self._load_table(engine, table, info))
                except Exception as e:
                    self._log_error(f"Failed to load table '{table}': {e}")
                    continue
        finally:
            engine.dispose()

        self._log_info(f"Total: {len(documents)} records loaded from database")
        return documents

    def _load_table(self, engine, table: str, info: Dict) -> List[LoadedDocument]:
        safe_columns = info["safe_columns"]
        pk_columns = info["pk"]
        if not safe_columns:
            self._log_warning(f"Table '{table}': all columns filtered as sensitive, skipping")
            return []

        quoted = self._quote_identifier(table)
        query = sa_text(f"SELECT * FROM {quoted}")
        with engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()

        self._log_info(
            f"Table '{table}': {len(rows)} rows, "
            f"{len(safe_columns)} columns exposed"
        )

        documents = []
        for row_index, row in enumerate(rows):
            row_dict = dict(row._mapping)
            documents.append(
                self._row_to_document(table, row_dict, safe_columns, pk_columns)
            )
        return documents

    def _row_to_document(
        self,
        table_name: str,
        row: Dict[str, Any],
        safe_columns: List[str],
        pk_columns: List[str],
    ) -> LoadedDocument:
        lines = [f"[Tabela: {table_name}]"]
        for col in safe_columns:
            value = row.get(col)
            if value is None:
                value = "(vazio)"
            elif isinstance(value, datetime):
                value = value.isoformat()
            lines.append(f"{col}: {value}")
        content = "\n".join(lines)

        safe_pk_values = [
            str(row.get(col, "")) for col in pk_columns if col in safe_columns
        ]
        if safe_pk_values:
            suffix = "_".join(safe_pk_values)
        else:
            suffix = hashlib.md5(content.encode()).hexdigest()[:12]

        filename = f"{table_name}/{suffix}"
        filepath = f"db://{table_name}/{suffix}"

        modified_at = row.get("updated_at") or row.get("created_at") or datetime.now()
        if isinstance(modified_at, datetime):
            modified_at = modified_at.isoformat()
        else:
            modified_at = str(modified_at)

        return LoadedDocument(
            content=content,
            filepath=filepath,
            filename=filename,
            file_type="db",
            modified_at=modified_at,
            file_size=len(content),
            source_type=self.source_type,
            source_id=filepath,
            metadata={"table": table_name, "record_id": suffix},
            content_hash=sha256_text(content),
        )

    # ------------------------------------------------------------------ #

    def _log_info(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def _log_warning(self, message: str) -> None:
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str) -> None:
        if self.logger:
            self.logger.error(message)