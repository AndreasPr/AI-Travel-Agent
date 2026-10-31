"""Render measured results without filling in missing measurements."""
from eval.retrieval.modes import MODE_DEFINITIONS, MODE_SPECS

METRICS = ("recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10")


def render_report(summary: dict) -> str:
    count = summary.get("labeled_queries", "not run")
    average = summary.get("relevant_chunks_per_query")
    density = f"{average:.1f}" if average is not None else "not run"
    lines = [f"Evaluated on {count} labeled queries (about {density} relevant chunks per query)", "",
             "| mode | recall@1 | recall@3 | recall@5 | recall@10 | MRR (95% CI) | nDCG@10 (95% CI) |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, _ in MODE_SPECS:
        scores = summary.get("modes", {}).get(name, {})
        cells = []
        for metric in METRICS:
            value = scores.get(metric)
            cell = "not run" if value is None else f"{value:.2f}"
            if value is not None and metric in {"mrr", "ndcg@10"}:
                ci = scores.get("confidence_intervals", {}).get(metric)
                cell += f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci is not None else " [CI: not run]"
            cells.append(cell)
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "Mode definitions:", *[f"- {definition}" for definition in MODE_DEFINITIONS], "", "How to read this:",
              "- Labels were assigned by one person from a pool built from the top results of all modes available when labeling. Newly added modes require candidate regeneration and review; existing labels are preserved.",
              "- Differences under about 0.05 are within noise at this sample size; this is a rule of thumb, not a significance test.",
              "- Confidence intervals use a fixed seed and 1000 bootstrap resamples of labeled queries. Missing measurements are marked not run.",
              "- The bm25 row uses rank_bm25; historical Postgres full-text scores are shown under fts.",
              "- BM25 snapshots are cached per process. Restart search processes after ingestion to rebuild the index."]
    return "\n".join(lines) + "\n"
