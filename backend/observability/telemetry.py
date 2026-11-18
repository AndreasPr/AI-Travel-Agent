"""Bounded-cardinality metrics and content-free traces by default."""

import contextvars
from contextlib import contextmanager
from functools import wraps
import hashlib
import inspect
import json
import logging
import os
import re
import time
from uuid import uuid4
from datetime import datetime, timezone

_provider = None
_registry = None
_metrics = {}
identity = contextvars.ContextVar("observability_identity", default=None)
model_context = contextvars.ContextVar("observability_model", default=None)


class NoSpan:
    def set_attribute(self, *args):
        pass

    def add_event(self, *args, **kwargs):
        pass


@contextmanager
def span(name, **attributes):
    if _provider is None:
        yield NoSpan()
        return
    from opentelemetry.trace import Status, StatusCode

    with _provider.get_tracer("travel.backend").start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        try:
            yield current
        except BaseException as exc:
            current.set_attribute("error.type", type(exc).__name__)
            current.set_status(Status(StatusCode.ERROR))
            raise


def traced(name):
    def decorate(fn):
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_call(*args, **kwargs):
                with span(name):
                    return await fn(*args, **kwargs)

            return async_call

        @wraps(fn)
        def call(*args, **kwargs):
            with span(name):
                return fn(*args, **kwargs)

        return call

    return decorate


def configure(exporter=None):
    global _provider, _registry, _metrics
    if _provider is not None and exporter is None:
        return _provider
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge

    _provider = TracerProvider(resource=Resource.create({"service.name": "travel-api"}))
    if exporter is not None:
        _provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _registry = CollectorRegistry()
    _metrics = {
        "requests": Counter("travel_requests_total", "Chat requests by outcome", ["route", "status"], registry=_registry),
        "request_latency": Histogram(
            "travel_request_duration_seconds",
            "Chat latency",
            ["route"],
            buckets=(0.1, 1, 5, 10, 30, 60, 120, 300, 600, 900),
            registry=_registry,
        ),
        "model_errors": Counter(
            "travel_model_errors_total", "Failed model calls", ["provider", "model", "role", "error_type"], registry=_registry
        ),
        "model_calls": Counter("travel_model_calls_total", "Model calls", ["provider", "model", "role"], registry=_registry),
        "model_latency": Histogram(
            "travel_model_duration_seconds",
            "Model latency",
            ["provider", "model", "role"],
            buckets=(0.1, 1, 5, 10, 30, 60, 120, 300, 600),
            registry=_registry,
        ),
        "tokens": Counter("travel_tokens_total", "Observed tokens", ["provider", "model", "type"], registry=_registry),
        "trip_tokens": Histogram(
            "travel_trip_tokens",
            "Tokens per completed trip turn",
            ["type"],
            buckets=(100, 1000, 5000, 10000, 50000, 100000, 500000),
            registry=_registry,
        ),
        "shadow": Histogram(
            "travel_trip_shadow_cost_usd",
            "Estimated shadow cost per trip turn; not a charge",
            buckets=(0.001, 0.01, 0.1, 1, 10),
            registry=_registry,
        ),
        "shadow_unknown": Counter("travel_shadow_cost_unknown_total", "Turns with missing configured shadow prices", registry=_registry),
        "tool_calls": Counter("travel_tool_calls_total", "Tool calls", ["tool", "status"], registry=_registry),
        "tool_errors": Counter("travel_tool_errors_total", "Tool errors", ["tool", "error_type"], registry=_registry),
        "tool_latency": Histogram("travel_tool_duration_seconds", "Tool durations", ["tool"], registry=_registry),
        "quota_used": Gauge("travel_quota_requests_used", "Pacific-day requests consumed", ["provider", "model"], registry=_registry),
        "quota_limit": Gauge(
            "travel_quota_requests_limit", "Effective free daily request limit", ["provider", "model"], registry=_registry
        ),
    }
    return _provider


def metric(name, labels=(), value=1, method="inc"):
    if name in _metrics:
        obj = _metrics[name].labels(*labels) if labels else _metrics[name]
        getattr(obj, method)(value)


def redacted_prompt(messages):
    from backend.security.content import redact

    text = redact(json.dumps(messages, default=str))
    for key, value in os.environ.items():
        if len(value) >= 8 and any(word in key.upper() for word in ("KEY", "SECRET", "PASSWORD", "TOKEN")):
            text = text.replace(value, "[REDACTED_SECRET]")
    return re.sub(r'(?i)(api[_ -]?key|password|bearer)\s*[:= ]\s*[^\s,"}]+', r"\1 [REDACTED_SECRET]", text)[:4000]


def model_call(fn):
    @wraps(fn)
    async def wrapped(role, messages, *args, **kwargs):
        started = time.perf_counter()
        state = {"span": None, "retries": 0, "fallback": False, "provider": "unknown", "model": "unknown"}
        token = model_context.set(state)
        with span("gen_ai.chat", **{"gen_ai.operation.name": "chat", "travel.role": role}) as current:
            state["span"] = current
            if os.getenv("OBS_CAPTURE_PROMPTS", "false").lower() == "true":
                current.set_attribute("gen_ai.input.messages", redacted_prompt(messages))
            try:
                response = await fn(role, messages, *args, **kwargs)
                state.update(provider=response.provider, model=response.model)
                for key, value in {
                    "gen_ai.provider.name": "gcp.gemini" if response.provider == "gemini" else response.provider,
                    "gen_ai.request.model": response.model,
                    "gen_ai.response.model": response.model,
                    "gen_ai.usage.input_tokens": response.tokens_in,
                    "gen_ai.usage.output_tokens": response.tokens_out,
                    "gen_ai.usage.cache_read.input_tokens": response.cached_tokens,
                    "gen_ai.response.finish_reasons": [response.finish_reason or "unknown"],
                }.items():
                    current.set_attribute(key, value)
                for kind, value in [("input", response.tokens_in), ("output", response.tokens_out), ("cached", response.cached_tokens)]:
                    metric("tokens", (response.provider, response.model, kind), value)
                return response
            except BaseException as exc:
                metric("model_errors", (state["provider"], state["model"], role, type(exc).__name__))
                raise
            finally:
                elapsed = time.perf_counter() - started
                current.set_attribute("travel.latency_ms", elapsed * 1000)
                current.set_attribute("travel.retries", state["retries"])
                current.set_attribute("travel.fallback_used", state["fallback"])
                current.set_attribute("gen_ai.request.model", state["model"])
                metric("model_calls", (state["provider"], state["model"], role))
                metric("model_latency", (state["provider"], state["model"], role), elapsed, "observe")
                model_context.reset(token)

    return wrapped


def model_attempt(provider, model, remaining=None, limit=None):
    state = model_context.get()
    if state:
        state.update(provider=provider, model=model)
        state["span"].set_attribute("gen_ai.provider.name", "gcp.gemini" if provider == "gemini" else provider)
    if limit is not None and remaining is not None:
        metric("quota_used", (provider, model), limit - remaining, "set")
        metric("quota_limit", (provider, model), limit, "set")


def model_event(kind):
    state = model_context.get()
    if state:
        if kind == "retry":
            state["retries"] += 1
        else:
            state["fallback"] = True
        state["span"].add_event("travel." + kind)


def tool_call(fn):
    @wraps(fn)
    async def wrapped(name, arguments):
        started = time.perf_counter()
        with span("tool." + name, **{"gen_ai.tool.name": name}) as current:
            result = await fn(name, arguments)
            duration = time.perf_counter() - started
            error = (result.get("data") or {}).get("error", {}) if result["status"] == "error" else {}
            code = error.get("code", "unknown") if error else ""
            current.set_attribute("travel.tool.status", result["status"])
            current.set_attribute("travel.duration_ms", duration * 1000)
            current.set_attribute("travel.cache_hit", result.get("cache_hit", False))
            if code:
                current.set_attribute("error.type", code)
                if hasattr(current, "set_status"):
                    from opentelemetry.trace import StatusCode

                    current.set_status(StatusCode.ERROR)
                metric("tool_errors", (name, code))
            metric("tool_calls", (name, result["status"]))
            metric("tool_latency", (name,), duration, "observe")
            return result

    return wrapped


def shadow_cost(calls, config):
    total = 0.0
    for call in calls:
        prices = config.get("shadow_pricing_usd_per_1m_tokens", {}).get(call["model"], {})
        if prices.get("input") is None or prices.get("output") is None:
            return {"label": "shadow cost estimate", "estimated_usd": None, "actual_usd": 0, "reason": "config prices missing"}
        total += (call["tokens_in"] * prices["input"] + call["tokens_out"] * prices["output"]) / 1_000_000
    return {"label": "shadow cost estimate", "estimated_usd": total, "actual_usd": 0}


def chat_turn(fn):
    @wraps(fn)
    async def wrapped(self, request, **kwargs):
        route = "/api/chat/stream" if kwargs.get("event_sink") else "/api/chat"
        info = {
            **(identity.get() or {}),
            "request_id": str(kwargs.get("request_id") or (identity.get() or {}).get("request_id") or uuid4()),
            "user_hash": hashlib.sha256(str(kwargs.get("user_id", "local-cli")).encode()).hexdigest(),
        }
        token = identity.set(info)
        started = time.perf_counter()
        status = "error"
        try:
            with span("agent.chat", **{"travel.request_id": info["request_id"], "travel.user_hash": info["user_hash"]}) as current:
                result = await fn(self, request, **kwargs)
                status = "error" if any(i.get("severity") == "error" for i in result.issues) else "ok"
                current.set_attribute("travel.trip_id", str(result.trip_id))
                cost = shadow_cost(result.usage.calls, self.config)
                current.set_attribute("travel.shadow_cost.label", cost["label"])
                current.set_attribute("travel.actual_cost_usd", 0)
                if cost["estimated_usd"] is not None:
                    current.set_attribute("travel.shadow_cost.estimated_usd", cost["estimated_usd"])
                    metric("shadow", value=cost["estimated_usd"], method="observe")
                else:
                    metric("shadow_unknown")
                for kind in ("tokens_in", "tokens_out", "cached_tokens"):
                    metric("trip_tokens", (kind,), getattr(result.usage, kind), "observe")
                current.set_attribute("travel.status", status)
                logging.getLogger("travel.chat").info("Chat turn completed: %s", status)
                return result
        finally:
            metric("requests", (route, status))
            metric("request_latency", (route,), time.perf_counter() - started, "observe")
            identity.reset(token)

    return wrapped


class JSONFormatter(logging.Formatter):
    def format(self, record):
        from opentelemetry import trace
        from backend.security.content import redact

        ctx = trace.get_current_span().get_span_context()
        message = redact(record.getMessage())
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            _, method, path, _, status = record.args
            message = f"{method} {str(path).split(chr(63), 1)[0]} {status}"
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(message),
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "request_id": (identity.get() or {}).get("request_id"),
            "user_hash": (identity.get() or {}).get("user_hash"),
        }
        if record.exc_info:
            data["error_type"] = record.exc_info[0].__name__
        return json.dumps(data)


def instrument_app(app):
    from fastapi.responses import Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    provider = configure()
    app.add_middleware(RequestIdentityMiddleware)

    def hook(current, scope):
        current.set_attribute("url.query", "")
        current.set_attribute("url.full", scope.get("path", ""))
        current.set_attribute("http.url", scope.get("path", ""))
        current.set_attribute("travel.request_id", (identity.get() or {}).get("request_id", ""))
        current.set_attribute("http.target", scope.get("path", ""))

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, server_request_hook=hook, excluded_urls="healthz,readyz,metrics", exclude_spans=["send", "receive"]
    )

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint():
        return Response(generate_latest(_registry), media_type=CONTENT_TYPE_LATEST)

    logging.getLogger("travel.chat").setLevel(logging.INFO)
    if not logging.getLogger().handlers:
        logging.getLogger().addHandler(logging.StreamHandler())
    for logger in [logging.getLogger(), logging.getLogger("uvicorn"), logging.getLogger("uvicorn.access")]:
        for handler in logger.handlers:
            handler.setFormatter(JSONFormatter())


class RequestIdentityMiddleware:
    """Keep identity in context for the whole response, including SSE tasks."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        from backend.security.limits import identity as security_identity

        _, user = security_identity(Request(scope))
        token = identity.set({"request_id": str(uuid4()), "user_hash": hashlib.sha256(user.encode()).hexdigest()})
        from opentelemetry import trace

        current = trace.get_current_span()
        current.set_attribute("travel.request_id", identity.get()["request_id"])
        current.set_attribute("travel.user_hash", identity.get()["user_hash"])

        async def reply(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", identity.get()["request_id"].encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            return await self.app(scope, receive, reply)
        finally:
            identity.reset(token)
