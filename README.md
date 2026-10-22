# AI Travel Agent

This repository is being rebuilt as a portfolio-grade AI travel application.

## Current focus

- A grounded, cited, budget-aware trip planner
- Free local-first infrastructure and tooling
- Local environment configuration via `.env.example` files
- No secrets, private infrastructure references, or cloud-hosted deployment details in tracked files

## Default stack

- Next.js App Router
- FastAPI backend
- PostgreSQL with pgvector
- Docker Compose for local service orchestration
- Python 3.12
- SQLAlchemy 2
- Pydantic v2
- pytest
- OpenTelemetry

## Notes

- The default stack intentionally excludes legacy cloud and database experiments.
- Earlier MariaDB + MindsDB notes are kept under the `legacy/` folder only as reference material.
- Sensitive values must live in ignored local `.env` files or in the developer's secret store, never in the repository.

## Local workflow

```bash
# install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm install

# backend
uvicorn backend.main:app --reload

# frontend
npm run dev

# tests
pytest
```

## Retrieval evaluation summary

The current retrieval evaluation uses 29 labeled queries (n=29). Labels were created from a pooled candidate set built by taking the top results from all 5 retrieval modes: vector, bm25, hybrid, hybrid+rerank, and hybrid+rerank+filters. The pooled candidates were then reviewed and assigned labels before scoring.

Across these 29 queries, the mode averages are:

- vector: recall@1 = 0.532 (n=29), recall@3 = 0.701 (n=29), recall@5 = 0.730 (n=29), recall@10 = 0.859 (n=29), MRR = 0.877 (n=29), nDCG@10 = 0.780 (n=29)
- bm25: recall@1 = 0.063 (n=29), recall@3 = 0.155 (n=29), recall@5 = 0.270 (n=29), recall@10 = 0.359 (n=29), MRR = 0.207 (n=29), nDCG@10 = 0.223 (n=29)
- hybrid: recall@1 = 0.264 (n=29), recall@3 = 0.506 (n=29), recall@5 = 0.647 (n=29), recall@10 = 0.862 (n=29), MRR = 0.562 (n=29), nDCG@10 = 0.601 (n=29)
- hybrid+rerank: recall@1 = 0.451 (n=29), recall@3 = 0.756 (n=29), recall@5 = 0.845 (n=29), recall@10 = 0.874 (n=29), MRR = 0.802 (n=29), nDCG@10 = 0.775 (n=29)
- hybrid+rerank+filters: recall@1 = 0.468 (n=29), recall@3 = 0.687 (n=29), recall@5 = 0.764 (n=29), recall@10 = 0.764 (n=29), MRR = 0.796 (n=29), nDCG@10 = 0.715 (n=29)

## Explain-back drill

### Hybrid retrieval failure mode

The hybrid stack combines vector similarity and BM25 signals before fusion. A real failure mode is a query that should match relevant travel content but becomes too restrictive because the BM25 path used AND semantics. For example, the buggy query for "affordable hostels in Amsterdam" effectively required all terms to match at once, so it looked like affordable & hostels & amsterdam instead of affordable | hostels | amsterdam. The result was a thin candidate set, poor BM25 recall, and a downstream hybrid ranking that never reached the relevant chunks. That is exactly the kind of failure that the OR-based tsquery fix prevents.

### Verifier failure mode

The verifier checks whether a cited chunk actually supports a claim, not just whether the claim is semantically nearby. A real failure mode is a support check that accepts a claim with a weak or mismatched match. For example, if a query says "Lisbon has no museums" but the source text says "Lisbon has many museums", an over-permissive verifier could still label the claim as supported because it ignores negation symmetry. The fix is to compare positive and negative claims symmetrically, keep number matches exact, and require enough matched content words before accepting support. This is the same principle that prevents false positives after retrieval failures like the BM25 AND bug.

## Repository hygiene

- Keep `.env` files local and ignored.
- Use placeholder values in `.env.example` files.
- Do not commit private data, API credentials, or infrastructure IPs.
- Preserve a clean git history with small, focused changes.

> ```bash
> jupyter notebook
> ```
