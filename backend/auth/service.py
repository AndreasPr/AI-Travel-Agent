"""Argon2 credentials, restricted JWTs and atomic hashed refresh rotation."""

from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import logging
import re
import secrets
import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
import jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from backend.db.models import AuthUser, AuthSession, AuthRefresh, AuthDailyUsage, AuthLoginAttempt
from backend.env import config as env
from backend.llm.config import load_config

users, sessions, refreshes, usage, attempts = (m.__table__ for m in (AuthUser, AuthSession, AuthRefresh, AuthDailyUsage, AuthLoginAttempt))


class AuthError(Exception):
    def __init__(self, status=401, message="Authentication required", retry_after=None):
        self.status, self.message, self.retry_after = status, message, retry_after
        super().__init__(message)


@dataclass(frozen=True)
class Settings:
    secret: str = field(repr=False)
    production: bool
    origins: tuple[str, ...]

    def __post_init__(self):
        if (
            len(self.secret.encode()) < 32
            or len(set(self.secret)) < 12
            or any(word in self.secret.lower() for word in ("changeme", "replace-me", "example-secret"))
        ):
            raise ValueError("JWT_SECRET must be a randomly generated secret of at least 32 bytes")
        if not self.origins or any(o == "*" or not re.fullmatch(r"https?://[^/]+", o) for o in self.origins):
            raise ValueError("FRONTEND_ORIGINS must contain explicit frontend origins without paths")
        if self.production and any(not o.startswith("https://") for o in self.origins):
            raise ValueError("Production frontend origins must use HTTPS")


@lru_cache
def settings():
    mode = env("APP_ENV", default="development").lower()
    if mode not in {"development", "production"}:
        raise ValueError("APP_ENV must be development or production")
    production = mode == "production"
    secret = env("JWT_SECRET", default="")
    if not secret:
        if production:
            raise ValueError("JWT_SECRET is required in production")
        secret = secrets.token_urlsafe(48)
        logging.getLogger(__name__).warning("JWT_SECRET missing: development sessions will expire on process restart")
    origins = tuple(o.strip() for o in env("FRONTEND_ORIGINS", default="http://localhost:3000").split(",") if o.strip())
    return Settings(secret, production, origins)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def email_address(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise AuthError(422, "Enter a valid email address")
    return value


class AuthService:
    def __init__(self, engine, settings, config=None, clock=time.time):
        self.engine, self.settings, self.clock = engine, settings, clock
        self.config = config or load_config()["auth"]
        self.hasher = PasswordHasher()
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))

    def _insert_once(self, conn, table, values):
        if conn.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        conn.execute(insert(table).values(**values).on_conflict_do_nothing())

    def register(self, email, password):
        email = email_address(email)
        if not self.config["password_min_length"] <= len(password) <= self.config["password_max_length"] or len(set(password)) < 5:
            raise AuthError(
                422,
                f"Password must contain {self.config['password_min_length']}–{self.config['password_max_length']} characters and must not be repetitive",
            )
        row = dict(id=str(uuid4()), email=email, password_hash=self.hasher.hash(password), created_at=int(self.clock()))
        try:
            with self.engine.begin() as conn:
                conn.execute(users.insert().values(**row))
        except IntegrityError:
            raise AuthError(409, "Registration could not be completed") from None
        return {"id": row["id"], "email": row["email"]}

    def login_admission(self, email, ip, kind="login"):
        now = int(self.clock())
        period = self.config["login_window_seconds"]
        keys = [digest(kind + ":email:" + email), digest(kind + ":ip:" + ip)]
        with self.engine.begin() as conn:
            for key in sorted(keys):
                self._insert_once(conn, attempts, dict(key=key, window=now // period, attempts=0, failures=0, next_allowed=0))
                where = (attempts.c.key == key) & (attempts.c.window == now // period)
                row = conn.execute(select(attempts).where(where).with_for_update()).mappings().one()
                if row["attempts"] >= self.config["login_attempts"] or row["next_allowed"] > now:
                    retry = period - now % period if row["attempts"] >= self.config["login_attempts"] else row["next_allowed"] - now
                    raise AuthError(429, "Too many authentication attempts; try again later", retry)
                conn.execute(update(attempts).where(where).values(attempts=row["attempts"] + 1))
        return keys, now // period

    def failed_login(self, admission):
        keys, window = admission
        with self.engine.begin() as conn:
            for key in sorted(keys):
                where = (attempts.c.key == key) & (attempts.c.window == window)
                row = conn.execute(select(attempts).where(where).with_for_update()).mappings().one()
                failures = row["failures"] + 1
                delay = min(self.config["login_delay_max_seconds"], self.config["login_delay_base_seconds"] * 2 ** min(failures - 1, 16))
                conn.execute(update(attempts).where(where).values(failures=failures, next_allowed=int(self.clock()) + delay))

    def login(self, email, password, ip):
        email = email_address(email)
        admission = self.login_admission(email, ip)
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        try:
            self.hasher.verify(row["password_hash"] if row else self.dummy_hash, password)
            valid = row is not None
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid:
            self.failed_login(admission)
            raise AuthError(401, "Invalid email or password")
        if self.hasher.check_needs_rehash(row["password_hash"]):
            with self.engine.begin() as conn:
                conn.execute(update(users).where(users.c.id == row["id"]).values(password_hash=self.hasher.hash(password)))
        now = int(self.clock())
        sid, raw = str(uuid4()), secrets.token_urlsafe(48)
        expires = now + self.config["refresh_seconds"]
        with self.engine.begin() as conn:
            conn.execute(sessions.insert().values(id=sid, user_id=row["id"], expires_at=expires, revoked=False))
            conn.execute(refreshes.insert().values(token_hash=digest(raw), session_id=sid, expires_at=expires, used=False))
        return self.access(row["id"], sid), raw

    def access(self, user_id, session_id):
        now = int(self.clock())
        return jwt.encode(
            dict(
                sub=user_id,
                sid=session_id,
                iat=now,
                nbf=now,
                exp=now + self.config["access_seconds"],
                iss="travel-api",
                aud="travel-web",
                typ="access",
                jti=str(uuid4()),
            ),
            self.settings.secret,
            algorithm="HS256",
        )

    def authenticate(self, token):
        try:
            payload = jwt.decode(
                token,
                self.settings.secret,
                algorithms=["HS256"],
                issuer="travel-api",
                audience="travel-web",
                options={"require": ["sub", "sid", "iat", "nbf", "exp", "typ", "jti"]},
            )
            if payload["typ"] != "access" or payload["exp"] <= self.clock():
                raise ValueError()
            with self.engine.connect() as conn:
                row = (
                    conn.execute(
                        select(users.c.id, users.c.email)
                        .join(sessions, sessions.c.user_id == users.c.id)
                        .where(
                            sessions.c.id == payload["sid"],
                            users.c.id == payload["sub"],
                            sessions.c.revoked.is_(False),
                            sessions.c.expires_at > self.clock(),
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise ValueError()
            return dict(row)
        except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
            raise AuthError() from None

    def rotate(self, raw):
        invalid = False
        with self.engine.begin() as conn:
            token = conn.execute(select(refreshes).where(refreshes.c.token_hash == digest(raw))).mappings().first()
            if token is None:
                raise AuthError()
            session = conn.execute(select(sessions).where(sessions.c.id == token["session_id"]).with_for_update()).mappings().one()
            # Read again after the session lock: concurrent refreshes must not both rotate.
            token = conn.execute(select(refreshes).where(refreshes.c.token_hash == digest(raw))).mappings().one()
            if token["used"]:
                conn.execute(update(sessions).where(sessions.c.id == session["id"]).values(revoked=True))
                invalid = True
            elif session["revoked"] or min(session["expires_at"], token["expires_at"]) <= self.clock():
                invalid = True
            else:
                changed = conn.execute(
                    update(refreshes).where(refreshes.c.token_hash == digest(raw), refreshes.c.used.is_(False)).values(used=True)
                )
                if changed.rowcount != 1:
                    raise AuthError()
                new = secrets.token_urlsafe(48)
                conn.execute(
                    refreshes.insert().values(
                        token_hash=digest(new), session_id=session["id"], expires_at=session["expires_at"], used=False
                    )
                )
        if invalid:
            raise AuthError()
        return self.access(session["user_id"], session["id"]), new, session["expires_at"]

    def logout(self, raw):
        with self.engine.begin() as conn:
            sid = conn.scalar(select(refreshes.c.session_id).where(refreshes.c.token_hash == digest(raw)))
            if sid:
                conn.execute(update(sessions).where(sessions.c.id == sid).values(revoked=True))

    def reserve_turn(self, user_id, token_budget):
        now = int(self.clock())
        day = now // 86400
        with self.engine.begin() as conn:
            self._insert_once(conn, usage, dict(user_id=user_id, day=day, messages=0, tokens=0))
            where = (usage.c.user_id == user_id) & (usage.c.day == day)
            row = conn.execute(select(usage).where(where).with_for_update()).mappings().one()
            if row["messages"] + 1 > self.config["daily_messages"] or row["tokens"] + token_budget > self.config["daily_tokens"]:
                raise AuthError(429, "Daily message or token quota exhausted; try after the UTC reset", 86400 - now % 86400)
            conn.execute(update(usage).where(where).values(messages=row["messages"] + 1, tokens=row["tokens"] + token_budget))
        return (user_id, day, token_budget)

    def settle_turn(self, reservation, actual_tokens):
        user_id, day, reserved = reservation
        refund = max(0, reserved - actual_tokens)
        with self.engine.begin() as conn:
            conn.execute(update(usage).where(usage.c.user_id == user_id, usage.c.day == day).values(tokens=usage.c.tokens - refund))
