"""Agent tool contracts exercised with synthetic fixtures and respx; no live HTTP."""
import copy
import json
import socket
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import Flight, Hotel
from backend.tools.models import Itinerary, ToolResult
from backend.tools.registry import REGISTRY, tool_schemas
from backend.tools.runtime import DiskRateLimiter, Policy, ToolRuntime


class MemoryStore:
    def __init__(self):
        self.cache, self.results = {}, {}
        self.lock = threading.Lock()

    def get_cache(self, key):
        with self.lock:
            value = self.cache.get(key)
            return copy.deepcopy(value[0]) if value and value[1] > time.monotonic() else None

    def put_cache(self, key, tool, payload, ttl):
        with self.lock:
            self.cache[key] = (copy.deepcopy(payload), time.monotonic() + ttl)

    def save_result(self, result):
        with self.lock:
            self.results[result.tool_result_id] = result.model_dump(mode="json")

    def get_result(self, result_id):
        return copy.deepcopy(self.results.get(result_id))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Live network is forbidden in unit tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.delenv("NOMINATIM_URL", raising=False)


@pytest.fixture
def runtime(tmp_path):
    instance = ToolRuntime(store=MemoryStore(), client=httpx.Client(trust_env=False), today=lambda: date(2027, 3, 1), limiter=DiskRateLimiter(tmp_path / "rate"))
    yield instance
    instance.close()


def weather_payload(day):
    return {"latitude": 1, "longitude": 2, "daily": {"time": [day], "temperature_2m_max": [20], "temperature_2m_min": [10], "precipitation_sum": [0]}}


def test_weather_forecast_vs_historical_labeling(runtime, respx_mock):
    forecast = respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json=weather_payload("2027-03-03")))
    result = runtime.execute("get_weather", {"lat": 1, "lon": 2, "start_date": "2027-03-03", "end_date": "2027-03-03"})
    assert result.status == "ok" and result.data.days[0].label == "forecast"
    assert forecast.called and "latitude" not in result.data.model_dump()
    archive = respx_mock.get("https://archive-api.open-meteo.com/v1/archive").mock(return_value=httpx.Response(200, json=weather_payload("2026-04-10")))
    result = runtime.execute("get_weather", {"lat": 1, "lon": 2, "start_date": "2027-04-10", "end_date": "2027-04-10"})
    assert result.status == "ok" and result.data.days[0].label == "typical, based on 2026"
    assert result.data.days[0].date.isoformat() == "2027-04-10"
    assert archive.calls[0].request.url.params["start_date"] == "2026-04-10"


def test_currency_conversion_and_cache_hit(runtime, respx_mock):
    route = respx_mock.get("https://api.frankfurter.dev/v2/rates").mock(return_value=httpx.Response(200, json=[{"date": "2027-02-26", "base": "USD", "quote": "EUR", "rate": 0.9}]))
    args = {"amount": "100", "from": "USD", "to": "EUR", "date": "2027-02-28"}
    first = runtime.execute("convert_currency", args)
    second = runtime.execute("convert_currency", args)
    assert first.status == second.status == "ok"
    assert first.data.converted_amount == Decimal("90.00") and second.data.rate_date == date(2027, 2, 26)
    assert not first.cache_hit and second.cache_hit and route.call_count == 1
    assert first.tool_result_id != second.tool_result_id and first.fetched_at == second.fetched_at
    assert runtime.store.get_result(second.tool_result_id)["data"]["converted_amount"] == "90.00"


def test_geocode_respects_rate_limit_and_cache(runtime, respx_mock, monkeypatch, tmp_path):
    monkeypatch.setenv("NOMINATIM_USER_AGENT", "Synthetic Tool Test/contact-placeholder")
    now, sleeps = [100.0], []
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    runtime.limiter = DiskRateLimiter(tmp_path / "shared", clock=lambda: now[0], sleep=sleep)
    route = respx_mock.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[{"lat": "1.1", "lon": "2.2", "display_name": "Synthetic Place", "osm_id": 1, "osm_type": "node"}]))
    first = runtime.execute("geocode_place", {"name": "Synthetic A", "city": "Synthetic City"})
    second = runtime.execute("geocode_place", {"name": "Synthetic A", "city": "Synthetic City"})
    # A fresh limiter instance shares the persisted timestamp.
    runtime.limiter = DiskRateLimiter(tmp_path / "shared", clock=lambda: now[0], sleep=sleep)
    third = runtime.execute("geocode_place", {"name": "Synthetic B", "city": "Synthetic City"})
    assert first.status == third.status == "ok" and second.cache_hit
    assert route.call_count == 2 and sum(sleeps) >= 1
    assert "OpenStreetMap" in first.data.attribution
    assert route.calls[0].request.headers["User-Agent"] == "Synthetic Tool Test/contact-placeholder"


@pytest.fixture
def inventory_runtime(runtime):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Flight.__table__.create(engine)
    Hotel.__table__.create(engine)
    runtime.session_factory = sessionmaker(engine)
    with engine.begin() as conn:
        conn.execute(Flight.__table__.insert(), [{"flight_date": date(2027, 4, 10), "starting_airport": "JFK", "destination_airport": "LIS", "origin_city": "Synthetic Origin", "destination_city": "Lisbon", "airline": "Synthetic Demo Air", "price": 100, "source": "synthetic-v1", "currency": "USD"}])
        conn.execute(Hotel.__table__.insert(), [
            {"name": "Synthetic Budget", "city": "Lisbon", "country": "Portugal", "price_per_night": 80, "tier": "budget", "rating": 4.5, "source": "synthetic-v1", "currency": "USD"},
            {"name": "Synthetic Mid", "city": "Lisbon", "country": "Portugal", "price_per_night": 100, "tier": "mid", "rating": 3.5, "source": "synthetic-v1", "currency": "USD"},
            {"name": "Synthetic Legacy Fixture", "city": "Lisbon", "country": "Portugal", "price_per_night": 20, "tier": "budget", "rating": 4.9, "source": None, "currency": "USD"}])
    yield runtime
    engine.dispose()


def test_flights_no_data_when_no_match(inventory_runtime):
    args = {"origin": "JFK", "destination_city": "Lisbon", "depart_date": "2027-04-11"}
    assert inventory_runtime.execute("search_flights", args).status == "no_data"
    args["depart_date"] = "2027-04-10"
    result = inventory_runtime.execute("search_flights", args)
    assert result.status == "ok" and result.data.outbound[0].source == "synthetic-v1"
    args["return_date"] = "2027-04-15"
    assert inventory_runtime.execute("search_flights", args).status == "no_data"


def test_hotels_filters_price_rating_tier(inventory_runtime):
    args = {"city": "Lisbon", "check_in": "2027-04-10", "check_out": "2027-04-15", "max_price_per_night": 90, "min_rating": 4, "tier": "budget"}
    result = inventory_runtime.execute("search_hotels", args)
    assert result.status == "ok" and len(result.data.hotels) == 1
    assert result.data.hotels[0].name == "Synthetic Budget" and result.data.hotels[0].total_price == 400
    assert result.data.hotels[0].nights == 5
    assert inventory_runtime.execute("search_hotels", {**args, "tier": "mid"}).status == "no_data"
    assert inventory_runtime.execute("search_hotels", {**args, "min_rating": 4.8}).status == "no_data"
    assert inventory_runtime.execute("search_hotels", {**args, "max_price_per_night": 70}).status == "no_data"


def test_search_destinations_has_no_embedding_and_caps_excerpt(runtime):
    calls = []
    def search(*args, **kwargs):
        calls.append(kwargs)
        return [{"chunk_id": "synthetic-chunk", "text": "x" * 1000, "embedding": [1, 2], "title": "Synthetic title", "source_url": "https://example.invalid/synthetic", "license": "Synthetic fixture", "attribution": "Synthetic fixture"}]
    runtime.search = search
    result = runtime.execute("search_destinations", {"query": "synthetic query", "city": "Lisbon"})
    assert result.status == "ok" and len(result.data.chunks[0].excerpt) == 600
    assert "embedding" not in result.model_dump_json()
    assert calls[0]["rerank"] is True and "mode" not in calls[0]


def test_tool_timeout_returns_error_result(runtime):
    def slow(request, context):
        time.sleep(0.08)
        return {"chunks": []}
    runtime.definitions = {"search_destinations": replace(REGISTRY["search_destinations"], handler=slow, policy=Policy(timeout_seconds=0.01))}
    result = runtime.execute("search_destinations", {"query": "synthetic"})
    assert result.status == "error" and result.data.error.code == "timeout"
    time.sleep(0.1)
    assert not runtime.store.results


def test_tool_output_size_limit(runtime):
    runtime.search = lambda *a, **kw: [{"chunk_id": "synthetic", "text": "x" * 600}]
    runtime.definitions = {"search_destinations": replace(REGISTRY["search_destinations"], policy=Policy(max_output_bytes=512))}
    result = runtime.execute("search_destinations", {"query": "synthetic"})
    assert result.status == "error" and result.data.error.code == "output_too_large"
    assert len(result.model_dump_json().encode()) <= 512


def test_schema_snapshots():
    root = Path(__file__).parent / "snapshots/tools"
    schemas = {schema["name"]: schema for schema in tool_schemas()}
    schemas["itinerary"] = Itinerary.model_json_schema()
    assert {p.stem for p in root.glob("*.json")} == set(schemas)
    for name, schema in schemas.items():
        assert json.loads((root / f"{name}.json").read_text()) == schema


def save_evidence(runtime, result_id, tool, data):
    runtime.store.save_result(ToolResult(tool_result_id=result_id, tool=tool, status="ok", data=data, source="synthetic-test", fetched_at=datetime.now(timezone.utc), cache_hit=False))


def sample_itinerary():
    return {"trip": {"start_date": "2027-04-10", "end_date": "2027-04-15", "currency": "USD"}, "days": [
        {"date": "2027-04-10", "items": [
            {"id": "a", "start": "2027-04-10T09:00:00", "end": "2027-04-10T10:00:00", "place": "Synthetic Place", "category": "visit", "cost": "100", "currency": "USD", "tool_result_ids": ["synthetic-price"]}]}]}


def validation(runtime, itinerary=None, budget=500):
    save_evidence(runtime, "synthetic-price", "search_flights", {"outbound": [{"price": "100", "currency": "USD"}], "inbound": []})
    result = runtime.execute("validate_itinerary", {"itinerary": itinerary or sample_itinerary(), "budget": budget})
    assert result.status == "ok", result.model_dump_json()
    return result.data


def names(result):
    return {issue.name for issue in result.issues}


def test_validator_budget_exceeded(runtime):
    result = validation(runtime, budget=99)
    assert "budget_exceeded" in names(result) and not result.valid


def test_validator_overlap(runtime):
    itinerary = sample_itinerary()
    item = copy.deepcopy(itinerary["days"][0]["items"][0])
    item.update(id="b", start="2027-04-10T09:30:00", end="2027-04-10T11:00:00")
    itinerary["days"][0]["items"].append(item)
    assert "overlap" in names(validation(runtime, itinerary))


def test_validator_price_must_match_tool_result(runtime):
    itinerary = sample_itinerary()
    itinerary["days"][0]["items"][0]["cost"] = "101"
    assert "price_must_match_tool_result" in names(validation(runtime, itinerary))
    itinerary["days"][0]["items"][0]["cost"] = "100.01"
    assert "price_must_match_tool_result" not in names(validation(runtime, itinerary))


def test_validator_missing_tool_result_id(runtime):
    itinerary = sample_itinerary()
    itinerary["days"][0]["items"][0]["tool_result_ids"] = []
    assert "missing_tool_result_id" in names(validation(runtime, itinerary))
    itinerary["days"][0]["items"][0]["tool_result_ids"] = ["invented-id"]
    assert "missing_tool_result_id" in names(validation(runtime, itinerary))


def test_validator_day_outside_trip_dates(runtime):
    itinerary = sample_itinerary()
    itinerary["days"][0]["date"] = "2027-04-09"
    assert "day_outside_trip_dates" in names(validation(runtime, itinerary))


def test_validator_travel_time_implausible(runtime):
    itinerary = sample_itinerary()
    first = itinerary["days"][0]["items"][0]
    second = copy.deepcopy(first)
    first.update(coords={"lat": 0, "lon": 0}, coord_tool_result_id="synthetic-geo-a")
    second.update(id="b", start="2027-04-10T10:01:00", end="2027-04-10T11:00:00", coords={"lat": 0, "lon": 1}, coord_tool_result_id="synthetic-geo-b")
    itinerary["days"][0]["items"].append(second)
    save_evidence(runtime, "synthetic-geo-a", "geocode_place", {"lat": 0, "lon": 0})
    save_evidence(runtime, "synthetic-geo-b", "geocode_place", {"lat": 0, "lon": 1})
    assert "travel_time_implausible" in names(validation(runtime, itinerary))


def test_validator_skips_travel_check_without_coords(runtime):
    itinerary = sample_itinerary()
    second = copy.deepcopy(itinerary["days"][0]["items"][0])
    second.update(id="b", start="2027-04-10T11:00:00", end="2027-04-10T12:00:00")
    itinerary["days"][0]["items"].append(second)
    result = validation(runtime, itinerary)
    assert result.valid and "travel_check_skipped_without_coords" in names(result)
    assert "travel_time_implausible" not in names(result)


def test_validator_schema_window_currency_and_coordinate_provenance(runtime):
    result = runtime.execute("validate_itinerary", {"itinerary": {"trip": {}}, "budget": 100})
    assert "schema_valid" in names(result.data) and not result.data.valid
    itinerary = sample_itinerary()
    item = itinerary["days"][0]["items"][0]
    item.update(start="2027-04-10T07:00:00", coords={"lat": 1, "lon": 2}, coord_tool_result_id="synthetic-price", currency="EUR")
    result = validation(runtime, itinerary)
    assert {"outside_visiting_window", "coordinates_must_match_geocode_result", "currency_mismatch"} <= names(result)
    assert result.total_cost is None
    item["allow_outside_visiting_window"] = True
    assert "outside_visiting_window" not in names(validation(runtime, itinerary))


def test_converter_cannot_manufacture_price_evidence(runtime):
    itinerary = sample_itinerary()
    itinerary["days"][0]["items"][0]["tool_result_ids"] = ["synthetic-conversion"]
    save_evidence(runtime, "synthetic-conversion", "convert_currency", {"converted_amount": "100", "to_currency": "USD"})
    assert "price_must_match_tool_result" in names(validation(runtime, itinerary))


def test_http_retry_policy_and_cache_expiry(runtime, respx_mock):
    route = respx_mock.get("https://api.frankfurter.dev/v2/rates").mock(side_effect=[httpx.Response(503), httpx.Response(200, json=[{"date": "2027-03-01", "base": "USD", "quote": "EUR", "rate": 1}])])
    args = {"amount": "1", "from": "USD", "to": "EUR"}
    assert runtime.execute("convert_currency", args).status == "ok" and route.call_count == 2
    for key, value in runtime.store.cache.items():
        runtime.store.cache[key] = (value[0], time.monotonic() - 1)
    route.mock(return_value=httpx.Response(400))
    result = runtime.execute("convert_currency", args)
    assert result.status == "error" and not result.data.error.retryable
    assert route.call_count == 3


def test_geocode_no_data_and_missing_user_agent(runtime, respx_mock, monkeypatch):
    monkeypatch.delenv("NOMINATIM_USER_AGENT", raising=False)
    args = {"name": "Synthetic Missing", "city": "Synthetic City"}
    assert runtime.execute("geocode_place", args).data.error.code == "configuration"
    monkeypatch.setenv("NOMINATIM_USER_AGENT", "Synthetic test application")
    route = respx_mock.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[]))
    assert runtime.execute("geocode_place", args).status == "no_data"
    assert runtime.execute("geocode_place", args).cache_hit and route.call_count == 1


def test_weather_city_lookup_and_missing_future_baseline(runtime, respx_mock):
    geo = respx_mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(return_value=httpx.Response(200, json={"results": [{"latitude": 1, "longitude": 2}]}))
    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json=weather_payload("2027-03-02")))
    result = runtime.execute("get_weather", {"city": "Synthetic City", "start_date": "2027-03-02", "end_date": "2027-03-02"})
    assert result.status == "ok" and geo.called
    assert set(result.data.model_dump()) == {"days", "attribution", "note"}
    assert runtime.execute("get_weather", {"city": "Synthetic City", "start_date": "2029-03-02", "end_date": "2029-03-02"}).status == "no_data"


def test_cli_uses_the_tool_contract(inventory_runtime, monkeypatch, capsys):
    from backend.tools import cli
    monkeypatch.setattr(cli, "ToolRuntime", lambda: inventory_runtime)
    monkeypatch.setattr("sys.argv", ["cli", "search_hotels", "--city", "Lisbon", "--check_in", "2027-04-10", "--check_out", "2027-04-15", "--max_price_per_night", "90"])
    cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok" and payload["source"] == "synthetic-v1"
    assert payload["data"]["hotels"][0]["price_per_night"] == "80.00"
