"""Postgres ingestion test with synthetic pages and fake embeddings; no downloads."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.connect import engine
from backend.db.models import DocumentChunk
from backend.rag import ingest


@pytest.mark.integration
def test_ingestion_idempotency_and_removed_chunk_deleted(monkeypatch):
    page = {"city": "Synthetic City", "country": "Synthetic Country", "title": "Synthetic ingestion fixture",
            "url": "https://example.invalid/synthetic-ingestion-fixture",
            "retrieved_at": "2026-01-01T00:00:00+00:00",  # Synthetic fixture timestamp.
            "text": "== Overview ==\nSynthetic overview.\n\n== Food ==\nSynthetic food section."}
    monkeypatch.setattr(ingest, "read_cities", lambda _: ["Synthetic City"])
    monkeypatch.setattr(ingest, "read_city_country_map", lambda _: {"Synthetic City": "Synthetic Country"})
    monkeypatch.setattr(ingest, "fetch_city_pages", lambda _: [page])
    monkeypatch.setattr(ingest.LocalEmbedder, "encode", lambda self, texts: [[0.0] * 384 for _ in texts])
    with engine.connect() as connection:
        transaction = connection.begin()
        monkeypatch.setattr(ingest, "SessionLocal", lambda: Session(bind=connection, join_transaction_mode="create_savepoint"))
        try:
            first = ingest.ingest_cities()
            assert len(first) == 2
            document_id = first[0]["document_id"]

            def stored_ids():
                return connection.execute(select(DocumentChunk.chunk_id).where(DocumentChunk.document_id == document_id)).scalars().all()

            before = stored_ids()
            ingest.ingest_cities()
            after = stored_ids()
            assert len(after) == len(before) == 2
            assert len(set(after)) == len(after)
            assert set(before) == set(after)
            page["text"] = "== Overview ==\nSynthetic overview."
            remaining = ingest.ingest_cities()
            final = stored_ids()
            assert len(final) == 1
            assert set(final) == {row["chunk_id"] for row in remaining}
            assert len(set(before) - set(final)) == 1
        finally:
            transaction.rollback()
