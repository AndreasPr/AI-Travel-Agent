# Test suite

All synthetic scenarios are **scripted tests of the pipeline**, not model behavior.
They do not establish live model quality. Real recordings remain under tests/fixtures/llm
and eval/fixtures/recorded; synthetic data stays under tests/fixtures/synthetic.

## Offline checks

From the repository root, activate your existing environment, then:

```sh
python -m pip install -r requirements-dev.txt
make lint
make typecheck
python -m pytest -q
make test-ci
make test-contract
npm test -- --run
npm run build
```

pytest.ini adds the repository to Python's import path, so a new terminal does not
need a separate PYTHONPATH export. Default tests exclude integration, e2e and live.
Directories classify tests; mixed SQLite/Postgres parameterizations retain their
explicit integration marks. Existing assertions are preserved during relocation.

CI enforces .coveragerc's 70% floor across backend/ with branch coverage enabled.
Ruff checks the repository; mypy checks backend/ with incremental non-strict typing.
The only targeted mypy exemption covers heterogeneous SQLAlchemy migration types.
Tool and chat/SSE schemas are committed snapshots. Update them deliberately after
reviewing API compatibility; tests never rewrite snapshots.

## Disposable Postgres

Start Docker Desktop, then `make test-containers`. Testcontainers starts a separate
pgvector database, applies all migrations and removes it after the test. It never
connects to your project database. The synthetic test ingests tiny synthetic content,
uses synthetic vectors for SQL vector retrieval (not semantic quality), checks FTS,
seeds inventory twice, authenticates a user, runs the actual agent/validation/store
pipeline, and verifies quota rejection. The distinct real-recorded full-chat test
currently skips because greeting recordings do not cover an entire chat.

Other existing integration tests still target your configured project Postgres;
run them explicitly with `python -m pytest -m integration tests/` only when that
stack and its existing prerequisites are available.

## Synthetic browser smoke (M13)

```sh
python -m playwright install chromium
export TEST_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose -f compose.test.yaml up --build -d --wait
make test-e2e
```

The isolated project uses API port 18100 and web port 13100, a temporary database,
no .env file, no provider credentials and LLM_STUB=1 plus TEST_SUITE_MODE=1.
Production refuses this mode. It uses the normal authenticated endpoints, agent loop,
tool runtime, validator, store and SSE serializer. Only model responses and retrieved
content are scripted synthetic inputs. No model downloads or external tool calls.
The scenario is fixed; arbitrary prompts are not supported in this test mode.

Playwright registers and logs in, sends the synthetic request, checks progress,
itinerary cards and the citation dialog. All test identities use example.invalid.
Stop and remove **only this test project** after testing:

```sh
docker compose -f compose.test.yaml down
unset TEST_JWT_SECRET
```

## SSE load check (M13)

Install free local k6 (for example `brew install k6` on macOS), keep the isolated
stack running, and run:

```sh
PERF_SESSIONS=2 PERF_HOLD=10s make perf
```

PERF_SESSIONS controls the ramp target N. Tests use the k6 browser module and read
the streamed body incrementally; time to first token is measured at the first token
event, not the first HTTP response byte. The local Chromium load generator adds
resource overhead. Quotas and login throttling remain enabled; larger N may correctly
produce 429s, which count as errors. This is not an unlimited throughput benchmark.
The wrapper verifies the isolated running API has the synthetic stub enabled.

Results are written to perf/results/*-synthetic.json with actual OS/architecture/CPU
information; set PERF_HARDWARE_DESCRIPTION for Docker CPU/RAM allocation and machine
details. Do not include names, addresses or credentials. JSON numbers describe that
specific machine and configuration only. No paid service or model quota is used.
See [k6 browser documentation](https://grafana.com/docs/k6/latest/using-k6-browser/).

## Recording (M3, optional)

`make record` re-records the five provider smoke fixtures only when you explicitly
choose. Export GEMINI_API_KEY privately first; missing credentials stop with M3.
It is never part of tests or CI. `make eval-record` separately captures evaluation
outputs; they are not interchangeable with exact-request ReplayProvider fixtures.
A full recorded chat needs its matching request transcript and tool ledger; until
available, that coverage is reported skipped, never replaced by synthetic results.
