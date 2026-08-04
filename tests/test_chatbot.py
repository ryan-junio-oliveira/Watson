from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from rag.chatbot import ChatBot
from rag.response import AgentResponse, Mode


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
        builder.build_with_history.return_value = "Prompt com historico"
        return builder

    @pytest.fixture
    def mock_ollama_client(self):
        client = MagicMock()
        client.ask.return_value = "Resposta baseada no contexto."
        client._strip_thinking.return_value = "Resposta baseada no contexto."
        client.ask_stream.return_value = iter(["Resposta ", "baseada ", "no ", "contexto."])
        return client

    @pytest.fixture
    def chatbot(self, mock_retriever, mock_prompt_builder, mock_ollama_client):
        return ChatBot(
            retriever=mock_retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=mock_ollama_client,
        )

    def test_ask_returns_agent_response(self, chatbot):
        result = chatbot.ask("Qual a capital do Brasil?")
        assert isinstance(result, AgentResponse)
        assert isinstance(result.answer, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.verdict, str)

    def test_ask_with_empty_context(self, mock_prompt_builder, mock_ollama_client):
        retriever = MagicMock()
        retriever.retrieve.return_value = []
        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=mock_ollama_client,
        )
        result = chatbot.ask("Pergunta sem contexto")
        assert isinstance(result, AgentResponse)

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

    def test_ask_stream_yields_tokens(self, chatbot, mock_ollama_client):
        tokens = list(chatbot.ask_stream("Pergunta?"))
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_ask_stream_returns_agent_response(self, chatbot):
        gen = chatbot.ask_stream("Pergunta?")
        tokens = []
        try:
            while True:
                tokens.append(next(gen))
        except StopIteration as e:
            result = e.value
        assert isinstance(result, AgentResponse)
        assert result.answer == "".join(tokens)

    def test_ask_auto_mode_retrieves_rag(self, mock_prompt_builder, mock_ollama_client):
        retriever = MagicMock()
        retriever.retrieve.return_value = []
        chatbot = ChatBot(
            retriever=retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=mock_ollama_client,
        )
        result = chatbot.ask("Pergunta?", mode=Mode.auto)
        retriever.retrieve.assert_called_once()
        assert isinstance(result, AgentResponse)

    def test_ask_rag_mode(self, chatbot):
        result = chatbot.ask("Pergunta?", mode=Mode.rag)
        assert isinstance(result, AgentResponse)

    def test_ask_stream_auto_mode(self, chatbot):
        gen = chatbot.ask_stream("Pergunta?", mode=Mode.auto)
        tokens = []
        try:
            while True:
                tokens.append(next(gen))
        except StopIteration as e:
            result = e.value
        assert isinstance(result, AgentResponse)

    def test_ask_stream_survives_llm_timeout(self, mock_retriever, mock_prompt_builder):
        client = MagicMock()
        def failing_stream(*args, **kwargs):
            yield "token1 "
            raise TimeoutError("LLM timed out")
        client.ask_stream = failing_stream
        client.ask.return_value = "fallback"
        client._strip_thinking.return_value = "fallback"
        chatbot = ChatBot(
            retriever=mock_retriever,
            prompt_builder=mock_prompt_builder,
            ollama_client=client,
        )
        gen = chatbot.ask_stream("Pergunta?")
        tokens = []
        try:
            while True:
                tokens.append(next(gen))
        except StopIteration as e:
            result = e.value
        assert isinstance(result, AgentResponse)
        assert "token1 " in result.answer
