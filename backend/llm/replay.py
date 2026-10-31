"""Offline fixture playback and opt-in recording of normalized responses."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from backend.llm.types import InvalidOutput, Response, response_events
from backend.llm.validation import schema_dict, validate_response

FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures/llm"


def fixture_key(provider, model, messages, tools=None, schema=None):
    payload = {"provider": provider, "model": model, "messages": messages, "tools": tools, "schema": schema_dict(schema)}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def sanitize(value, secrets=()):
    if isinstance(value, dict):
        return {key: sanitize(item, secrets) for key, item in value.items()
                if not any(word in key.lower().replace("-", "_") for word in ("header", "api_key", "authorization", "password", "secret", "access_token", "refresh_token"))}
    if isinstance(value, list):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted((secret for secret in secrets if secret), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [REDACTED]", value)
        value = re.sub(r"AIza[\w-]+", "[REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", value)
    return value


class ReplayProvider:
    def __init__(self, provider, model, fixtures_dir=FIXTURES):
        self.provider, self.model = provider, model
        self.fixtures_dir = Path(fixtures_dir)

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        key = fixture_key(self.provider, self.model, messages, tools, response_schema)
        path = self.fixtures_dir / f"{key}.json"
        if not path.exists():
            raise InvalidOutput(f"Missing replay fixture: {path.name}; replay never calls the network")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            response = Response.model_validate(payload["response"])
        except (ValueError, KeyError) as exc:
            raise InvalidOutput("Invalid replay fixture") from exc
        if (response.provider, response.model) != (self.provider, self.model):
            raise InvalidOutput("Replay fixture provider/model mismatch")
        validate_response(response, tools, response_schema)
        return response_events(response) if stream else response


class Recorder:
    def __init__(self, provider, fixtures_dir=FIXTURES, secrets=()):
        self.inner = provider
        self.provider, self.model = provider.provider, provider.model
        self.fixtures_dir = Path(fixtures_dir)
        self.secrets = tuple(secrets)

    def _write(self, key, response):
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        secrets = self.secrets + tuple(value for name, value in os.environ.items()
                                      if any(term in name.upper() for term in ("KEY", "TOKEN", "SECRET", "PASSWORD")))
        payload = {"provenance": "recorded", "response": sanitize(response.model_dump(mode="json"), secrets)}
        fd, temporary = tempfile.mkstemp(dir=self.fixtures_dir, prefix=".recording-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(temporary, self.fixtures_dir / f"{key}.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def generate(self, messages, tools=None, response_schema=None, stream=False, **opts):
        enabled = os.getenv("RECORD") == "1"
        key = fixture_key(self.provider, self.model, messages, tools, response_schema)
        result = self.inner.generate(messages, tools=tools, response_schema=response_schema, stream=stream, **opts)
        if not stream:
            if enabled:
                self._write(key, result)
            return result

        def events():
            for event in result:
                if event.type == "done" and enabled:
                    self._write(key, event.response)
                yield event
        return events()


class ClaudeProvider(ReplayProvider):
    """Replay-only Anthropic adapter. Live calls are deliberately unavailable."""
    def __init__(self, model, fixtures_dir=FIXTURES):
        super().__init__("claude", model, fixtures_dir)


class BedrockProvider(ReplayProvider):
    """Replay-only Bedrock adapter. No AWS client or credential lookup."""
    def __init__(self, model, fixtures_dir=FIXTURES):
        super().__init__("bedrock", model, fixtures_dir)
