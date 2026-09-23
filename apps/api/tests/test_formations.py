from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import formations
from app.application.teams import add_member
from app.domain.formations import Choice, random_teams
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.event_models import EventGuest
from app.infrastructure.formation_models import Formation, FormationParticipant, FormationSquad
from app.infrastructure.models import MembershipPermission
from tests.conftest import make_player
from tests.test_events import DATA, setup_events
from tests.test_team_profiles import client_for


@pytest.mark.parametrize(
    "count,total,keepers", [(2, 10, 2), (3, 16, 3), (4, 15, 4), (3, 16, 1), (3, 16, 8), (5, 17, 17)]
)
def test_random_balance_and_keepers(count, total, keepers):
    choices = [Choice("member", uuid4(), i < keepers) for i in range(total)]
    groups = random_teams(choices, count)
    sizes = [len(g) for g in groups]
    gloves = [sum(p.goalkeeper for p in g) for g in groups]
    assert max(sizes) - min(sizes) <= 1
    assert max(gloves) - min(gloves) <= 1
    assert {p for g in groups for p in g} == set(choices)
    assert sum(sizes) == total


@pytest.mark.parametrize("count,total", [(0, 8), (1, 8), (9, 8), (33, 40), (2, 257)])
def test_impossible_limits(count, total):
    with pytest.raises(Conflict):
        random_teams([Choice("guest", uuid4()) for _ in range(total)], count)


def setup_formation(session: Session, plan=Plan.FREE):
    owner, team, client, path = setup_events(session, plan)
    event = client.post(path, json=DATA).json()
    event_path = f"{path}/{event['id']}"
    assert client.put(event_path + "/attendance", json={"response": "VOU"}).status_code == 200
    for name in ["Bruno", "Carlos", "Diego", "Eduardo", "Fabio"]:
        assert client.post(event_path + "/guests", json={"name": name}).status_code == 201
    return owner, team, client, event_path


def draw_payload(page, **changes):
    return {
        "team_count": 3,
        "expected_fingerprint": page["fingerprint"],
        "expected_version": page["formation"]["version"] if page["formation"] else None,
        "participants": [
            {"kind": p["kind"], "source_id": p["source_id"], "goalkeeper": i < 3}
            for i, p in enumerate(page["participants"])
        ],
        **changes,
    }


def test_lifecycle_exclusion_replacement_manual_and_attendance(session: Session):
    _, team, client, event = setup_formation(session)
    path = event + "/formation"
    page = client.get(path).json()
    payload = draw_payload(page)
    excluded = payload["participants"].pop()
    before = client.get(event).json()
    result = client.post(path + "/draw", json=payload)
    assert result.status_code == 200, result.text
    page = result.json()
    first = page["formation"]
    assert sorted(len(g["participants"]) for g in first["squads"]) == [1, 2, 2]
    assert len(first["excluded"]) == 1 and not page["participants_changed"]
    assert str(first["excluded"][0]["guest_id"]) == excluded["source_id"]
    assert client.get(event).json() == before
    assert client.get(path).json() == page
    participant = first["squads"][0]["participants"][0]
    move = {
        "formation_id": first["id"],
        "squad_id": first["squads"][1]["id"],
        "expected_version": first["version"],
    }
    moved = client.put(path + f"/participants/{participant['id']}", json=move)
    assert moved.status_code == 200, moved.text
    moved_page = moved.json()
    assert participant in moved_page["formation"]["squads"][1]["participants"]
    assert client.put(path + f"/participants/{participant['id']}", json=move).status_code == 409
    assert client.post(path + "/draw", json=payload).status_code == 409
    payload = draw_payload(moved_page, confirm_replace=True)
    again = client.post(path + "/draw", json=payload)
    assert again.status_code == 200, again.text
    assert again.json()["formation"]["id"] == first["id"]
    assert session.scalar(select(func.count()).select_from(Formation)) == 1
    assert session.scalar(select(func.count()).select_from(FormationSquad)) == 3
    assert session.scalar(select(func.count()).select_from(FormationParticipant)) == 6
    stable = again.json()["formation"]
    assert client.put(event + "/attendance", json={"response": "NAO_VOU"}).status_code == 200
    changed = client.get(path).json()
    assert changed["participants_changed"] and changed["formation"] == stable
    removed = next(
        p["guest_id"] for g in stable["squads"] for p in g["participants"] if p["guest_id"]
    )
    assert client.post(event + f"/guests/{removed}/remove").status_code == 200
    assert client.get(path).json()["formation"] == stable
    session.expire_all()
    assert session.get(EventGuest, UUID(removed)).removed_at is not None
    assert all(g["id"] != removed for g in client.get(event).json()["guests"])
    stale = draw_payload(changed, confirm_replace=True)
    assert client.post(path + "/draw", json=stale).status_code == 409
    fresh = client.get(path).json()
    assert (
        client.post(path + "/draw", json=draw_payload(fresh, confirm_replace=True)).status_code
        == 200
    )
    assert not client.get(path).json()["participants_changed"]
    assert client.post(event + "/cancel").status_code == 200
    assert not client.get(path).json()["can_manage"]
    assert (
        client.post(
            path + "/draw", json=draw_payload(client.get(path).json(), confirm_replace=True)
        ).status_code
        == 409
    )
    assert client.get(f"/v1/teams/{team.id}").json()["plan"] == "free"


def test_eligible_pool_permissions_and_id_manipulation(session: Session):
    _, team, client, event = setup_formation(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    member_client = client_for(session, player)
    path = event + "/formation"
    page = client.get(path).json()
    assert str(member.id) not in {p["source_id"] for p in page["participants"]}
    assert not member_client.get(path).json()["can_manage"]
    assert member_client.post(path + "/draw", json=draw_payload(page)).status_code == 403
    assert member_client.put(event + "/attendance", json={"response": "NAO_VOU"}).status_code == 200
    assert client.get(path).json()["fingerprint"] == page["fingerprint"]
    assert member_client.put(event + "/attendance", json={"response": "VOU"}).status_code == 200
    assert client.get(path).json()["fingerprint"] != page["fingerprint"]
    member.status = "inactive"
    session.commit()
    assert client.get(path).json()["fingerprint"] == page["fingerprint"]
    _, foreign_team, other, foreign_event = setup_formation(session)
    assert other.get(path).status_code == 404
    assert client.get(foreign_event + "/formation").status_code == 404
    assert (
        client.get(event.replace(str(team.id), str(foreign_team.id)) + "/formation").status_code
        == 404
    )
    foreign = other.get(foreign_event + "/formation").json()
    for person in foreign["participants"][:2]:
        payload = draw_payload(page)
        payload["participants"][0] = {"kind": person["kind"], "source_id": person["source_id"]}
        assert client.post(path + "/draw", json=payload).status_code == 409
    payload = draw_payload(page)
    payload["participants"][1] = payload["participants"][0]
    assert client.post(path + "/draw", json=payload).status_code == 409
    first = client.post(path + "/draw", json=draw_payload(page)).json()["formation"]
    second = other.post(foreign_event + "/formation/draw", json=draw_payload(foreign)).json()[
        "formation"
    ]
    person = first["squads"][0]["participants"][0]
    move = {
        "formation_id": first["id"],
        "squad_id": second["squads"][0]["id"],
        "expected_version": 1,
    }
    assert client.put(path + f"/participants/{person['id']}", json=move).status_code == 404
    move["squad_id"] = first["squads"][1]["id"]
    fake = second["squads"][0]["participants"][0]["id"]
    assert client.put(path + f"/participants/{fake}", json=move).status_code == 404
    member.status = "active"
    session.commit()
    assert member_client.put(path + f"/participants/{person['id']}", json=move).status_code == 403
    assert member_client.get(path).json()["formation"] == first
    # Database guards also reject a squad from a different occurrence.
    with pytest.raises(IntegrityError), session.begin_nested():
        stored = session.get(FormationParticipant, UUID(person["id"]))
        stored.squad_id = UUID(second["squads"][0]["id"])
        session.flush()


def test_pro_admin_uses_existing_event_permission(session: Session):
    _, team, client, event = setup_formation(session, Plan.PRO)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id, role=Role.ADMIN)
    session.add(
        MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_MEMBERS.value)
    )
    session.commit()
    admin = client_for(session, player)
    path = event + "/formation"
    payload = draw_payload(client.get(path).json())
    assert admin.post(path + "/draw", json=payload).status_code == 403
    session.add(
        MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_EVENTS.value)
    )
    session.commit()
    assert admin.post(path + "/draw", json=payload).status_code == 200
    team.plan = "free"
    session.commit()
    assert not admin.get(path).json()["can_manage"]


def test_concurrent_draw_requires_new_confirmation(engine: Engine, session: Session):
    owner, team, client, event = setup_formation(session)
    page = client.get(event + "/formation").json()
    choices = [Choice(p["kind"], UUID(p["source_id"])) for p in page["participants"]]
    user_id, team_id, event_id = owner.user_id, team.id, UUID(event.split("/")[-1])
    session.commit()
    barrier = Barrier(2)

    def run():
        with Session(engine) as writer:
            barrier.wait()
            try:
                formations.draw(
                    writer,
                    user_id=user_id,
                    team_id=team_id,
                    event_id=event_id,
                    choices=choices,
                    team_count=3,
                    expected_fingerprint=page["fingerprint"],
                    expected_version=None,
                    confirm_replace=False,
                )
                return "saved"
            except Conflict:
                return "conflict"

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["conflict", "saved"]
    assert session.scalar(select(func.count()).select_from(Formation)) == 1


def test_0006_preserves_all_rows_and_protects_downgrade(engine: Engine, session: Session):
    owner, team, client, event = setup_formation(session)
    owner.photo_url = "/v1/media/existing-photo.jpg"
    team.crest_url = "/v1/media/existing-crest.png"
    session.commit()
    assert (
        client.post(
            f"/v1/teams/{team.id}/events", json={**DATA, "recurring_weekly": True}
        ).status_code
        == 201
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    session.close()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005")
        tables = [t for t in inspect(connection).get_table_names() if t != "alembic_version"]
        before = {
            t: connection.execute(
                text(f'SELECT to_jsonb(t) FROM "{t}" t ORDER BY to_jsonb(t)::text')
            )
            .scalars()
            .all()
            for t in tables
        }
        command.upgrade(config, "head")
        for table in tables:
            rows = (
                connection.execute(
                    text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY to_jsonb(t)::text')
                )
                .scalars()
                .all()
            )
            if table == "event_guests":
                for row in rows:
                    assert row.pop("removed_at") is None
            assert rows == before[table]
        command.check(config)
    path = event + "/formation"
    assert (
        client.post(path + "/draw", json=draw_payload(client.get(path).json())).status_code == 200
    )
    session.close()
    with pytest.raises(RuntimeError, match="formation"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005")
    assert client.get(path).json()["formation"]


def test_same_team_other_event_guest_and_pending_member_are_rejected(session: Session):
    _, team, client, event = setup_formation(session)
    pending = add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    second = client.post(f"/v1/teams/{team.id}/events", json=DATA).json()
    second_path = f"/v1/teams/{team.id}/events/{second['id']}"
    guests = client.post(second_path + "/guests", json={"name": "Outro evento"}).json()["guests"]
    path = event + "/formation"
    page = client.get(path).json()
    for kind, source in [("member", str(pending.id)), ("guest", guests[0]["id"])]:
        payload = draw_payload(page)
        payload["participants"][0] = {"kind": kind, "source_id": source}
        assert client.post(path + "/draw", json=payload).status_code == 409
    for count in [0, 1, 33, 2.5]:
        assert (
            client.post(path + "/draw", json=draw_payload(page, team_count=count)).status_code
            == 422
        )
    assert client.post(path + "/draw", json=draw_payload(page, team_count=7)).status_code == 409
    game = client.post(f"/v1/teams/{team.id}/events", json={**DATA, "kind": "JOGO"}).json()
    game_path = f"/v1/teams/{team.id}/events/{game['id']}/formation"
    assert not client.get(game_path).json()["can_manage"]
    assert client.post(game_path + "/draw", json=draw_payload(page)).status_code == 409


def test_0006_downgrade_does_not_restore_removed_guests(engine: Engine, session: Session):
    _, _, client, event = setup_formation(session)
    guest = client.get(event).json()["guests"][0]["id"]
    assert client.post(event + f"/guests/{guest}/remove").status_code == 200
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="removed guest"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005")
    assert all(p["id"] != guest for p in client.get(event).json()["guests"])
