from datetime import date
from decimal import Decimal

from backend.rag.citations import CitationVerifier, CitedClaim, FakeNLI
from backend.rag.ingest import assert_rag_tables_exist, ingest_cities
from backend.rag.ingestion.chunker import chunk_document
from backend.rag.retrieval.hybrid import apply_metadata_filters, reciprocal_rank_fusion
from backend.rag.retrieval.rerank import CrossEncoderReranker
from backend.rag.search import build_or_tsquery, search
from backend.scripts.seed_inventory import normalize_flight_row
from eval.retrieval.make_candidates import merge_candidates


def test_chunk_document_splits_and_tracks_metadata():
    text = """
    == Overview ==
    Lisbon is lively and walkable.

    == Food ==
    Try the pastéis de nata at local bakeries.
    """
    chunks = chunk_document(
        title="Lisbon",
        city="Lisbon",
        country="Portugal",
        text=text,
        source_url="https://example.com/lisbon",
        license="CC BY-SA 4.0",
    )
    assert len(chunks) >= 2
    assert all(chunk["city"] == "Lisbon" for chunk in chunks)
    assert all(chunk["country"] == "Portugal" for chunk in chunks)
    assert all("source_url" in chunk for chunk in chunks)
    assert all(chunk["license"] == "CC BY-SA 4.0" for chunk in chunks)
    assert any(chunk["topic"] for chunk in chunks)


def test_chunk_document_handles_overlapping_chunk_boundaries():
    tokens = " ".join(f"token{i}" for i in range(400))
    chunks = chunk_document(
        title="Lisbon",
        city="Lisbon",
        country="Portugal",
        text=tokens,
        source_url="https://example.com/lisbon",
        license="CC BY-SA 4.0",
        chunk_size=260,
        overlap=40,
    )
    assert chunks
    assert all(chunk["text"] for chunk in chunks)
    assert all("token" in chunk["text"] for chunk in chunks)


def test_rrf_fusion_combines_rankings():
    vector_rank = ["a", "b", "c"]
    bm25_rank = ["c", "a", "d"]
    fused = reciprocal_rank_fusion(vector_rank, bm25_rank, k=60)
    assert fused[0][0] == "a"
    assert fused[1][0] == "c"


def test_rrf_fusion_handles_multiple_rankings():
    fused = reciprocal_rank_fusion(["a", "b"], ["b", "c"], ["c", "a"], k=10)
    order = [item for item, _ in fused]
    assert order[:3] == ["a", "b", "c"]


def test_ndcg_known_values():
    from eval.retrieval.metrics import ndcg_at_k

    assert ndcg_at_k(["x"], ["x"], 10) == 1.0
    assert ndcg_at_k(["x"], ["y", "x"], 10) > 0.0
    assert ndcg_at_k(["x"], ["y", "z"], 10) == 0.0


def test_metadata_filters_keep_supported_candidates():
    rows = [
        {"id": 1, "city": "Lisbon", "country": "Portugal", "season": "winter", "topic": "see"},
        {"id": 2, "city": "Rome", "country": "Italy", "season": "summer", "topic": "eat"},
    ]
    filtered = apply_metadata_filters(rows, city="Lisbon", topic="see")
    assert [row["id"] for row in filtered] == [1]


def test_extract_filters_maps_museum_queries_to_supported_topic_bucket():
    filters, _ = search.__globals__["_extract_filters"]("quiet museums in Lisbon in winter")
    assert filters["city"] == "Lisbon"
    assert filters["country"] == "Portugal"
    assert filters["season"] == "winter"
    assert filters["topic"] == "see"


def test_build_or_tsquery_matches_expected_or_semantics():
    assert build_or_tsquery("affordable hostels in Amsterdam") == "affordable | hostels | amsterdam"
    assert build_or_tsquery("bars & pubs (cheap)!") == "bars | pubs | cheap"
    assert build_or_tsquery("") is None
    assert build_or_tsquery("the and of") is None
    assert build_or_tsquery("pastéis de nata") == "pastéis | nata"


def test_citation_verifier_flags_unsupported_claims():
    source_a = {
        "chunk_id": "a",
        "title": "Lisbon basics",
        "url": "https://example.com/a",
        "license": "CC BY-SA 4.0",
        "text": "Lisbon has many museums and trams.",
    }
    source_b = {
        "chunk_id": "b",
        "title": "Winter tips",
        "url": "https://example.com/b",
        "license": "CC BY-SA 4.0",
        "text": "The city is mild in winter and famous for its tiled streets.",
    }
    verifier = CitationVerifier([source_a, source_b])
    supported = verifier.verify(CitedClaim(claim="Lisbon has many museums.", source_chunk_ids=["a"]))
    assert supported.is_supported is True
    assert verifier.verify(CitedClaim(claim="Lisbon has trams.", source_chunk_ids=["a"])).is_supported is True
    for claim in [
        "Lisbon has free wifi everywhere.",
        "Lisbon has a famous beach resort.",
        "Lisbon has great nightlife.",
        "Lisbon is in the Alps.",
    ]:
        assert verifier.verify(CitedClaim(claim=claim, source_chunk_ids=["a"])).is_supported is False


def test_citation_verifier_negation_and_numbers_are_symmetric():
    sources = [{
        "chunk_id": "a",
        "title": "Lisbon basics",
        "url": "https://example.com/a",
        "license": "CC BY-SA 4.0",
        "text": "Lisbon has no museums.",
    }, {
        "chunk_id": "b",
        "title": "Lisbon basics",
        "url": "https://example.com/b",
        "license": "CC BY-SA 4.0",
        "text": "Lisbon is known for fado music.",
    }, {
        "chunk_id": "c",
        "title": "Hotel cost",
        "url": "https://example.com/c",
        "license": "CC BY-SA 4.0",
        "text": "The hotel costs 1,200 euros.",
    }, {
        "chunk_id": "d",
        "title": "Metro notes",
        "url": "https://example.com/d",
        "license": "CC BY-SA 4.0",
        "text": "There is no metro on Sundays.",
    }]
    verifier = CitationVerifier(sources)

    assert verifier.verify(CitedClaim(claim="Lisbon has museums.", source_chunk_ids=["a"])).is_supported is False
    assert verifier.verify(CitedClaim(claim="Lisbon has no museums.", source_chunk_ids=["a"])) .is_supported is True
    assert verifier.verify(CitedClaim(claim="Lisbon has many museums. There is no metro on Sundays.", source_chunk_ids=["d"])).is_supported is False
    assert verifier.verify(CitedClaim(claim="Lisbon is known for fado.", source_chunk_ids=["b"])).is_supported is True
    assert verifier.verify(CitedClaim(claim="The hotel costs 1,500 euros.", source_chunk_ids=["c"])).is_supported is False
    assert verifier.verify(CitedClaim(claim="The hotel costs 1,200 euros.", source_chunk_ids=["c"])).is_supported is True
    assert verifier.verify(CitedClaim(claim="Lisbon is known for fado.", source_chunk_ids=[])).is_supported is False
    assert verifier.verify(CitedClaim(claim="Lisbon is known for fado.", source_chunk_ids=["missing"])).is_supported is False


def test_citation_verifier_rejects_irrelevant_claims_and_fake_nli_contradiction():
    source = {
        "chunk_id": "a",
        "title": "Lisbon basics",
        "url": "https://example.com/a",
        "license": "CC BY-SA 4.0",
        "text": "Lisbon has many museums and trams.",
    }
    verifier = CitationVerifier([source], nli_checker=FakeNLI(result=True))
    unsupported = [
        "Lisbon has free wifi everywhere.",
        "Lisbon has a famous beach resort.",
        "Lisbon has great nightlife.",
        "The museum opens at 9.",
    ]
    for claim in unsupported:
        result = verifier.verify(CitedClaim(claim=claim, source_chunk_ids=["a"]))
        assert result.is_supported is False

    contrad = CitationVerifier([{
        "chunk_id": "a",
        "title": "Museum hours",
        "url": "https://example.com/a",
        "license": "CC BY-SA 4.0",
        "text": "The museum is open on Mondays.",
    }], nli_checker=FakeNLI(result=False))
    result = contrad.verify(CitedClaim(claim="The museum is closed on Mondays.", source_chunk_ids=["a"]))
    assert result.is_supported is False


def test_search_auto_filters_and_explicit_hard_filters_are_respected(monkeypatch):
    captured = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, stmt):
            captured.append(str(stmt.compile(compile_kwargs={"literal_binds": False})))
            return type("Result", (), {"all": lambda self: []})()

    monkeypatch.setattr("backend.rag.search.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr("backend.rag.search.get_local_embedder", lambda: type("Embedder", (), {"encode_query": lambda self, text: [0.1, 0.2]})())

    search("affordable hostels in Amsterdam", mode="bm25", auto_filters=False)
    sql = captured[-1].lower()
    assert "document_chunks.city =" not in sql
    assert "document_chunks.country =" not in sql
    assert "document_chunks.season =" not in sql
    assert "document_chunks.topic =" not in sql

    search("affordable hostels in Amsterdam", mode="bm25", city="Amsterdam", auto_filters=True)
    sql = captured[-1].lower()
    assert "document_chunks.city =" in sql
    assert "document_chunks.country =" not in sql

    search("winter museums in Lisbon", mode="bm25", auto_filters=True)
    sql = captured[-1].lower()
    assert "document_chunks.city =" in sql
    assert "document_chunks.season =" not in sql
    assert "document_chunks.topic =" not in sql


def test_run_modes_pass_exact_parameters(monkeypatch):
    captured = []

    def fake_search(*args, **kwargs):
        captured.append(kwargs.copy())
        return [{"chunk_id": "c1"}]

    monkeypatch.setattr("eval.retrieval.run_modes.search", fake_search)
    monkeypatch.setattr(
        "eval.retrieval.run_modes.load_queries",
        lambda _path: [{"query": "cheap hotels in Lisbon", "relevant_chunk_ids": ["c1"]}],
    )

    import eval.retrieval.run_modes as run_modes

    run_modes.main()

    assert len(captured) == 5
    assert [call["mode"] for call in captured] == ["vector", "bm25", "hybrid", "hybrid", "hybrid"]
    assert [call["rerank"] for call in captured] == [False, False, False, True, True]
    assert [call["auto_filters"] for call in captured] == [False, False, False, False, True]
    assert [call["expand_queries"] for call in captured] == [False, False, False, False, True]


def test_merge_candidates_preserves_existing_relevant_and_adds_empty_rows():
    rows = [
        {"query": "q1", "chunk_id": "a1", "mode": "vector", "rank": "1", "city": "Lisbon", "topic": "stay", "snippet": "one", "relevant": ""},
        {"query": "q1", "chunk_id": "a1", "mode": "bm25", "rank": "2", "city": "Lisbon", "topic": "stay", "snippet": "one", "relevant": "keep"},
        {"query": "q1", "chunk_id": "a2", "mode": "vector", "rank": "3", "city": "Lisbon", "topic": "stay", "snippet": "two", "relevant": ""},
    ]
    merged = merge_candidates(rows, {("q1", "a1"): "keep"})
    by_chunk = {row["chunk_id"]: row for row in merged}
    assert by_chunk["a1"]["relevant"] == "keep"
    assert by_chunk["a2"]["relevant"] == ""


def test_assert_rag_tables_exist_raises_helpful_error(monkeypatch):
    def fake_inspect(_bind):
        class FakeInspector:
            def get_table_names(self):
                return ["users", "trips"]

        return FakeInspector()

    monkeypatch.setattr("backend.rag.ingest.inspect", fake_inspect)
    try:
        assert_rag_tables_exist()
        raise AssertionError("Expected a RuntimeError for missing tables")
    except RuntimeError as exc:
        assert "alembic upgrade head" in str(exc)


def test_normalize_flight_row_coerces_types():
    row = {
        "flightDate": "2022-04-18",
        "startingAirport": "ATL",
        "destinationAirport": "PHL",
        "segmentsAirlineName": "Frontier Airlines||Frontier Airlines",
        "totalFare": "570.0",
    }
    normalized = normalize_flight_row(row)
    assert normalized["flight_date"] == date(2022, 4, 18)
    assert normalized["starting_airport"] == "ATL"
    assert normalized["price"] == Decimal("570.0")


def test_search_uses_cached_embedder_once(monkeypatch):
    class FakeEmbedder:
        def __init__(self):
            self.calls = 0

        def encode_query(self, text):
            self.calls += 1
            return [0.1, 0.2, 0.3]

    fake = FakeEmbedder()
    calls = {"count": 0}

    def fake_get_embedder():
        calls["count"] += 1
        return fake

    monkeypatch.setattr("backend.rag.search.get_local_embedder", fake_get_embedder)

    class FakeChunk:
        chunk_id = "chunk-1"
        id = 1
        document_id = 1
        chunk_index = 0
        text = "Quiet museums in Lisbon in winter."
        city = "Lisbon"
        country = "Portugal"
        season = "winter"
        topic = "see"
        embedding = None
        search_vector = None
        source_url = "https://example.com"
        license = "CC BY-SA 4.0"

    class FakeDocument:
        title = "Lisbon"
        source_url = "https://example.com"
        license = "CC BY-SA 4.0"

    class FakeResult:
        def all(self):
            return [(FakeChunk(), FakeDocument())]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

    monkeypatch.setattr("backend.rag.search.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr("backend.rag.search.rewrite_user_query", lambda *args, **kwargs: ["quiet museums in Lisbon in winter"])

    results = search("quiet museums in Lisbon in winter", limit=5)
    assert results
    assert calls["count"] == 1
    assert fake.calls == 1


def test_reranker_uses_model_scores(monkeypatch):
    class FakeModel:
        def predict(self, pairs, batch_size=32):
            return [0.2, 0.9]

    reranker = CrossEncoderReranker(model=FakeModel())
    candidates = [{"text": "alpha"}, {"text": "beta"}]
    ranked = reranker.rerank(candidates, "query")
    assert [item["text"] for item in ranked] == ["beta", "alpha"]


def test_chunk_document_preserves_currency_text_exactly():
    text = "Pastéis de nata cost €1.50 and are popular."
    chunks = chunk_document(title="Lisbon", city="Lisbon", country="Portugal", text=text, source_url="", license="CC BY-SA 4.0")
    assert any(chunk["text"] == text for chunk in chunks)


def test_search_raises_when_embedding_model_fails(monkeypatch):
    class FakeChunk:
        id = 1
        document_id = 1
        chunk_index = 0
        text = "Quiet museums in Lisbon in winter."
        embedding = None

    class FakeDocument:
        title = "Lisbon"
        source_url = "https://example.com/lisbon"
        license = "CC BY-SA 4.0"

    class FakeResult:
        def all(self):
            return [(FakeChunk(), FakeDocument())]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

    monkeypatch.setattr("backend.rag.search.SessionLocal", lambda: FakeSession())

    def fake_encode_query(_self, _text):
        raise RuntimeError("Model download failed because the environment is offline or the network is unavailable.")

    monkeypatch.setattr("backend.rag.search.LocalEmbedder.encode_query", fake_encode_query)

    try:
        search("quiet museums in Lisbon in winter")
        raise AssertionError("Expected RuntimeError when embeddings are unavailable")
    except RuntimeError as exc:
        assert "network" in str(exc).lower() or "model" in str(exc).lower()


def test_ingest_raises_when_embedding_model_fails(monkeypatch):
    monkeypatch.setattr("backend.rag.ingest.read_cities", lambda _path=None: ["Lisbon"])
    monkeypatch.setattr("backend.rag.ingest.assert_rag_tables_exist", lambda: None)
    monkeypatch.setattr("backend.rag.ingest.fetch_city_pages", lambda _cities: [{"city": "Lisbon", "title": "Lisbon", "text": "Lisbon museums are great.", "url": "https://example.com", "license": "CC BY-SA 4.0"}])

    def fake_encode(_self, _texts):
        raise RuntimeError("Model download failed because the environment is offline or the network is unavailable.")

    monkeypatch.setattr("backend.rag.ingest.LocalEmbedder.encode", fake_encode)

    try:
        ingest_cities("config/cities.yaml")
        raise AssertionError("Expected RuntimeError when embeddings are unavailable")
    except RuntimeError as exc:
        assert "network" in str(exc).lower() or "model" in str(exc).lower()
