from datetime import date
from decimal import Decimal

from sqlalchemy import inspect

from backend.rag.citations import CitedClaim, CitationVerifier
from backend.rag.ingest import assert_rag_tables_exist
from backend.rag.ingestion.chunker import chunk_document
from backend.rag.retrieval.hybrid import reciprocal_rank_fusion, apply_metadata_filters
from backend.scripts.seed_inventory import normalize_flight_row


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


def test_rrf_fusion_combines_rankings():
    vector_rank = ["a", "b", "c"]
    bm25_rank = ["c", "a", "d"]
    fused = reciprocal_rank_fusion(vector_rank, bm25_rank, k=60)
    assert fused[0][0] == "a"
    assert fused[1][0] == "c"


def test_metadata_filters_keep_supported_candidates():
    rows = [
        {"id": 1, "city": "Lisbon", "country": "Portugal", "season": "winter", "topic": "see"},
        {"id": 2, "city": "Rome", "country": "Italy", "season": "summer", "topic": "eat"},
    ]
    filtered = apply_metadata_filters(rows, city="Lisbon", topic="see")
    assert [row["id"] for row in filtered] == [1]


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
    unsupported = verifier.verify(CitedClaim(claim="Lisbon is in the Alps.", source_chunk_ids=["a"]))
    assert unsupported.is_supported is False


def test_assert_rag_tables_exist_raises_helpful_error(monkeypatch):
    def fake_inspect(_bind):
        class FakeInspector:
            def get_table_names(self):
                return ["users", "trips"]

        return FakeInspector()

    monkeypatch.setattr("backend.rag.ingest.inspect", fake_inspect)
    try:
        assert_rag_tables_exist()
        assert False, "Expected a RuntimeError for missing tables"
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
