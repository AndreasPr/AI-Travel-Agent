from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.config import read_city_country_map, read_cities
from backend.rag.embeddings import LocalEmbedder
from backend.rag.ingestion.chunker import chunk_document
from backend.rag.ingestion.wikivoyage import fetch_city_pages


def _safe_city_name(city: str) -> str:
    return city.strip() or "city"


def assert_rag_tables_exist() -> None:
    with SessionLocal() as session:
        tables = set(inspect(session.bind).get_table_names())
    missing = {"documents", "document_chunks"} - tables
    if missing:
        raise RuntimeError(
            "RAG tables are missing. Run `alembic upgrade head` (or `make up`) before ingesting data. "
            f"Missing tables: {sorted(missing)}"
        )


def ingest_cities(cities_path: str | Path | None = None, max_pages: int | None = None) -> list[dict[str, Any]]:
    assert_rag_tables_exist()
    selected = read_cities(cities_path)
    country_map = read_city_country_map(cities_path)
    if max_pages is not None:
        selected = selected[:max_pages]
    if not selected:
        raise ValueError("No cities were provided. Check config/cities.yaml or pass --cities.")

    try:
        pages = fetch_city_pages(selected)
    except Exception as exc:  # pragma: no cover - network guard
        raise RuntimeError(
            "Wikivoyage download failed. Check network access and WIKIVOYAGE_USER_AGENT before retrying."
        ) from exc
    inserted: list[dict[str, Any]] = []
    embedder = LocalEmbedder()
    for page in pages:
        city = page.get("city") or _safe_city_name(page.get("title", "city"))
        country = page.get("country") or country_map.get(city) or "Unknown"
        text = page.get("text") or ""
        chunks = chunk_document(
            title=page.get("title") or city,
            city=city,
            country=country,
            text=text,
            source_url=page.get("url") or "",
            license=page.get("license") or "CC BY-SA 4.0",
            season=None,
        )
        if not chunks:
            continue
        try:
            embeddings = embedder.encode([chunk["text"] for chunk in chunks])
        except RuntimeError as exc:
            raise RuntimeError(
                "Embedding model unavailable. The model download failed because the environment is offline or the network is unavailable. "
                "Install the model cache or restore connectivity before retrying."
            ) from exc
        try:
            with SessionLocal() as session:
                document = session.execute(
                    select(Document)
                    .where(Document.source_url == (page.get("url") or ""))
                    .where(Document.title == (page.get("title") or city))
                    .order_by(Document.id.asc())
                    .limit(1)
                ).scalar_one_or_none()
                if document is None:
                    document = Document(
                        source_url=page.get("url") or "",
                        title=page.get("title") or city,
                        license=page.get("license") or "CC BY-SA 4.0",
                        city=city,
                        country=country,
                        season=None,
                        topic="other",
                        text=text,
                    )
                    session.add(document)
                    session.flush()
                for index, chunk in enumerate(chunks):
                    chunk_id = str(chunk["chunk_id"])
                    chunk_embedding = embeddings[index] if index < len(embeddings) else [0.0] * 384
                    stmt = insert(DocumentChunk).values(
                        chunk_id=chunk_id,
                        document_id=document.id,
                        chunk_index=index,
                        city=city,
                        country=country,
                        season=chunk.get("season") or None,
                        topic=chunk.get("topic") or "other",
                        revision_id=str(page.get("revision_id") or "" or ""),
                        retrieved_at=page.get("retrieved_at"),
                        source_url=page.get("url") or "",
                        license=page.get("license") or "CC BY-SA 4.0",
                        text=chunk["text"],
                        embedding=chunk_embedding,
                        search_vector=func.to_tsvector("english", chunk["text"]),
                    ).on_conflict_do_update(
                        index_elements=["chunk_id"],
                        set_={
                            "document_id": document.id,
                            "chunk_index": index,
                            "city": city,
                            "country": country,
                            "season": chunk.get("season") or None,
                            "topic": chunk.get("topic") or "other",
                            "source_url": page.get("url") or "",
                            "license": page.get("license") or "CC BY-SA 4.0",
                            "text": chunk["text"],
                            "embedding": chunk_embedding,
                            "search_vector": func.to_tsvector("english", chunk["text"]),
                        },
                    )
                    session.execute(stmt)
                    inserted.append({
                        "chunk_id": chunk_id,
                        "document_id": document.id,
                        "city": city,
                        "country": country,
                        "source_url": page.get("url"),
                        "license": page.get("license") or "CC BY-SA 4.0",
                        "text": chunk["text"],
                    })
                session.commit()
        except ProgrammingError as exc:
            raise RuntimeError(
                "The Postgres schema is missing. Run `alembic upgrade head` (or `make up`) before ingesting."
            ) from exc
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Wikivoyage city pages into Postgres with embeddings.")
    parser.add_argument("--cities", default="config/cities.yaml", help="Path to the city list YAML.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit the number of city pages for a quick test run.")
    args = parser.parse_args()
    result = ingest_cities(args.cities, max_pages=args.max_pages)
    print(json.dumps({"ingested_chunks": len(result)}, indent=2))


if __name__ == "__main__":
    main()
