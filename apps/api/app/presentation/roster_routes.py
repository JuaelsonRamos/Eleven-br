from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from app.application import roster
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.roster_schemas import (
    RosterCreate,
    RosterPage,
    RosterRead,
    RosterUpdate,
    SimilarRead,
)

router = APIRouter(prefix="/v1/teams/{team_id}/players", tags=["roster"])


@router.get("", response_model=RosterPage)
def list_players(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    status: Literal["active", "inactive", "all"] = "active",
) -> RosterPage:
    return RosterPage.model_validate(
        roster.list_roster(session, user_id=user.id, team_id=team_id, status=status)
    )


@router.post("/similar", response_model=list[SimilarRead])
def similar(
    team_id: UUID,
    data: RosterCreate,
    session: SessionDep,
    user: CurrentUser,
    exclude: UUID | None = None,
) -> list[SimilarRead]:
    matches = roster.similar_players(
        session,
        user_id=user.id,
        team_id=team_id,
        name=data.name,
        phone=data.phone,
        email=data.email,
        exclude=exclude,
    )
    return [SimilarRead.model_validate(item) for item in matches]


@router.post("", response_model=RosterRead, status_code=201)
def add(team_id: UUID, data: RosterCreate, session: SessionDep, user: CurrentUser) -> RosterRead:
    return RosterRead.model_validate(
        roster.add_player(session, user_id=user.id, team_id=team_id, **data.model_dump())
    )


@router.get("/{membership_id}", response_model=RosterRead)
def detail(
    team_id: UUID, membership_id: UUID, session: SessionDep, user: CurrentUser
) -> RosterRead:
    return RosterRead.model_validate(
        roster.get_person(session, user_id=user.id, team_id=team_id, membership_id=membership_id)
    )


@router.put("/{membership_id}", response_model=RosterRead)
def edit(
    team_id: UUID, membership_id: UUID, data: RosterUpdate, session: SessionDep, user: CurrentUser
) -> RosterRead:
    return RosterRead.model_validate(
        roster.edit_player(
            session,
            user_id=user.id,
            team_id=team_id,
            membership_id=membership_id,
            updates=data.model_dump(exclude_unset=True, exclude={"confirm_duplicate"}),
            confirm_duplicate=data.confirm_duplicate,
        )
    )


@router.post("/{membership_id}/deactivate", response_model=RosterRead)
def deactivate(
    team_id: UUID, membership_id: UUID, session: SessionDep, user: CurrentUser
) -> RosterRead:
    return RosterRead.model_validate(
        roster.change_status(
            session, user_id=user.id, team_id=team_id, membership_id=membership_id, activate=False
        )
    )


@router.post("/{membership_id}/reactivate", response_model=RosterRead)
def reactivate(
    team_id: UUID, membership_id: UUID, session: SessionDep, user: CurrentUser
) -> RosterRead:
    return RosterRead.model_validate(
        roster.change_status(
            session, user_id=user.id, team_id=team_id, membership_id=membership_id, activate=True
        )
    )
