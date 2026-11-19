"""Tests of explicitly synthetic inventory; no network or model calls."""
import hashlib
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

import airportsdata
import pytest
from sqlalchemy import Integer, MetaData, create_engine, func, select

from backend.db.models import Airport, Flight, Hotel
from backend.db.schemas import FlightSchema, HotelSchema
from backend.scripts.generate_inventory import canonical_json, generate_inventory, great_circle_km, read_config
from backend.scripts.seed_inventory import seed_inventory


@pytest.fixture(scope="module")
def inventory():
    return generate_inventory()


def test_generator_is_deterministic(inventory):
    def digest(rows):
        return hashlib.sha256(canonical_json(rows).encode()).hexdigest()
    assert digest(inventory) == digest(generate_inventory())
    seed = read_config("inventory.yaml")["seed"]
    assert digest(generate_inventory(seed)) == digest(generate_inventory(seed))
    assert digest(inventory) != digest(generate_inventory(seed + 1))


def test_all_airport_codes_exist_in_airportsdata():
    mapping = read_config("airports.yaml")
    airports = airportsdata.load("IATA")
    assert mapping["origin_hubs"] == ["JFK", "ORD", "ATL", "LAX", "MIA", "BOS", "SFO", "DFW"]
    assert set(mapping["cities"]) == {city["name"] for city in read_config("cities.yaml")["cities"]}
    for code in set(mapping["origin_hubs"]) | set(mapping["cities"].values()):
        assert code in airports
        record = airports[code]
        assert record["iata"] == code
        assert record["name"].strip() and record["city"].strip()
        assert -90 <= record["lat"] <= 90 and -180 <= record["lon"] <= 180
        assert (record["lat"], record["lon"]) != (0, 0)


def test_every_city_has_hotels_and_flights(inventory):
    cities = {city["name"] for city in read_config("cities.yaml")["cities"]}
    counts = Counter(row["city"] for row in inventory["hotels"])
    assert set(counts) == cities
    assert all(8 <= count <= 12 for count in counts.values())
    assert len(inventory["flights"]) >= 5000 and len(inventory["hotels"]) >= 250
    routes = defaultdict(set)
    for row in inventory["flights"]:
        routes[row["starting_airport"], row["destination_city"]].add(row["flight_date"])
    expected_dates = {date(2027, 3, 1) + timedelta(days=offset) for offset in range(0, 120, 3)}
    for hub in read_config("airports.yaml")["origin_hubs"]:
        for city in cities:
            assert routes[hub, city] == expected_dates
            assert len(routes[hub, city]) >= 30


def test_prices_positive_and_in_sane_range(inventory):
    # Synthetic demo bounds, not observed market ranges.
    for row in inventory["flights"]:
        assert Decimal("100") <= row["price"] <= Decimal("2000")
        assert 180 <= row["duration_minutes"] <= 1440
    for row in inventory["hotels"]:
        assert Decimal("20") <= row["price_per_night"] <= Decimal("500")
        assert 3.0 <= row["rating"] <= 4.9
        assert row["tier"] in {"budget", "mid", "upscale"}
        assert row["district"].startswith("Synthetic ")
    for rows in inventory.values():
        assert all(row["source"] == "synthetic-v1" and row["currency"] == "USD" for row in rows)


def average_ranks(values):
    groups = defaultdict(list)
    for index, value in enumerate(values):
        groups[value].append(index)
    ranks = [0.0] * len(values)
    offset = 0
    for value in sorted(groups):
        indices = groups[value]
        rank = offset + (len(indices) + 1) / 2
        for index in indices:
            ranks[index] = rank
        offset += len(indices)
    return ranks


def spearman(left, right):
    x, y = average_ranks(left), average_ranks(right)
    x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
    covariance = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
    variance = sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y)
    return covariance / variance ** 0.5


def test_price_correlates_with_distance(inventory):
    airports = airportsdata.load("IATA")
    distances = [great_circle_km(airports[row["starting_airport"]], airports[row["destination_airport"]]) for row in inventory["flights"]]
    prices = [float(row["price"]) for row in inventory["flights"]]
    assert spearman(distances, prices) > 0.5


def test_seed_is_idempotent(inventory):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (Airport, Flight, Hotel):
        table = model.__table__.to_metadata(metadata)
        # SQLite autoincrement requires INTEGER, unlike Postgres BIGINT.
        if model is Airport:
            table.c.index.type = Integer()
    metadata.create_all(engine)
    with engine.begin() as connection:
        seed_inventory(connection, inventory)
        first = {model.__tablename__: connection.scalar(select(func.count()).select_from(model)) for model in (Flight, Hotel, Airport)}
        ids = connection.execute(select(Flight.id).order_by(Flight.id)).scalars().all()
        seed_inventory(connection, inventory)
        second = {model.__tablename__: connection.scalar(select(func.count()).select_from(model)) for model in (Flight, Hotel, Airport)}
        assert first == second == {"flights": 8000, "hotels": 250, "airports": 33}
        assert ids == connection.execute(select(Flight.id).order_by(Flight.id)).scalars().all()
        changed = {"flights": [dict(inventory["flights"][0], price=Decimal("321.00"))], "hotels": []}
        seed_inventory(connection, changed)
        assert connection.scalar(select(func.count()).select_from(Flight)) == 8000
        assert connection.scalar(select(Flight.price).order_by(Flight.id).limit(1)) == Decimal("321.00")


def test_no_real_brand_names(inventory):
    denylist = ["Hilton", "Marriott", "Hyatt", "Ryanair", "Delta", "United", "Lufthansa", "easyJet", "TAP"]
    names = [row["airline"] for row in inventory["flights"]] + [row["name"] for row in inventory["hotels"]]
    assert all(name.startswith("Synthetic ") for name in names)
    assert all(brand.lower() not in name.lower() for name in names for brand in denylist)


def test_inventory_schemas_preserve_synthetic_source(inventory):
    flight = FlightSchema.model_validate({"id": 1, **inventory["flights"][0]})
    hotel = HotelSchema.model_validate({"id": 1, **inventory["hotels"][0]})
    assert flight.source == hotel.source == "synthetic-v1"
    assert flight.price > 0 and hotel.price_per_night > 0
