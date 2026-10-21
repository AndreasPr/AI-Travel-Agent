from __future__ import annotations

from typing import Any, Protocol

from backend.rag.config import get_reranker_model_name


class Reranker(Protocol):
    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        ...


class FakeReranker:
    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(candidates)[:limit]


class CrossEncoderReranker:
    def __init__(self, model_name: str | None = None, model: Any | None = None):
        self.model_name = model_name or get_reranker_model_name()
        self.model = model
        self._model = None

    def _load_model(self) -> Any:
        if self.model is not None:
            self._model = self.model
            return self._model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("sentence-transformers is not installed. Install requirements before using reranking.") from exc
        try:
            self._model = CrossEncoder(self.model_name)
        except Exception as exc:  # pragma: no cover - offline/download guard
            raise RuntimeError(
                "Reranker model download failed because the environment is offline or the network is unavailable. "
                "Preload the model or restore connectivity before retrying."
            ) from exc
        return self._model

    def rerank(self, candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not candidates:
            return []
        model = self._load_model()
        pairs = [(query, str(candidate.get("text", ""))) for candidate in candidates]
        scores = model.predict(pairs, batch_size=32)
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        if hasattr(scores, "item"):
            scores = [float(scores.item())]
        elif not isinstance(scores, list):
            scores = [float(scores)]
        if len(scores) == 1 and len(pairs) > 1:
            scores = [float(scores[0])] * len(pairs)
        scored: list[dict[str, Any]] = []
        for candidate, raw_score in zip(candidates, scores):
            item = dict(candidate)
            item["rerank_score"] = float(raw_score)
            scored.append(item)
        return sorted(scored, key=lambda item: float(item["rerank_score"]), reverse=True)[:limit]


def simple_rerank(candidates: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
    return FakeReranker().rerank(candidates, query, limit=limit)
