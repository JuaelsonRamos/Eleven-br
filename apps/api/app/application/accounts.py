from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.sessions import TokenPair, create_session, verified
from app.application.verification import VerificationTicket, prepare_verification
from app.domain.auth import Unauthorized
from app.domain.contacts import normalize_contact
from app.domain.policies import Conflict
from app.infrastructure.config import Settings
from app.infrastructure.models import Player, User
from app.infrastructure.rate_limit import rate_limit
from app.infrastructure.security import hash_password, verify_password

# Equal-cost password verification even for unknown accounts.
DUMMY_HASH = hash_password("dummy-credential-never-used")


def register(
    session: Session,
    *,
    name: str,
    contact: str,
    password: str,
    settings: Settings,
) -> VerificationTicket:
    channel, normalized = normalize_contact(contact)
    user = User(
        email=normalized if channel == "email" else None,
        phone=normalized if channel == "phone" else None,
        registration_name=name,
        password_hash=hash_password(password),
    )
    try:
        session.add(user)
        session.flush()
        result = prepare_verification(session, user, settings)
        session.commit()
        return result
    except IntegrityError:
        session.rollback()
        raise Conflict(
            "Não foi possível cadastrar esse contato. Tente entrar na sua conta."
        ) from None


def login(
    session: Session,
    *,
    contact: str,
    password: str,
    transport: str,
    settings: Settings,
) -> TokenPair | VerificationTicket:
    try:
        channel, normalized = normalize_contact(contact)
    except ValueError:
        verify_password(password, DUMMY_HASH)
        raise Unauthorized("Telefone/e-mail ou senha inválidos.") from None
    rate_limit(session, settings, "login-contact", normalized, limit=10, seconds=900)
    user = session.scalar(
        select(User)
        .where((User.email == normalized) if channel == "email" else (User.phone == normalized))
        .with_for_update()
    )
    password_hash = user.password_hash if user and user.password_hash else DUMMY_HASH
    valid = verify_password(password, password_hash)
    if not user or not user.password_hash or not valid or user.status != "active":
        raise Unauthorized("Telefone/e-mail ou senha inválidos.")
    if not verified(user):
        result = prepare_verification(session, user, settings)
        session.commit()
        return result
    pair = create_session(session, user, transport, settings)
    session.commit()
    return pair


def complete_profile(session: Session, user: User, name: str) -> Player:
    session.execute(select(User).where(User.id == user.id).with_for_update())
    player = session.scalar(select(Player).where(Player.user_id == user.id))
    if player is None:
        player = Player(user_id=user.id, display_name=name)
        session.add(player)
    else:
        player.display_name = name
    session.commit()
    return player
