"""Real PostgreSQL tests, isolated in a new schema for each test.

Never truncate or drop an existing database/schema. Run the actual migration in
each generated schema, including deferred FK checks and transactional commits.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.infrastructure.models import Player, User

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    values = dotenv_values(ROOT / ".env")
    url = os.getenv("TEST_DATABASE_URL") or values.get("TEST_DATABASE_URL")
    if not url or not (make_url(url).database or "").endswith("_test"):
        pytest.fail(
            "TEST_DATABASE_URL must point to a dedicated PostgreSQL database ending in _test"
        )
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    from app.infrastructure.config import get_settings

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "only-for-tests-" + "x" * 40)
    monkeypatch.setenv("DEV_VERIFICATION_CODES", "true")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:8081"]')
    get_settings.cache_clear()
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    try:
        with test_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield test_engine
    finally:
        test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()
        get_settings.cache_clear()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def make_player(session: Session) -> Player:
    user = User(email=f"{uuid4().hex}@example.com", email_verified_at=datetime.now(UTC))
    session.add(user)
    session.flush()
    player = Player(user_id=user.id, display_name="Jogador de teste")
    session.add(player)
    session.flush()
    return player
