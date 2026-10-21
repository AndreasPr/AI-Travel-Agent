from __future__ import annotations

from typing import Any, Protocol


class Reranker(Protocol):
    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        ...


class FakeReranker:
    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(candidates)[:limit]


class CrossEncoderReranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not candidates:
            return []
        query_terms = {token.lower() for token in query.split() if token.strip()}
        scored: list[dict[str, Any]] = []
        for candidate in candidates:
            text = str(candidate.get("text", "")).lower()
            overlap = sum(1 for term in query_terms if term in text)
            score = overlap + 0.05 * len(query_terms.intersection({token for token in text.split()}))
            scored.append({**candidate, "rerank_score": score})
        return sorted(scored, key=lambda item: item["rerank_score"], reverse=True)[:limit]


def simple_rerank(candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
    return FakeReranker().rerank(candidates, query, limit=limit)
