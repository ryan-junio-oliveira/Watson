"""SQL Tool — dados estruturados consultados diretamente via SQL (§12).

Separa o que deve ir para RAG (conhecimento textual) do que deve ser
consultado por SQL (dados estruturados). O tool é **read-only** e seguro:
- apenas SELECT/SHOW/DESCRIBE/EXPLAIN;
- apenas tabelas conhecidas do schema;
- LIMIT obrigatório (máximo configurável);
- colunas sensíveis são removidas do resultado.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ingestion.adapters.db_adapter import DatabaseAdapter, SENSITIVE_COLUMN_PATTERNS

_ALLOWED_PREFIX = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|EXPLAIN)\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"REPLACE|MERGE|ATTACH|DETACH|VACUUM|PRAGMA)\b",
    re.IGNORECASE,
)
_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)


class SqlQueryTool:
    def __init__(
        self,
        connection_string: str,
        tables: Optional[List[str]] = None,
        max_rows: int = 200,
        logger: Optional[logging.Logger] = None,
    ):
        self.connection_string = connection_string
        self.max_rows = max_rows
        self.logger = logger
        self._adapter = DatabaseAdapter(connection_string, tables=tables, logger=logger)
        self._schema_cache: Optional[Dict[str, Any]] = None

    @property
    def configured(self) -> bool:
        return bool(self.connection_string)

    def schema(self) -> Dict[str, Any]:
        if self._schema_cache is None:
            self._schema_cache = self._adapter.get_schema()
        return self._schema_cache

    def table_descriptions(self) -> str:
        """Resumo do schema para o prompt de geração de SQL."""
        lines = []
        for table, info in self.schema().items():
            cols = ", ".join(info["safe_columns"])
            lines.append(f"- {table}: {cols}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #

    def validate(self, sql: str) -> Optional[str]:
        """Valida a SQL. Retorna mensagem de erro ou None se OK."""
        if not sql or not sql.strip():
            return "SQL vazio"
        if ";" in sql.rstrip().rstrip(";"):
            return "Multiplas instrucoes nao sao permitidas"
        if _FORBIDDEN_KEYWORDS.search(sql):
            return "Apenas consultas de leitura sao permitidas"
        if not _ALLOWED_PREFIX.match(sql):
            return "Apenas SELECT/SHOW/DESCRIBE/EXPLAIN sao permitidos"

        tables = set(self.schema().keys())
        # Tabelas referenciadas (FROM/JOIN) precisam estar no whitelist
        referenced = re.findall(
            r"\b(?:FROM|JOIN)\s+[`]?([a-zA-Z_][a-zA-Z0-9_]*)",
            sql,
            re.IGNORECASE,
        )
        for t in referenced:
            if t not in tables:
                return f"Tabela desconhecida: {t}"
        return None

    def execute(self, sql: str) -> List[Dict[str, Any]]:
        """Executa a consulta validada e retorna linhas como dicts (colunas
        sensíveis removidas)."""
        error = self.validate(sql)
        if error:
            raise ValueError(f"SQL invalida: {error}")

        if not _LIMIT_RE.search(sql):
            sql = f"{sql.rstrip().rstrip(';')} LIMIT {self.max_rows}"

        from sqlalchemy import create_engine, text as sa_text

        engine = create_engine(self.connection_string)
        try:
            with engine.connect() as conn:
                result = conn.execute(sa_text(sql))
                rows = result.fetchmany(self.max_rows + 1)
            trimmed = rows[: self.max_rows]
            safe_rows = []
            for row in trimmed:
                mapping = dict(row._mapping)
                mapping = {
                    k: v for k, v in mapping.items()
                    if not any(p in k.lower() for p in SENSITIVE_COLUMN_PATTERNS)
                }
                safe_rows.append(self._serialize_values(mapping))
            return safe_rows
        finally:
            engine.dispose()

    @staticmethod
    def _serialize_values(row: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in row.items():
            if v is None:
                out[k] = None
            elif hasattr(v, "isoformat"):  # datetime/date
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    def rows_to_text(self, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return "(sem resultados)"
        lines: List[str] = []
        for r in rows:
            parts = [f"{k}: {v}" for k, v in r.items() if v is not None]
            lines.append(" | ".join(parts))
        return "\n".join(lines)