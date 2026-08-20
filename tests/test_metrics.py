import time

from metrics.store import MetricsStore


class TestMetricsStore:
    def test_record_and_summary(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_llm_call(model="m1", prompt_tokens=10, completion_tokens=5)
        store.record_llm_call(model="m1", prompt_tokens=3, completion_tokens=2, success=False, error="boom")
        store.record_request(question="olá", evidence_count=2, execution_ms=500)
        store.record_documents(documents=4, chunks=15, by_type={"pdf": {"documents": 4, "chunks": 15}})
        store.record_index_event(documents_processed=4, chunks_indexed=15)

        s = store.summary()
        assert s["llm_calls"] == 2
        assert s["llm_success"] == 1
        assert s["llm_errors"] == 1
        assert s["total_prompt_tokens"] == 13
        assert s["total_completion_tokens"] == 7
        assert s["total_tokens"] == 20
        assert s["requests"] == 1
        assert s["documents_indexed"] == 4
        assert s["chunks_indexed"] == 15

    def test_token_series(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_llm_call(model="m1", prompt_tokens=10, completion_tokens=5)
        series = store.token_series(hours=24)
        assert len(series) >= 1
        assert series[0]["input_tokens"] >= 10
        assert series[0]["output_tokens"] >= 5

    def test_by_model(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_llm_call(model="gemma3:4b", prompt_tokens=5, completion_tokens=3)
        store.record_llm_call(model="qwen3:4b", prompt_tokens=7, completion_tokens=2)
        models = store.by_model(hours=24)
        assert {m["model"] for m in models} == {"gemma3:4b", "qwen3:4b"}
        total_in = sum(m["input_tokens"] for m in models)
        assert total_in == 12

    def test_recent_requests(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_request(question="pergunta 1", evidence_count=2)
        store.record_request(question="pergunta 2", evidence_count=3, success=False, error="x")
        reqs = store.recent_requests(limit=10)
        assert len(reqs) == 2
        assert reqs[0]["success"] == 0

    def test_prune(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_request(question="antiga")
        # Força ts antigo
        store.record_request(question="nova")
        with store._lock:
            conn = store._connect()
            conn.execute("UPDATE requests SET ts = ? WHERE question='antiga'", (time.time() - 100000,))
            conn.commit()
            conn.close()
        store.prune(keep_hours=24)
        reqs = store.recent_requests(limit=10)
        assert all(r["question"] != "antiga" for r in reqs)

    def test_document_history_json(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_documents(documents=2, chunks=6, by_type={"pdf": {"documents": 2, "chunks": 6}})
        hist = store.document_history()
        assert hist[-1]["by_type"]["pdf"]["chunks"] == 6

    def test_clear_removes_all_records(self, tmp_path):
        store = MetricsStore(db_path=str(tmp_path / "m.db"))
        store.record_llm_call(model="m", prompt_tokens=1)
        store.record_request(question="q")
        store.record_documents(documents=1, chunks=2)
        store.record_index_event(documents_processed=1, chunks_indexed=2)
        cleared = store.clear()
        assert cleared >= 4
        s = store.summary()
        assert s["llm_calls"] == 0
        assert s["requests"] == 0
        assert s["documents_indexed"] == 0