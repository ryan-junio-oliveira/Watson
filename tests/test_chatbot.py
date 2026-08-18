from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from rag.chatbot import ChatBot, extract_sql
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


class TestExtractSql:
    def test_extracts_from_fences(self):
        raw = "Aqui está:\n```sql\nSELECT * FROM printers WHERE ativo=1\n```"
        assert "SELECT * FROM printers" in extract_sql(raw)

    def test_extracts_plain_select(self):
        assert extract_sql("SELECT modelo FROM printers") == "SELECT modelo FROM printers"


class TestSqlRouting:
    def make_chatbot(self, sql_tool=None, mock_retriever=None, mock_ollama=None):
        retriever = mock_retriever or MagicMock()
        retriever.retrieve.return_value = []
        builder = MagicMock()
        builder.build.return_value = "prompt"
        ollama = mock_ollama or MagicMock()
        ollama.ask.return_value = "Resposta SQL"
        ollama._strip_thinking.return_value = "Resposta SQL"
        return ChatBot(
            retriever=retriever,
            prompt_builder=builder,
            ollama_client=ollama,
            sql_tool=sql_tool,
        )

    def test_sql_routing_is_disabled_by_default(self):
        # Tudo é respondido via RAG; não há roteamento automático para SQL.
        tool = MagicMock()
        tool.configured = True
        bot = self.make_chatbot(sql_tool=tool)
        assert bot._should_use_sql("Quantas licenças ativas?", Mode.auto) is False
        assert bot._should_use_sql("Quantas licenças?", Mode.rag) is False

    def test_structured_question_goes_to_rag(self):
        tool = MagicMock()
        tool.configured = True
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            Document(page_content="dados de clientes", metadata={"filename": "clients"})
        ]
        bot = self.make_chatbot(sql_tool=tool, mock_retriever=retriever)
        resp = bot.ask("Quais clientes temos cadastrados?")
        # caiu em RAG (não em SQL)
        assert resp.metadata.get("provider") in ("rag", None)
        retriever.retrieve.assert_called_once()

    def test_process_sql_still_available_explicit(self):
        tool = MagicMock()
        tool.configured = True
        tool.table_descriptions.return_value = "- printers: modelo, tipo"
        tool.execute.return_value = [{"modelo": "E52645", "tipo": "printer"}]
        tool.rows_to_text.return_value = "modelo: E52645 | tipo: printer"

        ollama = MagicMock()
        ollama.ask.return_value = "SELECT modelo FROM printers"
        ollama._strip_thinking.return_value = "SELECT modelo FROM printers"
        bot = self.make_chatbot(sql_tool=tool, mock_ollama=ollama)

        resp = bot._process_sql("Quantas impressoras existem?")
        assert isinstance(resp, AgentResponse)
        assert resp.metadata.get("provider") == "sql"
        assert resp.metadata.get("rows") == 1
        assert resp.evidences[0].provider == "sql"
