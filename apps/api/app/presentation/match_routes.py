from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from app.application import matches
from app.application.events import authorize, find_event
from app.infrastructure.match_models import EventMatch
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.match_schemas import (
    CreateMatchInput,
    MatchActionInput,
    MatchRead,
    MatchScoreInput,
)

router = APIRouter(prefix="/v1/teams/{team_id}/events/{event_id}/matches", tags=["matches"])


@router.get("", response_model=list[MatchRead])
def list_matches(
    team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser
) -> list[EventMatch]:
    return matches.list_matches(session, user_id=user.id, team_id=team_id, event_id=event_id)


@router.post("", response_model=MatchRead, status_code=201)
def create(
    team_id: UUID, event_id: UUID, data: CreateMatchInput, session: SessionDep, user: CurrentUser
) -> EventMatch:
    return matches.create(
        session, user_id=user.id, team_id=team_id, event_id=event_id, **data.model_dump()
    )


@router.get("/{match_id}", response_model=MatchRead)
def detail(
    team_id: UUID, event_id: UUID, match_id: UUID, session: SessionDep, user: CurrentUser
) -> EventMatch:
    authorize(session, user.id, team_id)
    find_event(session, team_id, event_id)
    return matches.find_match(session, team_id, event_id, match_id)


@router.put("/{match_id}/score", response_model=MatchRead)
def score(
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    data: MatchScoreInput,
    session: SessionDep,
    user: CurrentUser,
) -> EventMatch:
    return matches.change(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        action="score",
        **data.model_dump(),
    )


@router.post("/{match_id}/{action}", response_model=MatchRead)
def transition(
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    action: Literal["start", "finish", "cancel"],
    data: MatchActionInput,
    session: SessionDep,
    user: CurrentUser,
) -> EventMatch:
    return matches.change(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        action=action,
        **data.model_dump(),
    )
