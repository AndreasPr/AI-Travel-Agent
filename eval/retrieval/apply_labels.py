import csv
import json
from pathlib import Path

base = Path(__file__).parent
YES = {"1", "y", "yes", "x"}

with open(base / "candidates.csv", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

labels: dict[str, list[str]] = {}
for r in rows:
    labels.setdefault(r["query"], [])
    if r["relevant"].strip().lower() in YES:
        labels[r["query"]].append(r["chunk_id"])

path = base / "queries.jsonl"
out, labeled = [], 0
for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    rec = json.loads(line)
    ids = labels.get(rec["query"], [])
    if ids:
        rec["relevant_chunk_ids"] = ids
        labeled += 1
    out.append(json.dumps(rec, ensure_ascii=False))
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"labeled queries: {labeled} / {len(out)}")