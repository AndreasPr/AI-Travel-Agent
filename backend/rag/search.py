from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import and_, func, select

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.config import read_city_country_map
from backend.rag.embeddings import LocalEmbedder
from backend.rag.retrieval.hybrid import reciprocal_rank_fusion, rewrite_user_query
from backend.rag.retrieval.rerank import CrossEncoderReranker


def _candidate_row(row: Any) -> dict[str, Any]:
    chunk, document = row
    embedding = chunk.embedding
    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()
    return {
        "id": chunk.id,
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "document_id": chunk.document_id,
        "chunk_index": chunk.chunk_index,
        "city": chunk.city,
        "country": chunk.country,
        "season": chunk.season,
        "topic": chunk.topic,
        "title": document.title,
        "source_url": document.source_url,
        "license": document.license or "CC BY-SA 4.0",
        "attribution": "Content from Wikivoyage is licensed under CC BY-SA 4.0.",
        "embedding": embedding,
        "metadata": {
            "chunk_id": chunk.chunk_id,
            "city": chunk.city,
            "country": chunk.country,
            "season": chunk.season,
            "topic": chunk.topic,
            "source_url": chunk.source_url,
            "license": chunk.license,
        },
    }


def _extract_filters(query: str) -> tuple[dict[str, str | None], str]:
    text = query.strip()
    city_map = read_city_country_map()
    city = None
    for candidate in sorted(city_map, key=len, reverse=True):
        if candidate.lower() in text.lower():
            city = candidate
            break
    season = None
    for candidate in ("winter", "spring", "summer", "autumn", "fall"):
        if candidate in text.lower():
            season = candidate
            break
    topic = None
    topic_aliases = {
        "museum": "see",
        "museums": "see",
        "food": "eat",
        "foods": "eat",
        "hotel": "sleep",
        "hotels": "sleep",
        "transport": "get around",
        "walking": "do",
        "hike": "do",
        "nightlife": "do",
        "history": "understand",
    }
    lowered = text.lower()
    for candidate, mapped in topic_aliases.items():
        if candidate in lowered:
            topic = mapped
            break
    filters = {"city": city, "country": city_map.get(city) if city else None, "season": season, "topic": topic}
    return filters, text


def search(query: str, limit: int = 5, mode: str = "hybrid", city: str | None = None, country: str | None = None, season: str | None = None, topic: str | None = None, rerank: bool = False) -> list[dict[str, Any]]:
    filters, query_text = _extract_filters(query)
    if city:
        filters["city"] = city
    if country:
        filters["country"] = country
    if season:
        filters["season"] = season
    if topic:
        filters["topic"] = topic

    def _select_candidates(active_filters: dict[str, str | None]) -> tuple[list[dict[str, Any]], list[str]]:
        clauses = []
        if active_filters.get("city"):
            clauses.append(DocumentChunk.city == active_filters["city"])
        if active_filters.get("country"):
            clauses.append(DocumentChunk.country == active_filters["country"])
        if active_filters.get("season"):
            clauses.append(DocumentChunk.season == active_filters["season"])
        if active_filters.get("topic"):
            clauses.append(DocumentChunk.topic == active_filters["topic"])

        with SessionLocal() as session:
            base_select = (
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(and_(*clauses))
                .where(DocumentChunk.text.isnot(None))
            )

            vector_candidates: list[dict[str, Any]] = []
            bm25_candidates: list[dict[str, Any]] = []
            if mode in {"vector", "hybrid"}:
                try:
                    query_vector = LocalEmbedder().encode_query(query_text)
                except RuntimeError as exc:
                    raise RuntimeError(
                        "Embedding model unavailable. The model download failed because the environment is offline or the network is unavailable. "
                        "Install the model cache or restore connectivity before retrying."
                    ) from exc
                vector_rows = session.execute(
                    base_select.order_by(DocumentChunk.embedding.cosine_distance(query_vector)).limit(30)
                ).all()
                vector_candidates = [_candidate_row(row) for row in vector_rows]

            if mode in {"bm25", "hybrid"}:
                rewritten = rewrite_user_query(query_text)
                ts_query = None
                if rewritten:
                    ts_query = func.websearch_to_tsquery("english", " ".join(rewritten))
                if ts_query is not None:
                    bm25_rows = session.execute(
                        select(DocumentChunk, Document, func.ts_rank_cd(DocumentChunk.search_vector, ts_query).label("rank"))
                        .join(Document, Document.id == DocumentChunk.document_id)
                        .where(and_(*clauses))
                        .where(DocumentChunk.search_vector.isnot(None))
                        .where(DocumentChunk.search_vector.op("@@")(ts_query))
                        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc())
                        .limit(30)
                    ).all()
                    bm25_candidates = [_candidate_row((row[0], row[1])) for row in bm25_rows]

            if mode == "vector":
                ranked_ids = [str(row["id"]) for row in vector_candidates]
                candidates = vector_candidates
            elif mode == "bm25":
                ranked_ids = [str(row["id"]) for row in bm25_candidates]
                candidates = bm25_candidates
            else:
                ranked_ids = [str(item_id) for item_id, _ in reciprocal_rank_fusion(
                    [str(row["id"]) for row in vector_candidates],
                    [str(row["id"]) for row in bm25_candidates],
                    k=60,
                )]
                by_id: dict[str, dict[str, Any]] = {}
                for row in vector_candidates + bm25_candidates:
                    by_id[str(row["id"])] = row
                candidates = [by_id[item_id] for item_id in ranked_ids if item_id in by_id]

            return candidates, [str(item_id) for item_id in ranked_ids if item_id in {str(row["id"]) for row in candidates}]

    candidates, ranked_ids = _select_candidates(filters)
    if not candidates and (filters.get("season") or filters.get("topic")):
        relaxed_filters = {key: value for key, value in filters.items() if key not in {"season", "topic"}}
        candidates, ranked_ids = _select_candidates(relaxed_filters)
    if not candidates:
        return []

    by_id = {str(row["id"]): row for row in candidates}
    if rerank:
        reranked = CrossEncoderReranker().rerank(list(by_id.values()), query_text, limit=limit)
        return reranked[:limit]
    return [by_id[item_id] for item_id in ranked_ids if item_id in by_id][:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local RAG collection.")
    parser.add_argument("query", help="Search query to run.")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to show.")
    parser.add_argument("--mode", choices=["vector", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--city", default=None)
    parser.add_argument("--country", default=None)
    parser.add_argument("--season", default=None)
    parser.add_argument("--topic", default=None)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    result = search(args.query, limit=args.limit, mode=args.mode, city=args.city, country=args.country, season=args.season, topic=args.topic, rerank=args.rerank)
    print(json.dumps({"query": args.query, "results": result}, indent=2))


if __name__ == "__main__":
    main()
