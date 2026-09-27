"""Local, transactional emission. Never commits; the business operation owns the transaction."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.notifications import NotificationAction, NotificationType
from app.domain.policies import Permission, Plan, Role, allows
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership, User
from app.infrastructure.notification_models import Notification


def recipients(
    session: Session,
    team: Team,
    *,
    permission: Permission | None = None,
    exclude: UUID | None = None,
) -> set[UUID]:
    rows = session.execute(
        select(TeamMembership, User.id)
        .join(Player, Player.id == TeamMembership.player_id)
        .join(User, User.id == Player.user_id)
        .where(
            TeamMembership.team_id == team.id,
            TeamMembership.status == "active",
            User.status == "active",
        )
    ).all()
    grants: dict[UUID, set[str]] = {}
    if permission:
        for member, grant in session.execute(
            select(MembershipPermission.membership_id, MembershipPermission.permission).where(
                MembershipPermission.membership_id.in_([m.id for m, _ in rows])
            )
        ):
            grants.setdefault(member, set()).add(grant)
    return {
        uid
        for member, uid in rows
        if uid != exclude
        and (
            permission is None
            or allows(
                Plan(team.plan),
                is_president=team.president_membership_id == member.id,
                role=Role(member.role),
                grants=grants.get(member.id, set()),
                permission=permission,
            )
        )
    }


def emit(
    session: Session,
    *,
    users: Iterable[UUID],
    team_id: UUID | None,
    kind: NotificationType,
    title: str,
    message: str,
    key: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    action: NotificationAction | None = None,
) -> int:
    users = sorted(set(users))
    if not users:
        return 0
    # Unique constraint, not a read-before-insert check, protects retries/concurrency.
    created = session.scalars(
        insert(Notification)
        .values(
            [
                {
                    "user_id": uid,
                    "team_id": team_id,
                    "type": kind.value,
                    "title": title,
                    "message": message,
                    "dedup_key": key,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": action.value if action else None,
                }
                for uid in users
            ]
        )
        .on_conflict_do_nothing(constraint="uq_notifications_user_dedup")
        .returning(Notification.id)
    ).all()
    return len(created)
