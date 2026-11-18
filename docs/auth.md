# Local authentication and user quotas (M12)

Accounts are local Postgres records in `auth_users`. Passwords use Argon2id via
argon2-cffi. This does not send credentials to an identity provider. Emails are
normalized to lowercase; addresses are not verified. Passwords must be 12–128
characters and contain at least five distinct characters; passphrases and Unicode
are allowed. There is no password-reset/email-delivery flow in this change.

## Setup

Activate the existing venv and install `requirements.txt`. Generate a signing key
in your shell without displaying it or storing it in git:

```bash
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export APP_ENV=development
export FRONTEND_ORIGINS=http://localhost:3000
export PYTHONPATH=.
python -m pip install -r requirements.txt
docker compose up -d db
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn backend.main:app --host localhost --port 8082
```

In another terminal, use your backend origin and start the UI:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8082 npm run dev
```

For Compose, export the generated key in the shell running Compose, then:

```bash
export FRONTEND_ORIGINS=http://localhost:3100
docker compose build api
docker compose up -d db
docker compose run --rm --no-deps api python -m alembic -c backend/alembic.ini upgrade head
docker compose up -d api
```

`JWT_SECRET` and `APP_ENV` are explicitly forwarded to the API. Apply the migration
before accepting authenticated requests. For repeated use, keep the
same generated key in your ignored local environment or secret manager. Changing
it invalidates access tokens. Do not replace it with an example/placeholder.

`APP_ENV=production` requires a configured signing key of at least 32 bytes with
basic diversity/placeholder checks, and HTTPS frontend origins. Missing/weak keys
fail application startup. Those checks cannot prove entropy: generate the key
with a cryptographic RNG. Refresh cookies are Secure in production. Development
without a key generates a per-process ephemeral key and warns; a weak explicitly
configured key is rejected. Multi-worker development also needs a stable key.

## Ownership and migration

Agent conversations have an `owner_id` foreign key to the new account table.
Trips, messages and versions inherit ownership through the conversation relation.
All `/api/chat`, `/api/chat/stream` and `/api/trips` endpoints require a valid
bearer token. Reading, editing, listing versions, undoing or deleting someone
else's trip returns 404 (unknown IDs also return 404); missing/invalid credentials
return 401. Lists contain only the current user's trips.

Existing conversations remain unclaimed (`owner_id=NULL`) and are inaccessible
through the authenticated API. No account automatically adopts old data. Their
rows are preserved. An explicit administrator-controlled mapping would be a
separate task. The old legacy `users` table is not used for authentication.
The direct database agent CLI is a trusted local debugging interface, not an
HTTP authentication bypass for remote users; it creates unclaimed conversations.
Public inventory/RAG/health/metrics endpoints have not been turned into account
APIs by this task; keep the deployment within its documented exposure boundary.

## Tokens, cookies and CSRF

`POST /api/auth/register` creates an account. `POST /api/auth/login` returns a
short-lived JWT access token and sets the refresh cookie. Access JWTs use HS256
with an explicit algorithm allowlist, audience, issuer, expiry, not-before,
subject, session ID and token type. Access tokens are held only in browser memory.
Every bearer request also checks the session in Postgres, so logout revokes
existing access tokens immediately, not merely when their JWT expiry arrives.

`POST /api/auth/refresh` consumes an opaque random refresh token and issues a
replacement. Only SHA-256 hashes are stored in Postgres. Refresh rotation locks
the session row and checks the token again after locking. Reusing a consumed
refresh token revokes the entire session family, including its newer credentials.
Sessions have an absolute expiry; rotation does not extend it indefinitely.
`POST /api/auth/logout` revokes the current cookie session and clears the cookie.
`GET /api/auth/me` returns the authenticated account identity.

The refresh cookie is HttpOnly, SameSite=Strict, path `/api/auth`, and Secure in
production. There are no refresh or access tokens in localStorage. Auth POSTs
require an exact allowed Origin and `X-CSRF-Protection: 1`, including login and
registration (login CSRF matters too). JSON/custom-header requests require browser
preflight; CORS permits only configured frontend origins. Bearer-authenticated
chat/trip mutations do not rely on ambient cookie credentials. Both frontend and
API must be same-site for Strict cookies; use matching localhost hostnames in dev
and same-site HTTPS origins in production. Do not loosen SameSite to work around
an incorrectly configured deployment.

The client serializes refreshes in a tab, and across tabs using Web Locks when
available. Browsers without Web Locks can experience a forced sign-out if tabs
race a rotation; server reuse detection is intentionally retained. Logout clears
locally cached trip histories. Histories are namespaced by user ID; server-side
ownership remains authoritative. XSS can still act as the logged-in user; HttpOnly
cookies do not remove the need for content sanitization and deployment hardening.

The stream CLI sends the access token from `TRAVEL_ACCESS_TOKEN`; it does not take
a password or token argument that would be saved in shell history. Use a current
access token from your own login session and unset it afterward. CLI auth POSTs,
if used, must explicitly include the configured Origin and CSRF header too.

## Quotas and login abuse protection

Defaults are in `config/models.yaml` under `auth`: access TTL 600 seconds,
refresh/session TTL 604800 seconds, 100 messages and 12000000 tokens per UTC day.
Before either chat endpoint starts generation or sends SSE headers, Postgres
atomically reserves one message plus the configured maximum turn-token budget.
If unavailable it returns HTTP 429 with `Retry-After` until UTC midnight. A turn
needs room for the full reservation, even if the expected answer is short.

On a successful turn, unused reserved tokens are refunded using reported usage.
Failed/cancelled turns retain the reservation because provider usage can be
unknown. Message counts are not refunded. Existing per-session/turn and IP/user
rate controls remain; their rate-limit 429 uses the shorter window reset. The
old conservative user-day guard is disabled for authenticated HTTP agents to
avoid charging a second, different daily budget. These controls survive API
restarts because admissions are in Postgres. They are per-account, not proof of
a unique human; automated account creation remains a residual abuse risk.

Login attempts are limited per hashed email and peer address in Postgres. Failed
credentials impose increasing cooldowns (1, 2, 4… seconds, capped at 30); attempts
during the cooldown return 429 with Retry-After without running Argon2 again.
There are at most 10 admitted attempts per 15-minute window per key. Registration
also uses a persistent admission limit. Unknown accounts verify a dummy Argon2
hash and return the same invalid-credentials error. Proxy headers are not trusted
for peer identity; configure trusted reverse-proxy handling before internet use.
Shared-address limits and account cooldowns can affect legitimate users. Email
verification, account recovery and background expiry-row cleanup are not included.

## Verification

```bash
export PYTHONPATH=.
make lint
pytest -q
pytest -v tests/unit/test_auth.py
pytest -q -m integration tests/unit/test_auth.py tests/unit/test_agent_persistence.py
npm test
npm run lint
npm run build
```

Integration tests use isolated synthetic schemas and remove them afterward. They
exercise Postgres row locks for concurrent refresh and quota admissions. No test
calls a real model, sends email or downloads model weights.

Manual browser check:

1. Open `/` while signed out: the planner must not render; you reach `/login`.
2. Register a local account with a unique passphrase. Log out and log back in.
3. Check browser storage: no tokens in localStorage; refresh cookie is HttpOnly,
   Strict, and Secure when running the production HTTPS configuration.
4. Plan a trip using your existing free/local provider and data. Refresh the page:
   the cookie restores the session and the browser history is scoped to that user.
5. Log out. Register a second account. The first account's history must not appear.
   Access the first trip's API ID with the second account's bearer token: expect
   404 for read, versions, chat edit, undo and delete.
6. Log out again: the old access token must return 401. Inspect a refresh rotation:
   its cookie value changes; never paste tokens into reports or commit them.
7. Use offline/integration quota and brute-force tests for exhaustion paths rather
   than consuming live model quota. The frontend displays the server retry time.

Use the exact required cases in `tests/unit/test_auth.py` as the acceptance checklist.
No browser screenshots or live planning success are claimed by these instructions.

References: [PyJWT validation](https://pyjwt.readthedocs.io/en/latest/usage.html)
and [argon2-cffi PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html).
