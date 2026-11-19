from typing import List
from backend.observability.telemetry import instrument_app

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.security.content import install_log_redaction
from backend.security.middleware import BodyLimitMiddleware
from backend.llm.config import load_config
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import schemas as db_schemas, utils as db_utils
from backend.db.connect import get_db_session
from backend.agent.api import router as agent_router
from backend.rag.search import search as rag_search

from contextlib import asynccontextmanager
from backend.auth.api import router as auth_router, install_auth_handlers
from backend.auth.service import settings as auth_settings


@asynccontextmanager
async def lifespan(app):
    from backend.testing.synthetic import enabled
    enabled()  # Reject unsafe test-provider configuration before serving.
    auth_settings()  # Fail before accepting requests when production credentials are unsafe.
    yield


install_log_redaction()
app = FastAPI(title="AI Travel Agent API", lifespan=lifespan)
install_auth_handlers(app)
app.add_middleware(BodyLimitMiddleware, max_bytes=load_config()['guardrails']['max_body_bytes'])


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Validation errors must not echo rejected PII or the original body.
    return JSONResponse({'detail': 'Invalid request fields or message size'}, status_code=422)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(auth_settings().origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Protection"],
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db_session: Session = Depends(get_db_session)):  # noqa: B008
    try:
        db_session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:  # pragma: no cover - only used in container readiness
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc


@app.get("/rag/search")
def rag_search_endpoint(query: str, limit: int = 5):
    results = rag_search(query, limit=limit)
    payload = []
    for result in results:
        payload.append(
            {
                "chunk_id": result.get("id"),
                "text": result.get("text"),
                "title": result.get("title"),
                "url": result.get("source_url"),
                "license": result.get("license") or "CC BY-SA 4.0",
                "attribution": result.get("attribution") or "Content from Wikivoyage is licensed under CC BY-SA 4.0.",
            }
        )
    return {"query": query, "results": payload}


@app.get("/airports", response_model=List[db_schemas.AirportSchema])
def read_airports(
    offset: int = 0,
    limit: int = 100,
    db_session: Session = Depends(get_db_session),  # noqa: B008
):
    return db_utils.get_airports(db_session, offset=offset, limit=limit)


@app.get("/flights", response_model=List[db_schemas.FlightPriceSchema])
def read_flights(
    offset: int = 0,
    limit: int = 100,
    db_session: Session = Depends(get_db_session),  # noqa: B008
):
    return db_utils.get_flight_prices(db_session, offset=offset, limit=limit)


@app.get("/flights/{flight_price}", response_model=db_schemas.FlightPriceDetailSchema)
def read_flight_price(
    flight_price: int, db_session: Session = Depends(get_db_session)  # noqa: B008
):
    df_flight_value = db_utils.get_flight_price(db_session, flight_price)
    if df_flight_value is None:
        raise HTTPException(status_code=404, detail="Flight Price not Found")

    return df_flight_value


app.include_router(auth_router)
app.include_router(agent_router)


# Instrument after routes are registered; /metrics contains no prompts or user IDs.
instrument_app(app)
