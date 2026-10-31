"""Observe filter/expansion effects without changing retrieval behavior."""
import json
from pathlib import Path

from sqlalchemy import select

from backend.db.connect import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.rag.search import _candidate_row, search
from eval.retrieval.modes import MODE_SPECS, mode_parameters
from eval.retrieval.run_modes import QUERIES_PATH, load_queries

ROOT = Path(__file__).resolve().parents[2]


def cause_guess(details: list[dict], metadata: dict, hard_filters: dict) -> str:
    if any(row["chunk_id"] not in metadata for row in details):
        return "Relevant chunk missing from the corpus; check label/corpus alignment."
    lost = [row for row in details if row["base_pool"] and not row["filtered_pool"]]
    if any(any(metadata[row["chunk_id"]].get(key) != value for key, value in hard_filters.items() if value is not None) for row in lost):
        return "Hard-filter mismatch likely excluded relevant candidates."
    if lost:
        return "Query expansion/fusion or the 30-candidate cutoff likely displaced relevant candidates."
    if any(row["base_rank"] != row["filtered_rank"] for row in details):
        return "Candidate composition or ordering changed; compare expansion/fusion and reranking."
    return "No observed difference for the labeled relevant chunks."


def diagnose(queries: list[dict], metadata: dict, search_fn=search) -> str:
    lines = ["# Filters diagnosis", "", "Observed candidate pools are the exact top-30 inputs to reranking. Final ranks cover all reranked candidates; absent means not returned. Cause guesses are hypotheses. The filtered mode also enables query expansion.", ""]
    specs = dict(MODE_SPECS)
    for record in queries:
        relevant = record.get("relevant_chunk_ids") or []
        if not relevant:
            continue
        traces, ranks = {}, {}
        for name in ("hybrid+rerank", "hybrid+rerank+filters"):
            trace = {}
            results = search_fn(record["query"], limit=30, trace=trace, **mode_parameters(record["query"], specs[name]))
            traces[name] = trace
            ranks[name] = {str(row["chunk_id"]): rank for rank, row in enumerate(results, 1)}
        base, filtered = traces.values()
        pools = [{str(row["chunk_id"]) for row in trace["candidate_pool"]} for trace in (base, filtered)]
        lines += [f"## {record['query']}", "", "Extracted filters: " + json.dumps(filtered["extracted_filters"], sort_keys=True),
                  "", "| relevant chunk | city | topic | season | hybrid+rerank pool | filtered pool | hybrid+rerank rank | filtered rank |",
                  "| --- | --- | --- | --- | --- | --- | ---: | ---: |"]
        details = []
        for chunk_id in relevant:
            row = metadata.get(chunk_id, {})
            detail = {"chunk_id": chunk_id, "base_pool": chunk_id in pools[0], "filtered_pool": chunk_id in pools[1],
                      "base_rank": ranks["hybrid+rerank"].get(chunk_id), "filtered_rank": ranks["hybrid+rerank+filters"].get(chunk_id)}
            details.append(detail)
            cells = [chunk_id, *[str(row.get(key, "unknown")) for key in ("city", "topic", "season")],
                     *["yes" if detail[key] else "no" for key in ("base_pool", "filtered_pool")],
                     *[str(detail[key]) if detail[key] is not None else "absent" for key in ("base_rank", "filtered_rank")]]
            lines.append("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
        lines += ["", "Cause guess: " + cause_guess(details, metadata, filtered["hard_filters"]), ""]
    return "\n".join(lines)


def main() -> None:
    queries = load_queries(QUERIES_PATH)
    relevant = {chunk_id for row in queries for chunk_id in row.get("relevant_chunk_ids", [])}
    with SessionLocal() as session:
        rows = session.execute(select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
                               .where(DocumentChunk.chunk_id.in_(relevant))).all()
    metadata = {row[0].chunk_id: _candidate_row(row) for row in rows}
    report = diagnose(queries, metadata)
    (ROOT / "eval/results/filters_diagnosis.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
