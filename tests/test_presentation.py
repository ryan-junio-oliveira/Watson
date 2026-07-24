import json

import pytest

from presentation.formatter import ApiFormatter, CliFormatter
from rag.response import AgentResponse, Source


@pytest.fixture
def api_formatter():
    return ApiFormatter()


@pytest.fixture
def cli_formatter():
    return CliFormatter()


@pytest.fixture
def sample_response():
    from rag.evidence import Evidence
    return AgentResponse(
        answer="A resposta é 42.",
        evidences=[
            Evidence(
                title="Wikipedia",
                url="https://en.wikipedia.org/wiki/42",
                content="42 é a resposta.",
                source="wikipedia",
                provider="web",
                score=0.95,
            ),
        ],
        confidence=0.94,
        verdict="consistent",
        issues=[],
        metadata={"provider": "web", "planner": "enabled"},
        execution_time=0.815,
    )


class TestSource:
    def test_to_dict(self):
        src = Source(title="Test", url="https://test.com", provider="web")
        assert src.to_dict() == {
            "title": "Test",
            "url": "https://test.com",
            "provider": "web",
        }

    def test_to_dict_empty_provider_excluded(self):
        src = Source(title="Test", url="https://test.com", provider="")
        d = src.to_dict()
        assert "provider" not in d

    def test_from_evidence(self):
        from rag.evidence import Evidence
        ev = Evidence(
            title="Fonte",
            url="https://fonte.com",
            content="texto",
            source="fonte",
            provider="web",
        )
        src = Source.from_evidence(ev)
        assert src.title == "Fonte"
        assert src.url == "https://fonte.com"
        assert src.provider == "web"

    def test_from_evidence_list_deduplicates(self):
        from rag.evidence import Evidence
        evs = [
            Evidence(title="A", url="https://a.com", content="a", source="a", provider="web"),
            Evidence(title="A", url="https://a.com", content="b", source="a", provider="web"),
            Evidence(title="B", url="https://b.com", content="c", source="b", provider="web"),
        ]
        sources = Source.from_evidence_list(evs)
        assert len(sources) == 2


class TestApiFormatter:
    def test_format_success(self, api_formatter, sample_response):
        result = api_formatter.format(sample_response)
        assert result["success"] is True
        assert result["answer"] == "A resposta é 42."
        assert result["confidence"] == 0.94
        assert len(result["sources"]) == 1
        assert result["sources"][0]["title"] == "Wikipedia"
        assert result["sources"][0]["url"] == "https://en.wikipedia.org/wiki/42"
        assert "metadata" in result

    def test_format_metadata(self, api_formatter, sample_response):
        result = api_formatter.format(sample_response)
        meta = result["metadata"]
        assert meta["evidence_count"] == 1
        assert meta["execution_time_ms"] == 815
        assert meta["verdict"] == "consistent"
        assert meta["provider"] == "web"

    def test_format_no_sources(self, api_formatter):
        resp = AgentResponse(
            answer="Sem fontes.",
            evidences=[],
            confidence=0.0,
            execution_time=0.0,
        )
        result = api_formatter.format(resp)
        assert result["sources"] == []
        assert result["metadata"]["evidence_count"] == 0

    def test_format_with_issues(self, api_formatter):
        resp = AgentResponse(
            answer="Resposta parcial.",
            evidences=[],
            confidence=0.5,
            verdict="unknown",
            issues=["Stream timeout"],
            execution_time=1.2,
        )
        result = api_formatter.format(resp)
        assert "issues" in result["metadata"]
        assert "Stream timeout" in result["metadata"]["issues"]

    def test_format_error(self, api_formatter):
        error = api_formatter.format_error("TIMEOUT", "The request timed out")
        assert error["success"] is False
        assert error["error"]["code"] == "TIMEOUT"
        assert error["error"]["message"] == "The request timed out"

    def test_format_stream_metadata(self, api_formatter, sample_response):
        meta = api_formatter.format_stream_metadata(sample_response)
        assert meta["confidence"] == 0.94
        assert len(meta["sources"]) == 1
        assert "evidence_count" in meta["metadata"]


class TestCliFormatter:
    def test_format_success(self, cli_formatter, sample_response):
        output = cli_formatter.format(sample_response)
        assert "A resposta é 42." in output
        assert "Wikipedia" in output
        assert "Sources" in output
        assert "Wikipedia" in output

    def test_format_no_sources(self, cli_formatter):
        resp = AgentResponse(answer="Apenas texto.", evidences=[], confidence=0.0)
        output = cli_formatter.format(resp)
        assert output.strip() == "Apenas texto."

    def test_format_with_issues(self, cli_formatter):
        resp = AgentResponse(
            answer="Texto.",
            evidences=[],
            confidence=0.3,
            issues=["Fonte não encontrada", "Timeout"],
        )
        output = cli_formatter.format(resp)
        assert "Fonte não encontrada" in output
        assert "Timeout" in output
        assert "Notes:" in output

    def test_format_compact(self, cli_formatter):
        from rag.evidence import Evidence
        resp = AgentResponse(
            answer="Resposta.",
            evidences=[
                Evidence(title="Src1", url="https://src1.com", content="", source="src1", provider="web"),
                Evidence(title="Src2", url="https://src2.com", content="", source="src2", provider="web"),
            ],
            confidence=0.9,
        )
        output = cli_formatter.format_compact(resp)
        assert "Resposta." in output
        assert "Src1" in output
        assert "Src2" in output

    def test_format_error(self, cli_formatter):
        output = cli_formatter.format_error("NOT_FOUND", "Resource not found")
        assert "NOT_FOUND" in output
        assert "Resource not found" in output
