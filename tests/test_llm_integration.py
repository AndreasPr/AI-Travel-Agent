"""Quota persistence tests against Postgres; no provider or model calls."""
import importlib.util
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, text

from backend.db.connect import engine
from backend.llm.limits import PostgresDailyCounter, usage_daily
from backend.llm.types import QuotaExhausted


@pytest.fixture
def isolated_quota_table():
    schema = "synthetic_quota_" + uuid4().hex
    path = Path(__file__).resolve().parents[1] / "backend/alembic/versions/20261101_llm_usage_daily.py"
    spec = importlib.util.spec_from_file_location("quota_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
        yield schema, usage_daily.to_metadata(MetaData(), schema=schema)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.mark.integration
def test_quota_counter_survives_new_process(isolated_quota_table):
    schema, table = isolated_quota_table
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), SYNTHETIC_QUOTA_SCHEMA=schema)
    code = '''
import os
from sqlalchemy import MetaData
from backend.llm.limits import PostgresDailyCounter, usage_daily
counter = PostgresDailyCounter(table=usage_daily.to_metadata(MetaData(), schema=os.environ["SYNTHETIC_QUOTA_SCHEMA"]))
assert counter.reserve("synthetic", "synthetic-model", 1) == 0
print("synthetic reservation committed")
'''
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "Child process quota reservation failed; inspect local database setup"
    assert result.stdout.strip() == "synthetic reservation committed"
    counter = PostgresDailyCounter(engine, table)
    assert counter.remaining("synthetic", "synthetic-model", 1) == 0
    with pytest.raises(QuotaExhausted):
        counter.reserve("synthetic", "synthetic-model", 1)


@pytest.mark.integration
def test_daily_quota_reservation_is_atomic(isolated_quota_table):
    _, table = isolated_quota_table
    counter = PostgresDailyCounter(engine, table)

    def reserve(_):
        try:
            counter.reserve("synthetic", "synthetic-concurrent", 3)
            return True
        except QuotaExhausted:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(reserve, range(12))) == 3
    assert counter.remaining("synthetic", "synthetic-concurrent", 3) == 0


@pytest.mark.integration
def test_async_daily_quota_reservation_is_atomic(isolated_quota_table):
    import asyncio
    _, table = isolated_quota_table
    counter = PostgresDailyCounter(engine, table)
    async def scenario():
        async def reserve():
            try:
                await counter.areserve('synthetic', 'synthetic-async', 3)
                return True
            except QuotaExhausted:
                return False
        assert sum(await asyncio.gather(*(reserve() for _ in range(8)))) == 3
    asyncio.run(scenario())
    assert counter.remaining('synthetic', 'synthetic-async', 3) == 0


@pytest.mark.integration
def test_cancelled_async_quota_transaction_rolls_back(isolated_quota_table):
    import asyncio
    schema, table = isolated_quota_table
    counter = PostgresDailyCounter(engine, table)
    async def scenario():
        with engine.begin() as connection:
            connection.execute(text(f'LOCK TABLE "{schema}".llm_usage_daily IN ACCESS EXCLUSIVE MODE'))
            task = asyncio.create_task(counter.areserve('synthetic', 'synthetic-cancel', 3))
            await asyncio.sleep(0.1)
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert counter.remaining('synthetic', 'synthetic-cancel', 3) == 3
    asyncio.run(scenario())
