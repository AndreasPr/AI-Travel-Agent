"""Postgres migration/seed test with synthetic rows in a rolled-back isolated schema."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, inspect, select, text

from backend.db.connect import engine
from backend.db.models import Airport, Flight, Hotel
from backend.scripts.generate_inventory import generate_inventory
from backend.scripts.seed_inventory import seed_inventory


@pytest.mark.integration
def test_fresh_migrations_and_seed_are_idempotent():
    schema = "synthetic_test_" + uuid4().hex
    versions = Path(__file__).resolve().parents[1] / "backend/alembic/versions"
    paths = ["20241020_initial_postgres_schema.py", "20261021_rag_metadata_schema_fix.py", "20261031_synthetic_inventory.py"]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            context = MigrationContext.configure(connection)
            modules = []
            with Operations.context(context):
                for index, filename in enumerate(paths):
                    spec = importlib.util.spec_from_file_location(f"synthetic_migration_{index}", versions / filename)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.upgrade()
                    modules.append(module)
            inventory = generate_inventory()
            assert seed_inventory(connection, inventory) == {"flights": 8000, "hotels": 250, "airports": 33}
            before = connection.execute(select(Flight.id).order_by(Flight.id)).scalars().all()
            seed_inventory(connection, inventory)
            assert connection.scalar(select(func.count()).select_from(Flight)) == 8000
            assert connection.scalar(select(func.count()).select_from(Hotel)) == 250
            assert connection.scalar(select(func.count()).select_from(Airport)) == 33
            assert before == connection.execute(select(Flight.id).order_by(Flight.id)).scalars().all()
            assert connection.scalar(select(func.count()).select_from(Flight).where(Flight.source != "synthetic-v1")) == 0
            with Operations.context(context):
                modules[-1].downgrade()
                assert "source" not in {column["name"] for column in inspect(connection).get_columns("flights", schema=schema)}
                modules[-1].upgrade()
                assert connection.scalar(select(func.count()).select_from(Flight).where(Flight.source.is_(None))) == 8000
        finally:
            transaction.rollback()
