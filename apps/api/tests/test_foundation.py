from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.sessions import create_session
from app.application.teams import add_member, create_team, require_membership, visible_teams
from app.domain.policies import Conflict, Forbidden, NotFound, Permission, Plan, Role
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session
from app.infrastructure.models import Player, Team, TeamMembership, User
from tests.conftest import make_player


def make_team(session: Session, president: Player, plan: Plan = Plan.FREE) -> Team:
    return create_team(
        session,
        president=president,
        name="Time de teste",
        code=uuid4().hex[:8].upper(),
        city="São Paulo",
        state="SP",
        modality="futebol",
        plan=plan,
    )


def test_distinct_identity_and_multiple_team_presidencies(session: Session) -> None:
    player = make_player(session)
    first, second = make_team(session, player), make_team(session, player)
    third = make_team(session, make_player(session), Plan.PRO)
    membership = add_member(session, team_id=third.id, player_id=player.id, role=Role.ADMIN)
    session.commit()
    assert player.id != player.user_id
    assert len(visible_teams(session, player.user_id)) == 3
    assert len({first.president_membership_id, second.president_membership_id, membership.id}) == 3
    assert session.get(TeamMembership, first.president_membership_id).player_id == player.id


@pytest.mark.parametrize("invalid", ["missing", "other_team", "null", "delete"])
def test_president_constraint_at_commit(session: Session, invalid: str) -> None:
    first = make_team(session, make_player(session))
    second = make_team(session, make_player(session))
    session.commit()
    if invalid == "missing":
        first.president_membership_id = uuid4()
    elif invalid == "other_team":
        first.president_membership_id = second.president_membership_id
    elif invalid == "null":
        first.president_membership_id = None
    else:
        session.delete(session.get(TeamMembership, first.president_membership_id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_player_and_membership_uniqueness(session: Session) -> None:
    player = make_player(session)
    team = make_team(session, player)
    session.commit()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(Player(user_id=player.user_id, display_name="Duplicado"))
        session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(TeamMembership(team_id=team.id, player_id=player.id))
        session.flush()


@pytest.mark.parametrize("plan,limit", [(Plan.FREE, 24), (Plan.PRO, 100)])
def test_active_player_limits(session: Session, plan: Plan, limit: int) -> None:
    team = make_team(session, make_player(session), plan)
    inactive = TeamMembership(team_id=team.id, player_id=make_player(session).id, status="inactive")
    session.add(inactive)
    for _ in range(limit - 1):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    with pytest.raises(Conflict, match="jogadores"):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()


@pytest.mark.parametrize("plan,limit", [(Plan.FREE, 0), (Plan.PRO, 5)])
def test_admin_limits(session: Session, plan: Plan, limit: int) -> None:
    president = make_player(session)
    team = make_team(session, president, plan)
    for _ in range(limit):
        add_member(session, team_id=team.id, player_id=make_player(session).id, role=Role.ADMIN)
    with pytest.raises(Conflict, match="administradores"):
        add_member(session, team_id=team.id, player_id=make_player(session).id, role=Role.ADMIN)
    assert (
        require_membership(
            session,
            user_id=president.user_id,
            team_id=team.id,
            permission=Permission.MANAGE_TEAM,
        ).id
        == team.id
    )


def test_team_isolation_and_granular_permissions(session: Session) -> None:
    player = make_player(session)
    own = make_team(session, player)
    other = make_team(session, make_player(session), Plan.PRO)
    with pytest.raises(NotFound):
        require_membership(session, user_id=player.user_id, team_id=other.id)
    membership = add_member(
        session,
        team_id=other.id,
        player_id=player.id,
        role=Role.ADMIN,
        permissions=frozenset({Permission.MANAGE_MEMBERS}),
    )
    require_membership(
        session, user_id=player.user_id, team_id=own.id, permission=Permission.MANAGE_TEAM
    )
    require_membership(
        session, user_id=player.user_id, team_id=other.id, permission=Permission.MANAGE_MEMBERS
    )
    with pytest.raises(Forbidden):
        require_membership(
            session, user_id=player.user_id, team_id=other.id, permission=Permission.MANAGE_TEAM
        )
    other.plan = Plan.FREE.value
    with pytest.raises(Forbidden):
        require_membership(
            session, user_id=player.user_id, team_id=other.id, permission=Permission.MANAGE_MEMBERS
        )
    membership.status = "inactive"
    with pytest.raises(NotFound):
        require_membership(session, user_id=player.user_id, team_id=other.id)


def test_simultaneous_last_slot_is_serialized(session: Session, engine: Engine) -> None:
    team = make_team(session, make_player(session))
    for _ in range(22):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    candidates = [make_player(session).id, make_player(session).id]
    team_id = team.id
    session.commit()

    def join(player_id):
        try:
            with Session(engine) as concurrent, concurrent.begin():
                add_member(concurrent, team_id=team_id, player_id=player_id)
            return "joined"
        except Conflict:
            return "full"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(join, candidates)) == ["full", "joined"]
    assert (
        session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
            )
        )
        == 24
    )


def test_api_authorization_and_safe_responses(session: Session) -> None:
    from app.main import create_app

    owner = make_player(session)
    outsider = make_player(session)
    team = make_team(session, owner)
    session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/v1/teams").status_code == 401
    assert client.get("/v1/teams", headers={"Authorization": "Bearer invalid"}).status_code == 401
    token = create_session(
        session, session.get(User, outsider.user_id), "native", get_settings()
    ).access_token
    session.commit()
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get("/v1/teams").json() == []
    assert client.get(f"/v1/teams/{team.id}").status_code == 404
    assert client.get(f"/v1/teams/{team.id}/administration").status_code == 404
    add_member(session, team_id=team.id, player_id=outsider.id)
    session.commit()
    assert client.get(f"/v1/teams/{team.id}").status_code == 200
    assert client.get(f"/v1/teams/{team.id}/administration").status_code == 403
    owner_token = create_session(
        session, session.get(User, owner.user_id), "native", get_settings()
    ).access_token
    session.commit()
    client.headers["Authorization"] = f"Bearer {owner_token}"
    assert client.get(f"/v1/teams/{team.id}/administration").status_code == 200
    assert "password_hash" not in client.get("/v1/me").text
    user = session.get(User, owner.user_id)
    user.status = "inactive"
    session.commit()
    assert client.get("/v1/me").status_code == 401
