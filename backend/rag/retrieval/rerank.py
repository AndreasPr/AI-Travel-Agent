from __future__ import annotations

from typing import Any


def simple_rerank(candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
    if not candidates:
        return []
    query_terms = {token.lower() for token in query.split() if token.strip()}
    scored = []
    for candidate in candidates:
        text = str(candidate.get("text", "")).lower()
        match_count = sum(1 for term in query_terms if term in text)
        score = match_count + 0.1 * len(query_terms.intersection({token for token in text.split()}))
        scored.append({**candidate, "rerank_score": score})
    return sorted(scored, key=lambda item: item["rerank_score"], reverse=True)[:limit]
