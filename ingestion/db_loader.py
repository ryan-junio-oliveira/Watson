import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text as sa_text

from ingestion.loader import LoadedDocument


class DatabaseLoader:
    SENSITIVE_COLUMN_PATTERNS: Set[str] = {
        "password",
        "senha",
        "secret",
        "token",
        "recovery_codes",
        "two_factor",
        "remember_token",
    }

    # Cache for table names to avoid repeated inspections
    _table_cache: Dict[str, List[str]] = {}

    def __init__(
        self,
        connection_string: str,
        tables: Optional[List[str]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.connection_string = connection_string
        self.tables = tables
        self.logger = logger

    def _is_sensitive(self, column_name: str) -> bool:
        name_lower = column_name.lower()
        for pattern in self.SENSITIVE_COLUMN_PATTERNS:
            if pattern in name_lower:
                return True
        return False

    def _sanitize_table_name(self, table_name: str, available_tables: Set[str]) -> Optional[str]:
        """Validates a table name against available tables to prevent SQL injection."""
        name = table_name.strip().strip('`"')
        if name in available_tables:
            return name
        # Try with backticks
        if f"`{name}`" in available_tables:
            return f"`{name}`"
        return None

    def _quote_identifier(self, name: str) -> str:
        """Safely quotes a SQL identifier using backticks."""
        # Remove any existing backticks and strip
        clean = name.strip().strip('`')
        # Only allow alphanumeric and underscores
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', clean):
            raise ValueError(f"Invalid SQL identifier: {clean}")
        return f"`{clean}`"

    def load(self) -> List[LoadedDocument]:
        try:
            from sqlalchemy import create_engine, inspect
        except ImportError:
            raise ImportError(
                "sqlalchemy is required for database loading. "
                "Install it with: pip install sqlalchemy pymysql"
            )

        documents: List[LoadedDocument] = []

        try:
            engine = create_engine(self.connection_string)
            inspector = inspect(engine)

            available_tables = set(inspector.get_table_names())
            requested = self.tables
            if requested and "*" in requested:
                requested = None

            if requested:
                # Validate each requested table against available tables
                validated_tables = []
                for t in requested:
                    valid = self._sanitize_table_name(t, available_tables)
                    if valid:
                        validated_tables.append(valid)
                    else:
                        self._log_error(
                            f"Table '{t}' not found in database. "
                            f"Available: {sorted(available_tables)}"
                        )
                if not validated_tables:
                    self._log_error("No valid tables found to load")
                    return documents
                table_names = validated_tables
            else:
                table_names = sorted(available_tables)

            if not table_names:
                self._log_info("No tables found in database")
                return documents

            self._log_info(f"Loading data from {len(table_names)} tables: {table_names}")

            for table_name in table_names:
                try:
                    all_columns = [col["name"] for col in inspector.get_columns(table_name)]
                    pk_constraint = inspector.get_pk_constraint(table_name)
                    pk_columns = pk_constraint.get("constrained_columns", []) if isinstance(pk_constraint, dict) else []

                    safe_columns = [c for c in all_columns if not self._is_sensitive(c)]
                    filtered_columns = [c for c in all_columns if self._is_sensitive(c)]

                    if filtered_columns:
                        self._log_info(
                            f"  Table '{table_name}': filtered sensitive columns: {filtered_columns}"
                        )

                    if not safe_columns:
                        self._log_warning(
                            f"  Table '{table_name}': all columns filtered as sensitive, skipping"
                        )
                        continue

                    # Use quoted, validated table name
                    quoted_table = self._quote_identifier(table_name)
                    query = sa_text(f"SELECT * FROM {quoted_table}")

                    with engine.connect() as conn:
                        result = conn.execute(query)
                        rows = result.fetchall()

                    self._log_info(
                        f"  Table '{table_name}': {len(rows)} rows, "
                        f"{len(safe_columns)}/{len(all_columns)} columns exposed"
                    )

                    row_index = 0
                    for row in rows:
                        row_dict = dict(row._mapping)
                        doc = self._row_to_document(
                            table_name, row_dict, safe_columns, pk_columns, row_index
                        )
                        documents.append(doc)
                        row_index += 1

                except Exception as e:
                    self._log_error(f"Failed to load table '{table_name}': {e}")
                    continue

            engine.dispose()
            self._log_info(
                f"Total: {len(documents)} records loaded from database "
                f"(sensitive fields excluded)"
            )

        except Exception as e:
            self._log_error(f"Database connection failed: {e}")
            raise

        return documents

    def _row_to_document(
        self,
        table_name: str,
        row: Dict[str, Any],
        safe_columns: List[str],
        pk_columns: List[str],
        row_index: int,
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

        modified_at = row.get("updated_at") or row.get("created_at") or datetime.now()
        if isinstance(modified_at, datetime):
            modified_at = modified_at.isoformat()
        else:
            modified_at = str(modified_at)

        return LoadedDocument(
            content=content,
            filepath=f"db://{table_name}/{suffix}",
            filename=filename,
            file_type="db",
            modified_at=modified_at,
            file_size=len(content),
        )

    def _log_info(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def _log_warning(self, message: str) -> None:
        if self.logger:
            self.logger.warning(message)

    def _log_error(self, message: str) -> None:
        if self.logger:
            self.logger.error(message)
