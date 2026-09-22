from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.application import roster
from app.application.teams import active_count, add_member
from app.domain.policies import Conflict, Permission, Plan, Role
from app.infrastructure.models import MembershipPermission, Player, TeamMembership, User
from tests.conftest import make_player
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for


def setup_roster(session: Session, plan: Plan = Plan.FREE):
    president = make_player(session)
    team = make_team(session, president, plan)
    client = client_for(session, president)
    return president, team, client, f"/v1/teams/{team.id}/players"


def test_president_initial_roster_and_manual_player_lifecycle(session: Session) -> None:
    president, team, client, path = setup_roster(session)
    initial = client.get(path).json()
    assert initial["active_count"] == 1 and initial["active_limit"] == 24
    assert initial["items"][0]["player_id"] == str(president.id)
    assert initial["items"][0]["is_president"] is True
    assert initial["items"][0]["account_linked"] is True
    users = session.scalar(select(func.count()).select_from(User))
    created = client.post(path, json={"name": "João Silva"})
    assert created.status_code == 201
    manual = created.json()
    assert manual["account_linked"] is False and manual["status"] == "active"
    player = session.get(Player, UUID(manual["player_id"]))
    assert player and player.user_id is None
    assert session.scalar(select(func.count()).select_from(User)) == users
    detail = f"{path}/{manual['membership_id']}"
    update = client.put(
        detail,
        json={
            "name": "João Souza",
            "nickname": "Joca",
            "phone": "(27) 99999-1234",
            "email": " JOAO@EXAMPLE.COM ",
        },
    )
    assert update.status_code == 200
    assert (
        update.json()["phone"] == "+5527999991234" and update.json()["email"] == "joao@example.com"
    )
    assert client.get(detail).json()["name"] == "João Souza"
    assert client.post(f"{detail}/deactivate").json()["status"] == "inactive"
    listing = client.get(path).json()
    assert listing["active_count"] == 1 and listing["inactive_count"] == 1
    assert len(listing["items"]) == 1
    assert (
        client.get(path + "?status=inactive").json()["items"][0]["membership_id"]
        == manual["membership_id"]
    )
    assert len(client.get(path + "?status=all").json()["items"]) == 2
    activated = client.post(f"{detail}/reactivate").json()
    assert activated["membership_id"] == manual["membership_id"]
    assert activated["player_id"] == manual["player_id"] and activated["status"] == "active"
    assert client.get(f"/v1/teams/{team.id}").json()["active_player_count"] == 2
    assert client.post(f"{path}/{team.president_membership_id}/deactivate").status_code == 409
    assert session.get(TeamMembership, team.president_membership_id).status == "active"


def test_permissions_idor_and_private_contacts(session: Session) -> None:
    president, team, owner, path = setup_roster(session)
    reader = make_player(session)
    membership = add_member(session, team_id=team.id, player_id=reader.id)
    member_client = client_for(session, reader)
    outsider_client = client_for(session, make_player(session))
    other = make_team(session, president)
    session.commit()
    created = owner.post(
        path, json={"name": "Pessoa manual", "phone": "27999991234", "email": "manual@example.com"}
    ).json()
    detail = f"{path}/{created['membership_id']}"
    member_page = member_client.get(path).json()
    assert member_page["can_manage"] is False
    assert member_client.get(detail).json()["phone"] is None
    assert "manual@example.com" not in member_client.get(path + "?status=all").text
    assert member_client.post(path, json={"name": "Novo"}).status_code == 403
    assert member_client.post(path + "/similar", json={"name": "Pessoa"}).status_code == 403
    assert member_client.put(detail, json={"name": "Invadido"}).status_code == 403
    for action in ["deactivate", "reactivate"]:
        assert member_client.post(detail + "/" + action).status_code == 403
    assert outsider_client.get(path).status_code == 404
    assert outsider_client.get(detail).status_code == 404
    assert outsider_client.put(detail, json={"name": "Invadido"}).status_code == 404
    for action in ["deactivate", "reactivate"]:
        assert outsider_client.post(detail + "/" + action).status_code == 404
    assert outsider_client.post(path, json={"name": "Novo"}).status_code == 404
    for fake in [other.president_membership_id, uuid4()]:
        forged = f"{path}/{fake}"
        assert owner.get(forged).status_code == 404
        assert owner.put(forged, json={"name": "Outro"}).status_code == 404
        for action in ["deactivate", "reactivate"]:
            assert owner.post(forged + "/" + action).status_code == 404
    # Even a president of both teams cannot combine a team ID and foreign membership ID.
    assert owner.get(f"/v1/teams/{other.id}/players/{created['membership_id']}").status_code == 404
    assert (
        owner.post(
            f"{path}/similar?exclude={other.president_membership_id}", json={"name": "Novo"}
        ).status_code
        == 404
    )
    membership.status = "inactive"
    session.commit()
    assert member_client.get(path).status_code == 404
    anonymous = client_for(session)
    assert anonymous.get(path).status_code == 401
    assert anonymous.post(path, json={"name": "Novo"}).status_code == 401


def test_linked_profile_and_other_team_data_cannot_be_modified(session: Session) -> None:
    _, team, owner, path = setup_roster(session)
    linked = make_player(session)
    member = add_member(session, team_id=team.id, player_id=linked.id)
    session.commit()
    original_name = linked.display_name
    original_user = session.get(User, linked.user_id).email
    detail = f"{path}/{member.id}"
    for payload in [
        {"name": "Changed"},
        {"email": "changed@example.com"},
        {"phone": "27999991234"},
    ]:
        assert owner.put(detail, json=payload).status_code == 403
    assert owner.put(detail, json={"nickname": "Capitão"}).status_code == 200
    assert (
        linked.display_name == original_name
        and session.get(User, linked.user_id).email == original_user
    )
    # Shared manual Player: the editable profile is scoped to each membership.
    created = owner.post(path, json={"name": "Manual original"}).json()
    shared = session.get(Player, UUID(created["player_id"]))
    other = make_team(session, make_player(session))
    other_membership = add_member(session, team_id=other.id, player_id=shared.id)
    other_membership.roster_name = "Nome no outro time"
    session.commit()
    assert (
        owner.put(f"{path}/{created['membership_id']}", json={"name": "Nome local"}).status_code
        == 200
    )
    session.refresh(other_membership)
    assert other_membership.roster_name == "Nome no outro time"
    assert shared.display_name == "Manual original"


def test_duplicates_require_confirmation_and_never_link_accounts(session: Session) -> None:
    _, _, owner, path = setup_roster(session)
    account = make_player(session)
    email = session.get(User, account.user_id).email
    session.commit()
    first = owner.post(
        path, json={"name": "José Silva", "email": email, "phone": "27999991234"}
    ).json()
    assert first["account_linked"] is False and first["player_id"] != str(account.id)
    assert owner.post(path, json={"name": "JOSE SILVA"}).status_code == 409
    matches = owner.post(
        path + "/similar", json={"name": "Outro nome", "email": email, "phone": "+5527999991234"}
    ).json()
    assert set(matches[0]["reasons"]) == {"telefone", "e-mail"}
    assert matches[0]["membership_id"] == first["membership_id"]
    second = owner.post(
        path, json={"name": "José Silva", "email": email, "confirm_duplicate": True}
    )
    assert second.status_code == 201 and second.json()["player_id"] != first["player_id"]
    assert second.json()["account_linked"] is False
    other = make_team(session, account)
    session.commit()
    another_client = client_for(session, account)
    assert (
        another_client.post(
            f"/v1/teams/{other.id}/players/similar", json={"name": "José Silva", "email": email}
        ).json()
        == []
    )


@pytest.mark.parametrize("plan,limit", [(Plan.FREE, 24), (Plan.PRO, 100)])
def test_capacity_activation_and_vacancy(session: Session, plan: Plan, limit: int) -> None:
    _, team, owner, path = setup_roster(session, plan)
    for _ in range(limit - 2):
        # Separate IDs are needed regardless of identical names in seeded capacity fixtures.
        member_player = Player(display_name="Participante")
        session.add(member_player)
        session.flush()
        add_member(session, team_id=team.id, player_id=member_player.id)
    session.commit()
    last = owner.post(path, json={"name": "Última vaga"}).json()
    assert owner.get(path).json()["active_count"] == limit
    before_players = session.scalar(select(func.count()).select_from(Player))
    assert owner.post(path, json={"name": "Sem vaga"}).status_code == 409
    assert session.scalar(select(func.count()).select_from(Player)) == before_players
    detail = f"{path}/{last['membership_id']}"
    assert owner.post(detail + "/deactivate").status_code == 200
    replacement = owner.post(path, json={"name": "Reposição"}).json()
    assert owner.post(detail + "/reactivate").status_code == 409
    assert owner.post(f"{path}/{replacement['membership_id']}/deactivate").status_code == 200
    assert owner.post(detail + "/reactivate").status_code == 200
    assert owner.post(detail + "/reactivate").status_code == 200  # idempotent, no extra slot
    assert owner.get(path).json()["active_count"] == limit
    assert active_count(session, team.id) == limit


@pytest.mark.parametrize("scenario", ["add", "reactivate", "mixed"])
def test_simultaneous_last_slot_across_add_and_reactivate(
    session: Session, engine: Engine, scenario: str
) -> None:
    president, team, _, _ = setup_roster(session)
    for _ in range(22):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    inactive = []
    for _ in range(2):
        player = Player(display_name="Inativo")
        session.add(player)
        session.flush()
        membership = TeamMembership(team_id=team.id, player_id=player.id, status="inactive")
        session.add(membership)
        session.flush()
        inactive.append(membership.id)
    team_id, user_id = team.id, president.user_id
    session.commit()
    barrier = Barrier(2)

    def compete(index: int) -> str:
        with Session(engine) as concurrent:
            barrier.wait(timeout=10)
            try:
                if scenario == "add" or (scenario == "mixed" and index == 0):
                    roster.add_player(
                        concurrent,
                        user_id=user_id,
                        team_id=team_id,
                        name=f"Concorrente {index}",
                        nickname=None,
                        phone=None,
                        email=None,
                        confirm_duplicate=True,
                    )
                else:
                    roster.change_status(
                        concurrent,
                        user_id=user_id,
                        team_id=team_id,
                        membership_id=inactive[index],
                        activate=True,
                    )
                return "ok"
            except Conflict:
                concurrent.rollback()
                return "full"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(compete, [0, 1])) == ["full", "ok"]
    session.expire_all()
    assert active_count(session, team_id) == 24


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " "},
        {"name": "Nome", "email": "invalid"},
        {"name": "Nome", "phone": "123"},
        {"name": "Nome", "user_id": str(uuid4())},
        {"name": "Nome", "role": "admin"},
        {"name": "Nome", "status": "inactive"},
    ],
)
def test_roster_validation_and_protected_fields(session: Session, payload: dict[str, str]) -> None:
    _, _, client, path = setup_roster(session)
    assert client.post(path, json=payload).status_code == 422
    assert client.get(path + "?status=deleted").status_code == 422


def test_existing_granular_permissions_and_admin_reactivation_limit(session: Session) -> None:
    _, team, owner, path = setup_roster(session, Plan.PRO)
    admin_player = make_player(session)
    admin = add_member(
        session,
        team_id=team.id,
        player_id=admin_player.id,
        role=Role.ADMIN,
        permissions=frozenset({Permission.MANAGE_TEAM}),
    )
    client = client_for(session, admin_player)
    assert client.get(path).json()["can_manage"] is False
    assert client.post(path, json={"name": "Sem permissão"}).status_code == 403
    session.add(MembershipPermission(membership_id=admin.id, permission=Permission.MANAGE_MEMBERS))
    session.commit()
    assert client.get(path).json()["can_manage"] is True
    assert client.post(path, json={"name": "Autorizado"}).status_code == 201
    for _ in range(4):
        add_member(session, team_id=team.id, player_id=make_player(session).id, role=Role.ADMIN)
    dormant = TeamMembership(
        team_id=team.id, player_id=make_player(session).id, role=Role.ADMIN.value, status="inactive"
    )
    session.add(dormant)
    session.commit()
    assert owner.post(f"{path}/{dormant.id}/reactivate").status_code == 409
    team.plan = Plan.FREE.value
    session.commit()
    assert client.get(path).json()["can_manage"] is False
    assert client.post(path, json={"name": "Sem permissão Free"}).status_code == 403
