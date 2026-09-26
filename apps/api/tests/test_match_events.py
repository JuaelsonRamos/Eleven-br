from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import match_events
from app.application.teams import add_member
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.match_event_models import MatchEvent
from app.infrastructure.models import MembershipPermission, Player, TeamMembership, User
from tests.conftest import make_player
from tests.test_formations import draw_payload, setup_formation
from tests.test_matches import action, create, setup_match
from tests.test_team_profiles import client_for


def setup_incidents(session, plan=Plan.FREE):
    owner, team, client, event, formation, payload = setup_match(session, plan)
    match = action(client, event, create(client, event, payload), "start")
    path = event + f"/matches/{match['id']}/events"
    return owner, team, client, event, formation, path, client.get(path).json()


def post(client, path, page, person, type="GOAL", assist=None, status=201):
    response = client.post(
        path,
        json={
            "expected_version": page["match"]["version"],
            "type": type,
            "participant_id": person,
            "assist_participant_id": assist,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def edit(client, path, page, item, person, type="GOAL", assist=None, status=200):
    response = client.put(
        path + "/" + item["id"],
        json={
            "expected_version": page["match"]["version"],
            "type": type,
            "participant_id": person,
            "assist_participant_id": assist,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def remove(client, path, page, item, confirm=True, status=200):
    response = client.post(
        path + "/" + item["id"] + "/remove",
        json={"expected_version": page["match"]["version"], "confirm": confirm},
    )
    assert response.status_code == status, response.text
    return response.json()


def test_goals_assists_guests_cards_edit_remove_and_official_score(session):
    owner, _, client, event, formation, path, page = setup_incidents(session)
    original_formation = client.get(event + "/formation").json()["formation"]
    identities = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in [User, Player, TeamMembership]
    }
    # One of the two squads necessarily has two guests (six participants / three squads).
    guest_squad = next(
        s for s in formation["squads"][:2] if all(p["guest_id"] for p in s["participants"])
    )
    scorer, assistant = [p["id"] for p in guest_squad["participants"]]
    page = post(client, path, page, scorer)
    assert page["items"][0]["assist_participant_id"] is None
    page = post(client, path, page, scorer, assist=assistant)
    assert sum(g["identified"] for g in page["goals"]) == 2
    assert sum(g["excess"] for g in page["goals"]) == 2
    page = post(client, path, page, assistant, "YELLOW_CARD")
    page = post(client, path, page, assistant, "YELLOW_CARD")
    assert len([i for i in page["items"] if i["type"] == "YELLOW_CARD"]) == 2
    assert not any(i["type"] == "RED_CARD" for i in page["items"])
    page = post(client, path, page, assistant, "RED_CARD")
    assert page["match"]["home_score"] == page["match"]["away_score"] == 0
    card = page["items"][-1]
    page = edit(client, path, page, card, scorer, "YELLOW_CARD")
    assert page["items"][-1]["type"] == "YELLOW_CARD"
    goal = page["items"][1]
    page = edit(client, path, page, goal, assistant, assist=scorer)
    assert page["items"][1]["participant_id"] == assistant
    session.expire_all()
    stored = session.get(MatchEvent, UUID(goal["id"]))
    assert stored.created_by_user_id == owner.user_id == stored.updated_by_user_id
    assert stored.updated_at > stored.created_at
    match = action(client, event, page["match"], "score", home_score=3, away_score=2)
    match = action(client, event, match, "finish", confirm=True)
    page = client.get(path).json()
    assert page["can_manage"] and page["match"]["status"] == "FINISHED"
    assert sum(g["missing"] for g in page["goals"]) == 3
    page = post(client, path, page, assistant, assist=scorer)
    assert page["match"]["finished_at"] == match["finished_at"]
    remove(client, path, page, goal, confirm=False, status=409)
    page = remove(client, path, page, goal)
    assert page["match"]["home_score"] == 3 and page["match"]["away_score"] == 2
    assert all(i["id"] != goal["id"] for i in page["items"])
    session.expire_all()
    assert session.get(MatchEvent, UUID(goal["id"])).removed_at is not None
    remove(client, path, page, goal, status=404)
    assert client.get(event + "/formation").json()["formation"] == original_formation
    assert identities == {
        model: session.scalar(select(func.count()).select_from(model)) for model in identities
    }


def test_invalid_assists_and_payloads(session):
    _, _, client, _, _, path, page = setup_incidents(session)
    a = page["participants"][0]
    opponent = next(p for p in page["participants"] if p["squad_id"] != a["squad_id"])
    mate = next(
        p for p in page["participants"] if p["squad_id"] == a["squad_id"] and p["id"] != a["id"]
    )
    for assist in [a["id"], opponent["id"]]:
        post(client, path, page, a["id"], assist=assist, status=409)
    post(client, path, page, a["id"], assist=str(uuid4()), status=404)
    post(client, path, page, a["id"], "YELLOW_CARD", mate["id"], status=409)
    for type in ["ASSIST", "OWN_GOAL", "PENALTY", "invalid"]:
        post(client, path, page, a["id"], type, status=422)
    data = {"expected_version": page["match"]["version"], "type": "GOAL", "participant_id": a["id"]}
    for field in ["team_id", "event_id", "formation_id", "squad_id", "created_by_user_id"]:
        assert client.post(path, json={**data, field: str(uuid4())}).status_code == 422
    assert client.get(path).json()["items"] == []


def test_only_saved_participants_of_match_not_other_squads_or_excluded(session):
    _, _, client, event = setup_formation(session)
    page = client.get(event + "/formation").json()
    payload = draw_payload(page)
    payload["participants"].pop()
    formation = client.post(event + "/formation/draw", json=payload).json()["formation"]
    match = create(
        client,
        event,
        {
            "formation_id": formation["id"],
            "expected_formation_version": 1,
            "home_formation_team_id": formation["squads"][0]["id"],
            "away_formation_team_id": formation["squads"][1]["id"],
        },
    )
    match = action(client, event, match, "start")
    path = event + f"/matches/{match['id']}/events"
    page = client.get(path).json()
    invalid = [
        formation["excluded"][0]["id"],
        formation["squads"][2]["participants"][0]["id"],
        str(uuid4()),
    ]
    for person in invalid:
        post(client, path, page, person, status=404)
        post(client, path, page, page["participants"][0]["id"], assist=person, status=404)
    # Removing a guest from current attendance must not erase saved participation/history.
    guest = next(p for s in formation["squads"][:2] for p in s["participants"] if p["guest_id"])
    client.post(event + f"/guests/{guest['guest_id']}/remove")
    page = post(client, path, page, guest["id"])
    assert any(p["id"] == guest["id"] for p in page["participants"])


def test_permissions_scopes_and_ids(session):
    _, team, client, event, formation, path, page = setup_incidents(session)
    person = page["participants"][0]["id"]
    page = post(client, path, page, person)
    item = page["items"][0]
    member = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=member.id)
    common = client_for(session, member)
    assert common.get(path).status_code == 200
    assert not common.get(path).json()["can_manage"]
    post(common, path, page, person, status=403)
    edit(common, path, page, item, person, status=403)
    remove(common, path, page, item, status=403)
    post(client, path, page, str(membership.id), status=404)
    post(client, path, page, str(member.id), status=404)
    other_owner, other_team, other, _, _, other_path, other_page = setup_incidents(session)
    other_person = other_page["participants"][0]["id"]
    other_page = post(other, other_path, other_page, other_person)
    assert client.get(other_path).status_code == 404
    post(client, path, page, other_person, status=404)
    edit(client, path, page, other_page["items"][0], person, status=404)
    remove(client, path, page, other_page["items"][0], status=404)
    second = create(
        client,
        event,
        {
            "formation_id": formation["id"],
            "expected_formation_version": formation["version"],
            "home_formation_team_id": page["match"]["home_formation_team_id"],
            "away_formation_team_id": page["match"]["away_formation_team_id"],
        },
    )
    second = action(client, event, second, "start")
    second_path = event + f"/matches/{second['id']}/events"
    second_page = client.get(second_path).json()
    edit(client, second_path, second_page, item, person, status=404)
    remove(client, second_path, second_page, item, status=404)
    assert client.get(second_path).json()["items"] == []
    for original, replacement in [
        (str(team.id), str(other_team.id)),
        (event.rsplit("/", 1)[1], other_page["match"]["event_id"]),
        (page["match"]["id"], other_page["match"]["id"]),
    ]:
        forged = path.replace(original, replacement)
        assert client.get(forged).status_code == 404
        post(client, forged, page, person, status=404)
    membership.status = "inactive"
    session.commit()
    assert common.get(path).status_code == 404
    session.get(User, other_owner.user_id).status = "inactive"
    session.commit()
    assert other.get(other_path).status_code == 401


def test_member_goal_and_assistance_use_saved_formation_identity(session):
    _, _, client, event, formation, payload = setup_match(session)
    squad = next(
        s for s in formation["squads"] if any(p["membership_id"] for p in s["participants"])
    )
    member = next(p for p in squad["participants"] if p["membership_id"])
    guest = next(p for p in squad["participants"] if p["guest_id"])
    opponent = next(s for s in formation["squads"] if s["id"] != squad["id"])
    match = create(
        client,
        event,
        {
            **payload,
            "home_formation_team_id": squad["id"],
            "away_formation_team_id": opponent["id"],
        },
    )
    match = action(client, event, match, "start")
    path = event + f"/matches/{match['id']}/events"
    page = client.get(path).json()
    page = post(client, path, page, member["id"], assist=guest["id"])
    page = post(client, path, page, guest["id"], assist=member["id"])
    assert page["items"][0]["participant_id"] == member["id"]
    assert not next(p for p in page["participants"] if p["id"] == member["id"])["is_guest"]


def test_pro_manager_and_free_downgrade(session):
    _, team, client, _, _, path, page = setup_incidents(session, Plan.PRO)
    admin = make_player(session)
    member = add_member(session, team_id=team.id, player_id=admin.id, role=Role.ADMIN)
    manager = client_for(session, admin)
    person = page["participants"][0]["id"]
    post(manager, path, page, person, status=403)
    session.add(
        MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_EVENTS.value)
    )
    session.commit()
    page = post(manager, path, page, person)
    page = edit(manager, path, page, page["items"][0], person)
    page = remove(manager, path, page, page["items"][0])
    team.plan = Plan.FREE.value
    session.commit()
    post(manager, path, page, person, status=403)
    assert client.get(path).json()["can_manage"]


@pytest.mark.parametrize("cancel_event", [False, True])
def test_cancelled_history_is_read_only(session, cancel_event):
    _, _, client, event, _, path, page = setup_incidents(session)
    person = page["participants"][0]["id"]
    page = post(client, path, page, person)
    item = page["items"][0]
    if cancel_event:
        assert client.post(event + "/cancel").status_code == 200
    else:
        action(client, event, page["match"], "cancel", confirm=True)
    page = client.get(path).json()
    assert page["items"] == [item] and not page["can_manage"]
    post(client, path, page, person, status=409)
    edit(client, path, page, item, person, status=409)
    remove(client, path, page, item, status=409)


def test_scheduled_and_duplicate_version_guards(session):
    _, _, client, event, _, payload = setup_match(session)
    match = create(client, event, payload)
    path = event + f"/matches/{match['id']}/events"
    page = client.get(path).json()
    person = page["participants"][0]["id"]
    post(client, path, page, person, status=409)
    action(client, event, match, "start")
    old = client.get(path).json()
    page = post(client, path, old, person)
    post(client, path, old, person, status=409)
    edit(client, path, old, page["items"][0], person, status=409)
    remove(client, path, old, page["items"][0], status=409)
    action(client, event, old["match"], "score", 409, home_score=1, away_score=0)
    assert len(client.get(path).json()["items"]) == 1


def test_parallel_duplicate_create(engine, session):
    owner, team, _, _, _, _, page = setup_incidents(session)
    user_id, team_id = owner.user_id, team.id
    session.commit()
    barrier = Barrier(2)

    def write():
        with Session(engine) as separate:
            barrier.wait()
            try:
                match_events.save(
                    separate,
                    user_id=user_id,
                    team_id=team_id,
                    event_id=UUID(page["match"]["event_id"]),
                    match_id=UUID(page["match"]["id"]),
                    expected_version=page["match"]["version"],
                    type="GOAL",
                    participant_id=UUID(page["participants"][0]["id"]),
                    assist_participant_id=None,
                )
                return "saved"
            except Conflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    assert sorted(results) == ["conflict", "saved"]
    assert session.scalar(select(func.count()).select_from(MatchEvent)) == 1


def test_database_guards_and_downgrade_protect_removed_history(engine, session):
    _, _, client, _, _, path, page = setup_incidents(session)
    person = page["participants"][0]
    opponent = next(p for p in page["participants"] if p["squad_id"] != person["squad_id"])
    page = post(client, path, page, person["id"])
    item = page["items"][0]
    for assignment in [
        "assist_participant_id = participant_id",
        f"assist_participant_id = '{opponent['id']}'",
        f"match_id = '{uuid4()}'",
        f"squad_id = '{opponent['squad_id']}'",
    ]:
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(f"UPDATE match_events SET {assignment} WHERE id = :id"), {"id": item["id"]}
            )
    session.rollback()
    remove(client, path, page, item)
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="match event history"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007")


def test_incremental_upgrade_preserves_all_rows(engine, session):
    _, _, client, event, _, payload = setup_match(session)
    match = create(client, event, payload)
    match = action(client, event, match, "start")
    action(client, event, match, "score", home_score=4, away_score=2)
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007")
        tables = [t for t in inspect(connection).get_table_names() if t != "alembic_version"]

        def snapshot(table):
            return connection.execute(
                text(f'SELECT to_jsonb(t)::text FROM "{table}" t ORDER BY to_jsonb(t)::text')
            ).all()

        before = {table: snapshot(table) for table in tables}
        command.upgrade(config, "head")
        assert all(snapshot(table) == data for table, data in before.items())
        command.check(config)
