from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.application.accounts import complete_profile
from app.application.teams import require_membership, visible_teams
from app.domain.policies import ENTITLEMENTS, Permission, Plan
from app.infrastructure.models import Player
from app.presentation.auth_schemas import ProfileInput
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.schemas import AdministrationRead, ProfileRead, TeamRead

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
    return [TeamRead.model_validate(team) for team in visible_teams(session, user.id)]


@router.get("/v1/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def team_detail(team_id: UUID, session: SessionDep, user: CurrentUser) -> TeamRead:
    return TeamRead.model_validate(require_membership(session, user_id=user.id, team_id=team_id))


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
