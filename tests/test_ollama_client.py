from unittest.mock import MagicMock, patch

import pytest

from llm.ollama_client import OllamaClient


class TestOllamaClient:
    @pytest.fixture
    def client(self):
        with patch("ollama.Client") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield OllamaClient(model="test-model", base_url="http://localhost:11434")

    def test_ask_returns_response(self, client):
        client._client.generate.return_value = {"response": "Resposta do modelo."}
        result = client.ask("Minha pergunta")
        assert result == "Resposta do modelo."
        client._client.generate.assert_called_once()

    def test_ask_passes_model_and_prompt(self, client):
        client._client.generate.return_value = {"response": "ok"}
        client.ask("teste")
        call_kwargs = client._client.generate.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["prompt"] == "teste"

    def test_ask_passes_options(self, client):
        client._client.generate.return_value = {"response": "ok"}
        client.ask("teste")
        call_kwargs = client._client.generate.call_args[1]
        assert "options" in call_kwargs
        assert call_kwargs["options"]["temperature"] == 0.1

    def test_ask_empty_response(self, client):
        client._client.generate.return_value = {}
        result = client.ask("teste")
        assert result == ""

    def test_ask_stream_yields_tokens(self, client):
        client._client.generate.return_value = [
            {"response": "Hello "},
            {"response": "World"},
        ]

        client._client.generate = MagicMock(return_value=[
            {"response": "Hello "},
            {"response": "World"},
        ])

        tokens = list(client.ask_stream("teste"))
        assert tokens == ["Hello ", "World"]

    def test_ask_stream_skips_empty(self, client):
        client._client.generate = MagicMock(return_value=[
            {"response": ""},
            {"response": "Real"},
        ])

        tokens = list(client.ask_stream("teste"))
        assert tokens == ["Real"]

    @patch("ollama.Client")
    def test_list_models_returns_names(self, mock_ollama_client):
        mock_instance = MagicMock()
        mock_ollama_client.return_value = mock_instance
        mock_model = MagicMock()
        mock_model.model = "qwen3:8b"
        mock_instance.list.return_value = MagicMock(models=[mock_model])

        client = OllamaClient()
        models = client.list_models()
        assert models == ["qwen3:8b"]

    @patch("ollama.Client")
    def test_list_models_fallback_on_error(self, mock_ollama_client):
        mock_instance = MagicMock()
        mock_ollama_client.return_value = mock_instance
        mock_instance.list.side_effect = Exception("Connection error")

        client = OllamaClient(model="fallback-model")
        models = client.list_models()
        assert models == ["fallback-model"]

    def test_default_model(self):
        with patch("ollama.Client") as mock:
            mock.return_value = MagicMock()
            client = OllamaClient()
            assert client.model == "qwen3:8b"
