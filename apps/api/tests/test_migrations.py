from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from app.infrastructure.models import User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_team_profiles import DATA, client_for


def test_migration_roundtrip(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            "users",
            "players",
            "teams",
            "team_memberships",
            "membership_permissions",
            "verification_challenges",
            "auth_sessions",
            "refresh_tokens",
            "auth_rate_limits",
        }
        command.check(config)


def test_incremental_migration_preserves_foundation_data(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    user_id, player_id = uuid4(), uuid4()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001")
        connection.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email)"),
            {"id": user_id, "email": "preserved@example.com"},
        )
        connection.execute(
            text("INSERT INTO players (id, user_id, display_name) VALUES (:id, :user_id, :name)"),
            {"id": player_id, "user_id": user_id, "name": "Perfil existente"},
        )
        command.upgrade(config, "head")
        assert (
            connection.execute(
                text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
            ).scalar_one()
            == "preserved@example.com"
        )
        row = connection.execute(
            text("SELECT display_name, photo_url FROM players WHERE id = :id"), {"id": player_id}
        ).one()
        assert row.display_name == "Perfil existente" and row.photo_url is None


def test_0003_preserves_existing_team_account_and_session(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        player = make_player(session)
        user = session.get(User, player.user_id)
        assert user
        user.password_hash = hash_password("migration-password-123")
        contact = user.email
        client = client_for(session, player)
        original = client.post("/v1/teams", json={**DATA, "name": "Tabajara FC"}).json()
        session.close()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0002")
            legacy = dict(connection.execute(text("SELECT * FROM teams")).mappings().one())
            assert legacy["modality"] == "society"
            preserved = {
                table: connection.execute(text(f"SELECT * FROM {table}")).all()
                for table in [
                    "users",
                    "players",
                    "team_memberships",
                    "auth_sessions",
                    "refresh_tokens",
                ]
            }
            command.upgrade(config, "0003")
            migrated = dict(connection.execute(text("SELECT * FROM teams")).mappings().one())
            assert migrated.pop("modalities") == [legacy.pop("modality")]
            assert migrated == legacy
            for table, rows in preserved.items():
                assert connection.execute(text(f"SELECT * FROM {table}")).all() == rows
            command.upgrade(config, "head")
        # The old access session and credentials still work after the schema upgrade.
        assert client.get(f"/v1/teams/{original['id']}").json() == original
        assert (
            client.post(
                "/v1/auth/login", json={"contact": contact, "password": "migration-password-123"}
            ).status_code
            == 200
        )


def test_0003_downgrade_refuses_to_discard_multiple_modalities(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        client = client_for(session, make_player(session))
        team = client.post("/v1/teams", json={**DATA, "modalities": ["society", "futsal"]}).json()
    with pytest.raises(RuntimeError, match="multiple modalities"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT modalities FROM teams")) == team["modalities"]
