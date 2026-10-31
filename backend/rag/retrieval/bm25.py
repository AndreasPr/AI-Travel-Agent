"""In-memory BM25 over a snapshot of chunk texts."""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower())


class BM25Index:
    def __init__(self, rows: list[dict]):
        self.rows = [dict(row) for row in rows]
        corpus = [tokenize(str(row["text"])) for row in rows]
        self.model = BM25Okapi(corpus) if any(corpus) else None

    def search(self, query: str, filters: dict | None = None, limit: int = 30) -> list[dict]:
        tokens = tokenize(query)
        if self.model is None or not tokens:
            return []
        scores = self.model.get_scores(tokens)
        order = sorted(range(len(self.rows)), key=lambda i: (-float(scores[i]), str(self.rows[i]["id"])))
        # Score against the full corpus before applying hard metadata constraints.
        return [self.rows[i] for i in order
                if set(tokens).intersection(tokenize(str(self.rows[i]["text"])))
                and all(self.rows[i].get(key) == value for key, value in (filters or {}).items() if value is not None)][:limit]
