from ingestion.dedup import Deduplicator


class TestDeduplicator:
    def test_first_occurrence_kept(self):
        d = Deduplicator()
        r = d.check("hash_a", "doc_1", "chunk_1")
        assert r.keep is True
        assert r.reason == ""

    def test_intra_document_duplicate_rejected(self):
        d = Deduplicator()
        d.check("hash_x", "doc_1", "chunk_1")
        r = d.check("hash_x", "doc_1", "chunk_2")
        assert r.keep is False
        assert r.reason == "duplicate_intra_document"
        assert r.duplicate_of == "chunk_1"
        assert d.intra_document_duplicates == 1

    def test_cross_document_duplicate_kept_and_marked(self):
        d = Deduplicator()
        d.check("hash_x", "doc_1", "chunk_1")
        r = d.check("hash_x", "doc_2", "chunk_1")
        assert r.keep is True
        assert r.reason == "duplicate_cross_document"
        assert r.duplicate_of == "chunk_1"
        assert d.cross_document_duplicates == 1

    def test_empty_hash_always_kept(self):
        d = Deduplicator()
        assert d.check("", "doc_1", "c1").keep is True
        assert d.check("", "doc_1", "c2").keep is True

    def test_reset(self):
        d = Deduplicator()
        d.check("hash_x", "doc_1", "c1")
        d.check("hash_x", "doc_1", "c2")
        d.reset()
        assert d.intra_document_duplicates == 0
        assert d.cross_document_duplicates == 0
        assert d.totals == {
            "intra_document_duplicates": 0,
            "cross_document_duplicates": 0,
        }