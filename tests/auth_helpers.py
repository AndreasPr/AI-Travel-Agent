"""Authenticated synthetic principals for existing agent behavior tests."""

import secrets
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.auth.api import current_user, get_auth_service, install_auth_handlers
from backend.auth.service import AuthService, Settings
from backend.db.models import AuthUser, AuthSession, AuthRefresh, AuthDailyUsage, AuthLoginAttempt


def authenticate_app(app, agent):
    engine = (
        agent.store.engine
        if hasattr(agent.store, "engine")
        else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    )
    for model in (AuthUser, AuthSession, AuthRefresh, AuthDailyUsage, AuthLoginAttempt):
        model.__table__.create(engine, checkfirst=True)
    service = AuthService(engine, Settings(secrets.token_urlsafe(48), False, ("http://frontend.test",)))
    user = service.register("synthetic-agent@example.invalid", "Synthetic test passphrase 123!")
    if hasattr(agent.store, "states"):
        for state in agent.store.states.values():
            state["owner_id"] = user["id"]
    if hasattr(agent.store, "engine"):
        from sqlalchemy import update
        from backend.db.models import AgentConversation

        with engine.begin() as conn:
            conn.execute(update(AgentConversation).where(AgentConversation.owner_id.is_(None)).values(owner_id=user["id"]))
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_auth_service] = lambda: service
    install_auth_handlers(app)
    return user
