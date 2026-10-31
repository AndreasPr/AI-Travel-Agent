.PHONY: up down logs seed migrate test lint fmt demo eval rag-candidates rag-eval reset-rag

export PYTHONPATH := .

up:
	docker compose pull db
	docker compose up --build -d --wait
	docker compose exec -T api alembic -c backend/alembic.ini upgrade head
	docker compose exec -T api python -m backend.scripts.seed_inventory

down:
	docker compose down -v

logs:
	docker compose logs -f

seed:
	docker compose exec -T api python -m backend.scripts.seed_inventory

migrate:
	docker compose exec -T api alembic -c backend/alembic.ini upgrade head

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff format .

demo:
	@echo "Demo placeholder"

rag-candidates:
	PYTHONPATH=. python eval/retrieval/make_candidates.py

rag-eval:
	PYTHONPATH=. python eval/retrieval/run_modes.py

rag-labels:
	PYTHONPATH=. python eval/retrieval/apply_labels.py

reset-rag:
	python -c "from backend.db.connect import engine; from sqlalchemy import text; conn = engine.connect(); conn.execute(text('TRUNCATE TABLE document_chunks RESTART IDENTITY CASCADE')); conn.execute(text('TRUNCATE TABLE documents RESTART IDENTITY CASCADE')); conn.close()"


eval:
	$(MAKE) rag-eval

.PHONY: rag-readme rag-diagnose
rag-readme:
	PYTHONPATH=. python -m eval.retrieval.readme

rag-diagnose:
	PYTHONPATH=. python -m eval.retrieval.diff_modes

.PHONY: test-llm
test-llm:
	pytest -q tests/test_llm.py tests/test_llm_integration.py
