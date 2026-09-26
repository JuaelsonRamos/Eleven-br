from uuid import UUID

from fastapi import APIRouter

from app.application import match_events
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.match_event_schemas import (
    MatchEventInput,
    MatchEventsPage,
    RemoveMatchEventInput,
)

router = APIRouter(
    prefix="/v1/teams/{team_id}/events/{event_id}/matches/{match_id}/events", tags=["match-events"]
)


@router.get("", response_model=MatchEventsPage)
def detail(
    team_id: UUID, event_id: UUID, match_id: UUID, session: SessionDep, user: CurrentUser
) -> MatchEventsPage:
    return MatchEventsPage.model_validate(
        match_events.detail(
            session, user_id=user.id, team_id=team_id, event_id=event_id, match_id=match_id
        )
    )


@router.post("", response_model=MatchEventsPage, status_code=201)
def create(
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    data: MatchEventInput,
    session: SessionDep,
    user: CurrentUser,
) -> MatchEventsPage:
    match_events.save(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        **data.model_dump(),
    )
    return detail(team_id, event_id, match_id, session, user)


@router.put("/{match_event_id}", response_model=MatchEventsPage)
def edit(
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    match_event_id: UUID,
    data: MatchEventInput,
    session: SessionDep,
    user: CurrentUser,
) -> MatchEventsPage:
    match_events.save(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        match_event_id=match_event_id,
        **data.model_dump(),
    )
    return detail(team_id, event_id, match_id, session, user)


@router.post("/{match_event_id}/remove", response_model=MatchEventsPage)
def remove(
    team_id: UUID,
    event_id: UUID,
    match_id: UUID,
    match_event_id: UUID,
    data: RemoveMatchEventInput,
    session: SessionDep,
    user: CurrentUser,
) -> MatchEventsPage:
    match_events.remove(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        match_id=match_id,
        match_event_id=match_event_id,
        **data.model_dump(),
    )
    return detail(team_id, event_id, match_id, session, user)
