from uuid import UUID

from fastapi import APIRouter

from app.application import events
from app.domain.events import EventDraft
from app.presentation.dependencies import CurrentUser, SessionDep
from app.presentation.event_schemas import (
    AttendanceInput,
    EventCreate,
    EventInput,
    EventPage,
    EventRead,
    GuestInput,
)

router = APIRouter(prefix="/v1/teams/{team_id}/events", tags=["events"])


@router.get("", response_model=EventPage)
def listing(team_id: UUID, session: SessionDep, user: CurrentUser) -> EventPage:
    return EventPage.model_validate(events.list_events(session, user_id=user.id, team_id=team_id))


@router.post("", response_model=EventRead, status_code=201)
def create(team_id: UUID, data: EventCreate, session: SessionDep, user: CurrentUser) -> EventRead:
    event = events.create_event(
        session,
        user_id=user.id,
        team_id=team_id,
        draft=EventDraft(**data.model_dump(exclude={"recurring_until", "recurring_weekly"})),
        recurring_weekly=data.recurring_weekly,
        recurring_until=data.recurring_until,
    )
    return detail(team_id, event.id, session, user)


@router.get("/{event_id}", response_model=EventRead)
def detail(team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser) -> EventRead:
    return EventRead.model_validate(
        events.detail(session, user_id=user.id, team_id=team_id, event_id=event_id)
    )


@router.put("/{event_id}", response_model=EventRead)
def edit(
    team_id: UUID, event_id: UUID, data: EventInput, session: SessionDep, user: CurrentUser
) -> EventRead:
    events.edit_event(
        session,
        user_id=user.id,
        team_id=team_id,
        event_id=event_id,
        draft=EventDraft(**data.model_dump()),
    )
    return detail(team_id, event_id, session, user)


@router.post("/{event_id}/cancel", response_model=EventRead)
def cancel(team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser) -> EventRead:
    events.cancel_event(session, user_id=user.id, team_id=team_id, event_id=event_id)
    return detail(team_id, event_id, session, user)


@router.put("/{event_id}/attendance", response_model=EventRead)
def attendance(
    team_id: UUID, event_id: UUID, data: AttendanceInput, session: SessionDep, user: CurrentUser
) -> EventRead:
    events.respond(
        session, user_id=user.id, team_id=team_id, event_id=event_id, response=data.response
    )
    return detail(team_id, event_id, session, user)


@router.post("/{event_id}/cancel-series", response_model=EventRead)
def cancel_recurrence(
    team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser
) -> EventRead:
    events.cancel_series(session, user_id=user.id, team_id=team_id, event_id=event_id)
    return detail(team_id, event_id, session, user)


@router.post("/{event_id}/guests", response_model=EventRead, status_code=201)
def guest(
    team_id: UUID, event_id: UUID, data: GuestInput, session: SessionDep, user: CurrentUser
) -> EventRead:
    events.add_guest(session, user_id=user.id, team_id=team_id, event_id=event_id, name=data.name)
    return detail(team_id, event_id, session, user)


@router.post("/{event_id}/guests/{guest_id}/remove", response_model=EventRead)
def remove(
    team_id: UUID, event_id: UUID, guest_id: UUID, session: SessionDep, user: CurrentUser
) -> EventRead:
    events.remove_guest(
        session, user_id=user.id, team_id=team_id, event_id=event_id, guest_id=guest_id
    )
    return detail(team_id, event_id, session, user)
