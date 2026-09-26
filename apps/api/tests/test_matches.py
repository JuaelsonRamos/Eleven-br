from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import matches
from app.application.teams import add_member
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.match_models import EventMatch
from app.infrastructure.models import MembershipPermission
from tests.conftest import make_player
from tests.test_events import DATA
from tests.test_formations import draw_payload, setup_formation
from tests.test_team_profiles import client_for


def setup_match(session, plan=Plan.FREE):
    owner, team, client, event = setup_formation(session, plan)
    page = client.get(event + "/formation").json()
    formation = client.post(event + "/formation/draw", json=draw_payload(page)).json()["formation"]
    payload = dict(
        formation_id=formation["id"],
        expected_formation_version=formation["version"],
        home_formation_team_id=formation["squads"][0]["id"],
        away_formation_team_id=formation["squads"][1]["id"],
    )
    return owner, team, client, event, formation, payload


def create(client, event, payload):
    response = client.post(event + "/matches", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def action(client, event, match, op, status=200, **changes):
    payload = {"expected_version": match["version"], **changes}
    response = (client.put if op == "score" else client.post)(
        event + f"/matches/{match['id']}/{op}", json=payload
    )
    assert response.status_code == status, response.text
    return response.json()


def test_match_lifecycle_history_and_free(session):
    owner, _, client, event, formation, payload = setup_match(session)
    match = create(client, event, payload)
    assert (match["home_score"], match["away_score"], match["status"]) == (0, 0, "SCHEDULED")
    action(client, event, match, "score", 409, home_score=1, away_score=0)
    action(client, event, match, "finish", 409, confirm=True)
    match = action(client, event, match, "start")
    assert match["started_at"]
    action(client, event, match, "start", 409)
    stale = match
    match = action(client, event, match, "score", home_score=2, away_score=1)
    action(client, event, stale, "score", 409, home_score=1, away_score=1)
    match = action(client, event, match, "score", home_score=1, away_score=1)
    for bad in [-1, 1.5, True, 1000]:
        action(client, event, match, "score", 422, home_score=bad, away_score=0)
    action(client, event, match, "finish", 409)
    match = action(client, event, match, "finish", confirm=True)
    assert match["finished_at"] and match["home_score"] == match["away_score"]
    action(client, event, match, "score", 409, home_score=3, away_score=1)
    match = action(client, event, match, "score", confirm=True, home_score=3, away_score=1)
    assert match["corrected_at"] and match["updated_at"] >= match["corrected_at"]
    session.expire_all()
    assert session.get(EventMatch, UUID(match["id"])).corrected_by_user_id == owner.user_id
    second = create(client, event, payload)
    action(client, event, second, "cancel", 409)
    second = action(client, event, second, "cancel", confirm=True)
    action(client, event, second, "start", 409)
    action(client, event, second, "cancel", 409, confirm=True)
    action(client, event, second, "score", 409, home_score=0, away_score=0)
    assert client.get(event + "/matches").json() == [match, second]
    assert client.get(event + f"/matches/{match['id']}").json() == match
    page = client.get(event + "/formation").json()
    assert page["locked_by_matches"] and not page["can_manage"]
    assert (
        client.post(
            event + "/formation/draw", json=draw_payload(page, confirm_replace=True)
        ).status_code
        == 409
    )
    person = formation["squads"][0]["participants"][0]["id"]
    assert (
        client.put(
            event + "/formation/participants/" + person,
            json={
                "formation_id": formation["id"],
                "expected_version": formation["version"],
                "squad_id": formation["squads"][1]["id"],
            },
        ).status_code
        == 409
    )
    assert client.get(event + "/formation").json()["formation"] == formation
    assert client.post(event + "/cancel").status_code == 200
    action(client, event, match, "score", 409, confirm=True, home_score=0, away_score=0)
    assert len(client.get(event + "/matches").json()) == 2


def test_ids_permissions_and_formation_version(session):
    _, team, client, event, _, payload = setup_match(session)
    match = create(client, event, payload)
    player = make_player(session)
    add_member(session, team_id=team.id, player_id=player.id)
    member = client_for(session, player)
    assert member.get(event + "/matches").status_code == 200
    assert member.post(event + "/matches", json=payload).status_code == 403
    for op in ["start", "finish", "cancel", "score"]:
        action(
            member,
            event,
            match,
            op,
            403,
            **({"home_score": 0, "away_score": 0} if op == "score" else {}),
        )
    _, other_team, other_client, other_event, _, other_payload = setup_match(session)
    other_match = create(other_client, other_event, other_payload)
    assert client.get(other_event + "/matches").status_code == 404
    assert client.get(event + "/matches/" + other_match["id"]).status_code == 404
    action(client, event, other_match, "start", 404)
    assert (
        client.get(event.replace(str(team.id), str(other_team.id)) + "/matches").status_code == 404
    )
    for key in ["formation_id", "home_formation_team_id", "away_formation_team_id"]:
        assert (
            client.post(event + "/matches", json={**payload, key: other_payload[key]}).status_code
            == 404
        )
        assert (
            client.post(event + "/matches", json={**payload, key: str(uuid4())}).status_code == 404
        )
    assert (
        client.post(
            event + "/matches",
            json={**payload, "away_formation_team_id": payload["home_formation_team_id"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            event + "/matches", json={**payload, "expected_formation_version": 999}
        ).status_code
        == 409
    )
    another = client.post(event.rsplit("/", 1)[0], json=DATA).json()
    other_path = event.rsplit("/", 1)[0] + "/" + another["id"]
    assert client.post(other_path + "/matches", json=payload).status_code == 404
    assert client.get(other_path + "/matches/" + match["id"]).status_code == 404
    assert client.get(other_path + "/matches").json() == []


def test_pro_manager(session):
    _, team, client, event, _, payload = setup_match(session, Plan.PRO)
    player = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=player.id, role=Role.ADMIN)
    session.add(
        MembershipPermission(membership_id=membership.id, permission=Permission.MANAGE_EVENTS.value)
    )
    session.commit()
    manager = client_for(session, player)
    match = create(manager, event, payload)
    match = action(manager, event, match, "start")
    match = action(manager, event, match, "score", home_score=2, away_score=0)
    match = action(manager, event, match, "finish", confirm=True)
    assert match["status"] == "FINISHED"
    team.plan = Plan.FREE.value
    session.commit()
    action(manager, event, match, "cancel", 403, confirm=True)


def test_concurrent_scores(engine, session):
    owner, team, client, event, _, payload = setup_match(session)
    match = action(client, event, create(client, event, payload), "start")
    user_id, team_id = owner.user_id, team.id
    session.commit()
    barrier = Barrier(2)

    def update(home, away):
        with Session(engine) as separate:
            barrier.wait()
            try:
                matches.change(
                    separate,
                    user_id=user_id,
                    team_id=team_id,
                    event_id=UUID(event.rsplit("/", 1)[1]),
                    match_id=UUID(match["id"]),
                    action="score",
                    expected_version=match["version"],
                    home_score=home,
                    away_score=away,
                )
                return "ok"
            except Conflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: update(*pair), [(1, 0), (0, 1)]))
    assert sorted(results) == ["conflict", "ok"]


def test_database_constraints_and_safe_downgrade(engine, session):
    _, _, client, event, _, payload = setup_match(session)
    match = create(client, event, payload)
    for expression in [
        "home_score = -1",
        "away_formation_team_id = home_formation_team_id",
        "formation_id = '" + str(uuid4()) + "'",
    ]:
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(f"UPDATE event_matches SET {expression} WHERE id = :id"), {"id": match["id"]}
            )
    session.rollback()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="match history"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0006")
    assert client.get(event + "/matches").json() == [match]


def test_upgrade_preserves_existing_formation(engine, session):
    _, _, client, event, formation, _ = setup_match(session)
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006")
        tables = [
            "users",
            "players",
            "teams",
            "team_memberships",
            "events",
            "event_guests",
            "event_attendance",
            "event_formations",
            "formation_squads",
            "formation_participants",
            "auth_sessions",
            "refresh_tokens",
        ]

        def snapshot(table):
            return connection.execute(
                text(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY to_jsonb(t)::text")
            ).all()

        before = {table: snapshot(table) for table in tables}
        command.upgrade(config, "head")
        assert all(snapshot(table) == rows for table, rows in before.items())
        command.check(config)
    assert client.get(event + "/formation").json()["formation"] == formation
