"""Backward-compat: `DatabaseLoader` agora é o `DatabaseAdapter`.

A implementação real está em `ingestion/adapters/db_adapter.py` (§6/§11).
"""

from ingestion.adapters.db_adapter import DatabaseAdapter as DatabaseLoader
from ingestion.adapters.db_adapter import SENSITIVE_COLUMN_PATTERNS

__all__ = ["DatabaseLoader", "SENSITIVE_COLUMN_PATTERNS"]