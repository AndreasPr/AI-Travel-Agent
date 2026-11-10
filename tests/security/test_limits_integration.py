"""Atomic Postgres admissions with synthetic subjects and isolated tables."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, select, text

from backend.security.limits import Charge, LimitExceeded, PostgresCounterStore, usage_table

pytestmark = pytest.mark.integration


@pytest.fixture
def counter():
    from backend.db.connect import engine
    schema = 'synthetic_security_' + uuid4().hex
    migration = Path(__file__).resolve().parents[2] / 'backend/alembic/versions/20261109_guardrails.py'
    spec = importlib.util.spec_from_file_location('security_migration', migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
        yield PostgresCounterStore(engine, usage_table.to_metadata(MetaData(), schema=schema))
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def test_postgres_admission_atomic_and_persistent(counter):
    charge = Charge('synthetic-subject', 0, 1, 10, 3, 30)
    def attempt(_):
        try:
            counter.charge([charge])
            return True
        except LimitExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 3
    new_instance = PostgresCounterStore(counter.engine, counter.table)
    with pytest.raises(LimitExceeded):
        new_instance.charge([charge])
    with counter.engine.connect() as conn:
        row = conn.execute(select(counter.table)).mappings().one()
        assert row['requests'] == 3 and row['tokens'] == 30


def test_postgres_multi_subject_denial_rolls_back(counter):
    with pytest.raises(LimitExceeded):
        counter.charge([Charge('synthetic-a', 0, 1, 0, 1, 0), Charge('synthetic-b', 0, 2, 0, 1, 0)])
    with counter.engine.connect() as conn:
        assert not conn.execute(select(counter.table)).all()
