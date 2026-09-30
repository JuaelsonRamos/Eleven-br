from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.application import municipalities, team_locations, team_roles
from app.application.accounts import complete_profile
from app.application.billing_access import effective_plan, effective_plans
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
    LocationInput,
    PresidencyInput,
    ProfileRead,
    TeamCreate,
    TeamEdit,
    TeamInput,
    TeamPublicRead,
    TeamRead,
)

router = APIRouter()


@router.get("/v1/public/platform-stats", tags=["public"])
def platform_stats(session: SessionDep, response: Response) -> dict[str, int]:
    response.headers["Cache-Control"] = "public, max-age=60"
    teams, players = session.execute(
        select(
            select(func.count()).select_from(Team).where(Team.status == "active").scalar_subquery(),
            select(func.count()).select_from(Player).scalar_subquery(),
        )
    ).one()
    return {"teams": teams, "players": players}


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
    items = visible_teams(session, user.id)
    plans = effective_plans(session, items)
    return [team_response(team, session, user.id, plans[team.id]) for team in items]


def team_response(
    team: Team, session: SessionDep, user_id: UUID, plan: Plan | None = None
) -> TeamRead:
    plan = plan or effective_plan(session, team)
    role, can_edit = membership_context(session, team, user_id, plan=plan)
    return TeamRead.model_validate(team).model_copy(
        update={
            "my_role": role,
            "plan": plan,
            "can_edit": can_edit,
            "active_player_count": active_count(session, team.id),
            "location_confirmed": team.location_confirmed_at is not None,
        }
    )


@router.get("/v1/teams/options", tags=["teams"])
def team_options(user: CurrentUser) -> dict[str, object]:
    return {
        "modalities": [{"value": value, "label": label} for value, label in MODALITIES.items()],
        "states": [{"value": code, "label": f"{name} ({code})"} for code, name in STATES.items()],
    }


@router.get("/v1/locations/states/{state}/municipalities", tags=["teams"])
def state_municipalities(
    state: str, session: SessionDep, user: CurrentUser, response: Response
) -> dict[str, object]:
    # Official reference data; the app caches it and never needs the IBGE service.
    response.headers["Cache-Control"] = "private, max-age=86400"
    return {"state": state, "items": municipalities.listing(session, state)}


@router.post("/v1/teams/similar", response_model=list[TeamPublicRead], tags=["teams"])
def check_similar(data: TeamInput, session: SessionDep, user: CurrentUser) -> list[TeamPublicRead]:
    return [
        TeamPublicRead.model_validate(team) for team in similar_teams(session, **data.model_dump())
    ]


@router.post("/v1/teams", response_model=TeamRead, status_code=201, tags=["teams"])
def new_team(data: TeamCreate, session: SessionDep, user: CurrentUser) -> TeamRead:
    team = register_team(session, user_id=user.id, **data.model_dump())
    return team_response(team, session, user.id)


@router.put("/v1/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def update_team(team_id: UUID, data: TeamEdit, session: SessionDep, user: CurrentUser) -> TeamRead:
    team = edit_team(session, user_id=user.id, team_id=team_id, **data.model_dump())
    return team_response(team, session, user.id)


@router.get("/v1/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def team_detail(team_id: UUID, session: SessionDep, user: CurrentUser) -> TeamRead:
    return team_response(
        require_membership(session, user_id=user.id, team_id=team_id), session, user.id
    )


@router.get("/v1/teams/{team_id}/location", tags=["teams"])
def team_location(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return team_locations.location(session, user.id, team_id)


@router.put("/v1/teams/{team_id}/location", response_model=TeamRead, tags=["teams"])
def confirm_location(
    team_id: UUID, data: LocationInput, session: SessionDep, user: CurrentUser
) -> TeamRead:
    team = team_locations.change(session, user.id, team_id, **data.model_dump())
    return team_response(team, session, user.id)


@router.post("/v1/teams/{team_id}/presidency", response_model=TeamRead, tags=["teams"])
def transfer_presidency(
    team_id: UUID, data: PresidencyInput, session: SessionDep, user: CurrentUser
) -> TeamRead:
    team = team_roles.transfer_presidency(
        session, user.id, team_id, data.membership_id, confirm=data.confirm
    )
    return team_response(team, session, user.id)


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
    plan = effective_plan(session, team)
    limits = ENTITLEMENTS[plan]
    return AdministrationRead(
        team_id=team.id,
        president_membership_id=team.president_membership_id,
        plan=plan,
        active_player_limit=limits.active_players,
        administrator_limit=limits.administrators,
    )
