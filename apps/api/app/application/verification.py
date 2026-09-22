import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.sessions import TokenPair, create_session, verified
from app.domain.auth import (
    CODE_MINUTES,
    MAX_CODE_ATTEMPTS,
    RESEND_SECONDS,
    InvalidVerification,
    RateLimited,
)
from app.domain.contacts import normalize_contact
from app.domain.policies import Conflict
from app.infrastructure.auth_models import VerificationChallenge
from app.infrastructure.config import Settings
from app.infrastructure.delivery import get_sender
from app.infrastructure.models import Player, User
from app.infrastructure.rate_limit import rate_limit
from app.infrastructure.security import secret_digest


@dataclass(frozen=True)
class VerificationTicket:
    challenge_token: str
    masked_contact: str
    resend_after: int
    development_code: str | None = None


def mask_contact(contact: str, channel: str) -> str:
    if channel == "phone":
        return "+" + "•" * (len(contact) - 5) + contact[-4:]
    local, domain = contact.split("@", 1)
    return local[:1] + "•••@" + domain


def ticket(
    challenge: VerificationChallenge, raw: str, code: str | None = None
) -> VerificationTicket:
    wait = max(0, RESEND_SECONDS - int((datetime.now(UTC) - challenge.sent_at).total_seconds()))
    return VerificationTicket(raw, mask_contact(challenge.contact, challenge.channel), wait, code)


def prepare_verification(session: Session, user: User, settings: Settings) -> VerificationTicket:
    """Caller holds the User row lock. Correct-password login can resume an existing code."""
    now = datetime.now(UTC)
    challenge = session.scalar(
        select(VerificationChallenge).where(
            VerificationChallenge.user_id == user.id,
        )
    )
    raw = secrets.token_urlsafe(32)
    if challenge is None:
        channel = "email" if user.email else "phone"
        challenge = VerificationChallenge(
            id=uuid4(),
            user_id=user.id,
            channel=channel,
            contact=user.email or user.phone,
            handle_hash=secret_digest(f"challenge:{raw}", settings),
            handle_expires_at=now + timedelta(hours=24),
        )
        session.add(challenge)
        # Avoid autoflush until all non-null fields have been assigned.
        code = send_code(challenge, settings)
    else:
        challenge.handle_hash = secret_digest(f"challenge:{raw}", settings)
        challenge.handle_expires_at = now + timedelta(hours=24)
        code = None
    session.flush()
    return ticket(challenge, raw, code)


def send_code(challenge: VerificationChallenge, settings: Settings) -> str | None:
    sender = get_sender(settings)
    now = datetime.now(UTC)
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = secret_digest(f"verify_contact:{challenge.id}:{code}", settings)
        if digest != challenge.code_hash:
            break
    challenge.code_hash = digest
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(minutes=CODE_MINUTES)
    challenge.sent_at = now
    challenge.consumed_at = None
    return sender.send(contact=challenge.contact, channel=challenge.channel, code=code)


def limit_delivery(session: Session, raw: str, settings: Settings) -> None:
    user_id = session.scalar(
        select(VerificationChallenge.user_id).where(
            VerificationChallenge.handle_hash == secret_digest(f"challenge:{raw}", settings),
        )
    )
    # A new login rotates the continuation handle, but must not reset the user's send budget.
    rate_limit(
        session, settings, "code-delivery", str(user_id) if user_id else raw, limit=5, seconds=3600
    )


def locked_challenge(
    session: Session,
    raw: str,
    settings: Settings,
) -> tuple[User, VerificationChallenge]:
    # All verification operations lock the User first, matching login/register lock order.
    user = session.scalar(
        select(User)
        .join(VerificationChallenge, VerificationChallenge.user_id == User.id)
        .where(VerificationChallenge.handle_hash == secret_digest(f"challenge:{raw}", settings))
        .with_for_update(of=User)
    )
    if user is None:
        raise InvalidVerification("Verificação indisponível. Entre novamente para continuar.")
    challenge = session.scalar(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.user_id == user.id,
        )
        .execution_options(populate_existing=True)
    )
    if (
        challenge is None
        or challenge.handle_expires_at <= datetime.now(UTC)
        or challenge.consumed_at is not None
        or user.status != "active"
        or verified(user)
        or not hmac.compare_digest(
            challenge.handle_hash, secret_digest(f"challenge:{raw}", settings)
        )
    ):
        raise InvalidVerification("Verificação indisponível. Entre novamente para continuar.")
    return user, challenge


def confirm_code(
    session: Session,
    raw: str,
    code: str,
    transport: str,
    settings: Settings,
) -> TokenPair:
    user, challenge = locked_challenge(session, raw, settings)
    now = datetime.now(UTC)
    if challenge.expires_at <= now:
        raise InvalidVerification("Código expirado. Solicite um novo código.")
    if challenge.attempts >= MAX_CODE_ATTEMPTS:
        raise InvalidVerification("Limite de tentativas atingido. Solicite um novo código.")
    expected = secret_digest(f"verify_contact:{challenge.id}:{code}", settings)
    if not hmac.compare_digest(expected, challenge.code_hash):
        challenge.attempts += 1
        session.commit()  # Failed attempts must survive the HTTP error response.
        raise InvalidVerification("Código inválido. Confira e tente novamente.")
    if challenge.channel == "email" and user.email == challenge.contact:
        user.email_verified_at = now
    elif challenge.channel == "phone" and user.phone == challenge.contact:
        user.phone_verified_at = now
    else:
        raise InvalidVerification("Contato alterado. Solicite um novo código.")
    challenge.consumed_at = now
    player = session.scalar(select(Player).where(Player.user_id == user.id))
    if player is None and user.registration_name:
        session.add(Player(user_id=user.id, display_name=user.registration_name))
    user.registration_name = None
    pair = create_session(session, user, transport, settings)
    session.commit()
    return pair


def resend_code(
    session: Session,
    raw: str,
    settings: Settings,
    new_contact: str | None = None,
) -> VerificationTicket:
    user, challenge = locked_challenge(session, raw, settings)
    wait = RESEND_SECONDS - int((datetime.now(UTC) - challenge.sent_at).total_seconds())
    if wait > 0:
        raise RateLimited(wait)
    if new_contact is not None:
        channel, contact = normalize_contact(new_contact)
        duplicate = session.scalar(
            select(User.id).where(
                (User.email == contact) if channel == "email" else (User.phone == contact),
                User.id != user.id,
            )
        )
        if duplicate:
            raise Conflict("Não foi possível usar esse contato. Tente entrar na sua conta.")
        user.email = contact if channel == "email" else None
        user.phone = contact if channel == "phone" else None
        challenge.channel, challenge.contact = channel, contact
    code = send_code(challenge, settings)
    result = ticket(challenge, raw, code)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise Conflict("Não foi possível usar esse contato. Tente entrar na sua conta.") from None
    return result
