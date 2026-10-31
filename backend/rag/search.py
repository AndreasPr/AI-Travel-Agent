from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from typing import Any

from sqlalchemy import and_, func, select

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.embeddings import LocalEmbedder
from backend.rag.config import get_default_retrieval_mode
from backend.rag.retrieval.bm25 import BM25Index
from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter, reciprocal_rank_fusion, rewrite_user_query
from backend.rag.retrieval.rerank import CrossEncoderReranker


@lru_cache(maxsize=1)
def get_local_embedder() -> LocalEmbedder:
    return LocalEmbedder()


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


FTS_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "de", "for", "from",
    "if", "in", "is", "it", "its", "of", "on", "or", "so", "that", "the", "their",
    "this", "to", "too", "very", "we", "with", "yet"
}


def build_or_tsquery(text: str | None) -> str | None:
    if text is None:
        return None
    lowered = str(text).lower().strip()
    if not lowered:
        return None
    tokens: list[str] = []
    for raw in re.findall(r"[^\W_]+", lowered, flags=re.UNICODE):
        token = re.sub(r"[^0-9a-zà-öø-ÿ]+", "", raw, flags=re.IGNORECASE | re.UNICODE)
        if not token or token in FTS_STOPWORDS:
            continue
        tokens.append(token)
    if not tokens:
        return None
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return " | ".join(unique)


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


@lru_cache(maxsize=1)
def get_bm25_index() -> BM25Index:
    with SessionLocal() as session:
        rows = session.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.text.isnot(None))
            .order_by(DocumentChunk.id)
        ).all()
    return BM25Index([_candidate_row(row) for row in rows])


def _extract_filters(query: str) -> tuple[dict[str, str | None], str]:
    rewriter = RuleBasedQueryRewriter()
    metadata = rewriter.extract_metadata(query)
    return {
        "city": metadata.get("city"),
        "country": metadata.get("country"),
        "season": metadata.get("season"),
        "topic": metadata.get("topic"),
    }, query.strip()


def _resolve_filters(
    query: str,
    *,
    city: str | None = None,
    country: str | None = None,
    season: str | None = None,
    topic: str | None = None,
    auto_filters: bool = True,
) -> tuple[dict[str, str | None], dict[str, str | None], dict[str, str | None]]:
    extracted_filters, query_text = _extract_filters(query) if auto_filters else ({"city": None, "country": None, "season": None, "topic": None}, query.strip())
    hard_filters: dict[str, str | None] = {}

    if city:
        hard_filters["city"] = city
    elif auto_filters and extracted_filters.get("city"):
        hard_filters["city"] = extracted_filters["city"]

    if country:
        hard_filters["country"] = country
    elif auto_filters and extracted_filters.get("country") and not hard_filters.get("city"):
        hard_filters["country"] = extracted_filters["country"]

    if season is not None:
        hard_filters["season"] = season
    if topic is not None:
        hard_filters["topic"] = topic

    soft_filters: dict[str, str | None] = {}
    if auto_filters and season is None and extracted_filters.get("season") is not None:
        soft_filters["season"] = extracted_filters["season"]
    if auto_filters and topic is None and extracted_filters.get("topic") is not None:
        soft_filters["topic"] = extracted_filters["topic"]
    return hard_filters, soft_filters, extracted_filters


def search(
    query: str,
    limit: int = 5,
    mode: str | None = None,
    city: str | None = None,
    country: str | None = None,
    season: str | None = None,
    topic: str | None = None,
    rerank: bool = False,
    auto_filters: bool = True,
    expand_queries: bool = True,
    trace: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    mode = mode if mode is not None else get_default_retrieval_mode()
    if mode not in {"vector", "fts", "bm25", "hybrid", "hybrid(bm25)"}:
        raise ValueError(f"Unknown retrieval mode: {mode}")
    embedder = get_local_embedder() if mode in {"vector", "hybrid", "hybrid(bm25)"} else None
    reranker = get_reranker() if rerank else None
    hard_filters, soft_filters, _ = _resolve_filters(query, city=city, country=country, season=season, topic=topic, auto_filters=auto_filters)
    query_text = query.strip()

    query_variants = rewrite_user_query(query_text, rewriter=RuleBasedQueryRewriter()) or [query_text]
    if not expand_queries:
        query_variants = [query_text]
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
                .where(DocumentChunk.text.isnot(None))
            )
            if clauses:
                base_select = base_select.where(and_(*clauses))

            vector_rows: list[dict[str, Any]] = []
            lexical_rows: list[dict[str, Any]] = []
            if mode in {"vector", "hybrid", "hybrid(bm25)"}:
                query_vector = _encode_variant(variant)
                vector_hits = session.execute(
                    base_select.order_by(DocumentChunk.embedding.cosine_distance(query_vector)).limit(30)
                ).all()
                vector_rows = [_candidate_row(row) for row in vector_hits]

            if mode in {"fts", "hybrid"}:
                ts_query_sql = build_or_tsquery(variant)
                if ts_query_sql is None:
                    lexical_rows = []
                else:
                    ts_query = func.to_tsquery("english", ts_query_sql)
                    fts_query = (
                        select(DocumentChunk, Document, func.ts_rank_cd(DocumentChunk.search_vector, ts_query).label("rank"))
                        .join(Document, Document.id == DocumentChunk.document_id)
                        .where(DocumentChunk.search_vector.isnot(None))
                        .where(DocumentChunk.search_vector.op("@@")(ts_query))
                    )
                    if clauses:
                        fts_query = fts_query.where(and_(*clauses))
                    fts_hits = session.execute(
                        fts_query.order_by(func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc()).limit(30)
                    ).all()
                    lexical_rows = [_candidate_row((row[0], row[1])) for row in fts_hits]

            if mode in {"bm25", "hybrid(bm25)"}:
                lexical_rows = get_bm25_index().search(variant, filters_by_field)

            if mode == "vector":
                candidate_ids = [str(row["id"]) for row in vector_rows]
                by_id = {str(row["id"]): row for row in vector_rows}
            elif mode in {"fts", "bm25"}:
                candidate_ids = [str(row["id"]) for row in lexical_rows]
                by_id = {str(row["id"]): row for row in lexical_rows}
            else:
                fused = reciprocal_rank_fusion(
                    [str(row["id"]) for row in vector_rows],
                    [str(row["id"]) for row in lexical_rows],
                    k=60,
                )
                candidate_ids = [item_id for item_id, _ in fused]
                by_id = {str(row["id"]): row for row in vector_rows + lexical_rows}

            return candidate_ids, by_id

    ranking_sets: list[list[str]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for variant in query_variants:
        filter_sets: list[dict[str, str | None]]
        if expand_queries:
            filter_sets = [hard_filters.copy() | soft_filters, hard_filters.copy()]
        else:
            filter_sets = [hard_filters.copy()]
        for filter_set in filter_sets:
            ranking, item_map = _fetch_ranking_for_variant(variant, filter_set)
            ranking_sets.append(ranking)
            by_id.update(item_map)

    if not ranking_sets:
        return []

    fused = reciprocal_rank_fusion(*ranking_sets, k=60)
    ranked_ids = [item_id for item_id, _ in fused]
    rerank_candidates = [by_id[item_id] for item_id in ranked_ids if item_id in by_id][:30]
    if trace is not None:
        trace.update(extracted_filters=_extract_filters(query)[0], hard_filters=hard_filters,
                     soft_filters=soft_filters, candidate_pool=rerank_candidates)
    if rerank and reranker is not None:
        reranked = reranker.rerank(rerank_candidates, query_text, limit=limit)
        return reranked[:limit]
    return [by_id[item_id] for item_id in ranked_ids if item_id in by_id][:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local RAG collection.")
    parser.add_argument("query", help="Search query to run.")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to show.")
    parser.add_argument("--mode", choices=["vector", "fts", "bm25", "hybrid", "hybrid(bm25)"], default=None)
    parser.add_argument("--city", default=None)
    parser.add_argument("--country", default=None)
    parser.add_argument("--season", default=None)
    parser.add_argument("--topic", default=None)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--auto-filters", dest="auto_filters", action="store_true", default=True)
    parser.add_argument("--no-auto-filters", dest="auto_filters", action="store_false")
    parser.add_argument("--expand-queries", dest="expand_queries", action="store_true", default=True)
    parser.add_argument("--no-expand-queries", dest="expand_queries", action="store_false")
    args = parser.parse_args()
    result = search(args.query, limit=args.limit, mode=args.mode, city=args.city, country=args.country, season=args.season, topic=args.topic, rerank=args.rerank, auto_filters=args.auto_filters, expand_queries=args.expand_queries)
    print(json.dumps({"query": args.query, "results": result}, indent=2))


if __name__ == "__main__":
    main()
