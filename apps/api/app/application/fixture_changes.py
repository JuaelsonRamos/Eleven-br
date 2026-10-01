"""Bilateral fixture decisions, serialized with scores and both teams' participation."""

from datetime import UTC, date, datetime, time
from datetime import date as Date
from datetime import time as Time
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.callups import called_users
from app.application.fixtures import involving, present
from app.application.notification_delivery import emit, recipients
from app.application.opponent_common import lock_teams
from app.application.teams import require_membership
from app.domain import opponents as rules
from app.domain.notifications import NotificationAction as Action
from app.domain.notifications import NotificationType as Kind
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.event_models import Event
from app.infrastructure.models import Team
from app.infrastructure.opponent_models import FixtureProposal, TeamFixture


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    command_id: UUID
    expected_version: int = Field(ge=1)
    kind: Literal["CHANGE", "CANCEL", "WITHDRAW"]
    reason: str | None = Field(default=None, max_length=500)
    date: Date | None = None
    time: Time | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    confirm: bool = False

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.kind == "CHANGE":
            if self.date is None or self.time is None or self.location is None:
                raise ValueError("Informe data, horário e local propostos.")
            if self.time.tzinfo or self.time.second or self.time.microsecond:
                raise ValueError("Informe horário local HH:MM.")
        elif any(value is not None for value in (self.date, self.time, self.location)):
            raise ValueError("Datas e local são exclusivos da proposta de alteração.")
        if self.kind == "WITHDRAW" and not self.confirm:
            raise ValueError("Confirme explicitamente a desistência.")
        return self


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]


def values(item: TeamFixture) -> dict[str, object]:
    return {"date": item.date.isoformat(), "time": item.time.isoformat(), "location": item.location}


def editable(item: TeamFixture) -> None:
    if item.status != "SCHEDULED" or item.result_status != "NONE":
        raise Conflict("Confronto encerrado ou com placar informado não aceita esta operação.")


def notify(
    session: Session,
    item: TeamFixture,
    proposal: FixtureProposal,
    teams: dict[UUID, Team],
    *,
    effective: bool,
) -> None:
    pending = proposal.status == "PENDING"
    title = (
        ("Proposta de alteração" if proposal.kind == "CHANGE" else "Cancelamento solicitado")
        if pending
        else (
            "Desistência do confronto"
            if proposal.kind == "WITHDRAW"
            else "Proposta recusada"
            if proposal.status == "REJECTED"
            else "Confronto alterado"
            if proposal.kind == "CHANGE"
            else "Confronto cancelado por acordo"
        )
    )
    for event in session.scalars(select(Event).where(Event.fixture_id == item.id)):
        if pending and event.team_id == proposal.team_id:
            continue
        users = recipients(session, teams[event.team_id], permission=Permission.MANAGE_EVENTS)
        if effective:
            users |= called_users(session, event)
        emit(
            session,
            users=users,
            team_id=event.team_id,
            kind=Kind.FIXTURE_PROPOSAL if pending else Kind.FIXTURE_CHANGED,
            title=title,
            message=f"{event.title} • {item.date:%d/%m} às {item.time:%H:%M}.",
            key=f"fixture-proposal:{proposal.id}:{proposal.status}:{event.team_id}",
            entity_type="fixture",
            entity_id=item.id,
            action=Action.OPEN_FIXTURE,
        )


def apply(session: Session, item: TeamFixture, proposal: FixtureProposal) -> None:
    if proposal.kind == "CHANGE":
        day = date.fromisoformat(str(proposal.proposed["date"]))
        hour = time.fromisoformat(str(proposal.proposed["time"]))
        if rules.started(day, hour, rules.local_now()):
            raise Conflict("A data proposta já passou. Recuse e envie uma nova proposta.")
        item.date, item.time = day, hour
        item.location = str(proposal.proposed["location"])
    else:
        item.status = "WITHDRAWN" if proposal.kind == "WITHDRAW" else "CANCELLED"
    for event in session.scalars(select(Event).where(Event.fixture_id == item.id)):
        if proposal.kind == "CHANGE":
            event.date, event.time, event.location = item.date, item.time, item.location
        else:
            event.status = "cancelled"


def create(
    session: Session, user_id: UUID, team_id: UUID, fixture_id: UUID, data: ProposalInput
) -> dict[str, object]:
    item = involving(session, team_id, fixture_id)
    teams = lock_teams(session, item.home_team_id, item.away_team_id)
    require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_EVENTS
    )
    session.refresh(item)
    proposed = (
        {"date": data.date.isoformat(), "time": data.time.isoformat(), "location": data.location}
        if data.date and data.time
        else {}
    )
    existing = session.scalar(
        select(FixtureProposal).where(
            FixtureProposal.team_id == team_id, FixtureProposal.command_id == data.command_id
        )
    )
    if existing:
        if (existing.fixture_id, existing.kind, existing.reason, existing.proposed) != (
            item.id,
            data.kind,
            data.reason,
            proposed,
        ):
            raise Conflict("Identificador já utilizado com outros dados.")
        return present(session, item, team_id, True)
    editable(item)
    if item.version != data.expected_version:
        raise Conflict("O confronto mudou. Atualize antes de continuar.")
    pending = session.scalar(
        select(FixtureProposal).where(
            FixtureProposal.fixture_id == item.id, FixtureProposal.status == "PENDING"
        )
    )
    if pending and data.kind != "WITHDRAW":
        raise Conflict("Já existe uma proposta pendente. Aguarde a decisão do adversário.")
    if data.kind == "CHANGE":
        assert data.date and data.time
        if rules.started(data.date, data.time, rules.local_now()) or proposed == values(item):
            raise Conflict("Proponha data futura e ao menos uma alteração.")
    now = datetime.now(UTC)
    if pending:
        pending.status, pending.resolved_by, pending.resolved_at = "SUPERSEDED", user_id, now
        session.flush()
    row = FixtureProposal(
        fixture_id=item.id,
        team_id=team_id,
        created_by=user_id,
        command_id=data.command_id,
        kind=data.kind,
        reason=data.reason,
        before=values(item),
        proposed=proposed,
    )
    session.add(row)
    if data.kind == "WITHDRAW":
        row.status, row.resolved_by, row.resolved_at = "ACCEPTED", user_id, now
        apply(session, item, row)
    item.version += 1
    session.flush()
    notify(session, item, row, teams, effective=data.kind == "WITHDRAW")
    result = present(session, item, team_id, True)
    session.commit()
    return result


def decide(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    fixture_id: UUID,
    proposal_id: UUID,
    data: DecisionInput,
) -> dict[str, object]:
    item = involving(session, team_id, fixture_id)
    teams = lock_teams(session, item.home_team_id, item.away_team_id)
    require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_EVENTS
    )
    session.refresh(item)
    row = session.scalar(
        select(FixtureProposal).where(
            FixtureProposal.id == proposal_id, FixtureProposal.fixture_id == fixture_id
        )
    )
    if row is None:
        raise NotFound("Proposta não encontrada.")
    if row.team_id == team_id or row.kind == "WITHDRAW":
        raise Conflict("Somente o adversário pode responder à proposta.")
    if row.status == data.decision:
        return present(session, item, team_id, True)
    editable(item)
    if row.status != "PENDING":
        raise Conflict("Esta proposta já foi encerrada.")
    row.status, row.resolved_by, row.resolved_at = data.decision, user_id, datetime.now(UTC)
    if data.decision == "ACCEPTED":
        apply(session, item, row)
    item.version += 1
    session.flush()
    notify(session, item, row, teams, effective=data.decision == "ACCEPTED")
    result = present(session, item, team_id, True)
    session.commit()
    return result
