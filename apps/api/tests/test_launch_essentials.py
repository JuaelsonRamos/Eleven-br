from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.application import lineups, password_recovery, roster
from app.application.teams import add_member
from app.domain.auth import InvalidVerification
from app.domain.policies import Permission, Plan, Role
from app.infrastructure.config import get_settings
from app.infrastructure.launch_models import Lineup, PasswordRecovery, TeamAudit
from app.infrastructure.models import MembershipPermission, Player, TeamMembership, User
from app.infrastructure.security import hash_password
from tests.conftest import make_player
from tests.test_events import DATA as EVENT
from tests.test_foundation import make_team
from tests.test_join_requests import approve, history, request, scenario
from tests.test_roster import setup_roster
from tests.test_team_profiles import DATA, client_for


def recover(session):
    person = make_player(session)
    user = session.get(User, person.user_id)
    user.password_hash = hash_password("old-password-123")
    client = client_for(session, person)
    ticket = client.post("/v1/auth/password-recovery", json={"email": user.email}).json()
    return user, client, ticket


def reset_data(ticket):
    return dict(
        recovery_token=ticket["recovery_token"],
        code=ticket["development_code"],
        password="new-password-123",
        password_confirmation="new-password-123",
    )


def test_recovery_one_use_hashes_and_revokes_sessions(session):
    user, client, ticket = recover(session)
    anonymous = client_for(session)
    item = session.scalar(select(PasswordRecovery))
    assert ticket["recovery_token"] not in item.handle_hash
    assert ticket["development_code"] != item.code_hash
    counts = session.scalar(select(func.count()).select_from(Player))
    assert anonymous.post("/v1/auth/password-reset", json=reset_data(ticket)).status_code == 200
    assert client.get("/v1/me").status_code == 401
    assert anonymous.post("/v1/auth/password-reset", json=reset_data(ticket)).status_code == 400
    assert (
        anonymous.post(
            "/v1/auth/login", json={"contact": user.email, "password": "old-password-123"}
        ).status_code
        == 401
    )
    assert (
        anonymous.post(
            "/v1/auth/login", json={"contact": user.email, "password": "new-password-123"}
        ).status_code
        == 200
    )
    assert session.scalar(select(func.count()).select_from(Player)) == counts


def test_recovery_generic_response_and_delivery_purpose(session, monkeypatch):
    delivered = []
    monkeypatch.setattr(password_recovery, "deliver", lambda *args: delivered.append(args))
    user, client, real = recover(session)
    missing = client.post(
        "/v1/auth/password-recovery", json={"email": "missing@example.com"}
    ).json()
    assert real.keys() == missing.keys() and real["message"] == missing["message"]
    assert len(delivered) == 1 and delivered[0][0] == user.email
    user.email_verified_at = None
    session.commit()
    unverified = client.post("/v1/auth/password-recovery", json={"email": user.email}).json()
    assert unverified["message"] == real["message"] and len(delivered) == 1


@pytest.mark.parametrize(
    "invalid", ["expired", "wrong", "changed_email", "disabled", "password_mismatch"]
)
def test_recovery_invalid_preserves_password(session, invalid):
    user, client, ticket = recover(session)
    original = user.password_hash
    payload = reset_data(ticket)
    item = session.scalar(select(PasswordRecovery))
    if invalid == "expired":
        item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif invalid == "wrong":
        payload["code"] = "999999" if payload["code"] != "999999" else "111111"
    elif invalid == "changed_email":
        user.email = "changed@example.com"
    elif invalid == "disabled":
        user.status = "inactive"
    else:
        payload["password_confirmation"] = "different-password"
    session.commit()
    result = client.post("/v1/auth/password-reset", json=payload)
    assert result.status_code in (400, 422), result.text
    session.refresh(user)
    assert user.password_hash == original and not item.consumed_at


def test_recovery_limits_and_rotation(session):
    user, client, old = recover(session)
    new = client.post("/v1/auth/password-recovery", json={"email": user.email}).json()
    assert client.post("/v1/auth/password-reset", json=reset_data(old)).status_code == 400
    payload = reset_data(new)
    payload["code"] = "999999" if payload["code"] != "999999" else "111111"
    for _ in range(5):
        assert client.post("/v1/auth/password-reset", json=payload).status_code == 400
    assert client.post("/v1/auth/password-reset", json=reset_data(new)).status_code == 429
    for _ in range(3):
        assert (
            client.post("/v1/auth/password-recovery", json={"email": user.email}).status_code == 200
        )
    assert client.post("/v1/auth/password-recovery", json={"email": user.email}).status_code == 429


def test_recovery_concurrent_single_use(session, engine):
    _, _, ticket = recover(session)
    settings = get_settings()
    session.commit()

    def attempt(_):
        with Session(engine) as worker:
            try:
                password_recovery.reset(
                    worker,
                    ticket["recovery_token"],
                    ticket["development_code"],
                    "new-password-123",
                    settings,
                )
                return True
            except InvalidVerification:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]


def test_category_required_public_counts_and_legacy(session):
    player = make_player(session)
    team = make_team(session, player)
    client = client_for(session, player)
    assert client.get(f"/v1/teams/{team.id}").json()["category"] is None
    missing = {k: v for k, v in DATA.items() if k != "category"}
    profile = {"name": DATA["name"], "modalities": DATA["modalities"]}  # No location edits.
    assert client.post("/v1/teams", json=missing).status_code == 422
    assert client.post("/v1/teams", json={**DATA, "category": "unknown"}).status_code == 422
    assert (
        client.post("/v1/teams", json={**DATA, "category": "female"}).json()["category"] == "female"
    )
    assert (
        client.put(f"/v1/teams/{team.id}", json={**profile, "category": "male"}).json()["category"]
        == "male"
    )
    # One global Player counts once even when belonging to two teams.
    response = client_for(session).get("/v1/public/platform-stats")
    assert response.json() == {"teams": 2, "players": 1}
    assert response.headers["cache-control"] == "public, max-age=60"


@pytest.mark.parametrize(
    "values,primary",
    [(["GOL", "GOL"], "GOL"), (["XX"], "XX"), (["ZAG"], "ATA"), (["ZAG"], None), ([], "GOL")],
)
def test_positions_validation(session, values, primary):
    _, team, client, path = setup_roster(session)
    result = client.put(
        f"{path}/{team.president_membership_id}/positions",
        json={"positions": values, "primary_position": primary, "expected_version": 1},
    )
    assert result.status_code == 422


def test_positions_free_local_audited_permissions_and_version(session):
    owner, team, admin, path = setup_roster(session)
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    other = make_team(session, owner)
    other_member = add_member(session, team_id=other.id, player_id=player.id)
    reader = client_for(session, player)
    detail = f"{path}/{member.id}/positions"
    data = dict(positions=["GOL", "ZAG"], primary_position="GOL", expected_version=1)
    assert reader.put(detail, json=data).status_code == 403
    assert admin.put(detail, json=data).json()["primary_position"] == "GOL"
    assert admin.put(detail, json=data).status_code == 200  # retry
    assert admin.put(detail, json={**data, "primary_position": "ZAG"}).status_code == 409
    assert admin.put(f"{path}/{other_member.id}/positions", json=data).status_code == 404
    session.refresh(other_member)
    assert other_member.positions == []
    assert session.scalar(select(func.count()).select_from(TeamAudit)) == 1


def test_remove_preserves_sporting_history_reentry_and_audit(session):
    _, team, admin, manual, source, client = scenario(session)
    history(session, team, admin, manual)
    approve(admin, team, request(client, team), manual["membership_id"])
    path = f"/v1/teams/{team.id}/players/{manual['membership_id']}"
    member = session.get(TeamMembership, UUID(manual["membership_id"]))
    player_id = member.player_id
    before = admin.get(f"/v1/teams/{team.id}/statistics").json()
    payload = {"confirm": True, "expected_version": member.roster_version}
    assert client.post(path + "/remove", json=payload).status_code == 403
    assert admin.post(path + "/remove", json={**payload, "confirm": False}).status_code == 409
    assert admin.post(path + "/remove", json=payload).json()["status"] == "removed"
    assert admin.post(path + "/remove", json=payload).status_code == 200
    assert client.get(f"/v1/teams/{team.id}").status_code == 404
    assert admin.post(path + "/reactivate").status_code == 409
    assert admin.get(f"/v1/teams/{team.id}/statistics").json()["summary"] == before["summary"]
    assert session.get(Player, player_id) is not None
    approved = approve(admin, team, request(client, team))
    assert approved["status"] == "APPROVED"
    session.refresh(member)
    assert member.status == "active" and member.player_id == player_id
    assert (
        session.scalar(
            select(func.count()).select_from(TeamAudit).where(TeamAudit.action == "MEMBER_REMOVED")
        )
        == 1
    )


def test_remove_president_and_inactive_distinction(session):
    _, team, admin, manual, _, _ = scenario(session)
    root = f"/v1/teams/{team.id}/players"
    assert (
        admin.post(
            f"{root}/{team.president_membership_id}/remove",
            json={"confirm": True, "expected_version": 1},
        ).status_code
        == 409
    )
    path = root + "/" + manual["membership_id"]
    inactive = admin.post(path + "/deactivate").json()
    assert inactive["status"] == "inactive"
    assert len(admin.get(root + "?status=inactive").json()["items"]) == 1
    assert admin.post(path + "/reactivate").status_code == 200
    assert set(session.scalars(select(TeamAudit.action))) == {
        "MEMBER_INACTIVATED",
        "MEMBER_REACTIVATED",
    }


def test_removed_manual_player_can_return_with_new_account_without_losing_identity(session):
    _, team, admin, manual, source, client = scenario(session)
    history(session, team, admin, manual)
    path = f"/v1/teams/{team.id}/players/{manual['membership_id']}"
    assert (
        admin.post(path + "/remove", json={"confirm": True, "expected_version": 1}).status_code
        == 200
    )
    item = request(client, team)
    detail = admin.get(f"/v1/teams/{team.id}/join-requests/{item['id']}").json()
    candidate = next(
        row for row in detail["candidates"] if row["membership_id"] == manual["membership_id"]
    )
    assert candidate["status"] == "removed" and candidate["unavailable_reason"] is None
    user_id = source.user_id
    approve(admin, team, item, manual["membership_id"])
    member = session.get(TeamMembership, UUID(manual["membership_id"]))
    session.refresh(member)
    assert member.status == "active" and str(member.player_id) == manual["player_id"]
    assert session.get(Player, member.player_id).user_id == user_id


def lineup_data(team):
    return dict(
        title="Titulares",
        modality="campo",
        formation="4-4-2",
        positions=[{"slot": 0, "membership_id": str(team.president_membership_id)}],
        expected_version=0,
        command_id=str(uuid4()),
    )


def test_lineup_plan_permission_idor_and_duplicates(session):
    owner, team, admin, _ = setup_roster(session)
    path = f"/v1/teams/{team.id}/lineups"
    data = lineup_data(team)
    assert not admin.get(path).json()["enabled"]
    assert admin.post(path, json=data).status_code == 403
    team.plan = Plan.PRO
    player = make_player(session)
    member = add_member(session, team_id=team.id, player_id=player.id)
    reader = client_for(session, player)
    assert reader.post(path, json=data).status_code == 403
    created = admin.post(path, json=data)
    assert created.status_code == 201, created.text
    item = created.json()
    assert reader.get(path + "/" + item["id"]).status_code == 200
    assert admin.post(path, json=data).json()["id"] == item["id"]
    assert session.scalar(select(func.count()).select_from(Lineup)) == 1
    duplicate = {
        **data,
        "command_id": str(uuid4()),
        "positions": data["positions"]
        + [{"slot": 1, "membership_id": str(team.president_membership_id)}],
    }
    assert admin.post(path, json=duplicate).status_code == 409
    other = make_team(session, owner, Plan.PRO)
    session.commit()
    assert admin.get(f"/v1/teams/{other.id}/lineups/{item['id']}").status_code == 404
    assert (
        admin.post(
            path,
            json={
                **data,
                "positions": [{"slot": 1, "membership_id": str(other.president_membership_id)}],
            },
        ).status_code
        == 409
    )
    member.role = Role.ADMIN
    session.add(MembershipPermission(membership_id=member.id, permission=Permission.MANAGE_EVENTS))
    session.commit()
    assert (
        reader.put(
            path + "/" + item["id"], json={**data, "expected_version": 1, "title": "Nova"}
        ).status_code
        == 200
    )
    assert (
        admin.put(
            path + "/" + item["id"], json={**data, "expected_version": 1, "title": "Conflito"}
        ).status_code
        == 409
    )
    team.plan = Plan.FREE
    session.commit()
    assert admin.get(path + "/" + item["id"]).status_code == 403


@pytest.mark.parametrize(
    "modality,formation,count",
    [("campo", "3-5-2", 11), ("society", "2-3-1", 7), ("futsal", "1-2-1", 5)],
)
def test_lineup_templates_and_invalid_slots(session, modality, formation, count):
    _, team, admin, _ = setup_roster(session, Plan.PRO)
    team.modalities = [modality]
    session.commit()
    path = f"/v1/teams/{team.id}/lineups"
    templates = admin.get(path).json()["templates"]
    assert all(sum(map(len, rows)) == count for rows in templates[modality].values())
    data = {**lineup_data(team), "modality": modality, "formation": formation}
    assert admin.post(path, json=data).status_code == 201
    data["positions"][0]["slot"] = count
    assert admin.post(path, json=data).status_code in (409, 422)


def test_lineup_event_and_inactive_validation(session):
    _, team, admin, path = setup_roster(session, Plan.PRO)
    person = admin.post(path, json={"name": "Inativo"}).json()
    admin.post(f"{path}/{person['membership_id']}/deactivate")
    root = f"/v1/teams/{team.id}"
    data = lineup_data(team)
    invalid = {**data, "positions": [{"slot": 1, "membership_id": person["membership_id"]}]}
    assert admin.post(root + "/lineups", json=invalid).status_code == 409
    event = admin.post(root + "/events", json=EVENT).json()
    assert admin.post(root + "/lineups", json={**data, "event_id": event["id"]}).status_code == 201
    admin.post(root + "/events/" + event["id"] + "/cancel")
    assert (
        admin.post(
            root + "/lineups", json={**data, "command_id": str(uuid4()), "event_id": event["id"]}
        ).status_code
        == 409
    )
    assert admin.post(root + "/lineups", json={**data, "event_id": str(uuid4())}).status_code == 404


def test_lineup_concurrency_and_transaction_rollback(session, engine, monkeypatch):
    owner, team, _, _ = setup_roster(session, Plan.PRO)
    user_id, team_id = owner.user_id, team.id
    data = lineups.LineupInput(**lineup_data(team))
    session.commit()

    def save(_):
        with Session(engine) as worker:
            return lineups.save(worker, user_id, team_id, data)["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(save, range(2)))) == 1
    assert session.scalar(select(func.count()).select_from(Lineup)) == 1
    session.commit()
    with Session(engine) as worker:

        def fail():
            raise RuntimeError("commit failure")

        monkeypatch.setattr(worker, "commit", fail)
        with pytest.raises(RuntimeError, match="commit failure"):
            lineups.save(worker, user_id, team_id, data.model_copy(update={"command_id": uuid4()}))
    assert session.scalar(select(func.count()).select_from(Lineup)) == 1
    assert session.scalar(select(func.count()).select_from(TeamAudit)) == 1


def test_remove_rollback(session, engine, monkeypatch):
    owner, team, admin, path = setup_roster(session)
    person = admin.post(path, json={"name": "Preservar"}).json()
    user_id, team_id, member_id = owner.user_id, team.id, UUID(person["membership_id"])
    session.commit()
    with Session(engine) as worker:

        def fail():
            raise RuntimeError("commit failure")

        monkeypatch.setattr(worker, "commit", fail)
        with pytest.raises(RuntimeError, match="commit failure"):
            roster.remove(worker, user_id, team_id, member_id, True, 1)
    session.expire_all()
    assert session.get(TeamMembership, member_id).status == "active"
    assert session.scalar(select(func.count()).select_from(TeamAudit)) == 0


def test_0013_preserves_all_original_columns_and_guards_new_data(session, engine):
    _, team, admin, manual, _, _ = scenario(session)
    history(session, team, admin, manual)
    session.close()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0012")
        tables = {
            name: [column["name"] for column in inspect(connection).get_columns(name)]
            for name in inspect(connection).get_table_names()
            if name != "alembic_version"
        }

        def snapshot(name, columns):
            fields = ", ".join(f'"{column}"' for column in columns)
            return connection.execute(
                text(
                    f'SELECT to_jsonb(t)::text FROM (SELECT {fields} FROM "{name}") t '
                    "ORDER BY to_jsonb(t)::text"
                )
            ).all()

        before = {name: snapshot(name, columns) for name, columns in tables.items()}
        command.upgrade(config, "head")
        assert all(snapshot(name, columns) == before[name] for name, columns in tables.items())
        assert connection.scalar(text("SELECT count(*) FROM teams WHERE category IS NOT NULL")) == 0
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM team_memberships WHERE cardinality(positions) > 0 "
                    "OR primary_position IS NOT NULL OR roster_version != 1"
                )
            )
            == 0
        )
        command.check(config)
    with engine.begin() as connection:
        connection.execute(text("UPDATE teams SET category = 'mixed'"))
    with pytest.raises(RuntimeError, match="preserve"), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0012")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0016"
