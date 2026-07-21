from langchain_core.documents import Document

from rag.prompt import PromptBuilder


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()

    def test_build_returns_string(self):
        contexts = [
            Document(page_content="Contexto relevante.", metadata={"filename": "doc.txt"})
        ]
        prompt = self.builder.build("Qual a capital?", contexts)
        assert isinstance(prompt, str)
        assert "Qual a capital?" in prompt
        assert "Contexto relevante." in prompt
        assert "Fonte: doc.txt" in prompt

    def test_build_includes_system_prompt(self):
        contexts = [
            Document(page_content="Teste", metadata={"filename": "doc.txt"})
        ]
        prompt = self.builder.build("Pergunta?", contexts)
        assert "assistente especializado" in prompt

    def test_build_with_multiple_contexts(self):
        contexts = [
            Document(page_content="Primeiro documento.", metadata={"filename": "doc1.txt"}),
            Document(page_content="Segundo documento.", metadata={"filename": "doc2.txt"}),
        ]
        prompt = self.builder.build("Pergunta?", contexts)
        assert "Primeiro documento." in prompt
        assert "Segundo documento." in prompt
        assert "Fonte: doc1.txt" in prompt
        assert "Fonte: doc2.txt" in prompt

    def test_build_with_history(self):
        contexts = [
            Document(page_content="Contexto.", metadata={"filename": "doc.txt"})
        ]
        prompt = self.builder.build_with_history(
            "Pergunta?", contexts, history_context="user: Olá\nassistant: Olá!"
        )
        assert "Histórico da conversa:" in prompt
        assert "user: Olá" in prompt
        assert "Pergunta?" in prompt

    def test_build_without_history(self):
        contexts = [
            Document(page_content="Contexto.", metadata={"filename": "doc.txt"})
        ]
        prompt = self.builder.build_with_history("Pergunta?", contexts)
        assert "Histórico da conversa:" not in prompt
        assert "Pergunta?" in prompt

    def test_build_and_build_with_history_share_base(self):
        contexts = [
            Document(page_content="Mesmo contexto.", metadata={"filename": "doc.txt"})
        ]
        prompt1 = self.builder.build("Pergunta?", contexts)
        prompt2 = self.builder.build_with_history("Pergunta?", contexts, "user: Hi")
        assert prompt1 != prompt2
        assert "Histórico da conversa:" in prompt2
        assert "user: Hi" in prompt2
        assert "Mesmo contexto." in prompt1
        assert "Mesmo contexto." in prompt2

    def test_build_with_relevance_score(self):
        contexts = [
            Document(
                page_content="Conteudo relevante.",
                metadata={"filename": "doc.txt", "relevance_score": 0.95},
            )
        ]
        prompt = self.builder.build("Pergunta?", contexts)
        assert "Relevância: 0.95" in prompt
        assert "Fonte: doc.txt" in prompt

    def test_build_uses_numbered_contexts(self):
        contexts = [
            Document(page_content="Primeiro.", metadata={"filename": "a.txt"}),
            Document(page_content="Segundo.", metadata={"filename": "b.txt"}),
        ]
        prompt = self.builder.build("Pergunta?", contexts)
        assert "[1] Fonte: a.txt" in prompt
        assert "[2] Fonte: b.txt" in prompt

    def test_build_without_context_uses_fallback(self):
        prompt = self.builder.build("Pergunta?", [])
        assert "documentos relevantes" in prompt or "conhecimento geral" in prompt
        assert "Não foram encontrados documentos" in prompt
        assert "Pergunta?" in prompt

    def test_build_without_context_and_history_uses_fallback(self):
        prompt = self.builder.build_with_history(
            "Pergunta?", [], "user: Oi"
        )
        assert "Não foram encontrados documentos" in prompt
        assert "Histórico da conversa:" in prompt
        assert "user: Oi" in prompt

    def test_build_with_context_uses_system_prompt(self):
        contexts = [Document(page_content="Algo.", metadata={"filename": "f.txt"})]
        prompt = self.builder.build("Pergunta?", contexts)
        assert "APENAS com base no contexto" in prompt
        assert "documentos relevantes" not in prompt
