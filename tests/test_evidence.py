from langchain_core.documents import Document

from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer
from search.fetcher import FetchResult
from search.provider import SearchResult


class TestEvidence:
    def test_creation(self):
        ev = Evidence(
            provider="google",
            source="https://exemplo.com",
            title="Título",
            url="https://exemplo.com",
            content="Conteúdo da página.",
            score=0.85,
            metadata={"key": "value"},
            source_type="web",
        )
        assert ev.provider == "google"
        assert ev.title == "Título"
        assert ev.url == "https://exemplo.com"
        assert ev.content == "Conteúdo da página."
        assert ev.score == 0.85

    def test_id_is_unique(self):
        ev1 = Evidence(provider="web", source="url1", content="abc", url="url1")
        ev2 = Evidence(provider="web", source="url2", content="def", url="url2")
        assert ev1.id != ev2.id

    def test_hash(self):
        ev = Evidence(provider="web", source="url1", content="abc", url="url1")
        assert hash(ev) == hash(ev.id)


class TestEvidenceNormalizer:
    def test_from_search_result(self):
        sr = SearchResult(title="Título", url="https://exemplo.com", snippet="Descrição", source="google")
        ev = EvidenceNormalizer.from_search_result(sr)
        assert ev.provider == "google"
        assert ev.title == "Título"
        assert ev.url == "https://exemplo.com"
        assert ev.source_type == "web"

    def test_from_fetch_result(self):
        fr = FetchResult(url="https://exemplo.com", html="<html>conteudo</html>", status_code=200, content_length=25)
        ev = EvidenceNormalizer.from_fetch_result(fr)
        assert ev.url == "https://exemplo.com"
        assert ev.content == "<html>conteudo</html>"

    def test_from_chroma_document(self):
        doc = Document(
            page_content="Conteúdo do documento.",
            metadata={"filename": "doc.txt", "relevance_score": 0.9},
        )
        ev = EvidenceNormalizer.from_chroma_document(doc)
        assert ev.provider == "chroma"
        assert ev.source == "doc.txt"
        assert ev.content == "Conteúdo do documento."
        assert ev.source_type == "rag"

    def test_from_chroma_document_default_score(self):
        doc = Document(page_content="Conteúdo.", metadata={})
        ev = EvidenceNormalizer.from_chroma_document(doc)
        assert ev.score == 0.5

    def test_from_extracted_content(self):
        ev = EvidenceNormalizer.from_extracted_content(
            url="https://exemplo.com", title="Título", content="Texto extraído."
        )
        assert ev.url == "https://exemplo.com"
        assert ev.title == "Título"
        assert ev.content == "Texto extraído."


class TestEvidenceAggregator:
    def test_collect_empty(self):
        agg = EvidenceAggregator()
        result = agg.collect()
        assert result == []

    def test_collect_combines_sources(self):
        agg = EvidenceAggregator()
        rag = [Evidence(provider="chroma", source="doc1", content="a", title="D1", url="")]
        web = [Evidence(provider="google", source="url1", content="b", title="W1", url="https://url1")]
        result = agg.collect(rag_evidence=rag, web_evidence=web)
        assert len(result) == 2

    def test_deduplicate(self):
        agg = EvidenceAggregator()
        ev = Evidence(provider="web", source="url1", content="abc", url="url1")
        result = agg.deduplicate([ev, ev])
        assert len(result) == 1

    def test_rank(self):
        agg = EvidenceAggregator()
        low = Evidence(provider="web", source="u1", content="a", url="u1", score=0.3)
        high = Evidence(provider="web", source="u2", content="b", url="u2", score=0.9)
        result = agg.rank([low, high])
        assert result[0].score == 0.9

    def test_format_for_prompt(self):
        agg = EvidenceAggregator()
        ev = Evidence(
            provider="google",
            source="url",
            title="Título",
            url="https://exemplo.com",
            content="Conteúdo.",
        )
        result = agg.format_for_prompt([ev])
        assert "Fonte:" in result
        assert "URL:" in result
        assert "Título:" in result
        assert "Conteúdo." in result

    def test_sources_text(self):
        agg = EvidenceAggregator()
        evs = [
            Evidence(provider="web", source="u1", title="T1", url="https://a.com", content="a"),
            Evidence(provider="chroma", source="doc.txt", content="b", title="", url=""),
        ]
        result = agg.sources_text(evs)
        assert "T1" in result or "a.com" in result
        assert "doc.txt" in result
