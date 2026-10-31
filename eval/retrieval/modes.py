"""Shared evaluation and candidate-pool mode definitions."""
MODE_SPECS = [
    (name, {"mode": mode, "rerank": rerank, "auto_filters": filters, "expand_queries": filters})
    for name, mode, rerank, filters in [
        ("vector", "vector", False, False),
        ("vector+rerank", "vector", True, False),
        ("fts", "fts", False, False),
        ("bm25", "bm25", False, False),
        ("hybrid", "hybrid", False, False),
        ("hybrid(bm25)", "hybrid(bm25)", False, False),
        ("hybrid+rerank", "hybrid", True, False),
        ("hybrid+rerank+filters", "hybrid", True, True),
    ]
]

MODE_DEFINITIONS = [
    "vector: vector similarity search.",
    "vector+rerank: vector search followed by the configured cross-encoder.",
    "fts: Postgres full-text search ranked with ts_rank_cd (formerly labeled bm25).",
    "bm25: rank_bm25 BM25Okapi over chunk texts; hard filters apply after scoring.",
    "hybrid: vector + fts via reciprocal rank fusion (RRF).",
    "hybrid(bm25): vector + rank_bm25 via RRF.",
    "hybrid+rerank: hybrid followed by the configured cross-encoder.",
    "hybrid+rerank+filters: hybrid + cross-encoder with automatic filters and query expansion enabled; city/country are hard constraints, inferred season/topic are soft preferences.",
    "All other modes disable automatic filters and query expansion. Reranking uses at most 30 candidates; evaluation scores the top 10.",
]


def mode_parameters(query: str, params: dict) -> dict:
    """Keep evaluation, pooling and diagnosis filter arguments identical."""
    result = dict(params)
    if params["auto_filters"]:
        from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter
        metadata = RuleBasedQueryRewriter().extract_metadata(query)
        result.update(city=metadata.get("city"), country=metadata.get("country"))
    return result
