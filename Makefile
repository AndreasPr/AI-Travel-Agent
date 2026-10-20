.PHONY: up down logs seed migrate test lint fmt demo eval

up:
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

eval:
	@echo "Eval placeholder"
