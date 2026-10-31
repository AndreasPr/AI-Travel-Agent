"""Generate deterministic synthetic-v1 inventory without network or model calls."""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import airportsdata
import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "synthetic-v1"


def read_config(name: str, config_dir: Path = ROOT / "config") -> dict:
    return yaml.safe_load((config_dir / name).read_text(encoding="utf-8"))


def great_circle_km(origin: dict, destination: dict) -> float:
    lat1, lat2 = map(math.radians, (origin["lat"], destination["lat"]))
    dlat = lat2 - lat1
    dlon = math.radians(destination["lon"] - origin["lon"])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def season_for(day: date, config: dict) -> tuple[str, float]:
    for season, spec in config["season_multipliers"].items():
        if day.month in spec["months"]:
            return season, float(spec["multiplier"])
    raise ValueError(f"No synthetic season configured for month {day.month}")


def generate_inventory(seed: int | None = None, config_dir: Path = ROOT / "config") -> dict[str, list[dict]]:
    config = read_config("inventory.yaml", config_dir)
    mapping = read_config("airports.yaml", config_dir)
    cities = sorted(read_config("cities.yaml", config_dir)["cities"], key=lambda city: city["name"])
    city_names = {city["name"] for city in cities}
    if city_names != set(mapping["cities"]) or city_names != set(config["cost_index"]):
        raise ValueError("City, airport and synthetic cost-index configurations must cover the same cities")
    if config["source"] != SOURCE or config["currency"] != "USD":
        raise ValueError("Expected synthetic-v1 inventory in USD")
    if not 8 <= config["hotels_per_city"] <= 12:
        raise ValueError("Synthetic hotels_per_city must be between 8 and 12")
    if config["horizon_days"] <= 0 or config["departure_interval_days"] <= 0:
        raise ValueError("Synthetic date horizon and departure interval must be positive")
    rng = random.Random(config["seed"] if seed is None else seed)
    airports = airportsdata.load("IATA")
    codes = sorted(set(mapping["origin_hubs"]) | set(mapping["cities"].values()))
    missing = set(codes) - airports.keys()
    if missing:
        raise ValueError(f"Unknown airport codes: {sorted(missing)}")
    start = date.fromisoformat(str(config["start_date"]))
    settings = config["flights"]
    flights = []
    for origin in mapping["origin_hubs"]:
        for city in cities:
            destination = mapping["cities"][city["name"]]
            distance = great_circle_km(airports[origin], airports[destination])
            for offset in range(0, config["horizon_days"], config["departure_interval_days"]):
                day = start + timedelta(days=offset)
                _, multiplier = season_for(day, config)
                nonstop = rng.random() < settings["nonstop_probability"]
                noise = rng.uniform(-settings["noise_fraction"], settings["noise_fraction"])
                fare = (settings["base_usd"] + distance * settings["per_km_usd"]) * multiplier * (1 + noise)
                fare += settings["nonstop_premium_usd"] if nonstop else 0
                minutes = round(distance / settings["cruise_kmh"] * 60 + settings["ground_minutes"])
                minutes += 0 if nonstop else settings["connection_minutes"]
                flights.append({
                    "flight_date": day, "starting_airport": origin, "destination_airport": destination,
                    "origin_city": airports[origin]["city"], "destination_city": city["name"],
                    "airline": settings["airlines"][offset // config["departure_interval_days"] % len(settings["airlines"])],
                    "duration_minutes": minutes, "is_nonstop": nonstop, "price": money(fare),
                    "currency": "USD", "source": SOURCE,
                })
    hotels = []
    adjectives = ["Amber", "Azure", "Coral", "Ivory"]
    nouns = ["Lantern", "Orchard", "Pebble"]
    combinations = [(adjective, noun) for adjective in adjectives for noun in nouns]
    tiers = list(config["hotel_tiers"])
    season, multiplier = season_for(start, config)
    for city in cities:
        names = rng.sample(combinations, config["hotels_per_city"])
        for index, (adjective, noun) in enumerate(names):
            tier = tiers[index % len(tiers)]
            price = config["cost_index"][city["name"]]["value"] * config["hotel_tiers"][tier]["base_usd"] * multiplier
            hotels.append({
                "name": f"Synthetic {adjective} {noun} Stay", "city": city["name"], "country": city["country"],
                "district": f"Synthetic District {index % 4 + 1}", "tier": tier,
                "price_per_night": money(price), "rating": round(rng.uniform(3.0, 4.9), 1), "season": season,
                "currency": "USD", "source": SOURCE,
            })
    return {"flights": flights, "hotels": hotels}


def canonical_json(inventory: dict) -> str:
    return json.dumps(inventory, sort_keys=True, separators=(",", ":"), default=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic-v1 inventory; no real prices or availability.")
    parser.add_argument("--output", type=Path, help="Optional JSON output; otherwise print synthetic row counts")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    rows = generate_inventory(seed=args.seed)
    if args.output:
        args.output.write_text(canonical_json(rows) + "\n", encoding="utf-8")
    print(json.dumps({"source": SOURCE, **{name: len(values) for name, values in rows.items()}}))


if __name__ == "__main__":
    main()
