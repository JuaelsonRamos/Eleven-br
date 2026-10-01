"""Explicit callups reuse event attendance; ordinary peladas retain their existing pool."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import authorize, find_event, require_open
from app.application.notification_delivery import emit
from app.domain.notifications import NotificationAction as Action
from app.domain.notifications import NotificationType as Kind
from app.domain.policies import Conflict
from app.infrastructure.event_models import Event, EventAttendance
from app.infrastructure.launch_models import TeamAudit
from app.infrastructure.models import Player, TeamMembership, User
from app.infrastructure.opponent_models import TeamFixture


class CallupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_ids: list[UUID] = Field(max_length=100)
    expected_version: int = Field(ge=1)


def require_participation_open(session: Session, event: Event) -> None:
    require_open(event)
    if event.fixture_id:
        fixture = session.get(TeamFixture, event.fixture_id)
        if fixture and (fixture.status != "SCHEDULED" or fixture.result_status != "NONE"):
            raise Conflict("Este confronto não aceita mudanças de participação.")


def called_users(session: Session, event: Event, *, pending: bool = False) -> set[UUID]:
    query = (
        select(User.id)
        .join(Player, Player.user_id == User.id)
        .join(TeamMembership, TeamMembership.player_id == Player.id)
        .join(EventAttendance, EventAttendance.membership_id == TeamMembership.id)
        .where(
            TeamMembership.team_id == event.team_id,
            TeamMembership.status == "active",
            User.status == "active",
            EventAttendance.event_id == event.id,
            EventAttendance.called_up,
        )
    )
    if pending:
        query = query.where(EventAttendance.response == "PENDENTE")
    return set(session.scalars(query))


def save(session: Session, user_id: UUID, team_id: UUID, event_id: UUID, data: CallupInput) -> None:
    authorize(session, user_id, team_id, write=True, manage=True)
    event = find_event(session, team_id, event_id)
    require_participation_open(session, event)
    if not event.fixture_id:
        raise Conflict("Convocação explícita é exclusiva dos confrontos oficiais.")
    wanted = set(data.membership_ids)
    active = set(
        session.scalars(
            select(TeamMembership.id).where(
                TeamMembership.team_id == team_id, TeamMembership.status == "active"
            )
        )
    )
    if not wanted <= active:
        raise Conflict("Selecione somente jogadores ativos deste time.")
    rows = {
        row.membership_id: row
        for row in session.scalars(
            select(EventAttendance).where(EventAttendance.event_id == event.id)
        )
    }
    current = {mid for mid, row in rows.items() if row.called_up}
    if wanted == current:
        return
    if event.callup_version != data.expected_version:
        raise Conflict("A convocação mudou. Atualize antes de salvar.")
    before = {str(mid): row.response for mid, row in rows.items() if row.called_up}
    event.callup_version += 1
    for mid in current ^ wanted:
        added = mid in wanted
        row = rows.get(mid)
        if row is None:
            row = EventAttendance(team_id=team_id, event_id=event.id, membership_id=mid)
            session.add(row)
        row.called_up = added
        if added:
            row.response = "PENDENTE"
        uid = session.scalar(
            select(User.id)
            .join(Player, Player.user_id == User.id)
            .join(TeamMembership, TeamMembership.player_id == Player.id)
            .where(TeamMembership.id == mid, User.status == "active")
        )
        emit(
            session,
            users=[uid] if uid else [],
            team_id=team_id,
            kind=Kind.FIXTURE_CALLED_UP if added else Kind.FIXTURE_CALLUP_REMOVED,
            title="Você foi convocado" if added else "Convocação retirada",
            message=f"{event.title} • {event.date:%d/%m} às {event.time:%H:%M}.",
            key=f"callup:{event.id}:{event.callup_version}:{mid}",
            entity_type="event",
            entity_id=event.id,
            action=Action.OPEN_EVENT,
        )
    session.add(
        TeamAudit(
            team_id=team_id,
            actor_id=user_id,
            entity_id=event.id,
            action="CALLUP_CHANGED",
            before=before,
            after={"members": sorted(str(mid) for mid in wanted), "version": event.callup_version},
        )
    )
    session.commit()
