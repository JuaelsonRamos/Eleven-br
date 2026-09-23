from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from tests.conftest import make_player
from tests.test_events import DATA as EVENT_DATA
from tests.test_team_profiles import DATA, client_for


def test_events_upgrade_preserves_all_existing_data(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        client = client_for(session, make_player(session))
        team = client.post("/v1/teams", json={**DATA, "name": "Tabajara FC"}).json()
        assert (
            client.post(
                f"/v1/teams/{team['id']}/players", json={"name": "Jogador manual"}
            ).status_code
            == 201
        )
        session.close()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0004")
            tables = [
                table
                for table in inspect(connection).get_table_names()
                if table != "alembic_version"
            ]
            before = {
                table: connection.execute(
                    text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY to_jsonb(t)::text')
                )
                .scalars()
                .all()
                for table in tables
            }
            command.upgrade(config, "head")
            for table in tables:
                assert (
                    connection.execute(
                        text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY to_jsonb(t)::text')
                    )
                    .scalars()
                    .all()
                    == before[table]
                )
            command.check(config)
            command.downgrade(config, "0004")
            command.upgrade(config, "head")
        assert client.get("/v1/me").status_code == 200
        assert client.get(f"/v1/teams/{team['id']}/players").json()["active_count"] == 2


def test_events_downgrade_refuses_data_loss(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with Session(engine) as session:
        client = client_for(session, make_player(session))
        team = client.post("/v1/teams", json=DATA).json()
        created = client.post(
            f"/v1/teams/{team['id']}/events", json={**EVENT_DATA, "modality": "society"}
        )
        assert created.status_code == 201
    with pytest.raises(RuntimeError, match="event data"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
