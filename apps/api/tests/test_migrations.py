from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text


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
