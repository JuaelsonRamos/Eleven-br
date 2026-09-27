from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.application import notifications
from app.domain.notifications import NotificationAction, NotificationType
from app.presentation.dependencies import CurrentUser, SessionDep

router = APIRouter(tags=["notifications"])


class NotificationRead(BaseModel):
    id: UUID
    team_id: UUID | None
    team_name: str | None
    type: NotificationType
    title: str
    message: str
    entity_type: str | None
    entity_id: UUID | None
    action: NotificationAction | None
    read_at: datetime | None
    created_at: datetime
    available: bool


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    next_cursor: UUID | None


@router.get("/v1/me/notifications", response_model=NotificationPage)
def listing(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=50),
    cursor: UUID | None = None,
) -> dict[str, object]:
    return notifications.listing(session, user.id, limit, cursor)


@router.get("/v1/me/notifications/unread-count")
def count(session: SessionDep, user: CurrentUser) -> dict[str, int]:
    return {"count": notifications.unread_count(session, user.id)}


@router.post("/v1/me/notifications/read-all")
def read_all(session: SessionDep, user: CurrentUser) -> dict[str, int]:
    notifications.read_all(session, user.id)
    return {"count": notifications.unread_count(session, user.id)}


@router.get("/v1/me/notifications/{notification_id}", response_model=NotificationRead)
def detail(notification_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return notifications.present(
        session, user.id, [notifications.owned(session, user.id, notification_id)]
    )[0]


@router.post("/v1/me/notifications/{notification_id}/read", response_model=NotificationRead)
def read(notification_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return notifications.read(session, user.id, notification_id)


@router.post("/v1/teams/{team_id}/events/{event_id}/attendance-reminders")
def remind(team_id: UUID, event_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, int]:
    return {"count": notifications.remind_pending(session, user.id, team_id, event_id)}
