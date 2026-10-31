"""Compatibility checks for endpoints retained during the frontend transition."""
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.db.connect import get_db_session
from backend.main import app


def test_removed_endpoints_and_retained_routes(monkeypatch):
    routes = {route.path for route in app.routes}
    assert {"/healthz", "/readyz", "/rag/search", "/airports", "/flights", "/flights/{flight_price}"} <= routes
    client = TestClient(app)
    assert client.get("/hello-world").status_code == 404
    assert client.post("/predict", json={}).status_code == 404
    assert not Path("backend/ai/predict.py").exists()
    assert not Path("backend/ai/connect.py").exists()
    monkeypatch.setattr("backend.main.rag_search", lambda query, limit: [{"id": "synthetic-chunk", "text": "Synthetic fixture text"}])
    assert client.get("/rag/search", params={"query": "synthetic"}).json()["results"][0]["text"] == "Synthetic fixture text"


def test_airport_and_legacy_flight_response_contracts(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_db_session] = lambda: object()
    monkeypatch.setattr("backend.main.db_utils.get_airports", lambda *a, **kw: [SimpleNamespace(name="Synthetic test airport", iata="TST")])
    row = {"id": 1, "flightDate": "2027-03-01", "startingAirport": "TST", "destinationAirport": "TST",
           "segmentsAirlineName": "Synthetic Demo Air", "totalFare": 100, "isBasicEconomy": False, "isRefundable": False, "isNonStop": True}
    monkeypatch.setattr("backend.main.db_utils.get_flight_prices", lambda *a, **kw: [row])
    monkeypatch.setattr("backend.main.db_utils.get_flight_price", lambda *a, **kw: row)
    try:
        assert client.get("/airports").json() == [{"label": "Synthetic test airport", "value": "TST"}]
        assert client.get("/flights").json()[0]["totalFare"] == 100
        assert client.get("/flights/1").json()["isNonStop"] is True
    finally:
        app.dependency_overrides.pop(get_db_session, None)
