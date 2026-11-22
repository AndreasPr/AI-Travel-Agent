"""Synthetic pooled-connection protocol tests; no network or model calls."""
import asyncio

import pytest
from sqlalchemy import create_engine
from psycopg import AsyncConnection, OperationalError

from backend.llm.limits import PostgresDailyCounter
from backend.llm.types import ProviderUnavailable, QuotaExhausted


@pytest.mark.parametrize('row,expected', [((1,), 2), ((3,), 0), (None, None)])
def test_synthetic_async_quota_uses_transaction_local_timeout(monkeypatch, row, expected):
    statements = []
    exits = []
    class Connection:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            exits.append(args[0])
        async def execute(self, statement, parameters=None):
            statements.append((statement, parameters))
            return self
        async def fetchone(self):
            return row
    async def connect(*args, **kwargs):
        assert 'options' not in kwargs, 'Pooler rejects startup statement_timeout'
        assert kwargs['connect_timeout'] == 5
        return Connection()
    monkeypatch.setattr(AsyncConnection, 'connect', connect)
    # URL is synthetic; connection creation is intercepted above.
    engine = create_engine('postgresql+psycopg://synthetic:synthetic@localhost/synthetic')
    counter = PostgresDailyCounter(engine=engine)
    try:
        if row is None:
            with pytest.raises(QuotaExhausted):
                asyncio.run(counter.areserve('synthetic', 'synthetic-model', 3))
        else:
            assert asyncio.run(counter.areserve('synthetic', 'synthetic-model', 3)) == expected
        assert statements[0] == ('SET LOCAL statement_timeout = 5000', None)
        assert 'ON CONFLICT' in statements[1][0]
        assert statements[1][1]['provider'] == 'synthetic'
        assert len(exits) == 1
    finally:
        engine.dispose()


def test_synthetic_async_quota_timeout_failure_does_not_reserve(monkeypatch):
    calls = []
    exits = []
    class Connection:
        async def __aenter__(self):
            return self
        async def __aexit__(self, kind, *args):
            exits.append(kind)
        async def execute(self, statement, parameters=None):
            calls.append(statement)
            raise OperationalError('synthetic failure')
    async def connect(*args, **kwargs):
        return Connection()
    monkeypatch.setattr(AsyncConnection, 'connect', connect)
    engine = create_engine('postgresql+psycopg://synthetic:synthetic@localhost/synthetic')
    try:
        with pytest.raises(ProviderUnavailable):
            asyncio.run(PostgresDailyCounter(engine=engine).areserve('synthetic', 'synthetic-model', 3))
        assert calls == ['SET LOCAL statement_timeout = 5000']
        assert exits == [OperationalError]
    finally:
        engine.dispose()
