from __future__ import annotations

import argparse
import json
from functools import lru_cache
from typing import Any

from sqlalchemy import and_, func, select

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.embeddings import LocalEmbedder
from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter, reciprocal_rank_fusion, rewrite_user_query
from backend.rag.retrieval.rerank import CrossEncoderReranker


@lru_cache(maxsize=1)
def get_local_embedder() -> LocalEmbedder:
    return LocalEmbedder()


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


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
    rewriter = RuleBasedQueryRewriter()
    metadata = rewriter.extract_metadata(query)
    return {
        "city": metadata.get("city"),
        "country": metadata.get("country"),
        "season": metadata.get("season"),
        "topic": metadata.get("topic"),
    }, query.strip()


def search(query: str, limit: int = 5, mode: str = "hybrid", city: str | None = None, country: str | None = None, season: str | None = None, topic: str | None = None, rerank: bool = False) -> list[dict[str, Any]]:
    embedder = get_local_embedder()
    reranker = get_reranker() if rerank else None
    extracted_filters, query_text = _extract_filters(query)
    hard_filters: dict[str, str | None] = {}
    if city:
        hard_filters["city"] = city
    elif extracted_filters.get("city"):
        hard_filters["city"] = extracted_filters["city"]
    if country:
        hard_filters["country"] = country
    elif extracted_filters.get("country"):
        hard_filters["country"] = extracted_filters["country"]
    if season is not None:
        hard_filters["season"] = season
    if topic is not None:
        hard_filters["topic"] = topic

    soft_filters: dict[str, str | None] = {}
    if season is None and extracted_filters.get("season") is not None:
        soft_filters["season"] = extracted_filters["season"]
    if topic is None and extracted_filters.get("topic") is not None:
        soft_filters["topic"] = extracted_filters["topic"]

    query_variants = rewrite_user_query(query_text, rewriter=RuleBasedQueryRewriter()) or [query_text]
    if not query_variants:
        query_variants = [query_text]

    vector_cache: dict[str, list[float]] = {}

    def _encode_variant(variant: str) -> list[float]:
        if variant in vector_cache:
            return vector_cache[variant]
        try:
            query_vector = embedder.encode_query(variant)
        except RuntimeError as exc:
            raise RuntimeError(
                "Embedding model unavailable. The model download failed because the environment is offline or the network is unavailable. "
                "Install the model cache or restore connectivity before retrying."
            ) from exc
        vector_cache[variant] = query_vector
        return query_vector

    def _fetch_ranking_for_variant(variant: str, filters_by_field: dict[str, str | None]) -> tuple[list[str], dict[str, dict[str, Any]]]:
        clauses = []
        if filters_by_field.get("city"):
            clauses.append(DocumentChunk.city == filters_by_field["city"])
        if filters_by_field.get("country"):
            clauses.append(DocumentChunk.country == filters_by_field["country"])
        if filters_by_field.get("season"):
            clauses.append(DocumentChunk.season == filters_by_field["season"])
        if filters_by_field.get("topic"):
            clauses.append(DocumentChunk.topic == filters_by_field["topic"])

        with SessionLocal() as session:
            base_select = (
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(and_(*clauses))
                .where(DocumentChunk.text.isnot(None))
            )

            vector_rows: list[dict[str, Any]] = []
            bm25_rows: list[dict[str, Any]] = []
            if mode in {"vector", "hybrid"}:
                query_vector = _encode_variant(variant)
                vector_hits = session.execute(
                    base_select.order_by(DocumentChunk.embedding.cosine_distance(query_vector)).limit(30)
                ).all()
                vector_rows = [_candidate_row(row) for row in vector_hits]

            if mode in {"bm25", "hybrid"}:
                ts_query = func.websearch_to_tsquery("english", variant)
                bm25_hits = session.execute(
                    select(DocumentChunk, Document, func.ts_rank_cd(DocumentChunk.search_vector, ts_query).label("rank"))
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(and_(*clauses))
                    .where(DocumentChunk.search_vector.isnot(None))
                    .where(DocumentChunk.search_vector.op("@@")(ts_query))
                    .order_by(func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc())
                    .limit(30)
                ).all()
                bm25_rows = [_candidate_row((row[0], row[1])) for row in bm25_hits]

            if mode == "vector":
                candidate_ids = [str(row["id"]) for row in vector_rows]
                by_id = {str(row["id"]): row for row in vector_rows}
            elif mode == "bm25":
                candidate_ids = [str(row["id"]) for row in bm25_rows]
                by_id = {str(row["id"]): row for row in bm25_rows}
            else:
                fused = reciprocal_rank_fusion(
                    [str(row["id"]) for row in vector_rows],
                    [str(row["id"]) for row in bm25_rows],
                    k=60,
                )
                candidate_ids = [item_id for item_id, _ in fused]
                by_id = {str(row["id"]): row for row in vector_rows + bm25_rows}

            return candidate_ids, by_id

    ranking_sets: list[list[str]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for variant in query_variants:
        for filter_set in [hard_filters.copy() | soft_filters, hard_filters.copy()]:
            ranking, item_map = _fetch_ranking_for_variant(variant, filter_set)
            ranking_sets.append(ranking)
            by_id.update(item_map)

    if not ranking_sets:
        return []

    fused = reciprocal_rank_fusion(*ranking_sets, k=60)
    ranked_ids = [item_id for item_id, _ in fused]
    if rerank and reranker is not None:
        rerank_candidates = [by_id[item_id] for item_id in ranked_ids if item_id in by_id][:30]
        reranked = reranker.rerank(rerank_candidates, query_text, limit=limit)
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
