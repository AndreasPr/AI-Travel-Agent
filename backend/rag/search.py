from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import select

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.embeddings import LocalEmbedder
from backend.rag.retrieval.hybrid import reciprocal_rank_fusion


def _infer_bm25_rank(query: str, rows: list[dict[str, Any]]) -> list[str]:
    query_terms = {term.lower() for term in query.split() if term.strip()}
    scored = []
    for row in rows:
        text = row["text"].lower()
        score = sum(1 for term in query_terms if term in text)
        scored.append((row["id"], score))
    return [item_id for item_id, _ in sorted(scored, key=lambda pair: (-pair[1], pair[0]))]


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
        ).all()
    candidates = []
    for chunk, document in rows:
        embedding = chunk.embedding
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        candidates.append(
            {
                "id": chunk.id,
                "text": chunk.text,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "title": document.title,
                "source_url": document.source_url,
                "license": document.license or "CC BY-SA 4.0",
                "attribution": "Content from Wikivoyage is licensed under CC BY-SA 4.0.",
                "embedding": embedding,
                "metadata": {},
            }
        )
    if not candidates:
        return []
    bm25_rank = _infer_bm25_rank(query, candidates)
    embedder = LocalEmbedder()
    try:
        query_vector = embedder.encode_query(query)
    except RuntimeError as exc:
        raise RuntimeError(
            "Embedding model unavailable. The model download failed because the environment is offline or the network is unavailable. "
            "Install the model cache or restore connectivity before retrying."
        ) from exc
    vector_rank = []
    for row in candidates:
        vector = row.get("embedding") or []
        if not vector:
            vector_rank.append((row["id"], 0.0))
            continue
        numerator = sum(a * b for a, b in zip(query_vector, vector))
        denominator = (sum(v * v for v in query_vector) ** 0.5) * (sum(v * v for v in vector) ** 0.5)
        similarity = numerator / denominator if denominator else 0.0
        vector_rank.append((row["id"], similarity))
    fused = reciprocal_rank_fusion([item_id for item_id, _ in sorted(vector_rank, key=lambda item: (-item[1], item[0]))], bm25_rank, k=60)
    selected = []
    by_id = {row["id"]: row for row in candidates}
    for item_id, _ in fused[:limit]:
        row = by_id.get(item_id)
        if row:
            selected.append(row)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local RAG collection.")
    parser.add_argument("query", help="Search query to run.")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to show.")
    args = parser.parse_args()
    result = search(args.query, limit=args.limit)
    print(json.dumps({"query": args.query, "results": result}, indent=2))


if __name__ == "__main__":
    main()
