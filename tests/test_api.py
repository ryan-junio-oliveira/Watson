import json
from unittest.mock import MagicMock, patch

from rag.response import AgentResponse

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_env(tmp_path):
    with patch("api.app_config") as mock_cfg:
        mock_cfg.vector_db_dir = "/tmp/test_chroma"
        mock_cfg.documents_dir = "/tmp/test_docs"
        mock_cfg.log_level = "INFO"
        mock_cfg.log_file = "/tmp/test.log"
        mock_cfg.ollama_model = "test-model"
        mock_cfg.ollama_base_url = "http://localhost:11434"
        mock_cfg.ollama_timeout = 300
        mock_cfg.embedding_model = "all-MiniLM-L6-v2"
        mock_cfg.embedding_device = "cpu"
        mock_cfg.embedding_batch_size = 32
        mock_cfg.embedding_normalize = True
        mock_cfg.embedding_cache_path = "/tmp/test_emb_cache.sqlite3"
        mock_cfg.tesseract_cmd = ""
        mock_cfg.ocr_lang = "por+eng"
        mock_cfg.ocr_dpi = 300
        mock_cfg.ocr_min_text_chars = 20
        mock_cfg.image_dir = "/tmp/images"
        mock_cfg.vision_model = ""
        mock_cfg.temperature = 0.1
        mock_cfg.max_tokens = 2048
        mock_cfg.chunk_size = 1000
        mock_cfg.chunk_overlap = 200
        mock_cfg.top_k = 5
        mock_cfg.similarity_threshold = None
        mock_cfg.use_mmr = False
        mock_cfg.mmr_fetch_k = 20
        mock_cfg.mmr_lambda = 0.5
        mock_cfg.use_reranker = False
        mock_cfg.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        mock_cfg.index_batch_size = 100
        mock_cfg.google_drive_folder_id = ""
        mock_cfg.google_drive_dest_dir = "/tmp/test_drive"
        mock_cfg.google_drive_sync_timeout = 30
        mock_cfg.metrics_db = str(tmp_path / "metrics.db")
        mock_cfg.api_auth_token = ""
        mock_cfg.api_rate_limit = 1000
        mock_cfg.api_rate_window = 60
        mock_cfg.api_rate_enabled = False
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


class TestChatEndpoint:
    def test_chat_requires_question(self, client):
        response = client.post("/api/chat", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_chat_empty_question(self, client):
        response = client.post("/api/chat", json={"question": ""})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("api.chatbot")
    def test_chat_returns_answer(self, mock_chatbot, client):
        mock_chatbot.ask.return_value = AgentResponse(
            answer="Resposta do modelo.",
            evidences=[],
            confidence=0.95,
            verdict="consistent",
        )
        response = client.post("/api/chat", json={"question": "Qual a capital?"})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["answer"] == "Resposta do modelo."
        assert data["confidence"] == 0.95

    @patch("api.chatbot")
    def test_chat_response_has_sources_and_metadata(self, mock_chatbot, client):
        from rag.evidence import Evidence
        mock_chatbot.ask.return_value = AgentResponse(
            answer="Resposta com fontes.",
            evidences=[
                Evidence(title="Fonte1", url="https://exemplo.com", content="...", source="exemplo", provider="web"),
            ],
            confidence=0.8,
            verdict="partial",
        )
        response = client.post("/api/chat", json={"question": "Com fontes?"})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["sources"]) == 1
        assert data["sources"][0]["title"] == "Fonte1"
        assert data["sources"][0]["url"] == "https://exemplo.com"
        assert "metadata" in data
        assert "evidence_count" in data["metadata"]
        assert "execution_time_ms" in data["metadata"]

    @patch("api.chatbot")
    def test_chat_with_history(self, mock_chatbot, client):
        mock_chatbot.ask_with_context.return_value = AgentResponse(
            answer="Resposta contextual.",
            evidences=[],
            confidence=0.8,
            verdict="partial",
        )
        history = [{"role": "user", "content": "Olá"}]
        response = client.post(
            "/api/chat",
            json={"question": "Lembra de mim?", "history": history},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["answer"] == "Resposta contextual."
        assert data["confidence"] == 0.8

    @patch("api.chatbot")
    def test_chat_with_auto_mode(self, mock_chatbot, client):
        mock_chatbot.ask.return_value = AgentResponse(
            answer="Resposta baseada nos documentos.",
            evidences=[],
            confidence=0.9,
            verdict="consistent",
        )
        response = client.post(
            "/api/chat",
            json={"question": "Quais servidores estao cadastrados?", "mode": "auto"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["answer"] == "Resposta baseada nos documentos."
        from rag.response import Mode
        mock_chatbot.ask.assert_called_with(
            "Quais servidores estao cadastrados?", mode=Mode.auto, analyze=False
        )

    @patch("api.chatbot")
    def test_chat_stream_with_auto_mode(self, mock_chatbot, client):
        result = AgentResponse(
            answer="5 servidores encontrados",
            evidences=[],
            confidence=0.9,
            verdict="consistent",
        )
        mock_chatbot.ask_stream.return_value = _stream_gen(["5"], result)
        response = client.post(
            "/api/chat/stream",
            json={"question": "Quantos servidores?", "mode": "auto"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert 'data: {"content": "5"}' in response.text


def _stream_gen(tokens, result):
    yield from tokens
    return result


class TestChatStreamEndpoint:
    @patch("api.chatbot")
    def test_chat_stream_returns_sse_events(self, mock_chatbot, client):
        result = AgentResponse(
            answer="Resposta do modelo.",
            evidences=[],
            confidence=0.95,
            verdict="consistent",
            issues=[],
        )
        mock_chatbot.ask_stream.return_value = _stream_gen(
            ["Resposta ", "do ", "modelo."], result
        )
        response = client.post(
            "/api/chat/stream",
            json={"question": "Qual a capital?"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        lines = response.text.strip().split("\n\n")
        # tokens são enviados como JSON (preserva newlines/ espaços do markdown)
        assert json.loads(lines[0].replace("data: ", "", 1)) == {"content": "Resposta "}
        assert json.loads(lines[1].replace("data: ", "", 1)) == {"content": "do "}
        assert json.loads(lines[2].replace("data: ", "", 1)) == {"content": "modelo."}
        assert lines[3] == "data: [DONE]"
        final = json.loads(lines[4].replace("data: ", "", 1))
        assert final["confidence"] == 0.95

    @patch("api.chatbot")
    def test_chat_stream_does_not_emit_validation_event(self, mock_chatbot, client):
        result = AgentResponse(
            answer="Resposta.",
            evidences=[],
            confidence=0.8,
            verdict="partial",
        )
        mock_chatbot.ask_stream.return_value = _stream_gen(["Resposta."], result)
        response = client.post(
            "/api/chat/stream",
            json={"question": "Teste?"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "[VALIDATION]" not in response.text

    @patch("api.chatbot")
    def test_chat_stream_with_history(self, mock_chatbot, client):
        result = AgentResponse(
            answer="Resposta contextual.",
            evidences=[],
            confidence=0.8,
            verdict="partial",
        )
        mock_chatbot.ask_stream_with_history.return_value = _stream_gen(
            ["Resposta ", "contextual."], result
        )
        history = [{"role": "user", "content": "Olá"}]
        response = client.post(
            "/api/chat/stream",
            json={"question": "Lembra de mim?", "history": history},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "data: [DONE]" in response.text

    @patch("api.chatbot")
    def test_chat_stream_empty_question(self, mock_chatbot, client):
        response = client.post("/api/chat/stream", json={"question": ""})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_stream_no_question(self, client):
        response = client.post("/api/chat/stream", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_chat_stream_not_initialized(self, client):
        with patch("api.chatbot", None):
            response = client.post(
                "/api/chat/stream",
                json={"question": "Qual a capital?"},
            )
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


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
    @patch("api.indexer")
    @patch("api.cfg")
    def test_index_all(self, mock_cfg, mock_indexer, client, tmp_path):
        mock_indexer.has_pending_changes.return_value = (False, [], set())
        mock_indexer.index.return_value = 0
        mock_cfg.documents_dir = str(tmp_path)

        response = client.post("/api/index")
        assert response.status_code == status.HTTP_200_OK

    def test_index_async_starts_job(self, client):
        with patch("api._start_index_job") as mock_start:
            mock_start.return_value = "job123"
            response = client.post("/api/index/async", json={"mode": "documents"})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "started"
        assert data["job_id"] == "job123"
        mock_start.assert_called_once_with(
            index_documents=True, sync_drive=False
        )

    def test_index_async_sync_drive_true(self, client):
        with patch("api._start_index_job") as mock_start:
            mock_start.return_value = "job456"
            response = client.post(
                "/api/index/async",
                json={"mode": "all", "sync_drive": True},
            )
        assert response.status_code == status.HTTP_200_OK
        mock_start.assert_called_once_with(
            index_documents=True, sync_drive=True
        )

    def test_index_async_prunes_old_jobs(self, client):
        with patch("api._prune_index_jobs") as mock_prune, \
             patch("api._start_index_job") as mock_start:
            mock_start.return_value = "job789"
            response = client.post("/api/index/async", json={"mode": "documents"})
        assert response.status_code == status.HTTP_200_OK
        mock_prune.assert_called_once()

    def test_index_async_invalid_mode(self, client):
        with patch("api._start_index_job") as mock_start:
            response = client.post("/api/index/async", json={"mode": "nope"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_start.assert_not_called()

    def test_index_status_not_found(self, client):
        response = client.get("/api/index/status/inexistente")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_index_status_running(self, client):
        with patch("api._get_index_job") as mock_get:
            mock_get.return_value = {
                "status": "running", "result": None, "error": None,
                "progress": 2, "total": 10, "message": "doc.pdf",
            }
            response = client.get("/api/index/status/abc123")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["result"] is None
        assert data["progress"] == 2
        assert data["total"] == 10
        assert data["message"] == "doc.pdf"

    def test_index_status_done(self, client):
        with patch("api._get_index_job") as mock_get:
            mock_get.return_value = {
                "status": "done",
                "result": {
                    "status": "ok",
                    "documents_indexed": 3,
                    "total_chunks": 42,
                },
                "error": None,
                "progress": 3, "total": 3, "message": "",
            }
            response = client.get("/api/index/status/abc123")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "done"
        assert data["result"]["total_chunks"] == 42
        assert data["progress"] == 3

    def test_index_cancel_not_found(self, client):
        with patch("api._get_index_job", return_value=None):
            response = client.post("/api/index/cancel/inexistente")
        assert response.status_code == status.HTTP_404_NOT_FOUND


    def test_index_cancel_not_running(self, client):
        with patch("api._get_index_job") as mock_get:
            mock_get.return_value = {"status": "done", "cancel_requested": False}
            response = client.post("/api/index/cancel/abc123")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_index_cancel_running_sets_flag(self, client):
        import api as api_mod

        api_mod._index_jobs.clear()
        api_mod._index_jobs["abc123"] = {"status": "running", "cancel_requested": False}

        response = client.post("/api/index/cancel/abc123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelling"
        assert data["job_id"] == "abc123"
        assert api_mod._index_jobs["abc123"]["cancel_requested"] is True
        api_mod._index_jobs.clear()

    def test_index_async_conflict_when_running(self, client):
        import api as api_mod
        import time

        api_mod._index_jobs.clear()
        api_mod._index_jobs["job_running"] = {
            "status": "running",
            "created_at": time.time(),
        }

        response = client.post("/api/index/async", json={"mode": "documents"})

        assert response.status_code == status.HTTP_409_CONFLICT
        api_mod._index_jobs.clear()


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


class TestDriveEndpoints:
    def test_drive_sync_requires_config(self, client, mock_env):
        response = client.post("/api/drive/sync")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_drive_sync_ok(self, client, mock_env, tmp_path):
        mock_env.google_drive_folder_id = "ROOT"
        mock_env.google_drive_dest_dir = str(tmp_path / "drive")
        from ingestion.drive_sync import GoogleDriveSync, SelectedFolder

        with patch.object(GoogleDriveSync, "sync") as mock_sync:
            mock_sync.return_value = MagicMock(
                files_remote=5,
                folders=2,
                downloaded=3,
                skipped=1,
                failed=0,
                removed=0,
                bytes_downloaded=100,
                errors=[],
            )
            response = client.post("/api/drive/sync")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["downloaded"] == 3

    def test_drive_selection_empty(self, client, mock_env, tmp_path):
        mock_env.google_drive_dest_dir = str(tmp_path / "drive")
        response = client.get("/api/drive/selection")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["folders"] == []

    def test_drive_selection_save(self, client, mock_env, tmp_path):
        mock_env.google_drive_dest_dir = str(tmp_path / "drive")
        payload = {"folders": [{"folder_id": "ABC", "path": "MANUAIS/HP"}]}
        response = client.post("/api/drive/selection", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["selected"] == 1
        assert data["folders"][0]["folder_id"] == "ABC"

        # persistido: reload
        response = client.get("/api/drive/selection")
        assert response.json()["folders"][0]["path"] == "MANUAIS/HP"

    def test_drive_clear(self, client, mock_env, tmp_path):
        drive_dir = tmp_path / "drive"
        drive_dir.mkdir()
        (drive_dir / "file.pdf").write_bytes(b"data")
        mock_env.google_drive_dest_dir = str(drive_dir)
        response = client.post("/api/drive/clear")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["removed"] == 1
        assert not (drive_dir / "file.pdf").exists()

    def test_drive_folder_lists(self, client, mock_env, tmp_path):
        mock_env.google_drive_dest_dir = str(tmp_path / "drive")
        from ingestion.drive_sync import DriveEntry, GoogleDriveSync

        with patch.object(GoogleDriveSync, "list_folder") as mock_list:
            mock_list.return_value = [
                DriveEntry(entry_id="F1", name="Pasta", is_folder=True, modified="5/13/25"),
                DriveEntry(entry_id="F2", name="doc.pdf", is_folder=False, modified=""),
            ]
            response = client.get("/api/drive/folder/ROOT")
        assert response.status_code == status.HTTP_200_OK
        items = response.json()
        assert items[0]["type"] == "folder"
        assert items[1]["type"] == "file"
        assert items[1]["name"] == "doc.pdf"


class TestAuthMiddleware:
    def test_no_token_configured_allows_request(self, client, mock_env):
        mock_env.api_auth_token = ""
        response = client.get("/api/models")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_missing_token_rejected(self, client, mock_env):
        mock_env.api_auth_token = "secret-token"
        response = client.get("/api/models")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_token_rejected(self, client, mock_env):
        mock_env.api_auth_token = "secret-token"
        response = client.get("/api/models", headers={"X-API-Token": "wrong"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_correct_header_token_accepted(self, client, mock_env):
        mock_env.api_auth_token = "secret-token"
        response = client.get("/api/models", headers={"X-API-Token": "secret-token"})
        assert response.status_code == status.HTTP_200_OK

    def test_bearer_token_accepted(self, client, mock_env):
        mock_env.api_auth_token = "secret-token"
        response = client.get(
            "/api/models", headers={"Authorization": "Bearer secret-token"}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_health_is_exempt_from_auth(self, client, mock_env):
        mock_env.api_auth_token = "secret-token"
        response = client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK


class TestMetricsEndpoints:
    def test_metrics_summary(self, client, mock_env):
        from metrics.store import MetricsStore
        store = MetricsStore(db_path=mock_env.metrics_db)
        store.record_llm_call(model="m", prompt_tokens=10, completion_tokens=5)
        store.record_request(question="olá")
        response = client.get("/api/metrics/summary?hours=24")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["llm_calls"] == 1
        assert data["total_prompt_tokens"] == 10
        assert data["requests"] == 1

    def test_metrics_tokens(self, client, mock_env):
        response = client.get("/api/metrics/tokens?hours=24")
        assert response.status_code == status.HTTP_200_OK
        assert "series" in response.json()

    def test_metrics_models(self, client, mock_env):
        response = client.get("/api/metrics/models?hours=24")
        assert response.status_code == status.HTTP_200_OK
        assert "models" in response.json()

    def test_metrics_documents(self, client, mock_env):
        from metrics.store import MetricsStore
        store = MetricsStore(db_path=mock_env.metrics_db)
        store.record_documents(documents=3, chunks=9)
        response = client.get("/api/metrics/documents")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["history"]

    def test_dashboard_page(self, client, mock_env):
        response = client.get("/dashboard")
        assert response.status_code == status.HTTP_200_OK
        assert "Chart" in response.text
