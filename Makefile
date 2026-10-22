.PHONY: up down logs seed migrate test lint fmt demo eval rag-candidates rag-eval reset-rag

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
	python eval/retrieval/make_candidates.py

rag-eval:
	python eval/retrieval/run_modes.py

reset-rag:
	python - <<'PY'
	from backend.db.connect import engine
	with engine.begin() as conn:
	    conn.execute('TRUNCATE TABLE document_chunks RESTART IDENTITY CASCADE')
	    conn.execute('TRUNCATE TABLE documents RESTART IDENTITY CASCADE')
	PY


eval:
	$(MAKE) rag-eval
