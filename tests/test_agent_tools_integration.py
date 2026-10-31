"""Isolated Postgres persistence test with synthetic fixtures and no HTTP calls."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.db.connect import engine
from backend.db.models import Hotel
from backend.tools.runtime import ToolRuntime
from backend.tools.storage import PostgresStore


@pytest.mark.integration
def test_http_cache_and_tool_result_persist_across_runtime_instances():
    schema = "synthetic_tools_" + uuid4().hex
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    path = Path(__file__).resolve().parents[1] / "backend/alembic/versions/20261102_agent_tools.py"
    spec = importlib.util.spec_from_file_location("agent_tool_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        with scoped_engine.begin() as connection:
            Hotel.__table__.create(connection)
            connection.execute(Hotel.__table__.insert().values(name="Synthetic Stay", city="Lisbon", country="Portugal", price_per_night=100, rating=4, source="synthetic-v1", currency="USD", tier="mid"))
        first = PostgresStore(scoped_engine)
        first.put_cache("synthetic-cache", "get_weather", {"synthetic": True}, 60)
        second = PostgresStore(scoped_engine)
        assert second.get_cache("synthetic-cache") == {"synthetic": True}
        first.put_cache("synthetic-expired", "get_weather", {"synthetic": True}, -1)
        assert second.get_cache("synthetic-expired") is None
        runtime = ToolRuntime(store=first, session_factory=sessionmaker(scoped_engine))
        try:
            result = runtime.execute("search_hotels", {"city": "Lisbon", "check_in": "2027-04-10", "check_out": "2027-04-15"})
            assert result.status == "ok"
            saved = second.get_result(result.tool_result_id)
            assert saved["data"]["hotels"][0]["total_price"] == "500.00"
            assert saved["source"] == "synthetic-v1"
        finally:
            runtime.close()
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
