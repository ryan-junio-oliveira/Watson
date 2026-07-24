from search.chunker import Chunker


class TestChunker:
    def test_chunk_empty(self):
        chunker = Chunker(chunk_size=100, chunk_overlap=0)
        assert chunker.chunk("") == []

    def test_chunk_single(self):
        chunker = Chunker(chunk_size=1000, chunk_overlap=0)
        result = chunker.chunk("texto curto")
        assert len(result) == 1
        assert result[0] == "texto curto"

    def test_chunk_splits_long_text(self):
        chunker = Chunker(chunk_size=10, chunk_overlap=0)
        text = "uma palavra " * 20
        result = chunker.chunk(text)
        assert len(result) > 1

    def test_chunk_documents(self):
        chunker = Chunker(chunk_size=1000, chunk_overlap=0)
        docs = ["documento um", "documento dois"]
        result = chunker.chunk_documents(docs)
        assert len(result) == 2

    def test_chunk_respects_overlap(self):
        chunker = Chunker(chunk_size=20, chunk_overlap=5)
        text = "uma frase longa para testar a divisao em chunks"
        result = chunker.chunk(text)
        assert len(result) > 1
