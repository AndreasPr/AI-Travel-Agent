from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Protocol

from backend.rag.config import read_city_country_map


class QueryRewriter(Protocol):
    def rewrite(self, user_request: str) -> list[str]:
        ...


class RuleBasedQueryRewriter:
    def __init__(self, city_map: dict[str, str] | None = None):
        self.city_map = city_map or read_city_country_map()

    def rewrite(self, user_request: str) -> list[str]:
        text = (user_request or "").strip()
        if not text:
            return []
        lowered = text.lower()
        city = None
        for candidate in sorted(self.city_map, key=len, reverse=True):
            if re.search(rf"\b{re.escape(candidate.lower())}\b", lowered):
                city = candidate
                break

        season = None
        for candidate in ("winter", "spring", "summer", "autumn", "fall"):
            if re.search(rf"\b{candidate}\b", lowered):
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
        for candidate in topic_aliases:
            if re.search(rf"\b{re.escape(candidate)}\b", lowered):
                topic = topic_aliases[candidate]
                break

        cleaned = re.sub(r"\s+", " ", text)
        variants: list[str] = []
        if city or season or topic:
            parts = []
            if city:
                parts.append(city)
            if topic:
                parts.append(topic)
            if season:
                parts.append(season)
            variants.append(" ".join(parts))
        variants.append(cleaned)
        if len(cleaned.split()) > 4:
            variants.append(" ".join(cleaned.split()[:8]))
        if len(cleaned.split()) > 8:
            variants.append(" ".join(cleaned.split()[:12]))
        deduped: list[str] = []
        for variant in variants:
            normalized = " ".join(variant.split())
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped[:3]


class DefaultQueryRewriter(RuleBasedQueryRewriter):
    pass


def rewrite_user_query(user_request: str, rewriter: QueryRewriter | None = None) -> list[str]:
    return (rewriter or DefaultQueryRewriter()).rewrite(user_request)


def reciprocal_rank_fusion(*rankings: list[str], k: int = 60) -> list[tuple[str, float]]:
    """Fuse rankings with reciprocal rank fusion."""
    if not rankings:
        return []
    score_by_item: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank_index, item in enumerate(ranking, start=1):
            score_by_item[item] += 1.0 / (k + rank_index)
    ordered = sorted(score_by_item.items(), key=lambda pair: (-pair[1], pair[0]))
    return ordered


def apply_metadata_filters(rows: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
    """Apply exact-match metadata filtering in-memory for tests and adapters."""
    filtered = list(rows)
    for key, value in filters.items():
        if value is None or value == "":
            continue
        normalized = str(value).strip().lower()
        filtered = [
            row for row in filtered if str(row.get(key, "")).strip().lower() == normalized
        ]
    return filtered
