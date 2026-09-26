from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.application import statistics
from app.application.teams import add_member
from app.domain.statistics import PersonStatistics, Totals, ranking
from app.infrastructure.event_models import Event, EventGuest
from tests.conftest import make_player
from tests.test_events import DATA
from tests.test_formations import draw_payload, setup_formation
from tests.test_match_events import edit, post, remove, setup_incidents
from tests.test_matches import action, create, setup_match
from tests.test_team_profiles import client_for


def get(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def finish(client, event, match):
    match = action(client, event, match, "score", home_score=5, away_score=3)
    return action(client, event, match, "finish", confirm=True)


def person_path(root, person):
    kind = "players" if person["membership_id"] else "guests"
    return root + f"/{kind}/{person['membership_id'] or person['guest_id']}"


def test_totals_participation_profile_corrections_and_official_score(session):
    _, team, client, event, formation, path, page = setup_incidents(session)
    root = f"/v1/teams/{team.id}/statistics"
    a = page["participants"][0]
    b = next(p for p in page["participants"] if p["squad_id"] == a["squad_id"] and p != a)
    a, b = [
        next(p for s in formation["squads"] for p in s["participants"] if p["id"] == item["id"])
        for item in (a, b)
    ]
    page = post(client, path, page, a["id"], assist=b["id"])
    goal = page["items"][0]
    page = post(client, path, page, a["id"], "YELLOW_CARD")
    page = post(client, path, page, b["id"], "RED_CARD")
    assert get(client, root)["summary"]["matches"] == 0
    finish(client, event, page["match"])
    data = get(client, root)
    assert data["summary"] == dict(matches=1, goals=1, assists=1, yellow_cards=1, red_cards=1)
    assert sum(p["totals"]["matches"] for p in data["players"]) == 4
    for p in formation["squads"][2]["participants"]:
        assert get(client, person_path(root, p))["person"]["totals"]["matches"] == 0
    profile = get(client, person_path(root, a))
    assert profile["goals_per_match"] == 1 and profile["assists_per_match"] == 0
    assert profile["history"][0]["home_score"] == 5
    assert profile["history"][0]["away_score"] == 3
    assert profile["history"][0]["goals"] == 1
    page = get(client, path)
    page = edit(client, path, page, goal, b["id"], assist=a["id"])
    assert get(client, person_path(root, a))["person"]["totals"]["assists"] == 1
    assert get(client, person_path(root, b))["person"]["totals"]["goals"] == 1
    remove(client, path, page, goal)
    assert get(client, root)["summary"] == dict(
        matches=1, goals=0, assists=0, yellow_cards=1, red_cards=1
    )
    assert get(client, person_path(root, a))["history"][0]["home_score"] == 5


def test_scheduled_cancelled_and_multiple_matches_without_incidents(session):
    _, team, client, event, formation, payload = setup_match(session)
    root = f"/v1/teams/{team.id}/statistics"
    match = create(client, event, payload)
    assert get(client, root)["summary"]["matches"] == 0
    match = action(client, event, match, "start")
    page = get(client, event + f"/matches/{match['id']}/events")
    post(client, event + f"/matches/{match['id']}/events", page, page["participants"][0]["id"])
    match = get(client, event + "/matches")[0]
    action(client, event, match, "cancel", confirm=True)
    assert get(client, root)["summary"]["goals"] == 0
    for _ in range(2):
        finish(client, event, action(client, event, create(client, event, payload), "start"))
    p = formation["squads"][0]["participants"][0]
    profile = get(client, person_path(root, p), limit=1)
    assert profile["person"]["totals"]["matches"] == 2
    assert profile["goals_per_match"] == 0 and profile["has_more"]
    second = get(client, person_path(root, p), limit=1, offset=1)
    assert not second["has_more"]
    assert second["history"][0]["match_id"] != profile["history"][0]["match_id"]


@pytest.mark.parametrize(
    "day,period,expected",
    [
        (date(2026, 9, 1), "month", 1),
        (date(2026, 8, 31), "month", 0),
        (date(2026, 8, 28), "last30", 1),
        (date(2026, 8, 27), "last30", 0),
        (date(2026, 1, 1), "year", 1),
        (date(2025, 12, 31), "year", 0),
        (date(2026, 9, 27), "month", 0),
    ],
)
def test_period_uses_occurrence_date(session, monkeypatch, day, period, expected):
    monkeypatch.setattr(statistics, "today_local", lambda: date(2026, 9, 26))
    _, team, client, event, _, path, page = setup_incidents(session)
    page = post(client, path, page, page["participants"][0]["id"])
    finish(client, event, page["match"])
    occurrence = session.get(Event, UUID(event.split("/")[-1]))
    occurrence.date = day
    session.commit()
    root = f"/v1/teams/{team.id}/statistics"
    assert get(client, root, period=period)["summary"]["goals"] == expected
    assert get(client, root)["summary"]["goals"] == 1
    assert get(client, root, modality=occurrence.modality)["summary"]["goals"] == 1
    other = "futsal" if occurrence.modality != "futsal" else "campo"
    assert get(client, root, modality=other)["summary"]["matches"] == 0


def test_inactive_member_guest_identity_and_read_permissions(session):
    _, team, client, event = setup_formation(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    member_client = client_for(session, player)
    assert member_client.put(event + "/attendance", json={"response": "VOU"}).status_code == 200
    pool = get(client, event + "/formation")
    formation = client.post(
        event + "/formation/draw", json=draw_payload(pool, team_count=2)
    ).json()["formation"]
    payload = dict(
        formation_id=formation["id"],
        expected_formation_version=formation["version"],
        home_formation_team_id=formation["squads"][0]["id"],
        away_formation_team_id=formation["squads"][1]["id"],
    )
    root = f"/v1/teams/{team.id}/statistics"
    finish(client, event, action(client, event, create(client, event, payload), "start"))
    assert get(member_client, root)["summary"]["matches"] == 1
    member.status = "inactive"
    session.commit()
    data = get(client, root)
    historical = next(p for p in data["players"] if p["id"] == str(member.id))
    assert historical["inactive"] and historical["totals"]["matches"] == 1
    assert historical["player_id"] == str(player.id)
    assert member_client.get(root).status_code == 404
    guests = session.scalars(
        select(EventGuest).where(EventGuest.event_id == UUID(event.split("/")[-1]))
    ).all()
    for guest in guests:
        guest.name = "Mesmo nome"
    session.commit()
    data = get(client, root)
    guests_read = [p for p in data["players"] if p["kind"] == "guest"]
    assert len(guests_read) >= 3 and len({p["id"] for p in guests_read}) == len(guests_read)
    assert all(p["player_id"] is None and p["event_date"] for p in guests_read)
    assert get(client, root + f"/players/{member.id}")["person"]["inactive"]
    member.status = "active"
    session.commit()
    assert get(client, root + f"/players/{member.id}")["person"]["totals"]["matches"] == 1


def test_guest_same_name_across_events_and_constant_query_count(session, engine):
    from sqlalchemy import event as sql_event

    _, team, client, _, _, _ = setup_match(session)
    root = f"/v1/teams/{team.id}/statistics"
    ids = []
    for day in ["2026-09-01", "2026-09-15"]:
        occurrence = client.post(f"/v1/teams/{team.id}/events", json={**DATA, "date": day}).json()
        path = f"/v1/teams/{team.id}/events/{occurrence['id']}"
        for name in ["João", "Outro convidado"]:
            assert client.post(path + "/guests", json={"name": name}).status_code == 201
        formation = client.post(
            path + "/formation/draw",
            json=draw_payload(get(client, path + "/formation"), team_count=2),
        ).json()["formation"]
        payload = dict(
            formation_id=formation["id"],
            expected_formation_version=formation["version"],
            home_formation_team_id=formation["squads"][0]["id"],
            away_formation_team_id=formation["squads"][1]["id"],
        )
        match = action(client, path, create(client, path, payload), "start")
        incident_path = path + f"/matches/{match['id']}/events"
        person = next(
            p for s in formation["squads"] for p in s["participants"] if p["name"] == "João"
        )
        ids.append(person["guest_id"])
        page = post(client, incident_path, get(client, incident_path), person["id"])
        finish(client, path, page["match"])
    statements = []

    def count(*args):
        statements.append(args[2])

    sql_event.listen(engine, "before_cursor_execute", count)
    try:
        data = get(client, root)
    finally:
        sql_event.remove(engine, "before_cursor_execute", count)
    assert len(statements) <= 10
    guests = [p for p in data["scorers"] if p["name"] == "João"]
    assert {p["id"] for p in guests} == set(ids)
    assert [p["totals"]["goals"] for p in guests] == [1, 1]
    assert {p["event_date"] for p in guests} == {"2026-09-01", "2026-09-15"}
    assert all(p["goals_position"] == 1 for p in guests)
    for guest_id in ids:
        profile = get(client, root + f"/guests/{guest_id}")
        assert len(profile["history"]) == 1 and profile["person"]["totals"]["matches"] == 1


def test_team_and_person_isolation_validation_and_empty_profile(session):
    _, team, client, _, _, _ = setup_match(session)
    _, other, other_client, _, formation, _ = setup_match(session)
    root = f"/v1/teams/{team.id}/statistics"
    other_root = f"/v1/teams/{other.id}/statistics"
    assert client_for(session).get(root).status_code == 401
    assert client.get(other_root).status_code == 404
    assert other_client.get(root).status_code == 404
    assert client.get(root + f"/players/{other.president_membership_id}").status_code == 404
    guest = next(p for s in formation["squads"] for p in s["participants"] if p["guest_id"])
    assert client.get(root + f"/guests/{guest['guest_id']}").status_code == 404
    assert client.get(root + f"/players/{uuid4()}").status_code == 404
    for params in [{"period": "invalid"}, {"modality": "invalid"}]:
        assert client.get(root, params=params).status_code == 422
    profile = get(client, root + f"/players/{team.president_membership_id}")
    assert profile["history"] == [] and profile["goals_per_match"] == 0
    assert profile["person"]["totals"]["matches"] == 0
    assert (
        client.get(root + f"/players/{team.president_membership_id}?offset=-1").status_code == 422
    )


def test_shared_positions_secondary_criteria_and_stable_order():
    people = [
        PersonStatistics(uuid4(), "member", name, Totals(goals=g, assists=a))
        for name, g, a in [("Zeca", 3, 2), ("Ana", 3, 2), ("Bruno", 3, 1), ("Caio", 0, 4)]
    ]
    scorers = ranking(people)
    assert [(p.name, p.goals_position) for p in scorers] == [("Ana", 1), ("Zeca", 1), ("Bruno", 3)]
    assistants = ranking(people, assists=True)
    assert [(p.name, p.assists_position) for p in assistants] == [
        ("Caio", 1),
        ("Ana", 2),
        ("Zeca", 2),
        ("Bruno", 4),
    ]
