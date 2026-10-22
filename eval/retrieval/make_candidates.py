from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.rag.search import search


ROOT = Path(__file__).resolve().parents[2]
QUERIES_PATH = ROOT / "eval" / "retrieval" / "queries.jsonl"
OUT_PATH = ROOT / "eval" / "retrieval" / "candidates.csv"


def load_queries(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def main() -> None:
    queries = load_queries(QUERIES_PATH)
    fieldnames = ["query", "rank", "chunk_id", "city", "topic", "snippet", "relevant"]
    rows: list[dict[str, str]] = []
    for query_record in queries:
        query = str(query_record.get("query", "")).strip()
        results = search(query, limit=10, mode="hybrid", rerank=False)
        for rank, result in enumerate(results[:10], start=1):
            chunk_id = str(result.get("chunk_id", ""))
            rows.append(
                {
                    "query": query,
                    "rank": str(rank),
                    "chunk_id": chunk_id,
                    "city": str(result.get("city", "")),
                    "topic": str(result.get("topic", "")),
                    "snippet": str(result.get("text", ""))[:200].replace("\n", " "),
                    "relevant": "",
                }
            )
    with OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} candidate rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
