"""A separate one-use recovery capability never verifies contacts or authenticates a session."""

import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.auth import CODE_MINUTES, DeliveryUnavailable, InvalidVerification
from app.infrastructure.auth_models import AuthSession
from app.infrastructure.config import Settings
from app.infrastructure.delivery import get_sender
from app.infrastructure.launch_models import PasswordRecovery
from app.infrastructure.models import User
from app.infrastructure.rate_limit import rate_limit
from app.infrastructure.security import hash_password, secret_digest

MESSAGE = (
    "Se existir uma conta cadastrada com esse e-mail, enviaremos as instruções para recuperação."
)


def deliver(email: str, code: str, settings: Settings) -> None:
    try:
        get_sender(settings).send(
            contact=email, channel="email", code=code, purpose="password_reset"
        )
    except DeliveryUnavailable:
        # No exception details, contact or code in logs; response must not reveal account existence.
        logging.getLogger(__name__).warning("Password recovery delivery unavailable")


def request(
    session: Session, email: str, settings: Settings
) -> tuple[dict[str, object], str | None, str]:
    rate_limit(session, settings, "password-recovery-email", email, limit=5, seconds=3600)
    raw, code = secrets.token_urlsafe(32), f"{secrets.randbelow(1_000_000):06d}"
    user = session.scalar(select(User).where(User.email == email).with_for_update())
    recipient = None
    if user and user.status == "active" and user.email_verified_at is not None:
        item = session.scalar(select(PasswordRecovery).where(PasswordRecovery.user_id == user.id))
        if item is None:
            item = PasswordRecovery(user_id=user.id)
            session.add(item)
        item.handle_hash = secret_digest(f"reset-handle:{raw}", settings)
        item.code_hash = secret_digest(f"reset-code:{raw}:{code}", settings)
        item.email, item.attempts, item.consumed_at = email, 0, None
        item.expires_at = datetime.now(UTC) + timedelta(minutes=CODE_MINUTES)
        recipient = email
    session.commit()
    result: dict[str, object] = {"message": MESSAGE, "recovery_token": raw}
    if settings.app_env in ("development", "test") and settings.dev_verification_codes:
        result["development_code"] = code
    return result, recipient, code


def reset(session: Session, raw: str, code: str, password: str, settings: Settings) -> None:
    rate_limit(session, settings, "password-recovery-attempt", raw, limit=5, seconds=900)
    digest = secret_digest(f"reset-handle:{raw}", settings)
    user = session.scalar(
        select(User)
        .join(PasswordRecovery, PasswordRecovery.user_id == User.id)
        .where(PasswordRecovery.handle_hash == digest)
        .with_for_update(of=User)
    )
    item = session.scalar(
        select(PasswordRecovery)
        .where(PasswordRecovery.handle_hash == digest)
        .execution_options(populate_existing=True)
    )
    now = datetime.now(UTC)
    error = "Código inválido ou expirado. Solicite a recuperação novamente."
    if (
        not user
        or not item
        or user.status != "active"
        or user.email != item.email
        or item.consumed_at
        or item.expires_at <= now
        or item.attempts >= 5
    ):
        raise InvalidVerification(error)
    if not hmac.compare_digest(item.code_hash, secret_digest(f"reset-code:{raw}:{code}", settings)):
        item.attempts += 1
        session.commit()
        raise InvalidVerification(error)
    user.password_hash = hash_password(password)
    item.consumed_at = now
    session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.commit()
