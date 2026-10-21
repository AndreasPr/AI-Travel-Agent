from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Protocol


class QueryRewriter(Protocol):
    def rewrite(self, user_request: str) -> list[str]:
        ...


class DefaultQueryRewriter:
    def rewrite(self, user_request: str) -> list[str]:
        text = user_request.strip()
        if not text:
            return []
        cleaned = re.sub(r"\s+", " ", text)
        tokens = [part.strip() for part in cleaned.split(" ") if part.strip()]
        if not tokens:
            return []
        base = " ".join(tokens[:8])
        variants = [base]
        if len(tokens) > 3:
            variants.append(" ".join(tokens[:4]))
        if len(tokens) > 5:
            variants.append(" ".join(tokens[:6]))
        return variants[:3]


def rewrite_user_query(user_request: str, rewriter: QueryRewriter | None = None) -> list[str]:
    return (rewriter or DefaultQueryRewriter()).rewrite(user_request)


def reciprocal_rank_fusion(*rankings: list[str], k: int = 60) -> list[tuple[str, float]]:
    """Fuse rankings with reciprocal rank fusion.

    The function accepts one or more ordered rankings and returns a score-sorted list of
    (item, score) tuples.
    """
    if not rankings:
        return []
    score_by_item: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank_index, item in enumerate(ranking, start=1):
            score_by_item[item] += 1.0 / (k + rank_index)
    ordered = sorted(score_by_item.items(), key=lambda pair: (-pair[1], pair[0]))
    return ordered


def apply_metadata_filters(rows: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
    filtered = list(rows)
    for key, value in filters.items():
        if value is None or value == "":
            continue
        normalized = str(value).strip().lower()
        filtered = [
            row for row in filtered if str(row.get(key, "")).strip().lower() == normalized
        ]
    return filtered
