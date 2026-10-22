from __future__ import annotations

import json
from pathlib import Path

from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter
from backend.rag.search import search
from eval.retrieval.metrics import evaluate_query

ROOT = Path(__file__).resolve().parents[2]
QUERIES_PATH = ROOT / "eval" / "retrieval" / "queries.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_queries(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _extracted_filters(query: str) -> dict[str, str | None]:
    metadata = RuleBasedQueryRewriter().extract_metadata(query)
    return {
        "city": metadata.get("city"),
        "country": metadata.get("country"),
        "season": metadata.get("season"),
        "topic": metadata.get("topic"),
    }


def make_result(query: str, mode_name: str, ranked: list[str], relevant: list[str]) -> dict[str, float | str]:
    scores = evaluate_query(relevant, ranked)
    scores["mode"] = mode_name
    return scores


def main() -> None:
    queries = load_queries(QUERIES_PATH)
    labeled = [record for record in queries if (record.get("relevant_chunk_ids") or [])]
    if not labeled:
        summary = {
            "status": "not run",
            "labeled_queries": 0,
            "modes": {},
        }
        (RESULTS_DIR / "retrieval.md").write_text("not run\n", encoding="utf-8")
        (RESULTS_DIR / "retrieval.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("not run")
        return

    mode_names = ["vector", "bm25", "hybrid", "hybrid+rerank", "hybrid+rerank+filters"]
    averages: dict[str, dict[str, float]] = {mode: {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0, "ndcg@10": 0.0} for mode in mode_names}
    results_by_mode: dict[str, list[dict[str, float | str]]] = {mode: [] for mode in mode_names}

    for record in labeled:
        query = str(record.get("query", "")).strip()
        relevant = [str(item) for item in (record.get("relevant_chunk_ids") or [])]
        filters = _extracted_filters(query)
        ranked_vector = [str(result.get("chunk_id", "")) for result in search(query, limit=10, mode="vector", rerank=False)]
        ranked_bm25 = [str(result.get("chunk_id", "")) for result in search(query, limit=10, mode="bm25", rerank=False)]
        ranked_hybrid = [str(result.get("chunk_id", "")) for result in search(query, limit=10, mode="hybrid", rerank=False)]
        ranked_hybrid_rerank = [str(result.get("chunk_id", "")) for result in search(query, limit=10, mode="hybrid", rerank=True)]
        ranked_hybrid_filters = [
            str(result.get("chunk_id", ""))
            for result in search(
                query,
                limit=10,
                mode="hybrid",
                rerank=True,
                city=filters.get("city"),
                country=filters.get("country"),
                season=filters.get("season"),
                topic=filters.get("topic"),
            )
        ]

        for mode_name, ranked in [
            ("vector", ranked_vector),
            ("bm25", ranked_bm25),
            ("hybrid", ranked_hybrid),
            ("hybrid+rerank", ranked_hybrid_rerank),
            ("hybrid+rerank+filters", ranked_hybrid_filters),
        ]:
            scores = evaluate_query(relevant, ranked)
            results_by_mode[mode_name].append({"query": query, **scores})
            for key in averages[mode_name]:
                averages[mode_name][key] += scores[key]

    for mode_name in mode_names:
        if results_by_mode[mode_name]:
            for key in averages[mode_name]:
                averages[mode_name][key] /= len(results_by_mode[mode_name])

    summary = {
        "status": "ok",
        "labeled_queries": len(labeled),
        "modes": averages,
    }
    markdown_lines = [
        "# Retrieval evaluation",
        f"Labeled queries: {len(labeled)}",
        "",
        "| mode | recall@1 | recall@3 | recall@5 | recall@10 | mrr | ndcg@10 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in mode_names:
        metrics = averages[mode]
        markdown_lines.append(
            f"| {mode} | {metrics['recall@1']:.4f} | {metrics['recall@3']:.4f} | {metrics['recall@5']:.4f} | {metrics['recall@10']:.4f} | {metrics['mrr']:.4f} | {metrics['ndcg@10']:.4f} |"
        )
    (RESULTS_DIR / "retrieval.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    (RESULTS_DIR / "retrieval.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
