from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.sessions import refresh_session
from app.application.verification import confirm_code
from app.domain.auth import InvalidVerification, Unauthorized
from app.domain.contacts import normalize_contact
from app.infrastructure.auth_models import AuthSession, RefreshToken, VerificationChallenge
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_session
from app.infrastructure.models import Player, TeamMembership, User

PASSWORD = "futebol123"


@pytest.fixture
def client(session: Session):
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


def register(client, contact=None):
    contact = contact or f"{uuid4().hex}@example.com"
    response = client.post(
        "/v1/auth/register",
        json={
            "name": " Ana Silva ",
            "contact": contact,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def verify(client, ticket):
    return client.post(
        "/v1/auth/verify",
        json={
            "challenge_token": ticket["challenge_token"],
            "code": ticket["development_code"],
        },
    )


def auth_header(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


@pytest.mark.parametrize(
    "contact,field,expected",
    [
        ("  ANA@Example.com ", "email", "ana@example.com"),
        ("(11) 99999-9999", "phone", "+5511999999999"),
    ],
)
def test_registration_verification_profile(client, session, contact, field, expected):
    ticket = register(client, contact)
    user = session.scalar(select(User))
    assert getattr(user, field) == expected
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    assert session.scalar(select(func.count()).select_from(Player)) == 0
    challenge = session.scalar(select(VerificationChallenge))
    assert challenge.code_hash != ticket["development_code"]
    assert challenge.handle_hash != ticket["challenge_token"]
    assert challenge.purpose == "verify_contact"
    response = verify(client, ticket)
    assert response.status_code == 200, response.text
    pair = response.json()
    me = client.get("/v1/me", headers=auth_header(pair))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Ana Silva"
    assert me.json()["player_id"] != me.json()["user_id"]
    assert me.json()["photo_url"] is None
    assert "password" not in me.text
    assert session.scalar(select(func.count()).select_from(TeamMembership)) == 0
    assert verify(client, ticket).status_code == 400
    assert (
        client.post("/v1/auth/login", json={"contact": contact, "password": PASSWORD}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("ana@example.com", "ANA@EXAMPLE.COM"),
        ("(11) 99999-9999", "+5511999999999"),
    ],
)
def test_duplicate_normalized_contact(client, session, first, second):
    register(client, first)
    result = client.post(
        "/v1/auth/register",
        json={
            "name": "Outra",
            "contact": second,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert result.status_code == 409
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_wrong_expired_and_exhausted_code(client, session):
    ticket = register(client)
    bad_code = "000001" if ticket["development_code"] == "000000" else "000000"
    for _ in range(5):
        result = client.post(
            "/v1/auth/verify",
            json={
                "challenge_token": ticket["challenge_token"],
                "code": bad_code,
            },
        )
        assert result.status_code == 400
    assert "Limite" in verify(client, ticket).json()["detail"]
    challenge = session.scalar(select(VerificationChallenge))
    assert challenge.attempts == 5
    challenge.sent_at -= timedelta(seconds=61)
    session.commit()
    ticket = client.post(
        "/v1/auth/resend", json={"challenge_token": ticket["challenge_token"]}
    ).json()
    assert challenge.attempts == 0
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert "expirado" in verify(client, ticket).json()["detail"]


def test_resend_cooldown_old_code_and_change_contact(client, session):
    old = register(client, "wrong@example.com")
    result = client.post("/v1/auth/resend", json={"challenge_token": old["challenge_token"]})
    assert result.status_code == 429 and int(result.headers["Retry-After"]) > 0
    challenge = session.scalar(select(VerificationChallenge))
    challenge.sent_at -= timedelta(seconds=61)
    session.commit()
    updated = client.post(
        "/v1/auth/change-contact",
        json={
            "challenge_token": old["challenge_token"],
            "contact": "(21) 98888-7777",
        },
    )
    assert updated.status_code == 200, updated.text
    user = session.scalar(select(User))
    assert user.email is None and user.phone == "+5521988887777"
    if updated.json()["development_code"] != old["development_code"]:
        assert verify(client, old).status_code == 400
    assert verify(client, updated.json()).status_code == 200


def test_login_unverified_wrong_password_and_success(client, session):
    ticket = register(client, "ana@example.com")
    credentials = {"contact": "ANA@example.com", "password": PASSWORD}
    pending = client.post("/v1/auth/login", json=credentials)
    assert pending.status_code == 200
    assert pending.json()["status"] == "verification_required"
    assert "access_token" not in pending.json()
    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert verify(client, ticket).status_code == 400  # Old continuation handle revoked by login.
    resumed = {**pending.json(), "development_code": ticket["development_code"]}
    assert verify(client, resumed).status_code == 200
    assert client.post("/v1/auth/login", json=credentials).json()["status"] == "authenticated"
    incorrect = client.post("/v1/auth/login", json={**credentials, "password": "wrong"})
    absent = client.post("/v1/auth/login", json={**credentials, "contact": "absent@example.com"})
    assert incorrect.status_code == absent.status_code == 401
    assert incorrect.json() == absent.json()


def test_refresh_rotation_replay_and_logout(client, session):
    pair = verify(client, register(client, "ana@example.com")).json()
    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200
    current = refreshed.json()
    assert current["refresh_token"] != pair["refresh_token"]
    assert client.get("/v1/me", headers=auth_header(current)).status_code == 200
    assert (
        client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )
    assert client.get("/v1/me", headers=auth_header(current)).status_code == 401
    assert (
        client.post(
            "/v1/auth/refresh", json={"refresh_token": current["refresh_token"]}
        ).status_code
        == 401
    )
    pair = client.post(
        "/v1/auth/login", json={"contact": "ana@example.com", "password": PASSWORD}
    ).json()
    assert (
        client.post("/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}).status_code
        == 204
    )
    assert client.get("/v1/me", headers=auth_header(pair)).status_code == 401
    assert (
        client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )
    assert session.scalar(select(func.count()).select_from(User)) == 1
    for token in session.scalars(select(RefreshToken)):
        assert token.token_hash not in (pair["refresh_token"], current["refresh_token"])


def test_expired_access_refresh_and_disabled_account(client, session):
    pair = verify(client, register(client)).json()
    settings = get_settings()
    claims = jwt.decode(pair["access_token"], options={"verify_signature": False})
    claims["exp"] = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    pair = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).json()
    auth_session = session.scalar(select(AuthSession))
    auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert (
        client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )
    assert client.get("/v1/me").status_code == 401


def test_cookie_transport_csrf_and_profile(client, session):
    client.headers.update({"X-Eleven-Client": "web", "Origin": "http://localhost:8081"})
    response = verify(client, register(client))
    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/v1/auth/refresh", json={}, headers={"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/v1/auth/refresh", json={}, headers={"X-Eleven-Client": "native"}).status_code
        == 401
    )
    refreshed = client.post("/v1/auth/refresh", json={})
    assert refreshed.status_code == 200
    saved = client.put(
        "/v1/me/profile", json={"name": "Ana Souza"}, headers=auth_header(refreshed.json())
    )
    assert saved.status_code == 200 and saved.json()["display_name"] == "Ana Souza"
    assert client.post("/v1/auth/logout", json={}).status_code == 204
    assert client.post("/v1/auth/refresh", json={}).status_code == 401
    assert client.get("/v1/me", headers=auth_header(refreshed.json())).status_code == 401


def test_rate_limit_and_validation_do_not_leak_secrets(client):
    for _ in range(10):
        assert (
            client.post(
                "/v1/auth/login", json={"contact": "unknown@example.com", "password": "bad"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/v1/auth/login", json={"contact": "unknown@example.com", "password": "bad"}
        ).status_code
        == 429
    )
    result = client.post(
        "/v1/auth/register",
        json={
            "name": "Ana",
            "contact": "ana@example.com",
            "password": "sensitive",
            "password_confirmation": "different",
        },
    )
    assert (
        result.status_code == 422
        and "sensitive" not in result.text
        and "different" not in result.text
    )


def test_development_delivery_is_opt_in_and_production_rejects_it(client, monkeypatch, session):
    monkeypatch.setenv("DEV_VERIFICATION_CODES", "false")
    get_settings.cache_clear()
    response = client.post(
        "/v1/auth/register",
        json={
            "name": "Ana",
            "contact": "ana@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 503 and "development_code" not in response.text
    session.rollback()
    assert session.scalar(select(func.count()).select_from(User)) == 0
    with pytest.raises(ValidationError):
        Settings(app_env="production", dev_verification_codes=True)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(11) 99999-9999", "+5511999999999"),
        ("5511999999999", "+5511999999999"),
        ("+1 415 555 1234", "+14155551234"),
        ("  ANA@EXAMPLE.COM ", "ana@example.com"),
    ],
)
def test_normalization(raw, expected):
    assert normalize_contact(raw)[1] == expected


def test_verification_is_single_use_under_concurrency(client, session, engine):
    ticket = register(client)
    settings = get_settings()

    def attempt(_):
        with Session(engine) as concurrent:
            try:
                confirm_code(
                    concurrent,
                    ticket["challenge_token"],
                    ticket["development_code"],
                    "native",
                    settings,
                )
                return "verified"
            except InvalidVerification:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == ["rejected", "verified"]
    assert session.scalar(select(func.count()).select_from(Player)) == 1
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_concurrent_refresh_replay_revokes_session(client, session, engine):
    pair = verify(client, register(client)).json()
    settings = get_settings()

    def attempt(_):
        with Session(engine) as concurrent:
            try:
                refresh_session(concurrent, pair["refresh_token"], "native", settings)
                return "refreshed"
            except Unauthorized:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == ["refreshed", "rejected"]
    session.expire_all()
    assert session.scalar(select(AuthSession)).revoked_at is not None


def test_independent_devices_logout_and_inactive_user(client, session):
    first = verify(client, register(client, "ana@example.com")).json()
    second = client.post(
        "/v1/auth/login", json={"contact": "ana@example.com", "password": PASSWORD}
    ).json()
    assert (
        client.post("/v1/auth/logout", json={"refresh_token": first["refresh_token"]}).status_code
        == 204
    )
    assert client.get("/v1/me", headers=auth_header(second)).status_code == 200
    user = session.scalar(select(User))
    user.status = "inactive"
    session.commit()
    assert client.get("/v1/me", headers=auth_header(second)).status_code == 401
    assert (
        client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/auth/login", json={"contact": "ana@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )


def test_resend_budget_survives_login_handle_rotation(client, session):
    ticket = register(client, "ana@example.com")
    for _ in range(5):
        challenge = session.scalar(select(VerificationChallenge))
        challenge.sent_at -= timedelta(seconds=61)
        session.commit()
        result = client.post("/v1/auth/resend", json={"challenge_token": ticket["challenge_token"]})
        assert result.status_code == 200
        ticket = result.json()
    resumed = client.post(
        "/v1/auth/login", json={"contact": "ana@example.com", "password": PASSWORD}
    ).json()
    assert (
        client.post(
            "/v1/auth/resend", json={"challenge_token": resumed["challenge_token"]}
        ).status_code
        == 429
    )


def test_profile_completion_for_existing_verified_account(client, session):
    from app.application.sessions import create_session

    user = User(email="legacy@example.com", email_verified_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    pair = create_session(session, user, "native", get_settings())
    session.commit()
    headers = {"Authorization": f"Bearer {pair.access_token}"}
    assert client.get("/v1/me", headers=headers).json()["player_id"] is None
    assert client.put("/v1/me/profile", json={"name": "Nome"}, headers=headers).status_code == 200
    assert (
        client.put("/v1/me/profile", json={"name": "Novo Nome"}, headers=headers).status_code == 200
    )
    assert session.scalar(select(func.count()).select_from(Player)) == 1
