"""User-scoped inbox. Destinations are reauthorized against current memberships."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plans
from app.application.notification_delivery import emit, recipients
from app.domain.notifications import NotificationAction, NotificationType
from app.domain.policies import NotFound, Permission, Role, allows
from app.infrastructure.event_models import EventAttendance
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership
from app.infrastructure.notification_models import Notification


def owned(session: Session, user_id: UUID, notification_id: UUID) -> Notification:
    item = session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if item is None:
        raise NotFound("Notificação não encontrada.")
    return item


def present(session: Session, user_id: UUID, items: list[Notification]) -> list[dict[str, object]]:
    ids = {item.team_id for item in items if item.team_id}
    contexts = {
        team.id: (team, member)
        for team, member in session.execute(
            select(Team, TeamMembership)
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .join(Player, Player.id == TeamMembership.player_id)
            .where(Team.id.in_(ids), Player.user_id == user_id, TeamMembership.status == "active")
        )
    }
    grants: dict[UUID, set[str]] = {}
    for grant in session.scalars(
        select(MembershipPermission).where(
            MembershipPermission.membership_id.in_([member.id for _, member in contexts.values()])
        )
    ):
        grants.setdefault(grant.membership_id, set()).add(grant.permission)
    # One batched plan decision for every team that needs it, never one per notification.
    requested = {
        item.team_id
        for item in items
        if item.team_id and item.action == NotificationAction.OPEN_JOIN_REQUESTS
    }
    plans = effective_plans(session, [contexts[key][0] for key in requested if key in contexts])
    result = []
    for item in items:
        context = contexts.get(item.team_id) if item.team_id else None
        available = item.team_id is None or context is not None
        team_name = context[0].name if context else None
        if context and item.action == NotificationAction.OPEN_JOIN_REQUESTS:
            team, member = context
            available = allows(
                plans[team.id],
                is_president=member.id == team.president_membership_id,
                role=Role(member.role),
                grants=grants.get(member.id, set()),
                permission=Permission.MANAGE_MEMBERS,
            )
        # A rejected request belongs to its requester and requires no membership.
        if item.type == NotificationType.TEAM_JOIN_REJECTED:
            available = True
        result.append(
            {
                "id": item.id,
                "type": item.type,
                "read_at": item.read_at,
                "created_at": item.created_at,
                "available": available,
                "title": item.title if available else "Acesso indisponível",
                "message": item.message
                if available
                else "Você não tem mais acesso a este conteúdo do time.",
                "team_id": item.team_id if available else None,
                "team_name": team_name if available else None,
                "entity_type": item.entity_type if available else None,
                "entity_id": item.entity_id if available else None,
                "action": item.action if available else None,
            }
        )
    return result


def listing(session: Session, user_id: UUID, limit: int, cursor: UUID | None) -> dict[str, object]:
    query = select(Notification).where(Notification.user_id == user_id)
    if cursor:
        anchor = owned(session, user_id, cursor)
        query = query.where(
            tuple_(Notification.created_at, Notification.id) < (anchor.created_at, anchor.id)
        )
    rows = list(
        session.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
        )
    )
    return {
        "items": present(session, user_id, rows[:limit]),
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


def unread_count(session: Session, user_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def read(session: Session, user_id: UUID, notification_id: UUID) -> dict[str, object]:
    owned(session, user_id, notification_id)
    session.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    session.commit()
    return present(session, user_id, [owned(session, user_id, notification_id)])[0]


def read_all(session: Session, user_id: UUID) -> None:
    session.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    session.commit()


def remind_pending(session: Session, user_id: UUID, team_id: UUID, event_id: UUID) -> int:
    # Imports here keep the business event adapters independent of event commands.
    from app.application.events import authorize, find_event, require_open

    team = authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_open(event)
    answered = set(
        session.scalars(
            select(Player.user_id)
            .join(TeamMembership, TeamMembership.player_id == Player.id)
            .join(EventAttendance, EventAttendance.membership_id == TeamMembership.id)
            .where(EventAttendance.event_id == event.id, EventAttendance.team_id == team_id)
        )
    )
    count = emit(
        session,
        users=recipients(session, team) - answered,
        team_id=team_id,
        kind=NotificationType.ATTENDANCE_REMINDER,
        title="Confirme sua presença",
        message=f"Você vai à {event.title} de {event.date:%d/%m} às {event.time:%H:%M}?",
        key=f"attendance-reminder:{event.id}:manual-v1",
        entity_type="event",
        entity_id=event.id,
        action=NotificationAction.OPEN_EVENT,
    )
    session.commit()
    return count
