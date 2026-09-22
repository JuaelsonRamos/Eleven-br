import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.auth import SESSION_DAYS, Unauthorized
from app.infrastructure.auth_models import AuthSession, RefreshToken
from app.infrastructure.config import Settings
from app.infrastructure.models import User
from app.infrastructure.security import create_access_token, secret_digest


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def verified(user: User) -> bool:
    return user.email_verified_at is not None or user.phone_verified_at is not None


def issue_tokens(session: Session, auth_session: AuthSession, settings: Settings) -> TokenPair:
    raw = secrets.token_urlsafe(48)
    session.add(
        RefreshToken(
            session_id=auth_session.id,
            token_hash=secret_digest(f"refresh:{raw}", settings),
        )
    )
    session.flush()
    return TokenPair(create_access_token(auth_session.user_id, settings, auth_session.id), raw)


def create_session(
    session: Session,
    user: User,
    transport: str,
    settings: Settings,
) -> TokenPair:
    auth_session = AuthSession(
        user_id=user.id,
        transport=transport,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
    )
    session.add(auth_session)
    session.flush()
    return issue_tokens(session, auth_session, settings)


def refresh_session(session: Session, raw: str, transport: str, settings: Settings) -> TokenPair:
    digest = secret_digest(f"refresh:{raw}", settings)
    auth_session = session.scalar(
        select(AuthSession)
        .join(RefreshToken, RefreshToken.session_id == AuthSession.id)
        .where(RefreshToken.token_hash == digest)
        .with_for_update(of=AuthSession)
    )
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
        or auth_session.transport != transport
    ):
        raise Unauthorized("Sua sessão expirou. Entre novamente.")
    token = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))
    assert token is not None
    user = session.get(User, auth_session.user_id)
    if token.used_at is not None or user is None or user.status != "active" or not verified(user):
        # A consumed token is replay: revoke the whole session, including its newest access token.
        auth_session.revoked_at = now
        session.commit()
        raise Unauthorized("Sua sessão expirou. Entre novamente.")
    token.used_at = now
    pair = issue_tokens(session, auth_session, settings)
    session.commit()
    return pair


def logout_session(session: Session, raw: str | None, transport: str, settings: Settings) -> None:
    if raw:
        auth_session = session.scalar(
            select(AuthSession)
            .join(RefreshToken, RefreshToken.session_id == AuthSession.id)
            .where(RefreshToken.token_hash == secret_digest(f"refresh:{raw}", settings))
            .with_for_update(of=AuthSession)
        )
        if auth_session and auth_session.transport == transport:
            auth_session.revoked_at = datetime.now(UTC)
            session.commit()
