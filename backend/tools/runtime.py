"""Bounded tool execution, HTTP retries and shared-host geocoding throttling."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from backend.llm.retry import retry_after_seconds
from backend.tools.models import Failure, Itinerary, ToolError, ToolResult
from backend.tools.storage import PostgresStore, utcnow

POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent-tool")


class ToolFault(Exception):
    def __init__(self, code, message, retryable=False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


class DiskRateLimiter:
    """Serialize requests across processes on one host; no distributed deployment."""
    def __init__(self, path=None, clock=time.time, sleep=time.sleep):
        self.path = Path(path or Path(tempfile.gettempdir()) / "travel-nominatim-rate.lock")
        self.clock, self.sleep = clock, sleep

    @contextmanager
    def slot(self, context):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+") as handle:
            while True:
                context.check()
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    context.pause(0.05)
            try:
                handle.seek(0)
                raw = handle.read().strip()
                previous = float(raw) if raw else None
                delay = max(0, previous + 1 - self.clock()) if previous is not None else 0
                if delay >= context.remaining():
                    raise TimeoutError()
                self.sleep(delay)
                context.check()
                handle.seek(0)
                handle.truncate()
                handle.write(str(self.clock()))
                handle.flush()
                os.fsync(handle.fileno())
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


@dataclass(frozen=True)
class Policy:
    timeout_seconds: float = 15
    attempts: int = 3
    cache_ttl_seconds: int = 3600
    max_output_bytes: int = 65536


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: object
    source: str
    policy: Policy

    def schema(self):
        schema = {"name": self.name, "description": self.description,
                "input_schema": self.input_model.model_json_schema(by_alias=True),
                "output_schema": ToolResult[self.output_model].model_json_schema(),
                "policy": self.policy.__dict__}
        if self.name == "validate_itinerary":
            schema["related_schemas"] = {"Itinerary": Itinerary.model_json_schema()}
        return schema


class Context:
    def __init__(self, runtime, definition):
        self.runtime, self.definition = runtime, definition
        self.deadline = time.monotonic() + definition.policy.timeout_seconds
        self.cache_uses = []
        self.fetched_times = []

    def remaining(self):
        return max(0, self.deadline - time.monotonic())

    def check(self):
        if self.remaining() <= 0:
            raise TimeoutError()

    def pause(self, seconds):
        if seconds >= self.remaining():
            raise TimeoutError()
        time.sleep(seconds)
        self.check()

    def http(self, url, params, headers=None, rate_limited=False):
        key = hashlib.sha256(json.dumps([self.definition.name, url, params], sort_keys=True, default=str).encode()).hexdigest()
        self.check()
        cached = self.runtime.store.get_cache(key)
        if cached is not None:
            self.cache_uses.append(True)
            self.fetched_times.append(cached["fetched_at"])
            return cached["body"]
        self.cache_uses.append(False)
        for attempt in range(self.definition.policy.attempts):
            self.check()
            try:
                if rate_limited:
                    with self.runtime.limiter.slot(self):
                        # Another process might have populated this cache while we waited.
                        cached = self.runtime.store.get_cache(key)
                        if cached is not None:
                            self.cache_uses[-1] = True
                            self.fetched_times.append(cached["fetched_at"])
                            return cached["body"]
                        body = self._get(url, params, headers)
                else:
                    body = self._get(url, params, headers)
                timestamp = utcnow().isoformat()
                self.check()
                self.runtime.store.put_cache(key, self.definition.name, {"body": body, "fetched_at": timestamp}, self.definition.policy.cache_ttl_seconds)
                self.fetched_times.append(timestamp)
                return body
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status == 429 or status >= 500
                if not retryable or attempt + 1 == self.definition.policy.attempts:
                    raise ToolFault("upstream_error", f"Upstream HTTP {status}", retryable) from exc
                self.pause(max(0.25 * 2 ** attempt, retry_after_seconds(exc.response.headers.get("Retry-After")) or 0))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt + 1 == self.definition.policy.attempts:
                    code = "timeout" if isinstance(exc, httpx.TimeoutException) else "upstream_error"
                    raise ToolFault(code, "HTTP request did not complete", True) from exc
                self.pause(0.25 * 2 ** attempt)
        raise ToolFault("upstream_error", "HTTP attempts exhausted", True)

    def _get(self, url, params, headers):
        self.check()
        with self.runtime.client.stream("GET", url, params=params, headers=headers, timeout=min(10, self.remaining())) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                self.check()
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise ToolFault("output_too_large", "Upstream response exceeds one MiB")
        try:
            return json.loads(body)
        except ValueError as exc:
            raise ToolFault("upstream_error", "Upstream response is not JSON") from exc


class ToolRuntime:
    def __init__(self, definitions=None, store=None, client=None, session_factory=None, search=None, today=None, limiter=None):
        if definitions is None:
            from backend.tools.registry import REGISTRY
            definitions = REGISTRY
        self.definitions = definitions
        self.store = store if store is not None else PostgresStore()
        self.client = client if client is not None else httpx.Client(follow_redirects=False)
        if session_factory is None:
            from backend.db.connect import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory
        self.search, self.today = search, today or (lambda: utcnow().date())
        self.limiter = limiter if limiter is not None else DiskRateLimiter()

    def close(self):
        self.client.close()

    def _error(self, name, source, code, message, retryable=False):
        return ToolResult(tool_result_id=str(uuid4()), tool=name, status="error",
                          data=Failure(error=ToolError(code=code, message=message, retryable=retryable)),
                          source=source, fetched_at=utcnow(), cache_hit=False)

    def execute(self, name, arguments):
        if name not in self.definitions:
            return self._error(name, "registry", "invalid_input", "Unknown tool")
        definition = self.definitions[name]
        try:
            request = definition.input_model.model_validate(arguments)
        except ValidationError:
            return self._error(name, definition.source, "invalid_input", "Arguments do not match the tool input schema")
        future = POOL.submit(self._invoke, definition, request)
        try:
            return future.result(timeout=definition.policy.timeout_seconds)
        except FutureTimeout:
            future.cancel()
            return self._error(name, definition.source, "timeout", "Tool deadline exceeded", True)

    def _invoke(self, definition, request):
        context = Context(self, definition)
        try:
            data = definition.handler(request, context)
            context.check()
            status = "no_data" if data is None else "ok"
            if data is not None:
                data = definition.output_model.model_validate(data)
            result = ToolResult(tool_result_id=str(uuid4()), tool=definition.name, status=status, data=data,
                                source=definition.source, fetched_at=min(context.fetched_times) if context.fetched_times else utcnow(),
                                cache_hit=bool(context.cache_uses) and all(context.cache_uses))
            if len(result.model_dump_json().encode()) > definition.policy.max_output_bytes:
                return self._error(definition.name, definition.source, "output_too_large", "Tool output exceeds the configured byte limit")
            context.check()
            self.store.save_result(result)
            return result
        except TimeoutError:
            return self._error(definition.name, definition.source, "timeout", "Tool deadline exceeded", True)
        except ToolFault as exc:
            return self._error(definition.name, definition.source, exc.code, exc.message, exc.retryable)
        except (ValidationError, ValueError, KeyError, TypeError):
            return self._error(definition.name, definition.source, "upstream_error", "Tool data does not match its output contract")
        except Exception:
            return self._error(definition.name, definition.source, "internal_error", "Tool failed; verify database migrations and local dependencies")
