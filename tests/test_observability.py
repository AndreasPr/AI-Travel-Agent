"""Synthetic telemetry; in-memory spans, no exporters contacting services."""

import asyncio
import hashlib
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.observability import telemetry as t
from backend.llm.types import Response


@pytest.fixture
def exporter():
    old = (t._provider, t._registry, t._metrics)
    export = InMemorySpanExporter()
    t.configure(export)
    yield export
    t._provider.shutdown()
    t._provider, t._registry, t._metrics = old


def exercise():
    @t.model_call
    async def generate(role, messages):
        t.model_attempt("synthetic", "synthetic")
        t.model_event("retry")
        return Response(
            text="synthetic", provider="synthetic", model="synthetic", tokens_in=12, tokens_out=3, cached_tokens=4, finish_reason="stop"
        )

    @t.tool_call
    async def execute(name, arguments):
        return {"tool": name, "status": "ok", "data": {}, "cache_hit": True}

    async def run():
        with t.span("agent.chat"):
            await generate("plan", [{"role": "user", "content": "synthetic.person@example.invalid"}])
            await execute("search_hotels", {})

    asyncio.run(run())


def test_trace_has_model_and_tool_spans_with_attributes(exporter):
    exercise()
    spans = exporter.get_finished_spans()
    model = next(s for s in spans if s.name == "gen_ai.chat")
    tool = next(s for s in spans if s.name == "tool.search_hotels")
    parent = next(s for s in spans if s.name == "agent.chat")
    assert model.context.trace_id == tool.context.trace_id == parent.context.trace_id
    assert model.parent.span_id == parent.context.span_id
    assert model.attributes["gen_ai.usage.input_tokens"] == 12
    assert model.attributes["gen_ai.usage.cache_read.input_tokens"] == 4
    assert model.attributes["travel.role"] == "plan"
    assert model.attributes["travel.retries"] == 1
    assert model.attributes["gen_ai.response.finish_reasons"] == ("stop",)
    assert tool.attributes["travel.cache_hit"] is True
    assert tool.attributes["travel.tool.status"] == "ok"
    assert tool.attributes["travel.duration_ms"] >= 0


def test_logs_contain_trace_id_and_hashed_user(exporter):
    user = "synthetic.person@example.invalid"
    token = t.identity.set({"request_id": "synthetic-request", "user_hash": hashlib.sha256(user.encode()).hexdigest()})
    try:
        with t.span("synthetic") as current:
            record = logging.LogRecord("synthetic", logging.INFO, __file__, 1, "hello %s", (user,), None)
            row = json.loads(t.JSONFormatter().format(record))
            assert row["trace_id"] == format(current.get_span_context().trace_id, "032x")
            assert row["span_id"] == format(current.get_span_context().span_id, "016x")
            assert row["user_hash"] == hashlib.sha256(user.encode()).hexdigest()
            assert row["request_id"] == "synthetic-request"
            assert user not in json.dumps(row)
    finally:
        t.identity.reset(token)


def test_prompt_not_stored_by_default(exporter, monkeypatch):
    monkeypatch.delenv("OBS_CAPTURE_PROMPTS", raising=False)
    exercise()
    assert all("gen_ai.input.messages" not in span.attributes for span in exporter.get_finished_spans())
    monkeypatch.setenv("OBS_CAPTURE_PROMPTS", "true")
    exercise()
    text = json.dumps([dict(span.attributes) for span in exporter.get_finished_spans()])
    assert "synthetic.person@example.invalid" not in text
    assert "[REDACTED_EMAIL]" in text


def test_shadow_cost_uses_config_prices_and_is_labeled():
    config = {"shadow_pricing_usd_per_1m_tokens": {"synthetic": {"input": 2, "output": 4}}}
    value = t.shadow_cost([{"model": "synthetic", "tokens_in": 1000, "tokens_out": 500}], config)
    assert value == {"label": "shadow cost estimate", "estimated_usd": 0.004, "actual_usd": 0}
    assert t.shadow_cost([{"model": "unknown", "tokens_in": 1, "tokens_out": 1}], config)["estimated_usd"] is None


def test_metrics_endpoint_exposes_expected_series(exporter):
    app = FastAPI()
    t.instrument_app(app)
    exercise()
    t.metric("requests", ("/api/chat", "ok"))
    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    for name in (
        "travel_requests_total",
        "travel_tokens_total",
        "travel_model_duration_seconds_bucket",
        "travel_tool_calls_total",
        "travel_trip_shadow_cost_usd",
    ):
        assert name in response.text
    assert "synthetic.person@example.invalid" not in response.text


def test_agent_observability_uses_real_loop(exporter):
    from test_agent_loop import setup, run, calls, itinerary

    agent, _, _ = setup([calls("search_hotels"), {}, itinerary()])
    result = run(agent)
    assert result.itinerary is not None
    names = {s.name for s in exporter.get_finished_spans()}
    assert {"agent.chat", "agent.context_build", "gen_ai.chat", "tool.search_hotels", "agent.validate_itinerary"} <= names


def test_alerts_match_config():
    from pathlib import Path
    import yaml
    from observability.render_alerts import render

    assert yaml.safe_load(Path("observability/alerts.yaml").read_text()) == render()


def test_streaming_http_and_agent_share_trace(exporter):
    from backend.agent.api import get_agent, router
    from test_agent_streaming import agent_for

    agent = agent_for()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent] = lambda: agent
    t.instrument_app(app)
    response = TestClient(app).post("/api/chat/stream", json={"message": "Synthetic trip request under 1500 USD"})
    assert response.status_code == 200
    assert "event: done" in response.text
    spans = exporter.get_finished_spans()
    chat = next(s for s in spans if s.name == "agent.chat")
    http = next(s for s in spans if s.kind.name == "SERVER")
    assert chat.context.trace_id == http.context.trace_id
    assert chat.attributes["travel.request_id"] == response.headers["x-request-id"]
    assert len(chat.attributes["travel.user_hash"]) == 64


def test_tool_error_and_quota_metrics(exporter):
    from prometheus_client import generate_latest

    @t.tool_call
    async def fail(name, arguments):
        return {"status": "error", "data": {"error": {"code": "timeout"}}, "cache_hit": False}

    asyncio.run(fail("search_hotels", {}))
    t.model_attempt("synthetic", "synthetic", remaining=2, limit=10)
    tool = exporter.get_finished_spans()[0]
    assert tool.attributes["error.type"] == "timeout"
    assert tool.status.status_code.name == "ERROR"
    metrics = generate_latest(t._registry).decode()
    assert 'travel_tool_errors_total{error_type="timeout",tool="search_hotels"} 1.0' in metrics
    assert 'travel_quota_requests_used{model="synthetic",provider="synthetic"} 8.0' in metrics


def test_eval_gauges_preserve_synthetic_provenance(monkeypatch):
    from eval.push_metrics import push
    from eval.judge import LABEL
    from prometheus_client import generate_latest

    captured = []
    monkeypatch.setattr(
        "prometheus_client.push_to_gateway", lambda gateway, job, registry: captured.append(generate_latest(registry).decode())
    )
    row = {
        "source": "synthetic",
        "provider": "synthetic",
        "model": LABEL,
        "label": LABEL,
        "case_id": "synthetic",
        "checks": {"schema_valid": {"passed": True}},
    }
    push([row], "unused")
    assert 'source="synthetic"' in captured[0]
    assert LABEL in captured[0]
    assert "100.0" in captured[0]
    with pytest.raises(ValueError, match="never be attributed"):
        push([{**row, "model": "real-model"}], "unused")
