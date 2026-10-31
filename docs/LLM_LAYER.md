# Provider-independent LLM layer

`backend/llm/` exposes `get_provider(role, profile=None)` and an `LLMProvider` protocol. Model IDs, capabilities, limits and role/profile chains are read from `config/models.yaml`. No model IDs are embedded in backend code. Gemini and local Ollama are the live paths. ClaudeProvider and BedrockProvider are deliberately replay-only and unverified against provider recordings until those recordings exist; they never instantiate paid-service clients.

## Interface

```python
from backend.llm import get_provider

provider = get_provider("extract")
response = provider.generate([{"role": "user", "content": "say hi"}])
print(response.text, response.provider, response.model)
```

Messages use role/content dictionaries. Tool declarations accept either `{name, description, parameters}` or an OpenAI-style function wrapper. Tool messages for Gemini must include their function `name`. A response schema can be a JSON Schema dictionary or a Pydantic model class. The response carries text, tool_calls, tokens_in, tokens_out, cached_tokens, latency_ms, provider, model, finish_reason and raw_id. Unreported token counts default to zero, not an independent token measurement. Tool arguments and structured outputs are validated locally.

`generate(..., stream=True)` returns an iterator of `text_delta`, `tool_call`, `usage`, and `done` events. `done.response` contains the complete normalized response. Native text deltas are provisional until done; structured JSON is validated at completion. Tool-call events are delayed until argument validation succeeds. JSON fallback buffers its envelope before emitting normalized events. Replay emits a coalesced text event, not original token timing.

No adapter executes tools. The caller owns tool execution and conversation history. Native tool mode does not guarantee a tool call; Ollama callers can force `tool_mode="json"` for weak tool support. Models configured with supports.tools=false automatically use that validated envelope fallback. Ollama structured JSON uses the local API's format schema even when native structured_output support is not advertised.

## SDK and transports

Gemini uses the official `google-genai` SDK, `client.models.generate_content` and `generate_content_stream`, JSON-schema response configuration, and function declarations. Automatic function execution and SDK-level retries are disabled. The wrapper owns quota admission and retries. SDK 2.34.0 requires updated shared dependencies; requirements pins Pydantic 2.12.5, typing-extensions 4.14.1 and cffi 2.1.1. Pydantic selects its own exact pydantic-core dependency.

References: [official Google SDK documentation](https://googleapis.github.io/python-genai/), [SDK release dependencies](https://github.com/googleapis/python-genai/blob/v2.34.0/pyproject.toml), [Ollama chat API](https://docs.ollama.com/api/chat).

Ollama uses POST /api/chat with HTTP or NDJSON streaming. OLLAMA_BASE_URL must identify loopback or the local `ollama` service; it does not route to a paid cloud endpoint. Default is the local service port. Live Gemini requires an exported GEMINI_API_KEY belonging to a free-tier project; do not enable billing for this workflow. Environment values are not printed. The CLI does not load shell variables from .env automatically.

## Quotas, retries and routing

Effective rpm, tpm and rpd are floored after multiplying by safety_margin (default 1.0 when absent). Null means unlimited for that dimension. Request and token buckets are shared per provider/model within a process, guarded by a lock, and fail with RateLimited when insufficient capacity exists. Tokens are conservatively reserved using serialized request UTF-8 byte length plus the requested output ceiling; successful usage reconciles that reservation. This estimate is not the provider's tokenizer. Multiple worker processes do not share minute buckets; use one worker or add a shared minute limiter before scaling.

`llm_usage_daily` stores committed request reservations keyed by America/Los_Angeles calendar date, provider and model. Atomic conditional upserts prevent concurrent over-admission and survive restarts. Requests are reserved before each attempted provider invocation, including retries; failed invocations are conservatively counted and not refunded. Providers with null rpd bypass daily counting and report remaining quota as null. Quota storage failure prevents the limited provider from being called and allows router fallback. Migrations are required before using a daily-limited provider.

429/5xx failures use bounded exponential backoff with jitter and respect Retry-After seconds or HTTP dates. Ordinary 4xx errors become InvalidOutput and are not retried. QuotaExhausted, RateLimited and ProviderUnavailable fall through the configured role chain. Profiles replace the corresponding role chain. Streams retry/fall back only before their first emitted event; later failures propagate, preventing mixed or duplicated output.

The public adapters provide transport normalization. Application callers should use `get_provider` or `ManagedProvider` so quota/retry policy is applied; direct raw adapter calls bypass that policy.

## Replay and recording

Fixture filenames are SHA-256 hashes of canonical provider, model, messages, tools and schema. Sampling options are not included in this key, so a fixture represents one captured outcome for those inputs. Missing or malformed fixtures raise InvalidOutput and never cause a network fallback. Set LLM_REPLAY=1 to route configured live-provider identities through replay.

The checked-in replay fixture is explicitly synthetic unit-test data, not a provider recording. Claude/Bedrock model lists are empty until actual recorded model IDs can be added to configuration. Their live adapters and provider response fidelity remain unverified.

Recorder writes normalized fields only: no request messages, raw SDK payloads or transport headers. It recursively removes credential fields and redacts credential-like strings and known environment secret values. It writes only when RECORD=1 and only saves completed streams. Redaction cannot establish that arbitrary model text contains no personal data; review recordings before committing. Replay fixtures retain captured token counts/latency, not newly measured usage.

## Commands

```bash
source venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
make test-llm
PYTHONPATH=. pytest -q -m integration tests/test_llm_integration.py
python -m backend.llm.cli --role extract --show-limits
python -m backend.llm.cli --role extract --prompt "say hi"
# Optional: add --provider and --model using values already declared in models.yaml.
```

The integration tests use a separate temporary schema and remove it afterward. They never call a model. Existing database migrations are not automatically applied by tests.

M3 in MANUAL_STEPS.md covers optional real recording. `RECORD=1 python -m backend.llm.record_fixtures` requests five short responses using the first configured extract provider. Missing opt-in/key stops before calls. A partial failure can leave fewer than five completed fixtures; success prints the count only after all five complete. No real fixtures are required for unit tests.
