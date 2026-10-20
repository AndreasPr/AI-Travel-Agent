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

## Repository hygiene

- Keep `.env` files local and ignored.
- Use placeholder values in `.env.example` files.
- Do not commit private data, API credentials, or infrastructure IPs.
- Preserve a clean git history with small, focused changes.

> ```bash
> jupyter notebook
> ```
