"""Load only generated synthetic inventory and offline airport reference data."""
from __future__ import annotations

import airportsdata
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.db.models import Airport, Flight, Hotel
from backend.scripts.generate_inventory import SOURCE, generate_inventory, read_config

FLIGHT_KEY = ["source", "flight_date", "starting_airport", "destination_airport", "airline"]
HOTEL_KEY = ["source", "name", "city", "country"]


def seed_inventory(connection, inventory: dict | None = None) -> dict[str, int]:
    """Caller owns the transaction; natural keys exclude mutable prices."""
    rows = generate_inventory() if inventory is None else inventory
    insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
    if connection.dialect.name not in {"postgresql", "sqlite"}:
        raise ValueError("Inventory seeding supports PostgreSQL and SQLite")
    if connection.dialect.name == "postgresql":
        # Serialize concurrent seed runs, including airport reference upserts.
        from sqlalchemy import text
        connection.execute(text("SELECT pg_advisory_xact_lock(20270301)"))
    for table, records, key in [(Flight.__table__, rows["flights"], FLIGHT_KEY), (Hotel.__table__, rows["hotels"], HOTEL_KEY)]:
        if any(row.get("source") != SOURCE for row in records):
            raise ValueError("Seed accepts only explicitly labeled synthetic-v1 rows")
        for start in range(0, len(records), 100):
            batch = records[start:start + 100]
            stmt = insert(table).values(batch)
            mutable = {name: stmt.excluded[name] for name in batch[0] if name not in key}
            connection.execute(stmt.on_conflict_do_update(index_elements=key, set_=mutable))
    mapping = read_config("airports.yaml")
    airports = airportsdata.load("IATA")
    codes = sorted(set(mapping["origin_hubs"]) | set(mapping["cities"].values()))
    for code in codes:
        row = airports[code]
        values = {column.name: row[column.name] for column in Airport.__table__.columns if column.name in row}
        exists = connection.scalar(select(Airport.id).where(Airport.iata == code).limit(1))
        if exists is None:
            connection.execute(Airport.__table__.insert().values(**values))
        else:
            connection.execute(update(Airport).where(Airport.iata == code).values(**values))
    return {"flights": len(rows["flights"]), "hotels": len(rows["hotels"]), "airports": len(codes)}


def main() -> None:
    from backend.db.connect import engine
    with engine.begin() as connection:
        counts = seed_inventory(connection)
    print(f"seeded source={SOURCE} flights={counts['flights']} hotels={counts['hotels']} airport_references={counts['airports']}")


if __name__ == "__main__":
    main()
