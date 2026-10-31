"""Process-local minute buckets and atomic persistent daily request reservations."""
import math
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from backend.db.models import LLMUsageDaily
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from backend.llm.types import ProviderUnavailable, QuotaExhausted, RateLimited

usage_daily = LLMUsageDaily.__table__

def quota_day():
    return datetime.now(ZoneInfo("America/Los_Angeles")).date()


def effective_limits(spec):
    margin = spec.get("safety_margin", 1.0)
    if not 0 < margin <= 1:
        raise ValueError("safety_margin must be in (0, 1]")
    result = {}
    for name in ("rpm", "tpm", "rpd"):
        value = spec["limits"].get(name)
        if value is not None and value < 0:
            raise ValueError("Limits must be nonnegative or null")
        result[name] = None if value is None else math.floor(value * margin)
    return result


class TokenBucket:
    def __init__(self, rpm, tpm, clock=time.monotonic):
        self.capacity = {"requests": rpm, "tokens": tpm}
        self.available = dict(self.capacity)
        self.clock, self.updated = clock, clock()
        self.lock = threading.Lock()

    def reserve(self, tokens):
        if tokens < 0:
            raise ValueError("Token reservation cannot be negative")
        with self.lock:
            now = self.clock()
            elapsed = max(0, now - self.updated)
            self.updated = now
            delays = []
            for kind, amount in (("requests", 1), ("tokens", tokens)):
                capacity = self.capacity[kind]
                if capacity is None:
                    continue
                self.available[kind] = min(capacity, self.available[kind] + elapsed * capacity / 60)
                if amount > self.available[kind]:
                    delays.append(60 * (amount - self.available[kind]) / capacity if capacity else 60)
            if delays:
                raise RateLimited("Local model token bucket exhausted", retry_after=max(delays))
            for kind, amount in (("requests", 1), ("tokens", tokens)):
                if self.capacity[kind] is not None:
                    self.available[kind] -= amount

    def reconcile(self, reserved, actual):
        with self.lock:
            if self.capacity["tokens"] is not None:
                self.available["tokens"] = min(self.capacity["tokens"], self.available["tokens"] + reserved - actual)


class PostgresDailyCounter:
    def __init__(self, engine=None, table=usage_daily, day=quota_day):
        if engine is None:
            from backend.db.connect import engine
        self.engine, self.table, self.day = engine, table, day

    def reserve(self, provider, model, limit):
        if limit is None:
            return None
        if limit <= 0:
            raise QuotaExhausted("Daily model quota exhausted")
        table = self.table
        stmt = insert(table).values(date=self.day(), provider=provider, model=model, requests=1)
        stmt = stmt.on_conflict_do_update(index_elements=[table.c.date, table.c.provider, table.c.model],
                                         set_={"requests": table.c.requests + 1}, where=table.c.requests < limit).returning(table.c.requests)
        try:
            with self.engine.begin() as connection:
                count = connection.scalar(stmt)
        except SQLAlchemyError as exc:
            raise ProviderUnavailable("Daily quota store unavailable; run database migrations") from exc
        if count is None:
            raise QuotaExhausted("Daily model quota exhausted")
        return limit - count

    def remaining(self, provider, model, limit):
        if limit is None:
            return None
        table = self.table
        try:
            with self.engine.connect() as connection:
                count = connection.scalar(select(table.c.requests).where(table.c.date == self.day(), table.c.provider == provider, table.c.model == model)) or 0
        except SQLAlchemyError as exc:
            raise ProviderUnavailable("Daily quota store unavailable; run database migrations") from exc
        return max(0, limit - count)


_buckets = {}
_buckets_lock = threading.Lock()


def shared_bucket(provider, model, limits):
    key = provider, model, limits["rpm"], limits["tpm"]
    with _buckets_lock:
        if key not in _buckets:
            _buckets[key] = TokenBucket(limits["rpm"], limits["tpm"])
        return _buckets[key]
