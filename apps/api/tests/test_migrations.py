from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect


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
        }
        command.check(config)
