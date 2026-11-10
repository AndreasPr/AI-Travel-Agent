# Threat model and guardrails

The planner is not immune to prompt injection. The changes here reduce specific attack paths and bound resource use; they do not establish that an arbitrary model will correctly interpret every request or adversarial document.

## Assets

Provider quotas, local compute, Postgres availability, stored conversations/preferences/itinerary versions, tool-result provenance, budget constraints, source attribution, and user contact/payment information. Provider keys remain environment configuration; they are never prompt inputs. Synthetic inventory remains labeled synthetic and is not booking availability.

## Trust boundaries

1. Browser → FastAPI: request bodies, notes, trip IDs and arbitrary headers are untrusted. Messages are limited to 12,000 characters; raw `/api/` bodies are limited to 65,536 bytes before JSON parsing. Invalid request responses do not echo the rejected input.
2. User request → model: common PII is redacted before the agent sees or persists it. Quoted notes/code/role-like markup do not authorize tool arguments or budgets. Current request constraints and previously saved server state are separate from retrieved text.
3. Retrieved chunks and external tool output → model: HTML/markdown and hidden Unicode are sanitized; tool output remains in escaped DATA delimiters. Every generation role receives a system rule that these are data, never instructions. Delimiters are structural boundaries, not a complete defense.
4. Model → tools: the model proposes a call. The intent allowlist, current-step permission set, argument provenance checks and the tool runtime's Pydantic schema must permit execution. The model cannot call the final validator or invent a new tool. Rejected calls become structured observations and safe progress events.
5. Model → saved itinerary/public answer: the existing deterministic itinerary validator checks price/evidence, budget, dates, overlaps and coordinates. The new gate rejects unknown URLs, PII and known instruction-like text in itinerary fields. Server-authored final messages have an exact returned-URL allowlist. No raw model explanation is streamed.
6. Process → shared counters: Postgres transactions atomically admit all applicable subjects or none. In-memory counters implement the same interface for local/test use. A new migration creates `security_usage`.

## Threats and mitigations

| Threat | Implemented mitigation | Residual limitation |
|---|---|---|
| Retrieved prompt injection | Strip HTML, scripts/styles, markdown links/images and suspicious schemes; remove hidden/control/bidirectional Unicode; cap excerpts at 600 characters; DATA boundaries; system rules | Ordinary prose can still carry malicious instructions, Unicode confusables remain, and heuristics can remove legitimate formatting |
| Tool abuse / forged results | Intent and per-step allowlists; calls limited by existing step/parallel limits; argument values require user text or allowlisted structured earlier-result fields; retrieved excerpts/titles/URLs never supply argument facts; server ledger supplies evidence IDs | Literal value matching is not a semantic authorization proof. Structured upstream results are trusted as facts and may be wrong or compromised. Some valid requests now need more explicit arguments |
| Attacker-controlled search query | Retrieval query is reconstructed from sanitized user request context, not model-supplied retrieved prose | Broad user queries may reduce retrieval quality; legitimate city/field inference is deliberately restricted |
| Arbitrary flight search | Flight permission needs an explicit flight request and `from CODE` or `origin CODE`; the proposed origin must match | IATA syntax does not establish that a flight exists; inventory lookup can return no data |
| Budget escalation / fabricated discount | Budget parsed from explicit request text before notes, not classifier-generated numbers; preference budget proposals checked likewise; existing price equality/quote binding stays active | Parsing supports explicit numerical budgets, not every natural-language currency expression. Budgets across currencies are not inferred |
| Phishing / URL exfiltration | Exact HTTP(S) URL allowlist from sanitized tool citation metadata; unknown URLs rejected in itinerary and removed from public message text; unsafe-scheme/credential/PII URLs rejected | A malicious URL already present in trusted source metadata is allowed. An allowlisted site may redirect after a user clicks. This is not a safe-browsing service |
| System-prompt exfiltration | No tools expose environment/files/system messages; system refusal rule; fixed final message text; known instruction-like itinerary content rejected | Pattern matching cannot prove arbitrary paraphrases are harmless. The system prompt is not a place to store secrets |
| PII | Local regex redaction for email/phone/card-like numbers in input and standard Python log messages, exceptions and structured extras; existing sensitive-state checks retained; narrow unsafe-request policy in `config/safety.yaml` | Regex has false positives and false negatives, especially unusual international formats/obfuscation. Existing stored data is not retroactively scrubbed. Browser-local drafts/history and third-party logs outside Python logging are separate boundaries. No Presidio dependency or external PII service is used |
| SSRF | Chat tools use fixed weather/currency endpoints and operator-configured Nominatim URL; model cannot supply a fetch URL; HTTP client disables redirects | Operator environment, ingestion/crawling jobs, DNS and upstream service compromise are outside this guard. There is no general-purpose browse/fetch tool in this agent |
| Cost abuse / runaway generation | Session request/token ceilings, daily per-user ceilings, per-turn token ceiling; admission before model calls; conservative reservation includes configured retry/fallback count and max output; existing step/deadline limits | Reservations are conservative estimates, not exact billing. Provider noncompliance with output ceilings or unusual hidden token accounting is not proven bounded. Cancelled/failed dispatched calls retain their reservation |
| API abuse | Fixed-window per-peer and per-user rate limits on chat, stream, versions and Undo; 429 with Retry-After before streaming; atomic memory/Postgres interfaces; body-size guard | Fixed windows permit boundary bursts. Slow uploads and connection exhaustion need ingress timeouts. Counter retention/cleanup and database capacity require operations monitoring |
| Provider daily quota exhaustion | Existing atomic `llm_usage_daily` guard and Router fallback are reused; exhausted provider is not called | Remaining quota is local accounting, not authoritative provider metering; external use of the same key can cause earlier provider rejection |

## Identity and rate limiting

The application currently has **no login/authentication system and no trip ownership authorization**. A verified ASGI authentication principal is used when installed by authentication middleware. Otherwise users are anonymous and share a user bucket by their peer network address. `X-User-ID` and `X-Forwarded-For` are not read as authority by this code. Configure trusted reverse proxies correctly: ASGI peer identity may already have been rewritten by server/proxy middleware.

Raw peer addresses and authenticated identities are not stored in the counter table; SHA-256 subject keys are used. These are pseudonyms, not encryption or anonymization: low-entropy addresses can be guessed. Anonymous NAT users share caps; distributed clients can evade a single-IP cap. Access control for trip IDs remains a separate prerequisite before exposing this product to untrusted users. Knowing a trip UUID currently permits reading/editing it, including consuming its session allowance.

`PostgresTripStore` agents use Postgres counters. Memory/SQLite test agents use process-local counters, which reset with the process and are not a multi-worker limiter. The counter interface is in `backend/security/limits.py`. Session quotas are lifetime totals by trip ID; user quotas use UTC days; API rate windows are fixed intervals from Unix time. The provider's existing daily quota continues to use America/Los_Angeles. Old time-window counter rows are not automatically purged; add a retention job before prolonged public operation.

Admission consumes a request even for refusals. Model token admissions reserve UTF-8 serialized payload bytes plus the output ceiling, multiplied by configured retry count and role chain length. Those estimates are deliberately retained rather than refunded after failed/cancelled calls, so restarting the server or cancelling requests does not reset Postgres usage. Provider-reported tokens remain available separately in response usage. A `usage_limit` terminal SSE error identifies local usage denial; provider quota/rate errors retain their existing codes.

## Security regression suite

`tests/security/injections.jsonl` contains 26 **synthetic** adversarial cases. The cases cover discounts, prompt extraction, attacker flight arguments, phishing, hidden Unicode, forged results/system messages, data URLs, image beacons, tool spoofing, budget increases and validator bypass. `tests/security/scenarios.py` replays synthetic response fixtures through `ReplayProvider`, checks actual tool invocations and requires a validated final itinerary with the trusted synthetic quote and user budget. It does not claim these are live recordings. The expected adversarial responses are supplied deliberately; passing demonstrates application checks for these inputs, not a measured model attack-success rate.

```bash
source venv/bin/activate
export PYTHONPATH=.
make test-security
make security-report
make lint
pytest -q
```

The named required tests are `test_sanitizer_strips_invisible_unicode`, `test_sanitizer_blocks_bad_url_schemes`, `test_url_allowlist_removes_unknown_links`, `test_tool_args_not_copied_from_retrieved_text`, `test_tool_allowlist_per_intent`, `test_injection_suite_all_cases_safe_offline`, `test_runaway_loop_stopped_by_token_cap`, `test_rate_limit_returns_429_with_retry_after`, `test_pii_redacted_in_logs`, and `test_quota_guard_switches_provider`.

## M8 — Migration and optional live security run

Keep the existing database volumes. Apply the new migration before starting this version of the API:

```bash
source venv/bin/activate
export PYTHONPATH=.
python -m alembic -c backend/alembic.ini upgrade head
pytest -q -m integration tests/security/test_limits_integration.py tests/test_agent_persistence.py
```

For the Docker API, rebuild the API image with `docker compose up --build -d api`, then use `make migrate` instead of the host Alembic command. The rate-limited endpoints fail closed while the counter table is missing. No new keys, signup or model download is required. Set limits under `guardrails` in `config/models.yaml`; API body size is also configured there.

The optional manual runner calls only the **configured local Ollama provider**, using the same synthetic poisoned tool runtime and safety checks. It consumes local model time; no Gemini key or `RECORD=1` is needed. The existing provider daily-counter tables must be migrated. The full run has 26 cases and can be slow:

```bash
export OLLAMA_BASE_URL=http://localhost:11434
make security-live
# Or run one case first:
RECORD=0 LLM_REPLAY=0 python tests/security/report.py --live --case discount
```

Do not mix live and offline report numbers. Missing/invalid final plans are reported as failed scenarios, not automatically counted as successful defenses. Live mode does not use the scripted malicious provider responses and can reveal additional failure modes. **Live security/model testing is not run as part of unit tests.**

## Live discount-case follow-up

A local Ollama run initially failed because no final itinerary was accepted: the deterministic gate reported `requested_citations_missing`. Retrieved chunks existed, but the unpriced activity schema required citation IDs only when named-place extraction had run. The generation schema now also requires a nonempty retrieved-ID list when retrieval was requested and chunks exist. The final validator remains unchanged.

The report now names the failed invariant and emits allowlisted issue/tool-error codes and executed tool names, without raw model replies or arguments. Numerically equivalent representations of the synthetic quote (for example 100 and 100.000) are compared as decimals.

After this change, one live local `discount` run passed. The full live suite was **not run**. A single passing run does not establish consistent model behavior or immunity to prompt injection.

## User-notes follow-up

A user-reported full live run passed 25 scenarios and failed `user-notes` at the step limit. Unrequested optional tools were still exposed to the planner, and current-turn notes appeared in the same text field as actionable instructions. Notes now appear in an escaped DATA block separate from the request, and active tool definitions exclude optional geocoding/weather/currency/flights unless authorized by the request outside notes. One targeted live local `user-notes` run passed after this change; the full live suite was not rerun.
