"""Offline LLM tests using synthetic fixtures and fake transports only."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.llm.config import load_config, model_config
from backend.llm.gemini import GeminiProvider
from backend.llm.limits import TokenBucket, effective_limits
from backend.llm.ollama import OllamaProvider
from backend.llm.replay import Recorder, ReplayProvider, fixture_key
from backend.llm.retry import retry_call, status_error
from backend.llm.router import ManagedProvider, get_provider
from backend.llm.types import Event, InvalidOutput, ProviderUnavailable, QuotaExhausted, RateLimited, Response, response_events

MESSAGES = [{"role": "user", "content": "Synthetic replay greeting"}]
MODEL = "synthetic-test-model"
SPEC = {"limits": {"rpm": 10, "tpm": 10000, "rpd": 2}, "safety_margin": 1, "supports": {"tools": True, "structured_output": True}}
SETTINGS = {"max_output_tokens": 10, "retry": {"attempts": 1}}
TOOL = {"name": "lookup", "description": "Synthetic test lookup", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}}


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("Unit tests cannot make live network calls")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.delenv("RECORD", raising=False)
    monkeypatch.delenv("LLM_REPLAY", raising=False)


class FakeProvider:
    provider = "synthetic"
    model = MODEL

    def __init__(self):
        self.calls = 0

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        self.calls += 1
        result = Response(text="Synthetic hello", provider=self.provider, model=self.model, tokens_in=3, tokens_out=2)
        return response_events(result) if stream else result


class FakeCounter:
    def __init__(self):
        self.count = 0

    def reserve(self, provider, model, limit):
        if self.count >= limit:
            raise QuotaExhausted("Synthetic exhausted quota")
        self.count += 1
        return limit - self.count


def test_normalized_response_shape():
    result = FakeProvider().generate(MESSAGES)
    assert set(result.model_dump()) == {"text", "tool_calls", "tokens_in", "tokens_out", "cached_tokens", "latency_ms", "provider", "model", "finish_reason", "raw_id"}
    assert result.text == "Synthetic hello" and result.tokens_in == 3
    assert [event.type for event in response_events(result)] == ["text_delta", "usage", "done"]


def test_replay_returns_recorded_and_errors_when_missing():
    # This checked-in fixture is explicitly synthetic, not a live provider recording.
    replay = ReplayProvider("synthetic", MODEL)
    assert replay.generate(MESSAGES).text == "Synthetic replay response"
    assert list(replay.generate(MESSAGES, stream=True))[-1].type == "done"
    with pytest.raises(InvalidOutput, match="Missing replay fixture"):
        replay.generate([{"role": "user", "content": "Missing synthetic request"}])
    assert fixture_key("synthetic", MODEL, MESSAGES) != fixture_key("synthetic", MODEL, MESSAGES, schema={"type": "object"})


def test_recorder_strips_secrets(monkeypatch, tmp_path):
    class FakeSecretProvider(FakeProvider):
        def generate(self, *args, **kwargs):
            return Response(provider=self.provider, model=self.model,
                            text="synthetic-secret-value Bearer synthetic-bearer-value",
                            tool_calls=[{"name": "lookup", "arguments": {"headers": {"Authorization": "secret"}, "api_key": "secret", "safe": "kept"}}])
    monkeypatch.setenv("TEST_API_KEY", "synthetic-secret-value")
    recorder = Recorder(FakeSecretProvider(), tmp_path)
    recorder.generate(MESSAGES)
    assert not list(tmp_path.iterdir())
    monkeypatch.setenv("RECORD", "1")
    recorder.generate(MESSAGES)
    text = next(tmp_path.glob("*.json")).read_text()
    assert "synthetic-secret-value" not in text and "synthetic-bearer-value" not in text
    assert "Authorization" not in text and "api_key" not in text and "headers" not in text
    assert "kept" in text and "[REDACTED]" in text


def test_retry_on_429_then_success():
    calls, delays = [], []

    def call():
        calls.append(1)
        if len(calls) == 1:
            raise status_error(429, {"Retry-After": "7"})
        return "synthetic success"

    assert retry_call(call, sleep=delays.append, jitter=lambda: 0) == "synthetic success"
    assert len(calls) == 2 and delays == [7]


def test_no_retry_on_400():
    calls = []

    def call():
        calls.append(1)
        raise status_error(400)

    with pytest.raises(InvalidOutput):
        retry_call(call, sleep=lambda _: pytest.fail("must not sleep"))
    assert len(calls) == 1


def test_token_bucket_blocks_over_rpm():
    now = [0.0]
    bucket = TokenBucket(2, 100, clock=lambda: now[0])
    bucket.reserve(10)
    bucket.reserve(10)
    with pytest.raises(RateLimited):
        bucket.reserve(10)
    now[0] = 30
    bucket.reserve(10)
    with pytest.raises(RateLimited):
        TokenBucket(10, 5).reserve(6)
    assert effective_limits({**SPEC, "safety_margin": 0.8}) == {"rpm": 8, "tpm": 8000, "rpd": 1}


def test_daily_quota_exhausted_raises_without_calling_provider():
    provider, counter = FakeProvider(), FakeCounter()
    managed = ManagedProvider(provider, SPEC, SETTINGS, counter=counter, bucket=TokenBucket(100, None))
    managed.generate(MESSAGES)
    managed.generate(MESSAGES)
    with pytest.raises(QuotaExhausted):
        managed.generate(MESSAGES)
    assert provider.calls == 2


def synthetic_config():
    return {"providers": {"first": {"models": {MODEL: SPEC}}, "second": {"models": {MODEL: SPEC}}},
            "roles": {"extract": {"chain": [{"provider": "first", "model": MODEL}, {"provider": "second", "model": MODEL}]}},
            "profiles": {"demo_live": {"extract": {"chain": [{"provider": "second", "model": MODEL}]}}}}


def test_router_falls_back_on_quota_exhausted():
    calls = []

    def factory(provider, model):
        calls.append(provider)
        if provider == "first":
            raise QuotaExhausted("Synthetic exhausted quota")
        instance = FakeProvider()
        instance.provider = provider
        return instance

    result = get_provider("extract", config=synthetic_config(), factory=factory).generate(MESSAGES)
    assert calls == ["first", "second"]
    assert result.provider == "second" and result.model == MODEL


def test_profile_overrides_role():
    calls = []

    def factory(provider, model):
        calls.append(provider)
        instance = FakeProvider()
        instance.provider = provider
        return instance

    result = get_provider("extract", profile="demo_live", config=synthetic_config(), factory=factory).generate(MESSAGES)
    assert calls == ["second"] and result.provider == "second"


def test_ollama_json_fallback_validates_schema():
    requests = []
    content = {"text": "", "tool_calls": [{"name": "lookup", "arguments": {"city": "Synthetic City"}}]}

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(content)}, "done": True, "done_reason": "stop", "prompt_eval_count": 5, "eval_count": 7})

    provider = OllamaProvider(MODEL, {**SPEC, "supports": {"tools": False}}, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.generate(MESSAGES, tools=[TOOL])
    assert result.tool_calls[0].arguments == {"city": "Synthetic City"}
    assert "tools" not in requests[0] and isinstance(requests[0]["format"], dict)
    assert result.tokens_in == 5 and result.tokens_out == 7
    content["tool_calls"][0]["arguments"] = {"city": 7}
    with pytest.raises(InvalidOutput):
        provider.generate(MESSAGES, tools=[TOOL])
    provider.spec = SPEC
    content["tool_calls"][0]["arguments"] = {"city": "Synthetic City"}
    assert provider.generate(MESSAGES, tools=[TOOL], tool_mode="json").tool_calls


def test_gemini_adapter_maps_tool_calls():
    requests = []
    raw = {"candidates": [{"content": {"parts": [{"function_call": {"name": "lookup", "args": {"city": "Synthetic City"}, "id": "synthetic-call"}}]}, "finish_reason": "STOP"}],
           "usage_metadata": {"prompt_token_count": 8, "candidates_token_count": 4, "cached_content_token_count": 2}, "response_id": "synthetic-response"}

    def generate_content(**kwargs):
        requests.append(kwargs)
        return raw

    provider = GeminiProvider(MODEL, SPEC, client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    result = provider.generate(MESSAGES, tools=[TOOL])
    assert result.tool_calls[0].name == "lookup" and result.tool_calls[0].id == "synthetic-call"
    assert result.tokens_in == 8 and result.tokens_out == 4 and result.cached_tokens == 2
    assert result.raw_id == "synthetic-response" and result.provider == "gemini"
    assert requests[0]["model"] == MODEL
    assert requests[0]["config"]["automatic_function_calling"] == {"disable": True}
    assert requests[0]["config"]["tools"][0]["function_declarations"][0]["parameters_json_schema"] == TOOL["parameters"]


def test_no_model_names_hardcoded():
    # Word boundary excludes the provider name 'ollama' while detecting its model family.
    pattern = re.compile(r"gemini-|\bllama", re.IGNORECASE)
    root = Path(__file__).resolve().parents[1] / "backend"
    offenders = [str(path.relative_to(root)) for path in root.rglob("*.py") if pattern.search(path.read_text())]
    assert offenders == []
    config = load_config()
    for entry in config["roles"]["extract"]["chain"]:
        assert model_config(entry["provider"], entry["model"], config)["limits"]


def test_streaming_retries_only_before_first_event():
    class Broken(FakeProvider):
        def generate(self, *args, **kwargs):
            yield Event(type="text_delta", text="Synthetic partial")
            raise ProviderUnavailable("Synthetic disconnect")

    calls = []

    def factory(provider, model):
        calls.append(provider)
        return Broken()

    stream = get_provider("extract", config=synthetic_config(), factory=factory).generate(MESSAGES, stream=True)
    assert next(stream).text == "Synthetic partial"
    with pytest.raises(ProviderUnavailable):
        next(stream)
    assert calls == ["first"]


def test_gemini_stream_maps_usage_and_done():
    raw = [{"candidates": [{"content": {"parts": [{"text": "Synthetic hello"}]}}]},
           {"candidates": [{"finish_reason": "STOP"}], "usage_metadata": {"prompt_token_count": 2, "candidates_token_count": 3}}]
    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=lambda **kw: iter(raw)))
    events = list(GeminiProvider(MODEL, SPEC, client).generate(MESSAGES, stream=True))
    assert [event.type for event in events] == ["text_delta", "usage", "done"]
    assert events[-1].response.text == "Synthetic hello" and events[-1].response.tokens_out == 3


def test_ollama_stream_and_structured_output():
    def handler(request):
        return httpx.Response(200, text='{"message":{"content":"{\\"ok\\":true}"},"done":false}\n{"message":{"content":""},"done":true,"eval_count":3,"done_reason":"stop"}\n')
    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = list(OllamaProvider(MODEL, SPEC, client=client).generate(MESSAGES, stream=True, response_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}))
    assert events[-1].response.text == '{"ok":true}' and events[-1].response.tokens_out == 3


def test_recording_requires_opt_in_and_key(monkeypatch):
    from backend.llm.record_fixtures import main
    with pytest.raises(SystemExit, match="Recording disabled"):
        main()
    monkeypatch.setenv("RECORD", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="M3"):
        main()


def test_gemini_stream_rejects_truncation_and_invalid_tools():
    raw = [{"candidates": [{"content": {"parts": [{"text": "Synthetic partial"}]}}]}]
    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=lambda **kw: iter(raw)))
    with pytest.raises(ProviderUnavailable, match="finish reason"):
        list(GeminiProvider(MODEL, SPEC, client).generate(MESSAGES, stream=True))
    raw[:] = [{"candidates": [{"content": {"parts": [{"function_call": {"name": "undeclared", "args": {}}}]}, "finish_reason": "STOP"}]}]
    stream = GeminiProvider(MODEL, SPEC, client).generate(MESSAGES, tools=[TOOL], stream=True)
    with pytest.raises(InvalidOutput, match="undeclared"):
        next(stream)


def test_gemini_structured_output_uses_documented_sdk_config():
    requests = []
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}

    def generate_content(**kwargs):
        requests.append(kwargs)
        return {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}, "finish_reason": "STOP"}]}

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    result = GeminiProvider(MODEL, SPEC, client).generate(MESSAGES, response_schema=schema)
    assert json.loads(result.text) == {"ok": True}
    assert requests[0]["config"]["response_json_schema"] == schema
    assert requests[0]["config"]["response_mime_type"] == "application/json"


def test_retry_on_server_error_and_each_attempt_consumes_daily_quota():
    class Flaky(FakeProvider):
        def generate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise status_error(503)
            return Response(provider=self.provider, model=self.model, text="Synthetic recovered")
    counter, provider = FakeCounter(), Flaky()
    delays = []
    managed = ManagedProvider(provider, SPEC, SETTINGS, counter=counter, bucket=TokenBucket(100, None),
                              retry_options={"attempts": 2, "sleep": delays.append, "jitter": lambda: 0})
    assert managed.generate(MESSAGES).text == "Synthetic recovered"
    assert counter.count == provider.calls == 2 and len(delays) == 1


def test_streaming_router_falls_back_before_first_event():
    def factory(provider, model):
        if provider == "first":
            raise RateLimited("Synthetic throttle")
        result = FakeProvider()
        result.provider = provider
        return result
    events = list(get_provider("extract", config=synthetic_config(), factory=factory).generate(MESSAGES, stream=True))
    assert events[-1].response.provider == "second"


def test_quota_day_uses_los_angeles(monkeypatch):
    from datetime import datetime, timezone
    import backend.llm.limits as limits
    instant = datetime(2027, 3, 1, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(limits, "datetime", SimpleNamespace(now=lambda zone: instant.astimezone(zone)))
    assert limits.quota_day().isoformat() == "2027-02-28"


def test_official_google_sdk_with_mock_http_transport():
    from google import genai
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "lookup", "args": {"city": "Synthetic City"}}}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 3}, "responseId": "synthetic-sdk-response"})

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = genai.Client(api_key="synthetic-unit-test-key", http_options={"httpx_client": transport_client, "retry_options": {"attempts": 1}})
    try:
        result = GeminiProvider(MODEL, SPEC, client).generate(MESSAGES, tools=[TOOL])
        assert result.tool_calls[0].arguments == {"city": "Synthetic City"}
        assert result.tokens_in == 6 and result.tokens_out == 3
        assert requests[0]["tools"][0]["functionDeclarations"][0]["name"] == "lookup"
    finally:
        client.close()
