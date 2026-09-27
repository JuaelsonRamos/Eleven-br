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

from app.application import join_requests
from app.application.team_profiles import register_team
from app.application.teams import active_count, add_member
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.event_models import EventAttendance, EventGuest
from app.infrastructure.join_models import TeamJoinRequest
from app.infrastructure.models import MembershipPermission, Player, TeamMembership
from tests.conftest import make_player
from tests.test_events import DATA
from tests.test_formations import draw_payload
from tests.test_foundation import make_team
from tests.test_match_events import post
from tests.test_matches import action, create
from tests.test_roster import setup_roster
from tests.test_team_profiles import client_for


def scenario(session, plan=Plan.FREE):
    owner, team, admin, path = setup_roster(session, plan)
    manual = admin.post(path, json={"name": "João do elenco"}).json()
    source = make_player(session)
    client = client_for(session, source)
    return owner, team, admin, manual, source, client


def request(client, team):
    response = client.post(f"/v1/teams/{team.id}/join-requests", json={"code": team.code})
    assert response.status_code == 201, response.text
    return response.json()


def approve(admin, team, item, membership=None, status=200, confirm=True):
    response = admin.post(
        f"/v1/teams/{team.id}/join-requests/{item['id']}/approve",
        json={"membership_id": membership, "confirm": confirm},
    )
    assert response.status_code == status, response.text
    return response.json()


def history(session, team, admin, manual):
    event = admin.post(f"/v1/teams/{team.id}/events", json=DATA).json()
    path = f"/v1/teams/{team.id}/events/{event['id']}"
    assert admin.put(path + "/attendance", json={"response": "VOU"}).status_code == 200
    session.add(
        EventAttendance(
            team_id=team.id,
            event_id=UUID(event["id"]),
            membership_id=UUID(manual["membership_id"]),
            response="VOU",
        )
    )
    session.commit()
    for name in ["Convidado Um", "Convidado Dois"]:
        assert admin.post(path + "/guests", json={"name": name}).status_code == 201
    formation = admin.post(
        path + "/formation/draw",
        json=draw_payload(admin.get(path + "/formation").json(), team_count=2),
    ).json()["formation"]
    payload = dict(
        formation_id=formation["id"],
        expected_formation_version=formation["version"],
        home_formation_team_id=formation["squads"][0]["id"],
        away_formation_team_id=formation["squads"][1]["id"],
    )
    match = action(admin, path, create(admin, path, payload), "start")
    events = path + f"/matches/{match['id']}/events"
    squad = next(
        s
        for s in formation["squads"]
        if any(p["membership_id"] == manual["membership_id"] for p in s["participants"])
    )
    person = next(p for p in squad["participants"] if p["membership_id"] == manual["membership_id"])
    mate = next(p for p in squad["participants"] if p != person)
    page = admin.get(events).json()
    page = post(admin, events, page, person["id"], assist=mate["id"])
    page = post(admin, events, page, mate["id"], assist=person["id"])
    page = post(admin, events, page, person["id"], "YELLOW_CARD")
    page = post(admin, events, page, person["id"], "RED_CARD")
    action(admin, path, page["match"], "finish", confirm=True)
    return path


def test_code_discovery_normalization_privacy_and_rate_limit(session):
    _, team, _, _, _, client = scenario(session)
    response = client.post("/v1/teams/join/lookup", json={"code": f"  {team.code.lower()}  "})
    assert response.status_code == 200
    data = response.json()
    assert set(data["team"]) == {"id", "name", "code", "city", "state", "modalities", "crest_url"}
    assert data["team"]["code"] == team.code and not data["pending"]
    assert client.get(f"/v1/teams/{team.id}").status_code == 404
    assert (
        client_for(session).post("/v1/teams/join/lookup", json={"code": team.code}).status_code
        == 401
    )
    for _ in range(19):
        assert client.post("/v1/teams/join/lookup", json={"code": "ZZZZZZZZ"}).status_code == 404
    response = client.post("/v1/teams/join/lookup", json={"code": team.code})
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0


def test_request_duplicate_cancel_ownership_reject_and_audit(session):
    owner, team, admin, _, source, client = scenario(session)
    item = request(client, team)
    root = f"/v1/teams/{team.id}/join-requests"
    assert client.post(root, json={"code": team.code}).status_code == 409
    assert client.get(root).status_code == 404
    assert client.get("/v1/me/join-requests").json()[0]["status"] == "PENDING"
    assert admin.get("/v1/me/join-requests").json() == []
    assert admin.post(f"/v1/me/join-requests/{item['id']}/cancel").status_code == 404
    assert client.post(f"/v1/me/join-requests/{item['id']}/cancel").json()["status"] == "CANCELLED"
    assert client.post(f"/v1/me/join-requests/{item['id']}/cancel").status_code == 409
    item = request(client, team)
    page = admin.get(root).json()
    assert len(page) == 1 and page[0]["id"] == item["id"]
    assert "email" not in page[0] and "user_id" not in page[0]
    assert admin.post(root + f"/{item['id']}/reject", json={"confirm": False}).status_code == 409
    assert (
        admin.post(root + f"/{item['id']}/reject", json={"confirm": True}).json()["status"]
        == "REJECTED"
    )
    session.expire_all()
    stored = session.get(TeamJoinRequest, UUID(item["id"]))
    assert stored.resolved_by == owner.user_id and stored.resolved_at
    assert not join_requests.own_membership(session, source.user_id, team.id)
    assert active_count(session, team.id) == 2
    assert len(client.get("/v1/me/join-requests").json()) == 2


def test_link_empty_signup_player_preserves_membership_history_statistics_and_permissions(session):
    owner, team, admin, manual, source, client = scenario(session)
    source_id, user_id = source.id, source.user_id
    event = history(session, team, admin, manual)
    stats_path = f"/v1/teams/{team.id}/statistics/players/{manual['membership_id']}"
    before = admin.get(stats_path).json()
    member_before = dict(
        session.execute(
            text("SELECT * FROM team_memberships WHERE id=:id"), {"id": manual["membership_id"]}
        )
        .mappings()
        .one()
    )
    item = request(client, team)
    detail = admin.get(f"/v1/teams/{team.id}/join-requests/{item['id']}").json()
    assert detail["candidates"][0]["membership_id"] == manual["membership_id"]
    approve(admin, team, item, manual["membership_id"], status=409, confirm=False)
    approve(admin, team, item, manual["membership_id"])
    session.expire_all()
    assert session.get(Player, source_id) is None
    assert session.get(Player, UUID(manual["player_id"])).user_id == user_id
    assert session.get(TeamMembership, team.president_membership_id).player_id == owner.id
    assert member_before == dict(
        session.execute(
            text("SELECT * FROM team_memberships WHERE id=:id"), {"id": manual["membership_id"]}
        )
        .mappings()
        .one()
    )
    assert client.get(stats_path).json() == before
    assert before["person"]["totals"] == dict(
        matches=1, goals=1, assists=1, yellow_cards=1, red_cards=1
    )
    assert client.get("/v1/me").json()["player_id"] == manual["player_id"]
    assert client.get("/v1/teams").json()[0]["my_role"] == "member"
    assert client.put(event + "/attendance", json={"response": "NAO_VOU"}).status_code == 200
    assert client.get(f"/v1/teams/{team.id}/players").json()["can_manage"] is False
    assert client.get(f"/v1/teams/{team.id}/join-requests").status_code == 403
    assert client.post(f"/v1/teams/{team.id}/events", json=DATA).status_code == 403
    assert client.get(f"/v1/teams/{team.id}/administration").status_code == 403
    assert (
        client.post(f"/v1/teams/{team.id}/join-requests", json={"code": team.code}).status_code
        == 409
    )
    approve(admin, team, item, manual["membership_id"], status=409)


@pytest.mark.parametrize("inactive", [False, True])
def test_existing_sporting_identity_blocks_merge_but_reuses_player_in_second_team(
    session, inactive
):
    _, team, admin, manual, source, client = scenario(session)
    other = make_team(session, make_player(session))
    member = add_member(session, team_id=other.id, player_id=source.id)
    if inactive:
        member.status = "inactive"
    session.commit()
    item = request(client, team)
    result = approve(admin, team, item, manual["membership_id"], status=409)
    assert "unificação" in result["detail"]
    assert session.get(Player, UUID(manual["player_id"])).user_id is None
    assert session.get(Player, source.id).user_id is not None
    assert session.get(TeamJoinRequest, UUID(item["id"])).status == "PENDING"
    approve(admin, team, item)
    session.expire_all()
    assert join_requests.own_membership(session, source.user_id, team.id).player_id == source.id
    assert (
        session.scalar(
            select(func.count()).select_from(Player).where(Player.user_id == source.user_id)
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(TeamMembership.player_id == source.id)
        )
        == 2
    )


def test_inactive_target_requires_explicit_reactivation(session):
    _, team, admin, manual, _, client = scenario(session)
    path = f"/v1/teams/{team.id}/players/{manual['membership_id']}"
    assert admin.post(path + "/deactivate").status_code == 200
    item = request(client, team)
    approve(admin, team, item, manual["membership_id"], status=409)
    assert session.get(TeamMembership, UUID(manual["membership_id"])).status == "inactive"
    assert admin.post(path + "/reactivate").status_code == 200
    approve(admin, team, item, manual["membership_id"])


def test_ids_other_account_guest_and_team_permissions(session):
    _, team, admin, _, source, client = scenario(session)
    other_owner, other, other_admin, foreign, _, _ = scenario(session)
    item = request(client, team)
    root = f"/v1/teams/{team.id}/join-requests/{item['id']}"
    assert other_admin.get(root).status_code == 404
    assert client.post(root + "/approve", json={"confirm": True}).status_code == 404
    assert (
        admin.post(
            f"/v1/teams/{other.id}/join-requests/{item['id']}/approve", json={"confirm": True}
        ).status_code
        == 404
    )
    approve(admin, team, item, foreign["membership_id"], status=404)
    approve(admin, team, item, str(uuid4()), status=404)
    approve(admin, team, item, str(team.president_membership_id), status=409)
    assert (
        client.post(f"/v1/teams/{team.id}/join-requests", json={"code": other.code}).status_code
        == 404
    )
    assert (
        client.post(
            root + "/approve", json={"user_id": str(other_owner.user_id), "confirm": True}
        ).status_code
        == 422
    )
    add_member(session, team_id=team.id, player_id=source.id)
    session.commit()
    assert client.get(f"/v1/teams/{team.id}/join-requests").status_code == 403
    approve(admin, team, item, status=409)


def test_pro_manager_permission_and_free_president_only(session):
    _, team, _, manual, _, client = scenario(session, Plan.PRO)
    manager = make_player(session)
    member = add_member(
        session,
        team_id=team.id,
        player_id=manager.id,
        role=Role.ADMIN,
        permissions=frozenset({Permission.MANAGE_MEMBERS}),
    )
    session.commit()
    manager_client = client_for(session, manager)
    item = request(client, team)
    assert manager_client.get(f"/v1/teams/{team.id}/join-requests").status_code == 200
    team.plan = "free"
    session.commit()
    assert manager_client.get(f"/v1/teams/{team.id}/join-requests").status_code == 403
    team.plan = "pro"
    session.commit()
    approve(manager_client, team, item, manual["membership_id"])
    assert (
        session.scalar(
            select(func.count())
            .select_from(MembershipPermission)
            .where(MembershipPermission.membership_id == member.id)
        )
        == 1
    )


def test_free_limit_link_active_at_capacity_and_new_membership_blocked(session):
    _, team, admin, manual, _, client = scenario(session)
    for _ in range(22):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    item = request(client, team)
    approve(admin, team, item, status=409)
    approve(admin, team, item, manual["membership_id"])
    assert active_count(session, team.id) == 24


@pytest.mark.parametrize("photos", ["source", "target", "conflict"])
def test_photos_preserved_without_duplicating_files(session, photos):
    _, team, admin, manual, source, client = scenario(session)
    target = session.get(Player, UUID(manual["player_id"]))
    if photos in {"source", "conflict"}:
        source.photo_url = "/v1/media/source.jpg"
    if photos in {"target", "conflict"}:
        target.photo_url = "/v1/media/target.jpg"
    session.commit()
    item = request(client, team)
    approve(admin, team, item, manual["membership_id"], status=409 if photos == "conflict" else 200)
    session.expire_all()
    if photos == "conflict":
        assert session.get(Player, source.id).photo_url == "/v1/media/source.jpg"
        assert target.photo_url == "/v1/media/target.jpg" and target.user_id is None
    else:
        assert client.get("/v1/me").json()["photo_url"] == f"/v1/media/{photos}.jpg"


def test_complete_rollback_after_empty_player_replacement(session, monkeypatch):
    owner, team, _, manual, source, client = scenario(session)
    source_id, user_id = source.id, source.user_id
    item = request(client, team)

    def fail():
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(session, "commit", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        join_requests.approve(
            session,
            user_id=owner.user_id,
            team_id=team.id,
            request_id=UUID(item["id"]),
            membership_id=UUID(manual["membership_id"]),
            confirm=True,
        )
    assert session.get(Player, source_id).user_id == user_id
    assert session.get(Player, UUID(manual["player_id"])).user_id is None
    assert session.get(TeamJoinRequest, UUID(item["id"])).status == "PENDING"


@pytest.mark.parametrize("race", ["same_request", "same_player", "last_slot", "cancel"])
def test_concurrent_resolutions(engine, session, race):
    owner, team, _, manual, _, client = scenario(session)
    one = request(client, team)
    second_player = make_player(session)
    second_client = client_for(session, second_player)
    two = request(second_client, team)
    if race == "last_slot":
        for _ in range(21):
            add_member(session, team_id=team.id, player_id=make_player(session).id)
        session.commit()
    owner_id, team_id = owner.user_id, team.id
    source_user_id = session.get(TeamJoinRequest, UUID(one["id"])).user_id
    session.commit()
    barrier = Barrier(2)

    def run(index):
        with Session(engine) as connection:
            barrier.wait()
            try:
                if race == "cancel" and index:
                    return join_requests.cancel(
                        connection, user_id=source_user_id, request_id=UUID(one["id"])
                    )["status"]
                join_requests.approve(
                    connection,
                    user_id=owner_id,
                    team_id=team_id,
                    request_id=UUID(
                        (one if index == 0 or race in {"same_request", "cancel"} else two)["id"]
                    ),
                    membership_id=None if race == "last_slot" else UUID(manual["membership_id"]),
                    confirm=True,
                )
                return "APPROVED"
            except Conflict:
                connection.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert results.count("conflict") == 1
    session.expire_all()
    if race == "last_slot":
        assert active_count(session, team_id) == 24
    else:
        assert active_count(session, team_id) == 2
    assert (
        session.scalar(
            select(func.count())
            .select_from(TeamJoinRequest)
            .where(TeamJoinRequest.status == "APPROVED")
        )
        <= 1
    )


def test_migration_incremental_preservation_constraints_and_guard(engine, session):
    _, team, _, _, source, client = scenario(session)
    team_id, user_id = team.id, source.user_id
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0008")
        tables = [
            name for name in inspect(connection).get_table_names() if name != "alembic_version"
        ]
        before = {
            name: connection.execute(
                text(f'SELECT to_jsonb(t)::text FROM "{name}" t ORDER BY to_jsonb(t)::text')
            )
            .scalars()
            .all()
            for name in tables
        }
        command.upgrade(config, "head")
        assert all(
            connection.execute(
                text(f'SELECT to_jsonb(t)::text FROM "{name}" t ORDER BY to_jsonb(t)::text')
            )
            .scalars()
            .all()
            == before[name]
            for name in tables
        )
        command.check(config)
    with Session(engine) as connection:
        connection.add(TeamJoinRequest(team_id=team_id, user_id=user_id))
        connection.commit()
        connection.add(TeamJoinRequest(team_id=team_id, user_id=user_id))
        with pytest.raises(IntegrityError):
            connection.commit()
        connection.rollback()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="preservar"):
            command.downgrade(config, "0008")


def test_historical_identity_is_never_merged_or_moved_and_guest_is_not_convertible(session):
    _, team, admin, manual, _, client = scenario(session)
    event_path = history(session, team, admin, manual)
    stats = f"/v1/teams/{team.id}/statistics/players/{manual['membership_id']}"
    before = admin.get(stats).json()
    item = request(client, team)
    guest = session.scalar(
        select(EventGuest).where(EventGuest.event_id == UUID(event_path.rsplit("/", 1)[-1]))
    )
    approve(admin, team, item, str(guest.id), status=404)
    assert session.get(EventGuest, guest.id) is not None
    approve(admin, team, item, manual["membership_id"])
    _, other, other_admin, other_manual, _, _ = scenario(session)
    second = request(client, other)
    approve(other_admin, other, second, other_manual["membership_id"], status=409)
    assert client.get(stats).json() == before
    assert session.get(Player, UUID(other_manual["player_id"])).user_id is None
    assert session.get(TeamJoinRequest, UUID(second["id"])).status == "PENDING"


@pytest.mark.parametrize("target_kind", ["shared", "admin"])
def test_link_cannot_claim_other_team_or_administrative_identity(session, target_kind):
    _, team, admin, manual, _, client = scenario(session)
    member = session.get(TeamMembership, UUID(manual["membership_id"]))
    if target_kind == "shared":
        other = make_team(session, make_player(session))
        add_member(session, team_id=other.id, player_id=member.player_id)
    else:
        member.role = "admin"
    session.commit()
    item = request(client, team)
    data = admin.get(f"/v1/teams/{team.id}/join-requests/{item['id']}").json()
    assert data["candidates"][0]["unavailable_reason"]
    approve(admin, team, item, manual["membership_id"], status=409)
    assert session.get(Player, UUID(manual["player_id"])).user_id is None


@pytest.mark.parametrize("operation", ["approval", "create_team"])
def test_account_identity_serializes_across_teams(engine, session, operation):
    owner, team, _, manual, source, client = scenario(session)
    other_owner, other, _, other_manual, _, _ = scenario(session)
    one, two = request(client, team), request(client, other)
    owner_id, team_id, other_owner_id, other_id, user_id = (
        owner.user_id,
        team.id,
        other_owner.user_id,
        other.id,
        source.user_id,
    )
    session.commit()
    barrier = Barrier(2)

    def run(index):
        with Session(engine) as connection:
            barrier.wait()
            try:
                if index and operation == "create_team":
                    register_team(
                        connection,
                        user_id=user_id,
                        name="Segundo time",
                        city="Vitória",
                        state="ES",
                        modalities=["campo"],
                    )
                else:
                    join_requests.approve(
                        connection,
                        user_id=other_owner_id if index else owner_id,
                        team_id=other_id if index else team_id,
                        request_id=UUID((two if index else one)["id"]),
                        membership_id=UUID((other_manual if index else manual)["membership_id"]),
                        confirm=True,
                    )
                return "ok"
            except Conflict:
                connection.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert "ok" in results
    if operation == "approval":
        assert results.count("conflict") == 1
    session.expire_all()
    player = session.scalars(select(Player).where(Player.user_id == user_id)).one()
    assert (
        session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(TeamMembership.player_id == player.id)
        )
        >= 1
    )
