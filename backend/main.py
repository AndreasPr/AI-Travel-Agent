from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.db import schemas as db_schemas, utils as db_utils
from backend.db.connect import SessionLocal, get_db_session
from backend.env import config
from backend.agent.api import router as agent_router
from backend.rag.search import search as rag_search

FRONTEND_ORIGINS = config(
    "FRONTEND_ORIGINS",
    cast=lambda x: [s.strip() for s in x.split(",") if s.strip()],
    default="",
)


app = FastAPI(title="AI Travel Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or [
        "http://localhost:3100",
        "http://127.0.0.1:3100",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db_session: SessionLocal = Depends(get_db_session)):  # noqa: B008
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
    db_session: SessionLocal = Depends(get_db_session),  # noqa: B008
):
    return db_utils.get_airports(db_session, offset=offset, limit=limit)


@app.get("/flights", response_model=List[db_schemas.FlightPriceSchema])
def read_flights(
    offset: int = 0,
    limit: int = 100,
    db_session: SessionLocal = Depends(get_db_session),  # noqa: B008
):
    return db_utils.get_flight_prices(db_session, offset=offset, limit=limit)


@app.get("/flights/{flight_price}", response_model=db_schemas.FlightPriceDetailSchema)
def read_flight_price(
    flight_price: int, db_session: SessionLocal = Depends(get_db_session)  # noqa: B008
):
    df_flight_value = db_utils.get_flight_price(db_session, flight_price)
    if df_flight_value is None:
        raise HTTPException(status_code=404, detail="Flight Price not Found")

    return df_flight_value


app.include_router(agent_router)
