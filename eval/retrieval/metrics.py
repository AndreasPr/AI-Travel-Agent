from __future__ import annotations

import json
import math
from pathlib import Path


def load_queries(path: str | Path) -> list[dict]:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records.append(record)
    return records


def recall_at_k(relevant: list[str], ranked: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    top_k = ranked[:k]
    hits = sum(1 for item in relevant if item in top_k)
    return hits / len(relevant)


def reciprocal_rank(relevant: list[str], ranked: list[str]) -> float:
    if not relevant:
        return 0.0
    for idx, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / idx
    return 0.0


def ndcg_at_k(relevant: list[str], ranked: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    dcg = 0.0
    ideal = 0.0
    for idx, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            dcg += 1.0 / math.log2(idx + 1)
    ideal_hits = min(len(relevant), k)
    for idx in range(1, ideal_hits + 1):
        ideal += 1.0 / math.log2(idx + 1)
    return dcg / ideal if ideal else 0.0


def evaluate_query(relevant: list[str], ranked: list[str]) -> dict[str, float]:
    return {
        "recall@1": recall_at_k(relevant, ranked, 1),
        "recall@3": recall_at_k(relevant, ranked, 3),
        "recall@5": recall_at_k(relevant, ranked, 5),
        "recall@10": recall_at_k(relevant, ranked, 10),
        "mrr": reciprocal_rank(relevant, ranked),
        "ndcg@10": ndcg_at_k(relevant, ranked, 10),
    }


def main() -> None:
    queries_path = Path(__file__).with_name("queries.jsonl")
    if not queries_path.exists():
        print("No queries.jsonl file was found. Add manual labels for M9 before running this metric script.")
        return
    queries = load_queries(queries_path)
    labeled = [record for record in queries if (record.get("relevant_chunk_ids") or [])]
    if not labeled:
        print("not run")
        return

    metrics = {key: 0.0 for key in ["recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10"]}
    for record in labeled:
        ranked = record.get("predicted_chunk_ids", [])
        values = evaluate_query(record.get("relevant_chunk_ids", []), ranked)
        for key, score in values.items():
            metrics[key] += score
    for key in metrics:
        metrics[key] /= len(labeled)
    print(json.dumps({"queries": len(labeled), "average_metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
