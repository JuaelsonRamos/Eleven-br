from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from app.infrastructure.config import Settings
from app.infrastructure.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.presentation.schemas import AccountInput


def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused/unused_test",
        jwt_secret="test-only-" + "x" * 40,
    )


def test_argon2_and_token_roundtrip() -> None:
    hashed = hash_password("a-long-test-password")
    assert hashed.startswith("$argon2id$")
    assert verify_password("a-long-test-password", hashed)
    assert not verify_password("another-password", hashed)
    user_id = uuid4()
    config = settings()
    assert decode_access_token(create_access_token(user_id, config), config) == user_id


@pytest.mark.parametrize(
    "change", ["expired", "audience", "issuer", "subject", "type", "signature", "missing_exp"]
)
def test_invalid_tokens_are_rejected(change: str) -> None:
    config = settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=1),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "type": "access",
    }
    if change == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif change == "missing_exp":
        del claims["exp"]
    elif change == "subject":
        claims["sub"] = "not-a-uuid"
    elif change in ("audience", "issuer", "type"):
        claims[{"audience": "aud", "issuer": "iss", "type": "type"}[change]] = "wrong"
    secret = (
        "wrong-secret-" + "y" * 40
        if change == "signature"
        else config.jwt_secret.get_secret_value()
    )
    token = jwt.encode(claims, secret, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, config)


def test_contact_validation() -> None:
    account = AccountInput(
        email="PLAYER@example.com", password="test-password-long", display_name=" Ana "
    )
    assert account.email == "player@example.com"
    assert account.display_name == "Ana"
    AccountInput(phone="+5511999999999", password="test-password-long", display_name="Ana")
    for data in (
        {},
        {"phone": "11999999999"},
        {"email": "invalid"},
        {"email": "ok@example.com", "display_name": " "},
    ):
        with pytest.raises(ValidationError):
            AccountInput.model_validate(
                {"password": "test-password-long", "display_name": "Ana", **data}
            )
