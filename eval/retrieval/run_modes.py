from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag.retrieval.hybrid import RuleBasedQueryRewriter  # noqa: E402
from backend.rag.search import search  # noqa: E402
from eval.retrieval.metrics import evaluate_query  # noqa: E402
from eval.retrieval.modes import MODE_SPECS, mode_parameters
from eval.retrieval.report import render_report

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


def bootstrap_ci(values: list[float], seed: int = 42, resamples: int = 1000) -> list[float] | None:
    """Percentile interval for the query mean, using linear quantile interpolation."""
    if not values:
        return None
    if resamples < 2:
        raise ValueError("At least two resamples are required")
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(resamples))

    def quantile(probability: float) -> float:
        index = (len(means) - 1) * probability
        lower = int(index)
        upper = min(lower + 1, len(means) - 1)
        return means[lower] + (means[upper] - means[lower]) * (index - lower)

    return [quantile(0.025), quantile(0.975)]


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

    mode_specs = MODE_SPECS
    mode_names = [name for name, _ in mode_specs]
    averages: dict[str, dict[str, float]] = {mode: {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0, "ndcg@10": 0.0} for mode in mode_names}
    results_by_mode: dict[str, list[dict[str, float | str]]] = {mode: [] for mode in mode_names}

    for record in labeled:
        query = str(record.get("query", "")).strip()
        relevant = [str(item) for item in (record.get("relevant_chunk_ids") or [])]
        mode_results = {}
        for mode_name, config in mode_specs:
            mode_results[mode_name] = [
                str(result.get("chunk_id", ""))
                for result in search(query, limit=10, **mode_parameters(query, config))
            ]
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
    for mode_name in mode_names:
        averages[mode_name]["confidence_intervals"] = {
            metric: bootstrap_ci([row[metric] for row in results_by_mode[mode_name]])
            for metric in ("mrr", "ndcg@10")
        }
    summary["relevant_chunks_per_query"] = sum(len(set(row["relevant_chunk_ids"])) for row in labeled) / len(labeled)
    summary["per_query"] = results_by_mode
    summary["bootstrap"] = {"seed": 42, "resamples": 1000, "confidence": 0.95}
    (RESULTS_DIR / "retrieval.md").write_text("# Retrieval evaluation\n\n" + render_report(summary), encoding="utf-8")
    (RESULTS_DIR / "retrieval.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
