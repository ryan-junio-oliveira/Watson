from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from rag.chatbot import ChatBot


class TestChatBot:
    @pytest.fixture
    def mock_retriever(self):
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            Document(
                page_content="Contexto relevante para resposta.",
                metadata={"filename": "doc.txt"},
            )
        ]
        return retriever

    @pytest.fixture
    def mock_prompt_builder(self):
        builder = MagicMock()
        builder.build.return_value = "Prompt com contexto e pergunta"
        return builder

    @pytest.fixture
    def mock_ollama_client(self):
        client = MagicMock()
        client.ask.return_value = "Resposta baseada no contexto."
        return client

    @pytest.fixture
    def chatbot(self, mock_retriever, mock_prompt_builder, mock_ollama_client):
        return ChatBot(
            retriever=mock_retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=mock_ollama_client,
        )

    def test_ask_returns_answer(self, chatbot, mock_retriever, mock_prompt_builder, mock_ollama_client):
        answer = chatbot.ask("Qual a capital do Brasil?")
        assert answer == "Resposta baseada no contexto."
        mock_retriever.retrieve.assert_called_once_with("Qual a capital do Brasil?")
        mock_prompt_builder.build.assert_called_once()
        mock_ollama_client.ask.assert_called_once_with("Prompt com contexto e pergunta")

    def test_ask_with_empty_context(self, mock_prompt_builder, mock_ollama_client):
        retriever = MagicMock()
        retriever.retrieve.return_value = []
        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=mock_ollama_client,
        )
        answer = chatbot.ask("Pergunta sem contexto")
        assert answer == "Resposta baseada no contexto."

    def test_chat_loop_exit(self, chatbot, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "exit")
        chatbot.chat_loop()

    def test_chat_loop_quit(self, chatbot, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "quit")
        chatbot.chat_loop()

    def test_chat_loop_empty_input(self, chatbot, monkeypatch):
        inputs = iter(["", "exit"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        chatbot.chat_loop()

    def test_chat_loop_question(self, chatbot, monkeypatch):
        inputs = iter(["Qual a capital?", "exit"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        chatbot.chat_loop()
