"""Administrators and presidency transfer: President-only, transactional and audited."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import team_roles
from app.application.teams import add_member
from app.domain.policies import Forbidden, Permission, Plan, Role
from app.infrastructure.launch_models import TeamAudit
from app.infrastructure.models import MembershipPermission, Team, TeamMembership, User
from tests.conftest import make_player
from tests.test_join_requests import history
from tests.test_roster import setup_roster
from tests.test_team_profiles import client_for


def member(session, team, **kwargs):
    player = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=player.id, **kwargs)
    session.commit()
    return player, membership


def role(client, path, membership_id, value, permissions=(), status=200, version=None):
    current = client.get(f"{path}/{membership_id}").json()
    response = client.put(
        f"{path}/{membership_id}/role",
        json={
            "role": value,
            "permissions": list(permissions),
            "expected_version": version or current["roster_version"],
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def actions(session, team):
    return sorted(session.scalars(select(TeamAudit.action).where(TeamAudit.team_id == team.id)))


def test_president_grants_edits_and_revokes_admin_with_audit(session):
    _, team, client, path = setup_roster(session, Plan.PRO)
    player, membership = member(session, team)
    viewer_player, _ = member(session, team)
    target, admin = str(membership.id), client_for(session, player)
    viewer = client_for(session, viewer_player)
    assert admin.post(path, json={"name": "Antes da administração"}).status_code == 403
    granted = role(client, path, target, "admin", ["manage_members"])
    assert granted["role"] == "admin" and granted["permissions"] == ["manage_members"]
    assert admin.post(path, json={"name": "Novo pelo administrador"}).status_code == 201
    edited = role(client, path, target, "admin", ["manage_members", "manage_events"])
    assert edited["permissions"] == ["manage_events", "manage_members"]
    same = role(client, path, target, "admin", ["manage_events", "manage_members"])
    assert same["roster_version"] == edited["roster_version"]
    page = client.get(path).json()
    assert (page["can_manage_admins"], page["admin_limit"], page["admin_count"]) == (True, 5, 1)
    # Role is visible to the whole team; grants only to those who manage the roster.
    seen = next(i for i in viewer.get(path).json()["items"] if i["membership_id"] == target)
    assert seen["role"] == "admin" and seen["permissions"] == []
    assert viewer.get(path).json()["can_manage_admins"] is False
    assert admin.get(path).json()["can_manage_admins"] is False
    revoked = role(client, path, target, "member")
    assert revoked["role"] == "member" and revoked["permissions"] == []
    assert admin.post(path, json={"name": "Depois da administração"}).status_code == 403
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(MembershipPermission)) == 0
    assert session.get(TeamMembership, membership.id).status == "active"
    assert actions(session, team) == [
        "ADMIN_GRANTED",
        "ADMIN_PERMISSIONS_CHANGED",
        "ADMIN_REVOKED",
    ]


def test_free_plan_keeps_administration_with_the_president(session):
    _, team, client, path = setup_roster(session)
    player, membership = member(session, team)
    target = str(membership.id)
    refused = role(client, path, target, "admin", ["manage_members"], status=409)
    assert "ELEVEN PRO" in refused["detail"]
    assert client.get(path).json()["admin_limit"] == 0
    # A grant preserved from a former Pro plan has no effect in Free and can be revoked.
    team.plan = Plan.PRO.value
    session.commit()
    role(client, path, target, "admin", ["manage_members"])
    team.plan = Plan.FREE.value
    session.commit()
    assert client_for(session, player).post(path, json={"name": "Sem poder"}).status_code == 403
    assert role(client, path, target, "member")["role"] == "member"


def test_role_changes_require_president_and_eligible_members(session):
    _, team, client, path = setup_roster(session, Plan.PRO)
    admin_player, admin_membership = member(
        session, team, role=Role.ADMIN, permissions=frozenset(Permission)
    )
    plain_player, plain = member(session, team)
    target = str(plain.id)
    version = client.get(f"{path}/{target}").json()["roster_version"]

    def body(value=version, role_name="admin", permissions=("manage_events",)):
        return {"role": role_name, "permissions": list(permissions), "expected_version": value}

    # Administrative grants never manage roles; plain members and outsiders cannot either.
    assert (
        client_for(session, admin_player).put(f"{path}/{target}/role", json=body()).status_code
        == 403
    )
    assert (
        client_for(session, plain_player)
        .put(f"{path}/{admin_membership.id}/role", json=body(1, "member", ()))
        .status_code
        == 403
    )
    outsider = client_for(session, make_player(session))
    assert outsider.put(f"{path}/{target}/role", json=body()).status_code == 404
    _, other_team, _, _ = setup_roster(session, Plan.PRO)
    foreign = f"{path}/{other_team.president_membership_id}/role"
    assert client.put(foreign, json=body(1)).status_code == 404
    assert (
        client.put(f"{path}/{team.president_membership_id}/role", json=body(1)).status_code == 409
    )
    for invalid in (
        body(permissions=()),
        body(permissions=("delete_team",)),
        body(role_name="member", permissions=("manage_team",)),
        body(role_name="owner"),
        body(permissions=("manage_team", "manage_team")),
    ):
        assert client.put(f"{path}/{target}/role", json=invalid).status_code == 422
    assert client.put(f"{path}/{target}/role", json=body(version + 1)).status_code == 409
    manual = client.post(path, json={"name": "Jogador sem conta"}).json()
    manual_role = f"{path}/{manual['membership_id']}/role"
    assert client.put(manual_role, json=body(manual["roster_version"])).status_code == 409
    inactive = client.post(f"{path}/{target}/deactivate").json()
    refused = client.put(f"{path}/{target}/role", json=body(inactive["roster_version"]))
    assert refused.status_code == 409
    # Pro keeps the existing limit: five administrators besides the President.
    for _ in range(4):
        _, extra = member(session, team)
        role(client, path, str(extra.id), "admin", ["manage_events"])
    _, sixth = member(session, team)
    assert "Limite" in role(client, path, str(sixth.id), "admin", ["manage_events"], 409)["detail"]


def test_presidency_transfer_preserves_memberships_history_and_audit(session):
    owner, team, client, path = setup_roster(session, Plan.PRO)
    heir_player, heir = member(
        session, team, role=Role.ADMIN, permissions=frozenset({Permission.MANAGE_EVENTS})
    )
    heir_client = client_for(session, heir_player)
    old_id, heir_id = team.president_membership_id, heir.id
    history(session, team, client, {"membership_id": str(heir_id)})
    root = f"/v1/teams/{team.id}/statistics/players"
    before = {m: client.get(f"{root}/{m}").json() for m in (old_id, heir_id)}
    assert before[heir_id]["person"]["totals"]["goals"] == 1
    memberships = session.scalar(select(func.count()).select_from(TeamMembership))
    url = f"/v1/teams/{team.id}/presidency"
    response = client.post(url, json={"membership_id": str(heir_id), "confirm": True})
    assert response.status_code == 200, response.text
    assert response.json()["my_role"] == "member" and response.json()["can_edit"] is False
    session.expire_all()
    assert session.get(Team, team.id).president_membership_id == heir_id
    previous, successor = session.get(TeamMembership, old_id), session.get(TeamMembership, heir_id)
    assert previous.status == successor.status == "active"
    assert previous.role == successor.role == "member"
    assert session.scalar(select(func.count()).select_from(MembershipPermission)) == 0
    assert session.scalar(select(func.count()).select_from(TeamMembership)) == memberships
    for membership_id, snapshot in before.items():
        after = client.get(f"{root}/{membership_id}").json()
        assert after["person"]["totals"] == snapshot["person"]["totals"]
        assert after["history"] == snapshot["history"]
    # Presidential powers moved; the previous President is an ordinary member now.
    assert client.get(f"/v1/teams/{team.id}/administration").status_code == 403
    assert heir_client.get(f"/v1/teams/{team.id}/administration").status_code == 200
    assert heir_client.get(f"/v1/teams/{team.id}").json()["my_role"] == "president"
    listed = {i["membership_id"]: i for i in heir_client.get(path).json()["items"]}
    assert listed[str(heir_id)]["role"] == "president" and listed[str(old_id)]["role"] == "member"
    assert client.post(url, json={"membership_id": str(old_id), "confirm": True}).status_code == 403
    audit = session.scalars(
        select(TeamAudit).where(TeamAudit.action == "PRESIDENCY_TRANSFERRED")
    ).one()
    assert audit.actor_id == owner.user_id and audit.entity_id == team.id
    assert audit.before["president_membership_id"] == str(old_id)
    assert audit.before["successor_permissions"] == ["manage_events"]
    assert audit.after["president_membership_id"] == str(heir_id)
    back = heir_client.post(url, json={"membership_id": str(old_id), "confirm": True})
    assert back.status_code == 200 and back.json()["my_role"] == "member"


def test_presidency_transfer_rejects_invalid_requests(session):
    _, team, client, path = setup_roster(session, Plan.PRO)
    admin_player, _ = member(session, team, role=Role.ADMIN, permissions=frozenset(Permission))
    heir_player, heir = member(session, team)
    president = team.president_membership_id
    url = f"/v1/teams/{team.id}/presidency"

    def body(membership_id, confirm=True):
        return {"membership_id": str(membership_id), "confirm": confirm}

    assert client_for(session, admin_player).post(url, json=body(heir.id)).status_code == 403
    assert client_for(session, heir_player).post(url, json=body(heir.id)).status_code == 403
    outsider = client_for(session, make_player(session))
    assert outsider.post(url, json=body(heir.id)).status_code == 404
    assert client.post(url, json=body(heir.id, False)).status_code == 409
    assert client.post(url, json={"membership_id": str(heir.id)}).status_code == 422
    assert client.post(url, json=body(president)).status_code == 409
    manual = client.post(path, json={"name": "Jogador sem conta"}).json()
    assert client.post(url, json=body(manual["membership_id"])).status_code == 409
    _, other_team, _, _ = setup_roster(session, Plan.PRO)
    assert client.post(url, json=body(other_team.president_membership_id)).status_code == 404
    _, removed = member(session, team)
    removal = {"confirm": True, "expected_version": 1}
    assert client.post(f"{path}/{removed.id}/remove", json=removal).status_code == 200
    assert client.post(url, json=body(removed.id)).status_code == 409
    locked_player, locked = member(session, team)
    session.get(User, locked_player.user_id).status = "inactive"
    session.commit()
    assert client.post(url, json=body(locked.id)).status_code == 409
    assert client.post(f"{path}/{heir.id}/deactivate").status_code == 200
    assert client.post(url, json=body(heir.id)).status_code == 409
    session.expire_all()
    assert session.get(Team, team.id).president_membership_id == president
    assert "PRESIDENCY_TRANSFERRED" not in actions(session, team)


def test_concurrent_transfers_keep_exactly_one_president(engine, session):
    owner, team, _, _ = setup_roster(session, Plan.PRO)
    targets = [member(session, team)[1].id for _ in range(2)]
    owner_id, team_id = owner.user_id, team.id
    barrier = Barrier(2)

    def transfer(target):
        with Session(engine) as other:
            barrier.wait()
            try:
                team_roles.transfer_presidency(other, owner_id, team_id, target, confirm=True)
                return "ok"
            except Forbidden:
                return "forbidden"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(transfer, targets)) == ["forbidden", "ok"]
    session.expire_all()
    assert session.get(Team, team_id).president_membership_id in targets
    assert actions(session, team).count("PRESIDENCY_TRANSFERRED") == 1
