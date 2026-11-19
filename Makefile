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



.PHONY: rag-readme rag-diagnose
rag-readme:
	PYTHONPATH=. python -m eval.retrieval.readme

rag-diagnose:
	PYTHONPATH=. python -m eval.retrieval.diff_modes

.PHONY: test-llm
test-llm:
	pytest -q tests/unit/test_llm.py tests/integration/test_llm_integration.py

.PHONY: test-tools
test-tools:
	pytest -q tests/unit/test_agent_tools.py tests/integration/test_agent_tools_integration.py

.PHONY: test-agent
test-agent:
	pytest -q tests/unit/test_agent_loop.py tests/unit/test_agent_persistence.py

.PHONY: test-streaming
test-streaming:
	pytest -q tests/unit/test_agent_streaming.py

.PHONY: test-security security-report security-live
test-security:
	pytest -q tests/security

security-report:
	python tests/security/report.py

# Explicit operator action; configured local model and migrated Postgres required.
security-live:
	RECORD=0 LLM_REPLAY=0 python tests/security/report.py --live

.PHONY: eval-checks
eval-checks:
	@test -n "$(OUTPUTS)" || (echo 'Usage: make eval-checks OUTPUTS=/path/to/saved.jsonl'; exit 2)
	python -m eval.run_checks "$(OUTPUTS)"

.PHONY: eval eval-record eval-report eval-gate
EVAL_LIMIT ?= 49
EVAL_REPEATS ?= 1
EVAL_MODEL_INDEX ?= 0
EVAL_RUN_ID ?= manual
EVAL_ROUTE ?=
eval:
	python -m eval.run --recorded --limit $(EVAL_LIMIT) --repeats $(EVAL_REPEATS)

eval-record:
	python -m eval.run --live --run-id $(EVAL_RUN_ID) --limit $(EVAL_LIMIT) --repeats $(EVAL_REPEATS) --model-index $(EVAL_MODEL_INDEX) $(if $(EVAL_ROUTE),--route $(EVAL_ROUTE),)

eval-report:
	python -m eval.report --readme

eval-gate: eval
	python -m eval.gate

.PHONY: test-ci typecheck record test-contract test-containers test-e2e perf
# Coverage is enforced over backend code; no live providers in this target.
test-ci:
	python -m pytest -q --cov=backend --cov-report=term-missing --cov-report=xml

typecheck:
	mypy backend

record:
	RECORD=1 python -m backend.llm.record_fixtures

test-contract:
	python -m pytest -q tests/contract

test-containers:
	python -m pytest -q -m integration tests/integration/test_synthetic_container.py tests/integration/test_recorded_container.py

test-e2e:
	python -m pytest -q -m e2e tests/e2e

perf:
	python perf/run.py
