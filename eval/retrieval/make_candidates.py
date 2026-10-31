from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag.search import search  # noqa: E402
from eval.retrieval.modes import MODE_SPECS, mode_parameters

QUERIES_PATH = ROOT / "eval" / "retrieval" / "queries.jsonl"
OUT_PATH = ROOT / "eval" / "retrieval" / "candidates.csv"


def load_queries(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def merge_candidates(rows: list[dict], existing: dict[tuple[str, str], str] | None = None) -> list[dict]:
    pooled: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (str(row.get("query", "")), str(row.get("chunk_id", "")))
        if not key[1]:
            continue
        entry = pooled.get(key)
        if entry is None:
            entry = {
                "query": key[0],
                "chunk_id": key[1],
                "found_by": [],
                "best_rank": 10**9,
                "city": str(row.get("city", "")),
                "topic": str(row.get("topic", "")),
                "snippet": str(row.get("snippet", "")),
                "relevant": str(row.get("relevant", "")),
            }
            pooled[key] = entry
        entry["found_by"].append(str(row.get("mode", "")))
        rank = int(row.get("rank", 10**9))
        entry["best_rank"] = min(int(entry["best_rank"]), rank)
        if not entry["city"] and row.get("city"):
            entry["city"] = row.get("city")
        if not entry["topic"] and row.get("topic"):
            entry["topic"] = row.get("topic")
        if not entry["snippet"] and row.get("snippet"):
            entry["snippet"] = row.get("snippet")
        if not str(entry["relevant"]).strip() and str(row.get("relevant", "")).strip():
            entry["relevant"] = row.get("relevant")
    if existing:
        for key, value in existing.items():
            if key not in pooled:
                pooled[key] = {"query": key[0], "chunk_id": key[1], "found_by": [], "best_rank": 10**9, "city": "", "topic": "", "snippet": "", "relevant": value}
            elif str(value).strip():
                pooled[key]["relevant"] = value
    merged = list(pooled.values())
    for entry in merged:
        entry["found_by"] = ",".join(sorted(dict.fromkeys(entry["found_by"])))
        entry["best_rank"] = int(entry["best_rank"])
        entry["relevant"] = str(entry.get("relevant", ""))
    merged.sort(key=lambda row: (int(row["best_rank"]), str(row["query"]), str(row["chunk_id"])))
    return merged


def main() -> None:
    queries = load_queries(QUERIES_PATH)
    existing = {}
    if OUT_PATH.exists():
        with OUT_PATH.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("query") and row.get("chunk_id") and str(row.get("relevant", "")).strip():
                    existing[(str(row["query"]), str(row["chunk_id"]))] = str(row["relevant"])

    modes = MODE_SPECS
    rows: list[dict[str, object]] = []
    for query_record in queries:
        query = str(query_record.get("query", "")).strip()
        for mode_name, params in modes:
            results = search(query, limit=10, **mode_parameters(query, params))
            for rank, result in enumerate(results[:10], start=1):
                row = {
                    "query": query,
                    "rank": str(rank),
                    "mode": mode_name,
                    "chunk_id": str(result.get("chunk_id", "")),
                    "city": str(result.get("city", "")),
                    "topic": str(result.get("topic", "")),
                    "snippet": str(result.get("text", ""))[:200].replace("\n", " "),
                    "relevant": "",
                }
                rows.append(row)
    pooled = merge_candidates(rows, existing)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query", "chunk_id", "found_by", "best_rank", "city", "topic", "snippet", "relevant"])
        writer.writeheader()
        for item in pooled:
            writer.writerow({
                "query": item["query"],
                "chunk_id": item["chunk_id"],
                "found_by": item["found_by"],
                "best_rank": item["best_rank"],
                "city": item["city"],
                "topic": item["topic"],
                "snippet": item["snippet"],
                "relevant": item["relevant"],
            })
    print(f"wrote {len(pooled)} pooled candidate rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
