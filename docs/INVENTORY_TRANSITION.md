# Inventory transition

## Endpoint and table dependencies

| Endpoint | Consumer | Table/dependency | Result |
| --- | --- | --- | --- |
| GET /healthz | Docker health check, health test | none | retained |
| GET /readyz | readiness callers | database connection, SELECT 1 | retained |
| GET /rag/search | retrieval callers | documents, document_chunks, configured local retrieval models | retained |
| GET /airports | src/app/airports/dropdown.js, used by the homepage prediction form | airports through backend/db/utils.py | retained; seed loads offline airport reference data |
| GET /flights | src/app/flights/page.js | flight_prices through backend/db/utils.py | retained legacy response contract |
| GET /flights/{id} | src/app/flights/[id]/page.js | flight_prices through backend/db/utils.py | retained legacy response contract |
| POST /predict | src/app/flights/forms.js, rendered on src/app/page.js | MindsDB HTTP API, prediction model and recommendation query | removed |
| GET /hello-world | notebooks/Connect to FastAPI.ipynb; no current frontend reference found | none | removed |

`AirportSchema`, `FlightPriceSchema`, and `FlightPriceDetailSchema` remain for the existing frontend. `PredictSchema` and `get_mindsdb_session` were only used by the removed prediction endpoint. `backend/ai/` is removed.

`flights` and `hotels` hold the new synthetic inventory, loaded by `seed_inventory.py` and represented by `FlightSchema` and `HotelSchema`. The retained legacy endpoints do not expose those tables. `flight_prices` is retained but is no longer seeded. The `itineraries` table has flight_id/hotel_id fields, but no inventory consumer for them is implemented in the inspected API. The users, trips and messages tables are unaffected. RAG ingestion and retrieval continue to use documents and document_chunks.

## Expected frontend and notebook breakage

Frontend files are unchanged. The homepage prediction form will receive 404 on submit because `/predict` is gone; prediction/recommendation results will not work until the planned frontend replacement. Airport dropdowns continue working after seeding. Fresh databases have no legacy flight_prices records, so `/flights` returns an empty list and legacy detail links return 404. Existing flight_prices rows remain accessible if present. These pages do not yet display the new synthetic inventory.

The retained `notebooks/Connect to FastAPI.ipynb` still calls `/hello-world`; that cell will receive 404. It does not depend on MariaDB or MindsDB, so it was not moved. The archived notebooks and datasets are preserved, not executed by the default workflow.

## Local workflow

```bash
# Rebuild the backend, then migrate and generate/load synthetic inventory.
docker compose build api
docker compose up -d api
make migrate
make seed

# Optional standalone synthetic JSON export.
python -m backend.scripts.generate_inventory --output /tmp/synthetic-inventory.json

# Offline unit checks.
make lint
PYTHONPATH=. pytest -q

# Full migration chain and double-seed check in a temporary schema, rolled back.
PYTHONPATH=. pytest -q -m integration tests/test_inventory_integration.py
```

`make up` builds the services, runs migrations and seeds synthetic inventory. `make down` removes database volumes; running `make down && make up` also removes the RAG corpus and other stored application data. Do not use that command to preserve an existing corpus. No model or API key is needed for synthetic inventory generation or these inventory tests.

See `datasets/README.md` for synthetic formulas, natural keys and the unverified provenance of the legacy datasets.
