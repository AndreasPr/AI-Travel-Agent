from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://travel:travelpass@db:5432/travel")
ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "datasets"


def ensure_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def normalize_flight_row(row: dict[str, str]) -> dict[str, object]:
    flight_date_raw = (row.get("flightDate") or row.get("flight_date") or "2024-01-01").strip()
    try:
        flight_date = date.fromisoformat(flight_date_raw)
    except ValueError:
        flight_date = date.fromisoformat("2024-01-01")

    start = (row.get("startingAirport") or row.get("starting_airport") or "BOS").strip()
    dest = (row.get("destinationAirport") or row.get("destination_airport") or "SFO").strip()
    airline = (row.get("segmentsAirlineName") or row.get("airline") or "Synthetic Air").strip()
    price_raw = (row.get("totalFare") or row.get("price") or "0").strip()
    try:
        price = Decimal(str(price_raw))
    except Exception:
        price = Decimal("0")

    return {
        "flight_date": flight_date,
        "starting_airport": start,
        "destination_airport": dest,
        "airline": airline,
        "price": price,
    }


def load_flights(engine) -> int:
    flight_files = [
        DATASET_DIR / "sql-dump.csv",
        DATASET_DIR / "gretel" / "tabular-actgan-67db43cc641d963488489eda-data_preview.csv",
        DATASET_DIR / "gretel" / "tabular-actgan-67db47547c54e7516f73d9be-data.csv",
        DATASET_DIR / "itineraries-min-50k.csv",
        DATASET_DIR / "itineraries-min-100k.csv",
        DATASET_DIR / "itineraries-min-250k.csv",
    ]

    rows_loaded = 0
    seen = set()

    for csv_path in sorted({path for path in flight_files if path.exists()}):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                normalized = normalize_flight_row(row)
                key = tuple(normalized[k] for k in ("flight_date", "starting_airport", "destination_airport", "airline", "price"))
                if key in seen:
                    continue
                seen.add(key)

                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO flights (flight_date, starting_airport, destination_airport, airline, price)
                            SELECT CAST(:flight_date AS DATE), CAST(:starting_airport AS VARCHAR), CAST(:destination_airport AS VARCHAR), CAST(:airline AS VARCHAR), CAST(:price AS NUMERIC)
                            WHERE NOT EXISTS (
                                SELECT 1 FROM flights
                                WHERE flight_date = CAST(:flight_date AS DATE)
                                  AND starting_airport = CAST(:starting_airport AS VARCHAR)
                                  AND destination_airport = CAST(:destination_airport AS VARCHAR)
                                  AND airline = CAST(:airline AS VARCHAR)
                                  AND price = CAST(:price AS NUMERIC)
                            )
                            """
                        ),
                        normalized,
                    )
                rows_loaded += 1
    return rows_loaded


def load_hotels(engine) -> int:
    hotel_path = DATASET_DIR / "housing_ds.csv"
    if not hotel_path.exists():
        return 0

    rows_loaded = 0
    with hotel_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = f"Synthetic stay {row.get('type', 'hotel').strip() or 'hotel'}"
            city = "Boston"
            country = "USA"
            price = 120.0
            season = "spring"
            rating = 4.5

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO hotels (name, city, country, price_per_night, rating, season)
                        SELECT CAST(:name AS VARCHAR), CAST(:city AS VARCHAR), CAST(:country AS VARCHAR), CAST(:price_per_night AS NUMERIC), CAST(:rating AS FLOAT), CAST(:season AS VARCHAR)
                        WHERE NOT EXISTS (
                            SELECT 1 FROM hotels
                            WHERE name = CAST(:name AS VARCHAR)
                              AND city = CAST(:city AS VARCHAR)
                              AND country = CAST(:country AS VARCHAR)
                        )
                        """
                    ),
                    {
                        "name": name,
                        "city": city,
                        "country": country,
                        "price_per_night": price,
                        "rating": rating,
                        "season": season,
                    },
                )
            rows_loaded += 1
    return rows_loaded


def main() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    ensure_schema(engine)
    flight_count = load_flights(engine)
    hotel_count = load_hotels(engine)
    print(f"seeded flights={flight_count} hotels={hotel_count}")


if __name__ == "__main__":
    main()
