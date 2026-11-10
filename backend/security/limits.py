"""Atomic multi-key request/token admissions; conservative charges survive cancellation."""
from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Protocol

from sqlalchemy import select, update
from backend.db.models import SecurityUsage
from sqlalchemy.dialects.postgresql import insert

usage_table = SecurityUsage.__table__


class LimitExceeded(ValueError):
    def __init__(self, retry_after=60):
        super().__init__('Configured request or token limit reached')
        self.retry_after = max(1, int(retry_after))


@dataclass(frozen=True)
class Charge:
    key: str
    window: int
    requests: int
    tokens: int
    max_requests: int
    max_tokens: int


class CounterStore(Protocol):
    def charge(self, charges: list[Charge]) -> None: ...


class MemoryCounterStore:
    def __init__(self):
        self.rows, self.lock = {}, threading.Lock()

    def charge(self, charges):
        with self.lock:
            pending = dict(self.rows)
            for charge in sorted(charges, key=lambda c: (c.key, c.window)):
                key = (charge.key, charge.window)
                requests, tokens = pending.get(key, (0, 0))
                requests, tokens = requests + charge.requests, tokens + charge.tokens
                if requests > charge.max_requests or tokens > charge.max_tokens:
                    raise LimitExceeded()
                pending[key] = (requests, tokens)
            self.rows = pending


class PostgresCounterStore:
    def __init__(self, engine=None, table=usage_table):
        if engine is None:
            from backend.db.connect import engine
        self.engine, self.table = engine, table

    def charge(self, charges):
        table = self.table
        with self.engine.begin() as connection:
            # Consistent lock order prevents deadlocks; all admissions commit or none do.
            for charge in sorted(charges, key=lambda c: (c.key, c.window)):
                connection.execute(insert(table).values(key=charge.key, window=charge.window, requests=0, tokens=0).on_conflict_do_nothing())
                where = (table.c.key == charge.key) & (table.c.window == charge.window)
                row = connection.execute(select(table).where(where).with_for_update()).mappings().one()
                requests, tokens = row['requests'] + charge.requests, row['tokens'] + charge.tokens
                if requests > charge.max_requests or tokens > charge.max_tokens:
                    raise LimitExceeded()
                connection.execute(update(table).where(where).values(requests=requests, tokens=tokens))


def key(kind, value):
    return kind + ':' + hashlib.sha256(str(value).encode()).hexdigest()


class UsageGuard:
    def __init__(self, store, settings, clock=time.time):
        self.store, self.settings, self.clock = store, settings, clock

    def admit(self, session, user, *, tokens=0, requests=0):
        day = int(self.clock()) // 86400
        self.store.charge([Charge(key('session', session), 0, requests, tokens,
                                 self.settings['session_requests'], self.settings['session_tokens']),
                           Charge(key('user', user), day, requests, tokens,
                                  self.settings['user_daily_requests'], self.settings['user_daily_tokens'])])

    def rate(self, ip, user):
        period = self.settings['rate_window_seconds']
        now = int(self.clock())
        try:
            self.store.charge([Charge(key('rate-ip', ip), now // period, 1, 0, self.settings['ip_requests_per_window'], 0),
                               Charge(key('rate-user', user), now // period, 1, 0, self.settings['user_requests_per_window'], 0)])
        except LimitExceeded:
            raise LimitExceeded(period - now % period) from None


def identity(request):
    # Only authentication middleware may establish a user. Never trust an arbitrary header.
    user = request.scope.get('user')
    ip = request.client.host if request.client else 'unknown-peer'
    principal = getattr(user, 'identity', None) if getattr(user, 'is_authenticated', False) else None
    return ip, ('authenticated:' + str(principal)) if principal else 'anonymous:' + key('peer', ip)
