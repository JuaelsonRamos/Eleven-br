import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.domain.auth import ACCESS_MINUTES
from app.infrastructure.config import Settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if not 8 <= len(password) <= 128:
        raise ValueError("Password must have between 8 and 128 characters")
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: UUID, settings: Settings, session_id: UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_MINUTES),
            "sid": str(session_id),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "type": "access",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID


def secret_digest(value: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "sid", "exp", "iat", "iss", "aud", "type"]},
    )
    if payload["type"] != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    try:
        return AccessClaims(UUID(payload["sub"]), UUID(payload["sid"]))
    except (ValueError, TypeError, AttributeError) as error:
        raise jwt.InvalidTokenError("Invalid subject") from error
