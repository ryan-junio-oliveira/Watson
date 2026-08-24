from langchain_core.documents import Document

from rag.evidence import Evidence, EvidenceNormalizer
from rag.prompt import PromptBuilder
from rag.response import Source
from rag.retriever import Retriever
from unittest.mock import MagicMock, patch


def rich_document():
    return Document(
        page_content="Procedimento para resolver o erro E123.",
        metadata={
            "filename": "HP_E52645.pdf",
            "source": "/docs/HP_E52645.pdf",
            "relevance_score": 0.91,
            "chunk_id": "chunk_doc_1_5",
            "document_id": "doc_1",
            "source_id": "src_1",
            "source_type": "pdf",
            "manufacturer": "HP",
            "model": "E52645",
            "device_type": "printer",
            "document_type": "service_manual",
            "section": "Troubleshooting",
            "subsection": "Error Codes",
            "page_start": 142,
            "page_end": 143,
            "error_codes": ["E123"],
        },
    )


class TestEvidenceRichContract:
    def test_normalizer_maps_rich_metadata(self):
        ev = EvidenceNormalizer.from_chroma_document(rich_document())
        assert ev.manufacturer == "HP"
        assert ev.model == "E52645"
        assert ev.device_type == "printer"
        assert ev.document_type == "service_manual"
        assert ev.section == "Troubleshooting"
        assert ev.subsection == "Error Codes"
        assert ev.page_start == 142
        assert ev.page_end == 143
        assert ev.error_codes == ["E123"]
        assert ev.chunk_id == "chunk_doc_1_5"
        assert ev.document_id == "doc_1"

    def test_context_label(self):
        ev = EvidenceNormalizer.from_chroma_document(rich_document())
        label = ev.context_label
        assert "HP" in label
        assert "E52645" in label
        assert "Troubleshooting" in label
        assert "142" in label
        assert "E123" in label

    def test_context_label_empty(self):
        ev = Evidence(provider="chroma", source="x", content="y")
        assert ev.context_label == ""


class TestPromptRichContext:
    def test_evidence_block_includes_context(self):
        ev = EvidenceNormalizer.from_chroma_document(rich_document())
        block = PromptBuilder._format_evidence_block(ev)
        assert "HP" in block
        assert "E52645" in block
        assert "Troubleshooting" in block
        assert "E123" in block
        assert "Procedimento para resolver o erro E123." in block


class TestSourceRichContext:
    def test_from_evidence_includes_page_and_section(self):
        ev = EvidenceNormalizer.from_chroma_document(rich_document())
        src = Source.from_evidence(ev)
        assert src.page == 142
        assert src.section == "Troubleshooting"
        assert src.manufacturer == "HP"
        assert src.model == "E52645"

    def test_to_dict_includes_rich_fields(self):
        ev = EvidenceNormalizer.from_chroma_document(rich_document())
        d = Source.from_evidence(ev).to_dict()
        assert d["page"] == 142
        assert d["section"] == "Troubleshooting"
        assert d["manufacturer"] == "HP"
        assert d["model"] == "E52645"


class TestRetrieverFilter:
    def test_retrieve_passes_filter(self, mock_embeddings=None):
        mock = MagicMock()
        mock.embed_query.return_value = [0.1] * 384
        gen = MagicMock()
        gen.get_embeddings.return_value = mock

        with patch("rag.retriever.Chroma") as chroma_cls:
            instance = chroma_cls.return_value
            instance._collection.count.return_value = 10
            instance.similarity_search_with_relevance_scores.return_value = [
                (Document(page_content="R", metadata={"filename": "a.pdf"}), 0.9)
            ]
            retriever = Retriever(
                embedding_generator=gen,
                chroma_persist_dir="/tmp/x",
                top_k=5,
            )
            retriever.retrieve(
                "erro E123",
                filter={"manufacturer": "HP", "model": "E52645"},
            )
            instance.similarity_search_with_relevance_scores.assert_called_once_with(
                "erro E123", k=5, filter={"manufacturer": "HP", "model": "E52645"}
            )

    def test_retrieve_without_filter_no_filter_kwarg(self):
        mock = MagicMock()
        mock.embed_query.return_value = [0.1] * 384
        gen = MagicMock()
        gen.get_embeddings.return_value = mock

        with patch("rag.retriever.Chroma") as chroma_cls:
            instance = chroma_cls.return_value
            instance._collection.count.return_value = 10
            instance.similarity_search_with_relevance_scores.return_value = []
            retriever = Retriever(
                embedding_generator=gen,
                chroma_persist_dir="/tmp/x",
                top_k=3,
            )
            retriever.retrieve("pergunta")
            instance.similarity_search_with_relevance_scores.assert_called_once_with(
                "pergunta", k=3
            )