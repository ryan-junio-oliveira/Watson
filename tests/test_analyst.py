from unittest.mock import MagicMock

from langchain_core.documents import Document

from rag.analyst import Analyst, _extract_block, _split_items
from rag.evidence import Evidence


class TestParsing:
    def test_split_items_strips_bullets(self):
        text = "- conclusão um\n* conclusão dois\n3. terceira"
        assert _split_items(text) == [
            "conclusão um",
            "conclusão dois",
            "terceira",
        ]

    def test_extract_block(self):
        text = (
            "CONCLUSOES:\n- a\n- b\n\n"
            "PERGUNTAS:\n1. q1\n2. q2\n\n"
            "TOPICOS:\n- t1"
        )
        assert _split_items(_extract_block(text, "CONCLUSOES")) == ["a", "b"]
        assert _split_items(_extract_block(text, "PERGUNTAS")) == ["q1", "q2"]
        assert _split_items(_extract_block(text, "TOPICOS")) == ["t1"]


class TestAnalyst:
    def make_analyst(self, reflect_raw=""):
        retriever = MagicMock()
        ollama = MagicMock()
        ollama.ask.return_value = reflect_raw
        ollama._strip_thinking.return_value = reflect_raw
        return Analyst(retriever=retriever, ollama_client=ollama, max_followups=3)

    def _ev(self, content, chunk_id="c1"):
        return Evidence(
            provider="chroma",
            source="doc.pdf",
            content=content,
            chunk_id=chunk_id,
            metadata={"chunk_id": chunk_id},
        )

    def test_analyze_parses_blocks(self):
        raw = (
            "CONCLUSOES:\n- A impressora está acima do volume recomendado.\n"
            "- Ainda é possível usar pela bandeja bypass.\n\n"
            "PERGUNTAS:\n1. A remessa de papel é avulsa ou em volume?\n"
            "2. Qual a gramatura máxima suportada pela bypass?\n\n"
            "TOPICOS:\n- bandeja bypass gramatura máxima"
        )
        analyst = self.make_analyst(reflect_raw=raw)
        result = analyst.analyze(
            "Posso usar papel 120g?", "Use pela bypass.", [self._ev("dados")]
        )
        assert len(result.conclusions) == 2
        assert len(result.follow_up) == 2
        assert result.follow_up[0].startswith("A remessa")

    def test_follow_up_respects_max(self):
        raw = (
            "CONCLUSOES:\n- c\n\n"
            "PERGUNTAS:\n1. q1\n2. q2\n3. q3\n4. q4\n\n"
            "TOPICOS:\n- t"
        )
        analyst = self.make_analyst(reflect_raw=raw)
        result = analyst.analyze("pergunta", "resposta", [self._ev("d")])
        assert len(result.follow_up) == 3

    def test_proactive_search_collects_new_evidence(self):
        raw = "CONCLUSOES:\n- c\n\nPERGUNTAS:\n1. q\n\nTOPICOS:\n- bandeja bypass"
        analyst = self.make_analyst(reflect_raw=raw)
        analyst.retriever.retrieve.return_value = [
            Document(
                page_content="Bandeja bypass suporta até 163g.",
                metadata={
                    "chunk_id": "chunk_new",
                    "filename": "manual.pdf",
                    "relevance_score": 0.9,
                },
            )
        ]
        analyst.ollama_client.ask.side_effect = [
            raw,
            "O manual indica que a bandeja bypass aceita materiais até 163g.",
        ]
        result = analyst.analyze("pergunta", "resposta", [self._ev("d", "chunk_old")])
        assert len(result.extra_sources) == 1
        assert result.extra_sources[0].chunk_id == "chunk_new"
        assert len(result.additional_info) == 1

    def test_analyze_without_topics(self):
        raw = "CONCLUSOES:\n- c\n\nPERGUNTAS:\n1. q"
        analyst = self.make_analyst(reflect_raw=raw)
        result = analyst.analyze("pergunta", "resposta", [self._ev("d")])
        assert result.extra_sources == []
        assert result.additional_info == []
