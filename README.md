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

<!-- RETRIEVAL:START -->

Evaluated on 29 labeled queries (about 1.8 relevant chunks per query)

| mode | recall@1 | recall@3 | recall@5 | recall@10 | MRR (95% CI) | nDCG@10 (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| vector | 0.53 | 0.70 | 0.73 | 0.86 | 0.88 [0.76, 0.97] | 0.78 [0.68, 0.87] |
| vector+rerank | 0.45 | 0.73 | 0.83 | 0.84 | 0.80 [0.67, 0.91] | 0.76 [0.64, 0.86] |
| fts | 0.06 | 0.14 | 0.28 | 0.34 | 0.21 [0.11, 0.34] | 0.22 [0.13, 0.32] |
| bm25 | 0.21 | 0.40 | 0.43 | 0.47 | 0.42 [0.28, 0.58] | 0.40 [0.26, 0.54] |
| hybrid | 0.25 | 0.43 | 0.65 | 0.86 | 0.53 [0.40, 0.68] | 0.59 [0.48, 0.70] |
| hybrid(bm25) | 0.32 | 0.53 | 0.61 | 0.79 | 0.64 [0.49, 0.78] | 0.61 [0.49, 0.73] |
| hybrid+rerank | 0.45 | 0.76 | 0.84 | 0.87 | 0.80 [0.68, 0.92] | 0.77 [0.66, 0.88] |
| hybrid+rerank+filters | 0.47 | 0.69 | 0.76 | 0.76 | 0.80 [0.66, 0.91] | 0.72 [0.60, 0.83] |

Mode definitions:
- vector: vector similarity search.
- vector+rerank: vector search followed by the configured cross-encoder.
- fts: Postgres full-text search ranked with ts_rank_cd (formerly labeled bm25).
- bm25: rank_bm25 BM25Okapi over chunk texts; hard filters apply after scoring.
- hybrid: vector + fts via reciprocal rank fusion (RRF).
- hybrid(bm25): vector + rank_bm25 via RRF.
- hybrid+rerank: hybrid followed by the configured cross-encoder.
- hybrid+rerank+filters: hybrid + cross-encoder with automatic filters and query expansion enabled; city/country are hard constraints, inferred season/topic are soft preferences.
- All other modes disable automatic filters and query expansion. Reranking uses at most 30 candidates; evaluation scores the top 10.

How to read this:
- Labels were assigned by one person from a pool built from the top results of all modes available when labeling. Newly added modes require candidate regeneration and review; existing labels are preserved.
- Differences under about 0.05 are within noise at this sample size; this is a rule of thumb, not a significance test.
- Confidence intervals use a fixed seed and 1000 bootstrap resamples of labeled queries. Missing measurements are marked not run.
- The bm25 row uses rank_bm25; historical Postgres full-text scores are shown under fts.
- BM25 snapshots are cached per process. Restart search processes after ingestion to rebuild the index.

<!-- RETRIEVAL:END -->

Regenerate this section with `make rag-readme` after `make rag-eval`.

With the populated local database and cached embedding/cross-encoder models:

```bash
make rag-candidates
# Review new candidates.csv rows and assign relevance labels manually.
make rag-labels
make rag-eval
make rag-readme
make rag-diagnose
```

Run the ingestion idempotency test against the migrated local Postgres database:

```bash
DEBUG=false PYTHONPATH=. pytest -q -m integration tests/test_ingestion_integration.py::test_ingestion_idempotency_and_removed_chunk_deleted
```

This integration test uses synthetic pages and fake embeddings, checks repeated ingestion and deletion of a removed chunk, and rolls back its database changes. It does not fetch pages or download models.

## Repository hygiene

- Keep `.env` files local and ignored.
- Use placeholder values in `.env.example` files.
- Do not commit private data, API credentials, or infrastructure IPs.
- Preserve a clean git history with small, focused changes.

> ```bash
> jupyter notebook
> ```

## Synthetic inventory

The default seed now generates explicitly labeled `synthetic-v1` flights and hotels for `config/cities.yaml`, without network or model calls. Legacy CSVs are archived and are not loaded. See [inventory formulas and provenance](datasets/README.md) and [endpoint compatibility and local commands](docs/INVENTORY_TRANSITION.md). The existing homepage prediction form no longer works because `/predict` was removed; the frontend will be replaced separately.

## Agent tools

`backend/tools/` provides typed, bounded ToolResults for destination retrieval, weather, currency conversion, OSM geocoding, synthetic flight/hotel queries and deterministic itinerary validation. Run `make test-tools` for offline tests. See [contracts, provenance rules and local setup](docs/AGENT_TOOLS.md).
