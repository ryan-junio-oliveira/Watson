from unittest.mock import MagicMock, patch

import pytest

from ingestion.db_loader import DatabaseLoader


class TestDatabaseLoader:
    @pytest.fixture
    def loader(self):
        return DatabaseLoader(connection_string="mysql+pymysql://user:pass@localhost/test")

    def test_sensitive_column_detection(self, loader):
        assert loader._is_sensitive("password") is True
        assert loader._is_sensitive("senha") is True
        assert loader._is_sensitive("secret_token") is True
        assert loader._is_sensitive("recovery_codes") is True
        assert loader._is_sensitive("two_factor_auth") is True

    def test_non_sensitive_column_detection(self, loader):
        assert loader._is_sensitive("name") is False
        assert loader._is_sensitive("email") is False
        assert loader._is_sensitive("created_at") is False
        assert loader._is_sensitive("description") is False

    @patch("sqlalchemy.create_engine")
    def test_load_rejects_invalid_tables(self, mock_create_engine, loader):
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["valid_table"]
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_engine.connect.return_value.__enter__.return_value = MagicMock()

        loader.tables = ["nonexistent_table"]
        with patch("sqlalchemy.inspect", return_value=mock_inspector):
            result = loader.load()

        assert result == []

    @patch("sqlalchemy.create_engine")
    def test_load_accepts_valid_tables(self, mock_create_engine, loader):
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["valid_table"]
        mock_inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "name"},
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        loader.tables = ["valid_table"]
        with patch("sqlalchemy.inspect", return_value=mock_inspector):
            result = loader.load()

        assert result is not None

    @patch("sqlalchemy.create_engine")
    def test_filter_sensitive_columns(self, mock_create_engine, loader):
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users"]
        mock_inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "name"},
            {"name": "password"},
            {"name": "email"},
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        with patch("sqlalchemy.inspect", return_value=mock_inspector):
            result = loader.load()

        assert result is not None

    @patch("sqlalchemy.create_engine")
    def test_table_not_found_logs_error(self, mock_create_engine, loader):
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["valid_table"]
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_logger = MagicMock()
        loader.logger = mock_logger
        loader.tables = ["wrong_table"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector):
            loader.load()

        mock_logger.error.assert_called_once()

    def test_row_to_document(self, loader):
        doc = loader._row_to_document(
            table_name="users",
            row={"id": 1, "name": "John", "password": "secret"},
            safe_columns=["id", "name"],
            pk_columns=["id"],
            row_index=0,
        )
        assert doc.filepath == "db://users/1"
        assert doc.file_type == "db"
        assert "[Tabela: users]" in doc.content
        assert "name: John" in doc.content
        assert "password" not in doc.content
