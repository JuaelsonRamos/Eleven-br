from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.infrastructure.config import Settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must have between 12 and 128 characters")
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    """For a future verified login flow. Not exposed as an API endpoint."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "type": "access",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> UUID:
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "exp", "iat", "iss", "aud", "type"]},
    )
    if payload["type"] != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    try:
        return UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as error:
        raise jwt.InvalidTokenError("Invalid subject") from error
