from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter
from backend.rag.search import search
from eval.retrieval.metrics import evaluate_query

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

    mode_specs = [
        ("vector", {"mode": "vector", "rerank": False, "auto_filters": False, "expand_queries": False}),
        ("bm25", {"mode": "bm25", "rerank": False, "auto_filters": False, "expand_queries": False}),
        ("hybrid", {"mode": "hybrid", "rerank": False, "auto_filters": False, "expand_queries": False}),
        ("hybrid+rerank", {"mode": "hybrid", "rerank": True, "auto_filters": False, "expand_queries": False}),
        ("hybrid+rerank+filters", {"mode": "hybrid", "rerank": True, "auto_filters": True, "expand_queries": True}),
    ]
    mode_names = [name for name, _ in mode_specs]
    averages: dict[str, dict[str, float]] = {mode: {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0, "ndcg@10": 0.0} for mode in mode_names}
    results_by_mode: dict[str, list[dict[str, float | str]]] = {mode: [] for mode in mode_names}

    for record in labeled:
        query = str(record.get("query", "")).strip()
        relevant = [str(item) for item in (record.get("relevant_chunk_ids") or [])]
        filters = _extracted_filters(query)
        mode_results = {}
        for mode_name, config in mode_specs:
            if mode_name == "hybrid+rerank+filters":
                ranked = [
                    str(result.get("chunk_id", ""))
                    for result in search(
                        query,
                        limit=10,
                        mode=config["mode"],
                        rerank=config["rerank"],
                        city=filters.get("city"),
                        country=filters.get("country"),
                        auto_filters=config["auto_filters"],
                        expand_queries=config["expand_queries"],
                    )
                ]
            else:
                ranked = [
                    str(result.get("chunk_id", ""))
                    for result in search(
                        query,
                        limit=10,
                        mode=config["mode"],
                        rerank=config["rerank"],
                        auto_filters=config["auto_filters"],
                        expand_queries=config["expand_queries"],
                    )
                ]
            mode_results[mode_name] = ranked
        for mode_name, ranked in mode_results.items():
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
    markdown_lines.extend([
        "",
        "Mode definitions:",
        "- vector: search(..., mode='vector', rerank=False, auto_filters=False, expand_queries=False)",
        "- bm25: search(..., mode='bm25', rerank=False, auto_filters=False, expand_queries=False)",
        "- hybrid: search(..., mode='hybrid', rerank=False, auto_filters=False, expand_queries=False)",
        "- hybrid+rerank: search(..., mode='hybrid', rerank=True, auto_filters=False, expand_queries=False)",
        "- hybrid+rerank+filters: search(..., mode='hybrid', rerank=True, auto_filters=True, expand_queries=True, city=..., country=..., season=None, topic=None)",
    ])
    (RESULTS_DIR / "retrieval.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    (RESULTS_DIR / "retrieval.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
