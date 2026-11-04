# Streaming chat

`POST /api/chat/stream` accepts the same `{trip_id?, message}` body as `POST /api/chat`. Both call `Agent.chat`; the original endpoint still returns its JSON `ChatResponse`. Streaming adds an optional event sink to that loop. Event models are in `backend/agent/events.py`.

Each SSE data object has a server-generated `request_id` and `type`. The response also exposes `X-Request-ID`. SSE comments (`: heartbeat`) are sent every 15 seconds while waiting. Proxy buffering and transformation are disabled by response headers; deployment proxies must respect these headers.

| Event | Data |
| --- | --- |
| `message_start` | Request ID and supplied trip ID, if any |
| `tool_start` | Generated call ID, tool name, recognized argument field names and number of omitted fields; no argument values |
| `tool_end` | Matching call ID, tool name, `ok`/`no_data`/`error`, elapsed milliseconds |
| `token` | A partial segment of the final user-facing message |
| `itinerary_update` | Validated, saved itinerary and optional validated edit diff |
| `citations` | The final citation list |
| `done` | Trip ID, complete message, usage, budget status and preference proposal |
| `error` | Typed error code, fixed user-safe message and usage collected before failure |

A connected stream ends in exactly one `done` or `error` event. Parallel tools may interleave; correlate start/end by call ID. The final text is emitted only after validation and storage. `token` events are chunks of the server-authored final message, not raw model generation tokens. Intermediate model JSON and tool results remain private so unvalidated prices cannot escape the final validation gate. The `usage` fields report provider token counts, independent of the number of SSE text chunks.

Input validation failures before streaming begins return the normal FastAPI HTTP error response. After streaming starts, failures are SSE `error` events, not a changed HTTP status. `budget_met=false` with an otherwise-valid itinerary is a successful `done`; unpriced activities leave `budget_met=null`.

## Cancellation and quotas

The response watches `http.disconnect` and handles failed socket sends. Either cancels and joins the request's producer, agent task and async provider call, then closes its event generator. A disconnected client cannot receive a terminal event; the server does not continue the planning loop to manufacture one. The queue is bounded to 32 events. The entire streaming turn has `agent.request_timeout_seconds` in `config/models.yaml` (currently 900 seconds), in addition to the existing per-model and per-tool deadlines.

Ollama uses an owned `httpx.AsyncClient`; Gemini uses the official SDK's async client context manager. Cancellation closes the client request and prevents retries or provider fallback. Remote cancellation does not prove that the provider consumed no quota. Failed/cancelled daily admission refunds the local minute reservation; the database reservation transaction rolls back when cancelled before admission. Once admitted for provider execution, the daily request remains counted. Successful responses reconcile estimated minute tokens with reported usage. If execution ends without usage, the conservative minute charge is retained and refills normally; it is not a permanent lock or outstanding lease. Missing Gemini credentials fail preflight without consuming admission quota.

Tool workers receive a cooperative cancellation signal. Queued work is cancelled, pauses wake immediately, and completed handlers check cancellation before storing results. An already-running blocking tool operation may finish its current bounded operation; Python cannot forcibly terminate a thread. It cannot resume the cancelled agent or start another provider call. An itinerary transaction already committed before a disconnect remains saved: check versions before retrying an edit.

The async SDK usage follows [Google Gen AI's client lifecycle documentation](https://googleapis.github.io/python-genai/#client-context-managers). Async quota transactions use the already-installed driver, following [psycopg's async transaction/cancellation API](https://www.psycopg.org/psycopg3/docs/advanced/async.html). No new dependency or migration is required.

## M6 — Local streaming check

With your existing Postgres, inventory, retrieval corpus and configured local model ready (M4/M5), start a host-run backend:

```bash
source venv/bin/activate
export PYTHONPATH=.
export OLLAMA_BASE_URL=http://localhost:11434
export RECORD=0 LLM_REPLAY=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
unset GEMINI_API_KEY
python -m uvicorn backend.main:app --host localhost --port 8082
```

In another activated shell, run:

```bash
python -m backend.agent.stream_cli \
  'Plan five days in Lisbon from 2027-04-10 through 2027-04-14 under $1,500 USD, with museums and food. Use synthetic hotel quotes and leave unknown activity costs unpriced.' \
  --url http://localhost:8082/api/chat/stream
```

The CLI prints UTC timestamps, comments and events. It exits with status 1 for an error event or a stream missing its terminal event, and 130 on Ctrl+C. Use `--trip-id` for follow-up messages. To exercise cancellation, repeat a request and press Ctrl+C while waiting for the model or a tool. Do not interpret absence of a final event after deliberately disconnecting as an application protocol failure.

Offline checks:

```bash
make test-streaming
make lint
pytest -q
```

Postgres-only quota checks (isolated schemas; no model calls):

```bash
pytest -q --tb=short -m integration tests/test_llm_integration.py
```

The streaming unit tests use synthetic scripted responses, synthetic ReplayProvider fixtures and mocked HTTP/SDK clients. No real model, network access or model download is used by unit tests. M3/Gemini fixture recording is not required.

## Verification performed

On 2026-11-03, the timestamped CLI completed a live local Ollama/Postgres request through the HTTP endpoint. It returned a validated five-day itinerary, citations, matched tool events, periodic heartbeat comments and a final `done`. A separate client disconnected during planning; no conversation turn or itinerary version was saved for that request, and a subsequent ordinary `/api/chat` call returned HTTP 200. Unknown activity costs remained unpriced. Gemini live calls, browser/proxy deployment and load testing were not run. The temporary local server was stopped after verification.
