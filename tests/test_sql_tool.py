import sqlite3

import pytest

from ingestion.adapters.db_adapter import DatabaseAdapter
from tools.sql_tool import SqlQueryTool


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE printers (id INTEGER PRIMARY KEY, modelo TEXT, "
        "tipo TEXT, ativo INTEGER, password TEXT)"
    )
    conn.executemany(
        "INSERT INTO printers (modelo, tipo, ativo, password) VALUES (?, ?, ?, ?)",
        [
            ("E52645", "printer", 1, "segredo"),
            ("MFC-7860DW", "printer", 1, "segredo2"),
            ("SC-1520", "scanner", 0, "segredo3"),
        ],
    )
    conn.commit()
    conn.close()
    return str(path)


class TestDatabaseAdapter:
    def test_schema_detection(self, db_path):
        adapter = DatabaseAdapter(f"sqlite:///{db_path}")
        schema = adapter.get_schema()
        assert "printers" in schema
        info = schema["printers"]
        assert info["pk"] == ["id"]
        assert "password" not in info["safe_columns"]

    def test_load_records_as_documents(self, db_path):
        adapter = DatabaseAdapter(f"sqlite:///{db_path}")
        docs = adapter.load()
        assert len(docs) == 3
        assert docs[0].source_type == "database"
        assert docs[0].filepath.startswith("db://printers/")
        assert "password" not in docs[0].content
        assert docs[0].content_hash

    def test_record_identity_stable(self, db_path):
        adapter = DatabaseAdapter(f"sqlite:///{db_path}")
        docs = adapter.load()
        assert docs[0].source_id == f"db://printers/{docs[0].metadata['record_id']}"

    def test_sensitive_columns_filtered(self, db_path):
        adapter = DatabaseAdapter(f"sqlite:///{db_path}")
        docs = adapter.load()
        assert all("password" not in d.content for d in docs)

    def test_tables_whitelist(self, db_path):
        adapter = DatabaseAdapter(f"sqlite:///{db_path}", tables=["printers"])
        assert "printers" in adapter.get_schema()


class TestSqlQueryTool:
    def test_configured(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        assert tool.configured is True

    def test_validate_rejects_dml(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        assert tool.validate("DELETE FROM printers") is not None
        assert tool.validate("DROP TABLE printers") is not None
        assert tool.validate("UPDATE printers SET tipo='x'") is not None

    def test_validate_rejects_multiple_statements(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        assert tool.validate("SELECT * FROM printers; SELECT * FROM printers") is not None

    def test_validate_unknown_table(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        assert "desconhecida" in tool.validate("SELECT * FROM nao_existe")

    def test_validate_ok(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        assert tool.validate("SELECT modelo FROM printers WHERE ativo=1") is None

    def test_execute_returns_rows(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        rows = tool.execute("SELECT modelo, ativo FROM printers WHERE ativo=1")
        assert len(rows) == 2
        assert {"modelo", "ativo"} <= set(rows[0].keys())

    def test_execute_strips_sensitive_columns(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        rows = tool.execute("SELECT * FROM printers")
        assert all("password" not in r for r in rows)

    def test_execute_enforces_limit(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}", max_rows=2)
        rows = tool.execute("SELECT modelo FROM printers")
        assert len(rows) == 2

    def test_execute_invalid_raises(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        with pytest.raises(ValueError):
            tool.execute("DROP TABLE printers")

    def test_rows_to_text(self, db_path):
        tool = SqlQueryTool(f"sqlite:///{db_path}")
        rows = tool.execute("SELECT modelo FROM printers LIMIT 1")
        text = tool.rows_to_text(rows)
        assert "modelo" in text