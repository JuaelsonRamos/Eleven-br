from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.conftest import make_player
from tests.test_team_profiles import DATA, client_for


def test_roster_migration_preserves_data_and_roundtrips(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        client = client_for(session, make_player(session))
        original = client.post(
            "/v1/teams", json={**DATA, "name": "Tabajara FC", "modalities": ["society", "futsal"]}
        ).json()
        session.close()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0003")
            tables = [
                "users",
                "players",
                "teams",
                "auth_sessions",
                "refresh_tokens",
                "team_memberships",
            ]
            before = {
                table: connection.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                .scalars()
                .all()
                for table in tables
            }
            command.upgrade(config, "head")
            for table in tables:
                after = (
                    connection.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id"))
                    .scalars()
                    .all()
                )
                if table == "team_memberships":
                    for row in after:
                        for field in ["roster_name", "nickname", "contact_phone", "contact_email"]:
                            assert row.pop(field) is None
                assert before[table] == after
            command.downgrade(config, "0003")
            command.upgrade(config, "head")
            command.check(config)
        assert client.get(f"/v1/teams/{original['id']}").json() == original
        page = client.get(f"/v1/teams/{original['id']}/players").json()
        assert page["active_count"] == 1 and page["items"][0]["is_president"]


def test_roster_downgrade_protects_unlinked_players(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        client = client_for(session, make_player(session))
        team = client.post("/v1/teams", json=DATA).json()
        created = client.post(f"/v1/teams/{team['id']}/players", json={"name": "Sem conta"})
        assert created.status_code == 201
    with pytest.raises(RuntimeError, match="roster data"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM players WHERE user_id IS NULL")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
