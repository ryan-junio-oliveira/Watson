from langchain_core.documents import Document

from ingestion.models import LoadedDocument
from ingestion.quality import QualityGate


def make_chunk(content, meta=None):
    return Document(page_content=content, metadata=meta or {})


def make_doc(pages=None, ocr=False):
    return LoadedDocument(
        content="", filepath="/d.txt", filename="d.txt", file_type=".txt",
        modified_at="t", file_size=1, pages=pages or [],
    )


class TestQualityGate:
    def test_good_chunk_accepted(self):
        gate = QualityGate()
        chunk = make_chunk(
            "Texto técnico completo sobre resolução de erro E123 na impressora HP.",
            {
                "document_id": "doc_1",
                "source_id": "src_1",
                "source_type": "pdf",
                "section": "Troubleshooting",
                "page_start": 1,
            },
        )
        score = gate.assess(chunk, make_doc())
        assert score.accepted is True
        assert score.text_quality > 0.3
        assert score.structure_quality > 0.5
        assert score.metadata_quality > 0.5

    def test_short_chunk_rejected(self):
        gate = QualityGate()
        chunk = make_chunk("curto", {"document_id": "doc_1"})
        score = gate.assess(chunk, make_doc())
        assert score.accepted is False
        assert "too_short" in score.reasons

    def test_empty_rejected(self):
        gate = QualityGate()
        score = gate.assess(make_chunk(""), make_doc())
        assert score.accepted is False

    def test_low_quality_metadata_still_accepted_if_text_good(self):
        gate = QualityGate()
        chunk = make_chunk(
            "Conteúdo extenso e relevante sobre o procedimento de manutenção "
            "preventiva do equipamento com detalhes técnicos completos.",
        )
        score = gate.assess(chunk, make_doc())
        assert score.metadata_quality == 0.0
        assert score.accepted is True

    def test_ocr_page_penalizes_short_content(self):
        gate = QualityGate()
        pages = [type("P", (), {"ocr": True, "number": 1})()]
        chunk = make_chunk("ok", {"document_id": "doc_1", "source_id": "s", "source_type": "pdf"})
        score = gate.assess(chunk, make_doc(pages=pages))
        assert score.ocr_quality < 0.8

    def test_rejection_reason_recorded(self):
        gate = QualityGate()
        chunk = make_chunk("  ", {"document_id": "doc_1"})
        score = gate.assess(chunk, make_doc())
        assert score.accepted is False
        assert score.reasons  # pelo menos um motivo registrado