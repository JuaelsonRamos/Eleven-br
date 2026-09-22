from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.application.accounts import complete_profile
from app.application.team_profiles import (
    edit_team,
    membership_context,
    register_team,
    similar_teams,
)
from app.application.teams import active_count, require_membership, visible_teams
from app.domain.policies import ENTITLEMENTS, Permission, Plan
from app.domain.team_identity import MODALITIES, STATES
from app.infrastructure.models import Player, Team
from app.presentation.auth_schemas import ProfileInput
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.schemas import (
    AdministrationRead,
    ProfileRead,
    TeamInput,
    TeamPublicRead,
    TeamRead,
)

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "eleven-br-api"}


@router.get("/ready", tags=["health"])
def ready(session: SessionDep) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Banco indisponível") from None
    return {"status": "ready"}


@router.get("/v1/me", response_model=ProfileRead, tags=["profile"])
def me(session: SessionDep, user: CurrentUser) -> ProfileRead:
    player = session.scalar(select(Player).where(Player.user_id == user.id))
    return ProfileRead(
        user_id=user.id,
        player_id=player.id if player else None,
        display_name=player.display_name if player else None,
        photo_url=player.photo_url if player else None,
        email=user.email,
        phone=user.phone,
    )


@router.put("/v1/me/profile", response_model=ProfileRead, tags=["profile"])
def save_profile(data: ProfileInput, session: SessionDep, user: CurrentUser) -> ProfileRead:
    complete_profile(session, user, data.name)
    return me(session, user)


@router.get("/v1/teams", response_model=list[TeamRead], tags=["teams"])
def teams(session: SessionDep, user: CurrentUser) -> list[TeamRead]:
    return [team_response(team, session, user.id) for team in visible_teams(session, user.id)]


def team_response(team: Team, session: SessionDep, user_id: UUID) -> TeamRead:
    role, can_edit = membership_context(session, team, user_id)
    return TeamRead.model_validate(team).model_copy(
        update={
            "my_role": role,
            "can_edit": can_edit,
            "active_player_count": active_count(session, team.id),
        }
    )


@router.get("/v1/teams/options", tags=["teams"])
def team_options(user: CurrentUser) -> dict[str, object]:
    return {
        "modalities": [{"value": value, "label": label} for value, label in MODALITIES.items()],
        "states": [{"value": code, "label": f"{name} ({code})"} for code, name in STATES.items()],
    }


@router.post("/v1/teams/similar", response_model=list[TeamPublicRead], tags=["teams"])
def check_similar(data: TeamInput, session: SessionDep, user: CurrentUser) -> list[TeamPublicRead]:
    return [
        TeamPublicRead.model_validate(team) for team in similar_teams(session, **data.model_dump())
    ]


@router.post("/v1/teams", response_model=TeamRead, status_code=201, tags=["teams"])
def new_team(data: TeamInput, session: SessionDep, user: CurrentUser) -> TeamRead:
    team = register_team(session, user_id=user.id, **data.model_dump())
    return team_response(team, session, user.id)


@router.put("/v1/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def update_team(team_id: UUID, data: TeamInput, session: SessionDep, user: CurrentUser) -> TeamRead:
    team = edit_team(session, user_id=user.id, team_id=team_id, **data.model_dump())
    return team_response(team, session, user.id)


@router.get("/v1/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def team_detail(team_id: UUID, session: SessionDep, user: CurrentUser) -> TeamRead:
    return team_response(
        require_membership(session, user_id=user.id, team_id=team_id), session, user.id
    )


@router.get("/v1/teams/{team_id}/administration", tags=["teams"])
def administration(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
) -> AdministrationRead:
    team = require_membership(
        session,
        user_id=user.id,
        team_id=team_id,
        permission=Permission.MANAGE_TEAM,
    )
    limits = ENTITLEMENTS[Plan(team.plan)]
    return AdministrationRead(
        team_id=team.id,
        president_membership_id=team.president_membership_id,
        plan=Plan(team.plan),
        active_player_limit=limits.active_players,
        administrator_limit=limits.administrators,
    )
