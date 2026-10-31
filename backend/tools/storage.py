"""Persistent HTTP cache and trusted ToolResult ledger."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.db.models import ToolHTTPCache, StoredToolResult


def utcnow():
    return datetime.now(timezone.utc)


class PostgresStore:
    def __init__(self, engine=None):
        if engine is None:
            from backend.db.connect import engine
        self.engine = engine

    def get_cache(self, key):
        table = ToolHTTPCache.__table__
        with self.engine.connect() as conn:
            row = conn.execute(select(table.c.payload).where(table.c.cache_key == key, table.c.expires_at > utcnow())).first()
        return row[0] if row else None

    def put_cache(self, key, tool, payload, ttl):
        table = ToolHTTPCache.__table__
        now = utcnow()
        values = dict(cache_key=key, tool=tool, payload=payload, fetched_at=now, expires_at=now + timedelta(seconds=ttl))
        statement = insert(table).values(**values)
        with self.engine.begin() as conn:
            conn.execute(statement.on_conflict_do_update(index_elements=[table.c.cache_key], set_=values))

    def save_result(self, result):
        with self.engine.begin() as conn:
            conn.execute(StoredToolResult.__table__.insert().values(tool_result_id=result.tool_result_id, payload=result.model_dump(mode="json"), fetched_at=result.fetched_at))

    def get_result(self, result_id):
        with self.engine.connect() as conn:
            return conn.scalar(select(StoredToolResult.payload).where(StoredToolResult.tool_result_id == result_id))
