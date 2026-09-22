from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import events
from app.application.teams import add_member
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.event_models import Event, EventAttendance, EventSeries
from app.infrastructure.models import MembershipPermission, Player, TeamMembership, User
from tests.conftest import make_player
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for

DATA = {
    "modality": "campo",
    "kind": "PELADA",
    "title": "Pelada de Domingo",
    "date": "2026-09-27",
    "time": "08:00",
    "location": "Campo do bairro",
}


def setup_events(session: Session, plan: Plan = Plan.FREE):
    president = make_player(session)
    team = make_team(session, president, plan)
    client = client_for(session, president)
    return president, team, client, f"/v1/teams/{team.id}/events"


def test_create_edit_attendance_and_cancel_preserve_identity(session: Session) -> None:
    owner, team, client, path = setup_events(session)
    before = client.get(f"/v1/teams/{team.id}").json()
    created = client.post(path, json=DATA)
    assert created.status_code == 201, created.text
    item = created.json()
    detail = f"{path}/{item['id']}"
    assert item["pending"] == 1 and item["going"] == 0 and item["can_manage"]
    assert item["participants"][0]["player_id"] == str(owner.id)
    assert item["series_id"] is None and item["status"] == "open"
    assert (
        client.put(detail, json={**DATA, "title": "Novo título"}).json()["title"] == "Novo título"
    )
    for response in ["VOU", "VOU", "NAO_VOU", "VOU"]:
        result = client.put(detail + "/attendance", json={"response": response})
        assert result.status_code == 200
        assert result.json()["my_response"] == response and result.json()["pending"] == 0
        assert result.json()["going"] == (response == "VOU")
        assert result.json()["not_going"] == (response == "NAO_VOU")
    assert session.scalar(select(func.count()).select_from(EventAttendance)) == 1
    assert client.post(detail + "/cancel").json()["status"] == "cancelled"
    assert client.post(detail + "/cancel").status_code == 200
    assert client.put(detail + "/attendance", json={"response": "NAO_VOU"}).status_code == 409
    assert client.put(detail, json=DATA).status_code == 409
    assert client.post(detail + "/guests", json={"name": "Convidado"}).status_code == 409
    assert client.get(detail).json()["going"] == 1
    assert client.get(f"/v1/teams/{team.id}").json() == before
    assert client.get("/v1/me").status_code == 200


def test_weekly_occurrences_are_unique_independent_and_stable(session: Session) -> None:
    _, _, client, path = setup_events(session)
    first = client.post(path, json={**DATA, "recurring_until": "2026-10-18"}).json()
    items = client.get(path).json()["items"]
    assert sorted(item["date"] for item in items) == [
        "2026-09-27",
        "2026-10-04",
        "2026-10-11",
        "2026-10-18",
    ]
    assert len({item["series_id"] for item in items}) == 1
    assert len({item["id"] for item in items}) == 4
    assert session.scalar(select(func.count()).select_from(EventSeries)) == 1
    for _ in range(3):
        assert client.get(path).json()["items"] == items
    detail = f"{path}/{first['id']}"
    assert client.put(detail + "/attendance", json={"response": "VOU"}).status_code == 200
    assert client.put(detail, json={**DATA, "date": "2026-09-28"}).status_code == 200
    assert client.put(detail, json={**DATA, "kind": "JOGO"}).status_code == 409
    assert client.post(detail + "/cancel").status_code == 200
    others = [item for item in client.get(path).json()["items"] if item["id"] != first["id"]]
    assert all(item["going"] == 0 and item["status"] == "open" for item in others)
    existing = session.get(Event, UUID(first["id"]))
    assert existing and existing.recurrence_date == date(2026, 9, 27)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(
            Event(
                team_id=existing.team_id,
                series_id=existing.series_id,
                recurrence_date=existing.recurrence_date,
                modality="campo",
                kind="PELADA",
                title="Duplicate",
                date=existing.date,
                time=existing.time,
                location="Campo",
            )
        )
        session.flush()


def test_member_can_only_respond_for_self_and_active_roster(session: Session) -> None:
    _, team, client, path = setup_events(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    member_client = client_for(session, player)
    manual = client.post(f"/v1/teams/{team.id}/players", json={"name": "Manual"}).json()
    item = client.post(path, json=DATA).json()
    detail = f"{path}/{item['id']}"
    assert item["pending"] == 3
    assert member_client.get(path).json()["can_manage"] is False
    answer = member_client.put(detail + "/attendance", json={"response": "VOU"}).json()
    assert answer["going"] == 1 and answer["pending"] == 2
    assert [p["membership_id"] for p in answer["participants"] if p["response"] == "VOU"] == [
        str(member.id)
    ]
    assert (
        member_client.put(
            detail + "/attendance",
            json={"response": "VOU", "membership_id": manual["membership_id"]},
        ).status_code
        == 422
    )
    assert member_client.post(path, json=DATA).status_code == 403
    assert member_client.put(detail, json=DATA).status_code == 403
    assert member_client.post(detail + "/cancel").status_code == 403
    assert member_client.post(detail + "/guests", json={"name": "Intruso"}).status_code == 403
    member.status = "inactive"
    session.commit()
    assert (
        member_client.put(detail + "/attendance", json={"response": "NAO_VOU"}).status_code == 404
    )
    assert member_client.get(detail).status_code == 404
    # Inactive answers are retained, but active roster counts exclude them.
    assert client.get(detail).json()["pending"] == 2 and client.get(detail).json()["going"] == 0
    assert session.scalar(select(func.count()).select_from(EventAttendance)) == 1


def test_guest_is_event_only_and_ids_are_scoped(session: Session) -> None:
    owner, team, client, path = setup_events(session)
    other = make_team(session, owner)
    session.commit()
    counts = [
        session.scalar(select(func.count()).select_from(model))
        for model in [User, Player, TeamMembership]
    ]
    item = client.post(path, json=DATA).json()
    detail = f"{path}/{item['id']}"
    added = client.post(detail + "/guests", json={"name": "  Zeca  "})
    assert added.status_code == 201 and added.json()["guests"][0]["name"] == "Zeca"
    guest_id = added.json()["guests"][0]["id"]
    second = client.post(path, json={**DATA, "kind": "JOGO", "opponent": "Visitantes"}).json()
    assert second["opponent"] == "Visitantes" and second["guests"] == []
    assert client.post(f"{path}/{second['id']}/guests/{guest_id}/remove").status_code == 404
    foreign = f"/v1/teams/{other.id}/events/{item['id']}"
    assert client.get(foreign).status_code == 404
    assert client.put(foreign, json=DATA).status_code == 404
    assert client.put(foreign + "/attendance", json={"response": "VOU"}).status_code == 404
    assert client.post(foreign + "/cancel").status_code == 404
    assert client.post(foreign + "/guests", json={"name": "X"}).status_code == 404
    assert client.post(foreign + f"/guests/{guest_id}/remove").status_code == 404
    assert client.post(detail + f"/guests/{guest_id}/remove").json()["guests"] == []
    assert counts == [
        session.scalar(select(func.count()).select_from(model))
        for model in [User, Player, TeamMembership]
    ]


def test_outsider_and_anonymous_cannot_access(session: Session) -> None:
    _, _, owner, path = setup_events(session)
    item = owner.post(path, json=DATA).json()
    detail = f"{path}/{item['id']}"
    for client, status in [
        (client_for(session, make_player(session)), 404),
        (client_for(session), 401),
    ]:
        assert client.get(path).status_code == status
        assert client.get(detail).status_code == status
        assert client.post(path, json=DATA).status_code == status
        assert client.put(detail, json=DATA).status_code == status
        assert client.put(detail + "/attendance", json={"response": "VOU"}).status_code == status
        assert client.post(detail + "/guests", json={"name": "X"}).status_code == status
        assert client.post(detail + "/cancel").status_code == status


def test_granular_admin_permission_and_free_policy(session: Session) -> None:
    _, team, _, path = setup_events(session, Plan.PRO)
    admin = make_player(session)
    member = add_member(
        session,
        team_id=team.id,
        player_id=admin.id,
        role=Role.ADMIN,
        permissions={Permission.MANAGE_MEMBERS},
    )
    client = client_for(session, admin)
    assert client.post(path, json=DATA).status_code == 403
    session.add(MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_EVENTS))
    session.commit()
    item = client.post(path, json=DATA)
    assert item.status_code == 201
    assert client.get(path).json()["can_manage"] is True
    team.plan = "free"
    session.commit()
    assert client.post(path, json=DATA).status_code == 403
    assert client.get(path).json()["can_manage"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"title": " "},
        {"location": " "},
        {"date": "2026-02-30"},
        {"time": "25:00"},
        {"time": "08:00+03:00"},
        {"recurring_until": "2026-09-28"},
        {"recurring_until": "2026-09-26"},
        {"kind": "JOGO", "recurring_until": "2026-10-18"},
        {"opponent": "Não pode em pelada"},
        {"team_id": str(uuid4())},
        {"modality": "invalid"},
    ],
)
def test_invalid_event_input(session: Session, change: dict[str, str]) -> None:
    _, _, client, path = setup_events(session)
    assert client.post(path, json={**DATA, **change}).status_code == 422
    assert client.get(path).json()["items"] == []


def test_modality_must_belong_to_team(session: Session) -> None:
    _, _, client, path = setup_events(session)
    assert client.post(path, json={**DATA, "modality": "futsal"}).status_code == 409


def test_database_rejects_foreign_membership(session: Session) -> None:
    owner, team, client, path = setup_events(session)
    other = make_team(session, owner)
    session.commit()
    event = client.post(path, json=DATA).json()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(
            EventAttendance(
                team_id=team.id,
                event_id=UUID(event["id"]),
                membership_id=other.president_membership_id,
                response="VOU",
            )
        )
        session.flush()


def test_concurrent_responses_do_not_duplicate(engine: Engine, session: Session) -> None:
    owner, team, client, path = setup_events(session)
    event = client.post(path, json=DATA).json()
    user_id, team_id, event_id = owner.user_id, team.id, UUID(event["id"])
    session.commit()
    barrier = Barrier(2)

    def answer(value: str) -> None:
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            events.respond(
                independent, user_id=user_id, team_id=team_id, event_id=event_id, response=value
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(answer, ["VOU", "NAO_VOU"]))
    assert session.scalar(select(func.count()).select_from(EventAttendance)) == 1


def test_endless_recurrence_rolls_forward_without_backfill_or_overwriting(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock(date):
        current = date(2026, 9, 27)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(events, "date", Clock)
    _, _, client, path = setup_events(session)
    first = client.post(path, json={**DATA, "recurring_weekly": True}).json()
    assert first["series_id"] and first["recurring_until"] is None
    detail = f"{path}/{first['id']}"
    items = client.get(path).json()["items"]
    assert len(items) == 9
    assert items[-1]["date"] == "2026-11-22"
    assert client.put(detail + "/attendance", json={"response": "VOU"}).status_code == 200
    assert client.post(detail + "/guests", json={"name": "Zeca"}).status_code == 201
    assert client.put(detail, json={**DATA, "location": "Outro local"}).status_code == 200
    second = f"{path}/{items[1]['id']}"
    assert client.post(second + "/cancel").status_code == 200
    Clock.current = date(2026, 10, 4)
    assert len(client.get(path).json()["items"]) == 10
    assert client.get(second).json()["status"] == "cancelled"
    preserved = client.get(detail).json()
    assert preserved["going"] == 1 and preserved["guests"][0]["name"] == "Zeca"
    assert preserved["location"] == "Outro local"
    Clock.current = date(2036, 9, 27)
    future = client.get(path).json()["items"]
    assert 18 <= len(future) <= 19  # no ten-year backlog generated
    assert len({item["id"] for item in future}) == len(future)
    assert client.get(path).json()["items"] == future
    assert all(item["location"] == DATA["location"] for item in future if item["date"] >= "2036")
    # Ending the series preserves past history and blocks all further materialization.
    ended = client.post(detail + "/cancel-series")
    assert ended.status_code == 200 and ended.json()["recurrence_status"] == "cancelled"
    assert ended.json()["status"] == "open" and ended.json()["going"] == 1
    after = client.get(path).json()["items"]
    assert all(item["status"] == "cancelled" for item in after if item["date"] >= "2036-09-27")
    Clock.current = date(2040, 1, 1)
    assert client.get(path).json()["items"] == after


def test_long_finite_recurrence_is_bounded_and_stops_at_end(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock(date):
        current = date(2026, 9, 27)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(events, "date", Clock)
    _, _, client, path = setup_events(session)
    assert (
        client.post(
            path, json={**DATA, "recurring_weekly": True, "recurring_until": "2030-10-01"}
        ).status_code
        == 201
    )
    assert len(client.get(path).json()["items"]) == 9
    Clock.current = date(2030, 9, 25)
    items = client.get(path).json()["items"]
    assert len(items) == 10 and items[-1]["date"] == "2030-09-29"
    Clock.current = date(2031, 1, 1)
    assert client.get(path).json()["items"] == items


def test_cancel_series_authorization_and_isolation(session: Session) -> None:
    owner, team, client, path = setup_events(session)
    first = client.post(path, json={**DATA, "recurring_weekly": True}).json()
    detail = f"{path}/{first['id']}"
    player = make_player(session)
    add_member(session, team_id=team.id, player_id=player.id)
    reader = client_for(session, player)
    assert reader.post(detail + "/cancel-series").status_code == 403
    other = make_team(session, owner)
    session.commit()
    assert (
        client.post(f"/v1/teams/{other.id}/events/{first['id']}/cancel-series").status_code == 404
    )
    assert (
        client_for(session, make_player(session)).post(detail + "/cancel-series").status_code == 404
    )
    assert client_for(session).post(detail + "/cancel-series").status_code == 401
    single = client.post(path, json=DATA).json()
    assert client.post(f"{path}/{single['id']}/cancel-series").status_code == 409
    assert client.post(detail + "/cancel-series").status_code == 200
    assert client.post(detail + "/cancel-series").status_code == 200


def test_concurrent_materialization_keeps_one_occurrence_per_date(
    engine: Engine,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock(date):
        @classmethod
        def today(cls):
            return date(2027, 1, 3)

    monkeypatch.setattr(events, "date", Clock)
    owner, team, client, path = setup_events(session)
    assert client.post(path, json={**DATA, "recurring_weekly": True}).status_code == 201
    user_id, team_id = owner.user_id, team.id
    session.commit()
    barrier = Barrier(2)

    def load(_: int):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            return events.list_events(independent, user_id=user_id, team_id=team_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(pool.map(load, [1, 2]))
    assert pages[0] == pages[1]
    assert session.scalar(select(func.count()).select_from(Event)) == 18
