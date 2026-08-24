from rag.evidence import Evidence
from rag.prompt import PromptBuilder
from rag.response import Mode


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()

    def _ev(self, content: str, title: str = "", url: str = "") -> Evidence:
        return Evidence(
            provider="test",
            source=url or title or "test",
            title=title,
            url=url,
            content=content,
            score=1.0,
            source_type="rag",
        )

    def test_build_returns_string(self):
        evidences = [self._ev("Brasília é a capital.", "Site X", "https://exemplo.com")]
        prompt = self.builder.build("Qual a capital?", evidences)
        assert isinstance(prompt, str)
        assert "Qual a capital?" in prompt
        assert "Brasília é a capital" in prompt

    def test_build_includes_system_prompt(self):
        prompt = self.builder.build("Pergunta?", [self._ev("teste")])
        assert "analista meticuloso" in prompt

    def test_build_with_history(self):
        prompt = self.builder.build_with_history(
            "Pergunta?",
            [self._ev("teste")],
            history_context="user: Olá\nassistant: Olá!",
        )
        assert "Histórico da conversa:" in prompt
        assert "user: Olá" in prompt
        assert "Pergunta?" in prompt

    def test_build_without_history(self):
        prompt = self.builder.build_with_history("Pergunta?", [self._ev("teste")])
        assert "Histórico da conversa:" not in prompt
        assert "Pergunta?" in prompt

    def test_build_without_evidence_uses_no_evidence_prompt(self):
        prompt = self.builder.build("Pergunta?", None)
        assert "Não foram encontradas informações" in prompt
        assert "Pergunta?" in prompt

    def test_build_without_evidence_and_history_uses_no_evidence_prompt(self):
        prompt = self.builder.build_with_history("Pergunta?", None, "user: Oi")
        assert "Não foram encontradas informações" in prompt
        assert "Histórico da conversa:" in prompt
        assert "user: Oi" in prompt

    def test_build_with_evidence_uses_system_prompt(self):
        prompt = self.builder.build(
            "Pergunta?", [self._ev("Algo importante.", "Fonte")]
        )
        assert "analista meticuloso" in prompt

    def test_build_includes_evidence_in_prompt(self):
        e1 = self._ev("O céu é azul.", "Fonte A", "https://a.com")
        e2 = self._ev("A grama é verde.", "Fonte B", "https://b.com")
        prompt = self.builder.build("Pergunta?", [e1, e2])
        assert "O céu é azul" in prompt
        assert "A grama é verde" in prompt
        assert "a.com" in prompt
        assert "b.com" in prompt

    def test_build_auto_mode_no_evidence_uses_no_evidence_prompt(self):
        prompt = self.builder.build("Pergunta?", mode=Mode.auto)
        assert "Não foram encontradas informações" in prompt
        assert "base de conhecimento indexada" in prompt

    def test_build_rag_mode_no_evidence_uses_no_evidence_prompt(self):
        prompt = self.builder.build("Pergunta?", mode=Mode.rag)
        assert "Não foram encontradas informações" in prompt
        assert "base de conhecimento indexada" in prompt

    def test_build_rag_mode_with_evidence_uses_system_prompt(self):
        prompt = self.builder.build(
            "Pergunta?", [self._ev("Algo importante.", "Fonte")], mode=Mode.rag
        )
        assert "analista meticuloso" in prompt
        assert "Evidências:" in prompt

    def test_build_with_history_and_mode(self):
        prompt = self.builder.build_with_history(
            "Pergunta?", mode=Mode.rag, history_context="user: Oi"
        )
        assert "Histórico da conversa:" in prompt
        assert "user: Oi" in prompt
