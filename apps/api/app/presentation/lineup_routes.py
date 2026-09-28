from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.application import lineups
from app.presentation.dependencies import CurrentUser, SessionDep

router = APIRouter(prefix="/v1/teams/{team_id}/lineups", tags=["lineups"])


@router.get("")
def listing(
    team_id: UUID,
    session: SessionDep,
    user: CurrentUser,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> dict[str, object]:
    return lineups.list_items(session, user.id, team_id, offset)


@router.get("/{lineup_id}")
def detail(
    team_id: UUID, lineup_id: UUID, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return lineups.detail(session, user.id, team_id, lineup_id)


@router.post("", status_code=201)
def create(
    team_id: UUID, data: lineups.LineupInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    return lineups.save(session, user.id, team_id, data)


@router.put("/{lineup_id}")
def update(
    team_id: UUID,
    lineup_id: UUID,
    data: lineups.LineupInput,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, object]:
    return lineups.save(session, user.id, team_id, data, lineup_id)
