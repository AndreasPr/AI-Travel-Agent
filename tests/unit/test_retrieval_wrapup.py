"""Behavior tests using a synthetic corpus and fake model outputs."""
import importlib
import json
from types import SimpleNamespace

import pytest

from backend.rag.retrieval.bm25 import BM25Index
from eval.retrieval.diff_modes import diagnose
from eval.retrieval.make_candidates import merge_candidates
from eval.retrieval.readme import END, START, update_readme
from eval.retrieval.run_modes import bootstrap_ci

search_module = importlib.import_module("backend.rag.search")


@pytest.fixture
def synthetic_rows():
    return [
        {"id": 1, "chunk_id": "synthetic-a", "text": "museum museum art", "city": "A"},
        {"id": 2, "chunk_id": "synthetic-b", "text": "museum garden", "city": "B"},
        {"id": 3, "chunk_id": "synthetic-c", "text": "beach ocean", "city": "A"},
        {"id": 4, "chunk_id": "synthetic-d", "text": "food cafe", "city": "A"},
        {"id": 5, "chunk_id": "synthetic-e", "text": "rail station", "city": "B"},
    ]


def test_bm25_scores_full_corpus_then_filters(synthetic_rows, monkeypatch):
    index = BM25Index(synthetic_rows)
    assert [row["id"] for row in index.search("museum")] == [1, 2]
    seen = []
    original = index.model.get_scores

    def scores(tokens):
        result = original(tokens)
        seen.append(len(result))
        return result

    monkeypatch.setattr(index.model, "get_scores", scores)
    assert [row["id"] for row in index.search("museum", {"city": "B"}, limit=1)] == [2]
    assert seen == [5]
    assert index.search("absent") == []
    assert BM25Index([]).search("museum") == []
    assert BM25Index([{"id": 1, "text": ""}]).search("museum") == []


def fake_session(rows):
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement):
            return SimpleNamespace(all=lambda: rows)
    return Session


def test_bm25_index_built_once_and_cached(monkeypatch, synthetic_rows):
    calls = []
    session = fake_session(synthetic_rows)

    def factory():
        calls.append(True)
        return session()

    monkeypatch.setattr(search_module, "SessionLocal", factory)
    monkeypatch.setattr(search_module, "_candidate_row", lambda row: row)
    search_module.get_bm25_index.cache_clear()
    try:
        first = search_module.get_bm25_index()
        assert first.search("museum")[0]["id"] == 1
        assert search_module.get_bm25_index() is first
        assert len(calls) == 1
    finally:
        search_module.get_bm25_index.cache_clear()


def test_search_bm25_hybrid_rrf_and_config_default(monkeypatch, synthetic_rows):
    monkeypatch.setattr(search_module, "get_bm25_index", lambda: BM25Index(synthetic_rows))
    monkeypatch.setattr(search_module, "SessionLocal", fake_session([synthetic_rows[2], synthetic_rows[1]]))
    monkeypatch.setattr(search_module, "_candidate_row", lambda row: row)
    monkeypatch.setattr(search_module, "get_local_embedder", lambda: SimpleNamespace(encode_query=lambda text: [0.0] * 384))
    monkeypatch.setattr(search_module, "get_default_retrieval_mode", lambda: "bm25")
    assert [row["id"] for row in search_module.search("museum", auto_filters=False, expand_queries=False)] == [1, 2]
    result = search_module.search("museum", mode="hybrid(bm25)", auto_filters=False, expand_queries=False)
    # Items 1 and 3 each have score 1/61; existing RRF breaks ties by ID.
    assert [row["id"] for row in result] == [2, 1, 3]
    with pytest.raises(ValueError, match="Unknown retrieval mode"):
        search_module.search("museum", mode="unknown")


def test_default_mode_reads_models_yaml(monkeypatch, tmp_path):
    from backend.rag import config
    (tmp_path / "models.yaml").write_text("retrieval:\n  default_mode: fts\n")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert config.get_default_retrieval_mode() == "fts"


def test_vector_rerank_trace_is_exact_input_pool(monkeypatch):
    rows = [{"id": i, "chunk_id": f"synthetic-{i}", "text": "synthetic museum"} for i in range(35)]
    monkeypatch.setattr(search_module, "SessionLocal", fake_session(rows))
    monkeypatch.setattr(search_module, "_candidate_row", lambda row: row)
    monkeypatch.setattr(search_module, "get_local_embedder", lambda: SimpleNamespace(encode_query=lambda text: [0.0] * 384))
    captured = []

    def rerank(candidates, query, limit):
        captured.extend(candidates)
        return list(reversed(candidates))[:limit]

    monkeypatch.setattr(search_module, "get_reranker", lambda: SimpleNamespace(rerank=rerank))
    trace = {}
    result = search_module.search("museum", mode="vector", rerank=True, auto_filters=False, expand_queries=False, trace=trace)
    assert trace["candidate_pool"] == captured == rows[:30]
    assert result[0]["chunk_id"] == "synthetic-29"


def test_bootstrap_ci_fixed_input():
    assert bootstrap_ci([0.0, 0.5, 1.0]) == [0.0, 1.0]
    assert bootstrap_ci([0.8] * 3) == pytest.approx([0.8, 0.8])
    assert bootstrap_ci([0.1, 0.2, 0.3, 0.7, 0.9]) == bootstrap_ci([0.1, 0.2, 0.3, 0.7, 0.9])
    assert bootstrap_ci([]) is None
    with pytest.raises(ValueError):
        bootstrap_ci([1.0], resamples=1)


def test_candidate_regeneration_preserves_nonempty_marks_outside_pool():
    rows = [{"query": "synthetic q", "chunk_id": "a", "mode": "vector+rerank", "rank": 1, "relevant": "new"}]
    merged = merge_candidates(rows, {("synthetic q", "a"): "0", ("synthetic q", "removed"): "1"})
    assert {row["chunk_id"]: row["relevant"] for row in merged} == {"a": "0", "removed": "1"}


def test_candidates_union_all_modes(monkeypatch, tmp_path):
    from eval.retrieval import make_candidates
    from eval.retrieval.modes import MODE_SPECS, mode_parameters
    path = tmp_path / "candidates.csv"
    monkeypatch.setattr(make_candidates, "OUT_PATH", path)
    monkeypatch.setattr(make_candidates, "load_queries", lambda _: [{"query": "synthetic query"}])
    calls = []

    def fake_search(query, **params):
        calls.append(params)
        return [{"chunk_id": f"synthetic-{len(calls)}", "text": "synthetic"}]

    monkeypatch.setattr(make_candidates, "search", fake_search)
    make_candidates.main()
    assert calls == [{"limit": 10, **mode_parameters("synthetic query", params)} for _, params in MODE_SPECS]
    assert len(path.read_text().splitlines()) == len(MODE_SPECS) + 1


def test_readme_generated_from_json_preserves_surrounding_text(tmp_path):
    readme = tmp_path / "README.md"
    results = tmp_path / "retrieval.json"
    readme.write_text(f"before\n{START}\nstale\n{END}\nafter\n")
    results.write_text(json.dumps({"labeled_queries": 3, "relevant_chunks_per_query": 2,
                                  "modes": {"vector": {"mrr": 0.8, "confidence_intervals": {"mrr": [0.71, 0.88]}}}}))
    update_readme(readme, results)
    text = readme.read_text()
    assert text.startswith(f"before\n{START}") and text.endswith(f"{END}\nafter\n")
    assert "0.80 [0.71, 0.88]" in text and "not run" in text
    assert "Evaluated on 3 labeled queries (about 2.0 relevant chunks per query)" in text
    update_readme(readme, results)
    assert readme.read_text() == text


def test_diagnosis_records_metadata_pools_ranks_and_cause():
    metadata = {"synthetic-a": {"city": "A", "topic": "see", "season": "winter"}}

    def fake_search(query, trace, **params):
        rows = [] if params["auto_filters"] else [{"chunk_id": "synthetic-a"}]
        trace.update(candidate_pool=rows, extracted_filters={"city": "B"}, hard_filters={"city": "B"} if params["auto_filters"] else {})
        return rows

    report = diagnose([{"query": "synthetic query", "relevant_chunk_ids": ["synthetic-a"]}], metadata, fake_search)
    assert "| synthetic-a | A | see | winter | yes | no | 1 | absent |" in report
    assert '"city": "B"' in report
    assert "Hard-filter mismatch" in report
