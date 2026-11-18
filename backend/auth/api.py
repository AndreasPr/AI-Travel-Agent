"""Same-origin cookie lifecycle and bearer access-token authentication."""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from backend.auth.service import AuthError, AuthService, email_address, settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE = "travel_refresh"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


@lru_cache
def get_auth_service():
    from backend.db.connect import engine

    return AuthService(engine, settings())


def current_user(request: Request, service=Depends(get_auth_service)):  # noqa: B008
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer ") or len(value) > 4096:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = service.authenticate(value[7:])
    except AuthError:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Authentication storage unavailable") from None
    from starlette.authentication import SimpleUser

    request.scope["user"] = SimpleUser(user["id"])
    return user


def csrf(request: Request, service=Depends(get_auth_service)):  # noqa: B008
    if request.headers.get("origin") not in service.settings.origins or request.headers.get("x-csrf-protection") != "1":
        raise HTTPException(403, "Request origin or CSRF header rejected")


def cookie(response, raw, service, expires=None):
    maximum = max(0, int(expires - service.clock())) if expires is not None else service.config["refresh_seconds"]
    response.set_cookie(
        COOKIE, raw, max_age=maximum, httponly=True, secure=service.settings.production, samesite="strict", path="/api/auth"
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", status_code=201, dependencies=[Depends(csrf)])
def register(body: Credentials, request: Request, service=Depends(get_auth_service)):  # noqa: B008
    service.login_admission(email_address(body.email), request.client.host if request.client else "unknown", "register")
    user = service.register(body.email, body.password)
    return JSONResponse(user, status_code=201, headers={"Cache-Control": "no-store"})


@router.post("/login", dependencies=[Depends(csrf)])
def login(body: Credentials, request: Request, response: Response, service=Depends(get_auth_service)):  # noqa: B008
    access, raw = service.login(body.email, body.password, request.client.host if request.client else "unknown")
    cookie(response, raw, service)
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": service.config["access_seconds"],
        "user": service.authenticate(access),
    }


@router.post("/refresh", dependencies=[Depends(csrf)])
def refresh(request: Request, response: Response, service=Depends(get_auth_service)):  # noqa: B008
    access, raw, expires = service.rotate(request.cookies.get(COOKIE, ""))
    cookie(response, raw, service, expires)
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": service.config["access_seconds"],
        "user": service.authenticate(access),
    }


@router.post("/logout", dependencies=[Depends(csrf)])
def logout(request: Request, response: Response, service=Depends(get_auth_service)):  # noqa: B008
    service.logout(request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE, path="/api/auth", secure=service.settings.production, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Logged out"}


@router.get("/me")
def me(user=Depends(current_user)):  # noqa: B008
    return user


class PrivateResponses:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        private = scope["type"] == "http" and scope.get("path", "").startswith(("/api/auth", "/api/chat", "/api/trips"))

        async def reply(message):
            if private and message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
            await send(message)

        await self.app(scope, receive, reply)


def install_auth_handlers(app):
    app.add_middleware(PrivateResponses)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        headers = {"Cache-Control": "no-store"}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(max(1, int(exc.retry_after)))
        if exc.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse({"detail": exc.message}, status_code=exc.status, headers=headers)
