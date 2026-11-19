"""Synthetic accounts and scripted providers; no live model or HTTP requests."""

from copy import deepcopy
import secrets
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import StaticPool

from backend.auth.api import COOKIE, get_auth_service, install_auth_handlers, router as auth_router
from backend.auth.service import AuthService, Settings, settings
from backend.agent.api import get_agent, router as agent_router
from backend.agent.store import PostgresTripStore
from backend.db.models import (
    AuthUser,
    AuthSession,
    AuthRefresh,
    AuthDailyUsage,
    AuthLoginAttempt,
    AgentConversation,
    AgentTrip,
    AgentMessage,
    AgentItineraryVersion,
    SecurityUsage,
)
from backend.llm.config import load_config
from test_agent_streaming import agent_for

MODELS = (
    AuthUser,
    AuthSession,
    AuthRefresh,
    AuthDailyUsage,
    AuthLoginAttempt,
    AgentConversation,
    AgentTrip,
    AgentMessage,
    AgentItineraryVersion,
    SecurityUsage,
)
ORIGIN = "http://frontend.test"
HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}
PASSWORD = "Synthetic test passphrase 123!"


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.integration)])
def environment(request):
    schema = None
    if request.param == "postgres":
        from backend.db.connect import engine as base

        schema = "synthetic_auth_" + uuid4().hex
        with base.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = base.execution_options(schema_translate_map={None: schema})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in MODELS:
        model.__table__.create(engine)
    config = deepcopy(load_config()["auth"])
    service = AuthService(engine, Settings(secrets.token_urlsafe(48), False, (ORIGIN,)), config)
    agent = agent_for()
    agent.store = PostgresTripStore(engine)
    app = FastAPI()
    install_auth_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(service.settings.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Protection"],
    )
    app.include_router(auth_router)
    app.include_router(agent_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_agent] = lambda: agent
    yield TestClient(app), service, agent
    if schema:
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    else:
        engine.dispose()


def register_login(client, email="synthetic-a@example.invalid"):
    body = {"email": email, "password": PASSWORD}
    assert client.post("/api/auth/register", json=body, headers=HEADERS).status_code == 201
    result = client.post("/api/auth/login", json=body, headers=HEADERS)
    assert result.status_code == 200, result.text
    return result.json(), {"Authorization": "Bearer " + result.json()["access_token"]}


def test_register_login_logout(environment):
    client, _, _ = environment
    data, headers = register_login(client)
    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["id"] == data["user"]["id"]
    assert me.headers["Cache-Control"] == "no-store"
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/refresh", headers=HEADERS).status_code == 401


def test_password_is_hashed_with_argon2(environment):
    client, service, _ = environment
    register_login(client)
    with service.engine.connect() as conn:
        row = conn.execute(select(AuthUser)).mappings().one()
    assert row["password_hash"].startswith("$argon2id$")
    assert row["password_hash"] != PASSWORD
    assert service.hasher.verify(row["password_hash"], PASSWORD)


def test_expired_token_rejected(environment):
    client, service, _ = environment
    data, _ = register_login(client)
    payload = jwt.decode(data["access_token"], service.settings.secret, algorithms=["HS256"], audience="travel-web", issuer="travel-api")
    payload["exp"] = int(time.time()) - 1
    expired = jwt.encode(payload, service.settings.secret, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + expired}).status_code == 401


def test_tampered_token_rejected(environment):
    client, _, _ = environment
    data, _ = register_login(client)
    header, payload, signature = data["access_token"].split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {header}.{payload}.{signature}"}).status_code == 401


def test_missing_token_401(environment):
    client, _, _ = environment
    for method, path in [
        ("post", "/api/chat"),
        ("post", "/api/chat/stream"),
        ("get", "/api/trips"),
        ("get", "/api/trips/guessed"),
        ("get", "/api/trips/guessed/versions"),
        ("post", "/api/trips/guessed/undo"),
        ("delete", "/api/trips/guessed"),
    ]:
        assert (
            getattr(client, method)(path, **({"json": {"message": "synthetic"}} if path.startswith("/api/chat") else {})).status_code == 401
        )


def test_refresh_rotation_invalidates_old_token(environment):
    client, service, _ = environment
    _, headers = register_login(client)
    old = client.cookies.get(COOKIE)
    rotated = client.post("/api/auth/refresh", headers=HEADERS)
    assert rotated.status_code == 200
    new = client.cookies.get(COOKIE)
    assert new != old
    with service.engine.connect() as conn:
        stored = conn.execute(select(AuthRefresh.token_hash)).scalars().all()
    assert old not in stored and new not in stored
    client.cookies.clear()
    client.cookies.set(COOKIE, old)
    assert client.post("/api/auth/refresh", headers=HEADERS).status_code == 401
    # Reuse revokes the family, including the new refresh and access credentials.
    client.cookies.set(COOKIE, new)
    assert client.post("/api/auth/refresh", headers=HEADERS).status_code == 401
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_idor_read_edit_undo_delete_return_404(environment):
    client, _, agent = environment
    a, ha = register_login(client)
    state = agent.store.for_owner(a["user"]["id"]).create()
    _, hb = register_login(client, "synthetic-b@example.invalid")
    trip = state["id"]
    for path in (f"/api/trips/{trip}", f"/api/trips/{trip}/versions"):
        assert client.get(path, headers=hb).status_code == 404
        assert client.get(path, headers=ha).status_code == 200
    for path in ("/api/chat", "/api/chat/stream"):
        assert client.post(path, headers=hb, json={"trip_id": trip, "message": "Make day 2 cheaper"}).status_code == 404
    assert client.post(f"/api/trips/{trip}/undo", headers=hb).status_code == 404
    assert client.delete(f"/api/trips/{trip}", headers=hb).status_code == 404
    assert client.get("/api/trips", headers=hb).json()["trips"] == []
    assert client.delete(f"/api/trips/{trip}", headers=ha).status_code == 204
    assert client.get(f"/api/trips/{trip}", headers=ha).status_code == 404


def test_quota_429_with_retry_after(environment):
    client, service, agent = environment
    _, headers = register_login(client)
    service.config["daily_tokens"] = agent.config["guardrails"]["turn_tokens"] - 1
    called = []
    agent.providers = lambda role: called.append(role)
    for endpoint in ("/api/chat", "/api/chat/stream"):
        response = client.post(endpoint, headers=headers, json={"message": "Synthetic trip"})
        assert response.status_code == 429
        assert 0 < int(response.headers["Retry-After"]) <= 86400
    assert called == []


def test_login_rate_limited(environment):
    client, service, _ = environment
    now = int(time.time())
    service.clock = lambda: now
    credentials = {"email": "synthetic-absent@example.invalid", "password": PASSWORD}
    assert client.post("/api/auth/login", json=credentials, headers=HEADERS).status_code == 401
    limited = client.post("/api/auth/login", json=credentials, headers=HEADERS)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) == 1
    now += 1
    assert client.post("/api/auth/login", json=credentials, headers=HEADERS).status_code == 401
    limited = client.post("/api/auth/login", json=credentials, headers=HEADERS)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) == 2


def test_weak_jwt_secret_fails_startup_in_production(monkeypatch):
    from backend.main import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://frontend.test")
    try:
        for secret in ("", "short", "x" * 64):
            monkeypatch.setenv("JWT_SECRET", secret)
            settings.cache_clear()
            with pytest.raises(ValueError, match="JWT_SECRET"), TestClient(app):
                pass
    finally:
        settings.cache_clear()


def test_cors_only_allows_frontend_origin(environment):
    client, _, _ = environment
    headers = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    allowed = client.options("/api/chat", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == ORIGIN
    rejected = client.options("/api/chat", headers={**headers, "Origin": "https://attacker.invalid"})
    assert rejected.status_code == 400
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_refresh_csrf_and_cookie_flags(environment):
    client, _, _ = environment
    register_login(client)
    response = client.post("/api/auth/refresh", headers=HEADERS)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/auth" in cookie
    assert "secure" not in cookie
    for headers in ({}, {"Origin": ORIGIN}, {**HEADERS, "Origin": "https://attacker.invalid"}):
        assert client.post("/api/auth/refresh", headers=headers).status_code == 403
        assert client.post("/api/auth/logout", headers=headers).status_code == 403


def test_password_rules_and_duplicate_email(environment):
    client, _, _ = environment
    for password in ("short", "x" * 20):
        assert (
            client.post(
                "/api/auth/register", headers=HEADERS, json={"email": "synthetic@example.invalid", "password": password}
            ).status_code
            == 422
        )
    register_login(client)
    assert (
        client.post("/api/auth/register", headers=HEADERS, json={"email": "SYNTHETIC-A@example.invalid", "password": PASSWORD}).status_code
        == 409
    )


def test_successful_chat_is_owned_and_usage_is_persistent(environment):
    client, service, agent = environment
    data, headers = register_login(client)
    result = client.post("/api/chat", headers=headers, json={"message": "Synthetic trip request under 1500 USD"})
    assert result.status_code == 200, result.text
    assert result.json()["itinerary"] is not None
    trip_id = result.json()["trip_id"]
    assert agent.store.for_owner(data["user"]["id"]).load(trip_id)["owner_id"] == data["user"]["id"]
    again = AuthService(service.engine, service.settings, service.config)
    with again.engine.connect() as conn:
        row = conn.execute(select(AuthDailyUsage)).mappings().one()
        assert row["messages"] == 1
        assert row["tokens"] == result.json()["usage"]["tokens_in"] + result.json()["usage"]["tokens_out"]
    assert client.get(f"/api/trips/{trip_id}", headers=headers).status_code == 200


def test_daily_message_limit_and_reset(environment):
    client, service, agent = environment
    user, headers = register_login(client)
    service.config["daily_messages"] = 1
    reservation = service.reserve_turn(user["user"]["id"], 100)
    service.settle_turn(reservation, 10)
    response = client.post("/api/chat", headers=headers, json={"message": "Synthetic trip"})
    assert response.status_code == 429
    now = int(time.time())
    service.clock = lambda: now + 86400
    # A fresh UTC day admits again without clearing persisted rows.
    service.reserve_turn(user["user"]["id"], 100)
    with service.engine.connect() as conn:
        assert len(conn.execute(select(AuthDailyUsage)).all()) == 2


def test_production_refresh_cookie_is_secure(environment):
    from backend.auth.api import cookie
    from fastapi import Response as HTTPResponse

    _, service, _ = environment
    service.settings = Settings(secrets.token_urlsafe(48), True, ("https://frontend.test",))
    response = HTTPResponse()
    cookie(response, "synthetic-cookie-value", service)
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_unclaimed_trip_is_not_adopted(environment):
    client, _, agent = environment
    state = agent.store.create()
    _, headers = register_login(client)
    assert client.get("/api/trips/" + state["id"], headers=headers).status_code == 404
    assert client.post("/api/chat", headers=headers, json={"trip_id": state["id"], "message": "Synthetic edit"}).status_code == 404


@pytest.mark.integration
def test_refresh_rotation_serializes_concurrent_postgres_calls(environment):
    if environment[1].engine.dialect.name != "postgresql":
        pytest.skip("Requires Postgres row locks")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from backend.auth.service import AuthError

    client, service, _ = environment
    register_login(client)
    raw = client.cookies.get(COOKIE)
    barrier = Barrier(2)

    def rotate():
        barrier.wait(timeout=5)
        try:
            service.rotate(raw)
            return "ok"
        except AuthError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(results) == ["ok", "rejected"]


@pytest.mark.integration
def test_quota_admission_is_atomic_in_postgres(environment):
    if environment[1].engine.dialect.name != "postgresql":
        pytest.skip("Requires Postgres row locks")
    from concurrent.futures import ThreadPoolExecutor
    from backend.auth.service import AuthError

    client, service, _ = environment
    user, _ = register_login(client)
    service.config["daily_messages"] = 1

    def reserve():
        try:
            service.reserve_turn(user["user"]["id"], 100)
            return "ok"
        except AuthError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(results) == ["ok", "rejected"]
