from langchain_core.documents import Document

from rag.evidence import Evidence, EvidenceAggregator, EvidenceNormalizer


class TestEvidence:
    def test_creation(self):
        ev = Evidence(
            provider="chroma",
            source="doc.txt",
            title="Título",
            url="",
            content="Conteúdo do documento.",
            score=0.85,
            metadata={"key": "value"},
            source_type="rag",
        )
        assert ev.provider == "chroma"
        assert ev.title == "Título"
        assert ev.content == "Conteúdo do documento."
        assert ev.score == 0.85

    def test_id_is_unique(self):
        ev1 = Evidence(provider="chroma", source="doc1", content="abc")
        ev2 = Evidence(provider="chroma", source="doc2", content="def")
        assert ev1.id != ev2.id

    def test_hash(self):
        ev = Evidence(provider="chroma", source="doc1", content="abc")
        assert hash(ev) == hash(ev.id)


class TestEvidenceNormalizer:
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


class TestEvidenceAggregator:
    def test_collect_empty(self):
        agg = EvidenceAggregator()
        result = agg.collect()
        assert result == []

    def test_collect_rag_evidence(self):
        agg = EvidenceAggregator()
        rag = [Evidence(provider="chroma", source="doc1", content="a", title="D1")]
        result = agg.collect(rag_evidence=rag)
        assert len(result) == 1

    def test_deduplicate(self):
        agg = EvidenceAggregator()
        ev = Evidence(provider="chroma", source="doc1", content="abc")
        result = agg.deduplicate([ev, ev])
        assert len(result) == 1

    def test_rank(self):
        agg = EvidenceAggregator()
        low = Evidence(provider="chroma", source="d1", content="a", score=0.3)
        high = Evidence(provider="chroma", source="d2", content="b", score=0.9)
        result = agg.rank([low, high])
        assert result[0].score == 0.9

    def test_format_for_prompt(self):
        agg = EvidenceAggregator()
        ev = Evidence(
            provider="chroma",
            source="doc.txt",
            title="Documento",
            url="",
            content="Conteúdo.",
        )
        result = agg.format_for_prompt([ev])
        assert "Fonte:" in result
        assert "Título:" in result
        assert "Conteúdo." in result

    def test_sources_text(self):
        agg = EvidenceAggregator()
        evs = [
            Evidence(provider="chroma", source="d1", title="Doc 1", content="a"),
            Evidence(provider="chroma", source="d2", content="b", title="", url=""),
        ]
        result = agg.sources_text(evs)
        assert "d1" in result
        assert "d2" in result
