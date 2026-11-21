# Free public demo and optional deep planning

This is a deployment guide, not evidence of a deployed or load-tested public service.
Use **Vercel Hobby + Render Free web service + Neon Free Postgres**. No card or paid
upgrade is required for this chosen setup; stop if any signup or creation screen asks
for payment. Do not enable billing for the Gemini project. Availability and free limits
can change: verify the linked official pages before creating resources.

The opt-in `PUBLIC_DEMO=true` profile uses **Postgres full-text search (fts), without
embeddings or cross-encoder reranking at runtime**. This is a smaller retrieval product,
not equivalent quality to local hybrid search. The full local configuration is unchanged.
The banner identifies free infrastructure and lightweight retrieval. `/api/config` reports
the configured primary plan provider/model, not a claim that the last call used it;
actual selections and fallback are recorded in response `usage.calls`.

## Free limits and prerequisites (checked 2026-11-20)

- [Vercel Hobby](https://vercel.com/docs/plans/hobby) is for personal, non-commercial
  projects. Use a personal repository supported by Hobby, not a paid team deployment.
- [Render Free](https://render.com/docs/free) sleeps after 15 minutes without traffic;
  cold starts can take roughly a minute. Disk is ephemeral. Free compute/time and outbound
  traffic are limited; exhaustion can suspend the app. The [free instance](https://render.com/pricing)
  has 512 MB RAM and 0.1 CPU. Run one API worker. Memory under real chat load is **not run**:
  measure it after deployment; do not solve exhaustion by enabling a paid instance.
- [Neon Free](https://neon.com/blog/neon-free-plan-1-gb-per-project) provides limited
  storage and compute; confirm the allowance displayed in your project before importing
  data. [pgvector is available](https://github.com/neondatabase/website/blob/main/content/faqs/enable-pgvector-extension.md).
  Compute can suspend while idle, adding database wake-up latency. Monitor storage,
  compute and transfer quotas; no paid upgrade or overage is part of this guide.
- [Vercel external rewrites](https://vercel.com/docs/routing/rewrites) keep refresh cookies
  same-origin. The [proxy timeout is 120 seconds](https://vercel.com/docs/limits).
  Demo chat and deep-plan deadlines are 100 seconds. A cold API/database plus planning
  may still exceed the proxy limit. Wake `/healthz` and `/readyz` before demonstration.
- Gemini availability/rpm/tpm/rpd come from your free project and `config/models.yaml`.
  Confirm those configured models are available free in your account. Daily quota survives
  restart in Postgres; exhausted free routes fail safely. This demo excludes local Ollama
  routes because Render does not run Ollama. No paid fallback is added.

## 1. Verify locally

From the repository root, activate your existing tested Python environment and Node 24:

```bash
npm ci
make lint
pytest -q
npm test
node scripts/validate_asl.cjs
```

These are offline tests, including synthetic scripted pipeline tests, not measurements
of model quality. The container workflow `.github/workflows/demo.yml` builds API and web
images, starts an isolated synthetic Compose stack, and checks `/healthz` and `/api/config`.
It requires no GitHub secrets. Its test database is temporary, separate from your own DB.

## 2. Create the database and prepare only a small corpus

1. Create a **Free** Neon project with Postgres 16. Copy its connection string privately.
   Use the direct connection for migrations; the pooled connection is suitable for API
   traffic. Both must require TLS (`sslmode=require`). Change the Python URL scheme to
   `postgresql+psycopg://`; keep the host, credentials and TLS options supplied by Neon.
2. In a new terminal, from the project root, activate the full local Python environment.
   Set the Neon URL without putting it in shell history:

   ```bash
   export DATABASE_URL="$(python -c 'import getpass; print(getpass.getpass("Neon SQLAlchemy URL: "))')"
   python -m alembic -c backend/alembic.ini upgrade head
   python -m backend.scripts.seed_inventory
   ```

   The migration creates pgvector; seeding produces labeled synthetic inventory, not
   booking availability. Confirm you selected the new demo DB before running commands.
3. Export `WIKIVOYAGE_USER_AGENT` with your application's actual contact information.
   Ingest just the first configured city (currently Lisbon):

   ```bash
   python -m backend.rag.ingest --max-pages 1
   ```

   This is an operator-run network/data operation, not a unit test. It uses local embedding
   models, potentially downloading them on your machine. The hosted API does not load them.
   Preserve source/license attribution. Do not upload private conversations or personal data.
4. In Neon SQL Editor verify `SELECT extname FROM pg_extension WHERE extname='vector';`,
   `SELECT count(*) FROM document_chunks;`, and `SELECT pg_size_pretty(pg_database_size(current_database()));`.
   Keep below your Free storage allowance. Other cities have synthetic inventory but no
   retrieved corpus until you explicitly ingest them. Unset `DATABASE_URL` in this terminal
   after setup so later local commands do not accidentally target the demo database.

## 3. Create the Render API

1. New **Web Service**, connect the repository/branch, choose **Docker** and **Free**.
   Dockerfile path: `backend/Dockerfile.demo`; build context: repository root.
   Use the Dockerfile command unchanged. It serves port 8080 with one worker.
   Health check path: `/healthz`. Do not add persistent disks or paid pre-deploy commands.
2. Set these environment variables in Render's dashboard (secrets stay out of git):

   | Variable | Value/purpose |
   |---|---|
   | `PUBLIC_DEMO` | `true` (FTS only, no embedding/rerank inference) |
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | Your Neon pooled SQLAlchemy URL with TLS |
   | `JWT_SECRET` | Generate privately with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`; store only as a secret |
   | `GEMINI_API_KEY` | Your free, billing-disabled project's key; required for live planning (M3) |
   | `FRONTEND_ORIGINS` | Exact Vercel production HTTPS origin, no trailing slash; update after step 4 |
   | `NOMINATIM_USER_AGENT` | Your application name and real operator contact, needed for geocoding |
   | `RECORD` | `0` |
   | `LLM_REPLAY` | `0` |
   | `LLM_STUB` | `0` |
   | `TEST_SUITE_MODE` | `0` |
   | `HF_HUB_OFFLINE` | `1` |
   | `TRANSFORMERS_OFFLINE` | `1` |
   | `OBS_CAPTURE_PROMPTS` | `false` |

   Optional variables: leave `OTEL_EXPORTER_OTLP_ENDPOINT` unset unless you have an
   existing free collector; leave `NOMINATIM_URL` unset for the default service;
   `OLLAMA_BASE_URL` is unused in this profile. `WIKIVOYAGE_USER_AGENT` is for the
   local import step only. No AWS credentials or additional provider keys are used.
   Until Vercel assigns your actual origin, leave the service undeployed rather than
   using a fabricated origin or wildcard CORS setting.
3. After step 4 gives you the frontend origin, set it and deploy the API. Copy Render's
   assigned HTTPS origin for `API_PROXY_URL`. Visit `/healthz`, then `/readyz`, then
   `/api/config`. Expect demo mode true, retrieval mode fts, and the configured primary
   Gemini model. Health alone does not verify corpus, authentication or planning.

## 4. Deploy the Vercel frontend

1. Import the personal repository using the Next.js preset on **Hobby**; select Node 24.
   No domain purchase is needed; use Vercel's assigned domain.
2. Set `NEXT_PUBLIC_API_URL=/` and `API_PROXY_URL` to Render's assigned HTTPS origin
   (no path or credentials). Optional `NEXT_TELEMETRY_DISABLED=1` disables build telemetry.
   These are the frontend's only deployment variables; never copy DB/key/JWT secrets here.
3. Deploy. Copy the actual production origin to Render `FRONTEND_ORIGINS`, then redeploy
   Render if necessary. If you must first obtain the Vercel origin, create the Vercel
   project, then finish these variables and redeploy once Render has its assigned URL.
4. `next.config.mjs` proxies `/api/*` to `API_PROXY_URL`. Browser traffic remains same-origin:
   HttpOnly/Secure/SameSite=Strict refresh cookies work without third-party-cookie settings.
   Existing origin validation and `X-CSRF-Protection` remain enabled. Do not broaden CORS.
   Preview deployment domains are intentionally not authorized automatically.

## 5. Owner verification (M16)

1. Register a disposable demo account in the browser, log out, log back in, and reload.
   Confirm a refresh cookie is HttpOnly, Secure, SameSite=Strict and no token is in localStorage.
2. Confirm the exact banner **Public demo (free infrastructure)** and its lightweight
   retrieval description. Send a brief greeting, then a dated Lisbon trip with a budget.
   Expect a validated itinerary or an honest error; synthetic prices and unknown costs
   must remain labeled. Never report an error/partial response as a successful plan.
3. Start a **new trip**, enable Deep plan, supply 2–7 days with two ISO dates and an explicit
   budget. The endpoint `/api/chat/deep-plan` uses SSE when `Accept: text/event-stream`,
   otherwise JSON. Check tool progress, merged days, citations and budget status.
   Stop cancels workers. A failed day retries once; terminal failure names its date and
   saves no partial itinerary. The normal stream/edit path remains available.
4. Check Render memory and logs during concurrent day work, Neon usage, provider quotas,
   and behavior after idle wake-up. Deep planning uses more requests: 3 workers maximum,
   12 planning-tool calls per day attempt plus bounded validation calls, one retry, and global validation. All limits are in
   `config/models.yaml`; reservation covers both attempts before any provider call.
   Full-stay lodging/flight lookup belongs to the first day only; other days must not
   duplicate the full quote. Unknown prices still mean the full budget is unverified.
5. Confirm another account cannot read/edit your trip. Check 429 responses and retry times
   through existing offline auth tests, not by deliberately spending live model quota.
6. Record observed outcomes, cold-start timing and peak memory. **Hosted verification,
   free-host capacity and live deep-plan quality are not run until you perform these steps.**

## Step Functions reference

`infra/stepfunctions/deep_plan.asl.json` expresses bounded Map workers, retry/catch,
merge and global validation. `asl-validator` is pinned as an npm dev dependency and
runs in CI. It is **validated, not deployed**. No Lambda handlers, AWS account, IAM
permissions or free AWS runtime are implied. Never run deployment commands for this task.
