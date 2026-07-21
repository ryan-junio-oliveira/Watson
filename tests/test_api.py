import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_env():
    with patch("api.app_config") as mock_cfg:
        mock_cfg.vector_db_dir = "/tmp/test_chroma"
        mock_cfg.documents_dir = "/tmp/test_docs"
        mock_cfg.log_level = "INFO"
        mock_cfg.log_file = "/tmp/test.log"
        mock_cfg.ollama_model = "test-model"
        mock_cfg.ollama_base_url = "http://localhost:11434"
        mock_cfg.ollama_timeout = 120
        mock_cfg.embedding_model = "all-MiniLM-L6-v2"
        mock_cfg.embedding_device = "cpu"
        mock_cfg.temperature = 0.1
        mock_cfg.max_tokens = 2048
        mock_cfg.chunk_size = 1000
        mock_cfg.chunk_overlap = 200
        mock_cfg.top_k = 5
        mock_cfg.index_batch_size = 100
        mock_cfg.db_connection_string = None
        mock_cfg.db_tables = None
        yield mock_cfg


@pytest.fixture
def client():
    from api import app

    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client, mock_env):
        response = client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["ollama_model"] == "test-model"

    def test_health_shows_db_not_configured(self, client, mock_env):
        response = client.get("/api/health")
        data = response.json()
        assert data["db_configured"] is False

    def test_health_shows_db_configured(self, client, mock_env):
        mock_env.db_connection_string = "mysql://localhost/test"
        response = client.get("/api/health")
        data = response.json()
        assert data["db_configured"] is True


class TestChatEndpoint:
    def test_chat_requires_question(self, client):
        response = client.post("/api/chat", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_chat_empty_question(self, client):
        response = client.post("/api/chat", json={"question": ""})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("api.chatbot")
    def test_chat_returns_answer(self, mock_chatbot, client):
        mock_chatbot.ask.return_value = "Resposta do modelo."
        response = client.post("/api/chat", json={"question": "Qual a capital?"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["answer"] == "Resposta do modelo."

    @patch("api.chatbot")
    def test_chat_with_history(self, mock_chatbot, client):
        mock_chatbot.ask_with_context.return_value = "Resposta contextual."
        history = [{"role": "user", "content": "Olá"}]
        response = client.post(
            "/api/chat",
            json={"question": "Lembra de mim?", "history": history},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["answer"] == "Resposta contextual."


class TestUploadEndpoint:
    @patch("api.cfg")
    def test_upload_file(self, mock_cfg, client, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        mock_cfg.documents_dir = str(docs_dir)

        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.txt", b"conteudo do arquivo", "text/plain")},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["filename"] == "test.txt"

    @patch("api.cfg")
    def test_upload_sanitizes_filename(self, mock_cfg, client, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        mock_cfg.documents_dir = str(docs_dir)

        response = client.post(
            "/api/documents/upload",
            files={"file": ("../../etc/passwd", b"teste", "text/plain")},
        )
        assert response.status_code == status.HTTP_200_OK
        assert ".." not in response.json()["filename"]
        assert "/" not in response.json()["filename"]

    def test_upload_no_file(self, client):
        response = client.post("/api/documents/upload")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestIndexEndpoints:
    @patch("api.DatabaseLoader")
    @patch("api.indexer")
    @patch("api.cfg")
    def test_index_all(self, mock_cfg, mock_indexer, mock_db_loader_cls, client, tmp_path):
        mock_db_loader = MagicMock()
        mock_db_loader.load.return_value = []
        mock_db_loader_cls.return_value = mock_db_loader
        mock_indexer.has_pending_changes.return_value = (False, [], set())
        mock_indexer.index.return_value = 0
        mock_cfg.documents_dir = str(tmp_path)
        mock_cfg.db_connection_string = "mysql+pymysql://localhost/test"

        response = client.post("/api/index")
        assert response.status_code == status.HTTP_200_OK


class TestClearEndpoints:
    @patch("api.indexer")
    def test_clear_all(self, mock_indexer, client):
        mock_indexer.clear_vectorstore.return_value = 10
        mock_indexer.clear_documents.return_value = 5

        response = client.post("/api/clear")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["documents_removed"] == 5
        assert data["vectorstore_files_removed"] == 10

    @patch("api.indexer")
    def test_clear_vectorstore_only(self, mock_indexer, client):
        mock_indexer.clear_vectorstore.return_value = 10

        response = client.post("/api/clear/vectorstore")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["vectorstore_files_removed"] == 10


class TestModelsEndpoint:
    @patch("api.ollama_client")
    @patch("api.cfg")
    def test_list_models(self, mock_cfg, mock_ollama_client, client):
        mock_ollama_client.list_models.return_value = ["model1", "model2"]

        response = client.get("/api/models")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["models"] == ["model1", "model2"]
