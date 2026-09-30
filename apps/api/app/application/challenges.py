"""Challenges between registered teams; acceptance creates the single shared fixture.

Every write locks both team rows (same order), then authorizes the acting team with
MANAGE_EVENTS. The Free monthly credit is the challenge row itself (`charged`): nothing
is spent when sending fails. Counterproposals and fixture cancellation are not defined.
"""

from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plan
from app.application.notification_events import challenge_notice, event_notice
from app.application.opponent_common import (
    challenge_views,
    lock_teams,
    open_challenge,
    pair,
    used_credits,
)
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain import opponents as rules
from app.domain.notifications import NotificationType as Kind
from app.domain.opponents import ChallengeStatus, Venue
from app.domain.policies import ENTITLEMENTS, Conflict, Forbidden, NotFound, Permission
from app.domain.team_identity import Modality
from app.infrastructure.event_models import Event
from app.infrastructure.models import Team
from app.infrastructure.opponent_models import TeamChallenge, TeamFixture


class ChallengeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    command_id: UUID
    opponent_team_id: UUID
    modality: Modality
    date: Date
    time: Time
    location: str = Field(min_length=1, max_length=200)
    venue: Venue
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("time")
    @classmethod
    def local_time(cls, value: Time) -> Time:
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError("Informe o horário local em HH:MM, sem fuso ou segundos")
        return value

    @field_validator("notes")
    @classmethod
    def optional_notes(cls, value: str | None) -> str | None:
        return value or None


def acting(session: Session, user_id: UUID, team_id: UUID, *others: UUID) -> dict[UUID, Team]:
    teams = lock_teams(session, team_id, *others)
    require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_EVENTS
    )
    return teams


def involving(session: Session, team_id: UUID, challenge_id: UUID) -> TeamChallenge:
    item = session.scalar(
        select(TeamChallenge).where(
            TeamChallenge.id == challenge_id,
            or_(
                TeamChallenge.challenger_team_id == team_id,
                TeamChallenge.challenged_team_id == team_id,
            ),
        )
    )
    if item is None:
        raise NotFound("Desafio não encontrado.")
    return item


def view(session: Session, item: TeamChallenge, team_id: UUID) -> dict[str, object]:
    return challenge_views(session, [item], team_id, can_manage=True)[0]


def create(
    session: Session, user_id: UUID, team_id: UUID, data: ChallengeInput
) -> dict[str, object]:
    teams = acting(session, user_id, team_id, data.opponent_team_id)
    previous = session.scalar(
        select(TeamChallenge).where(
            TeamChallenge.challenger_team_id == team_id,
            TeamChallenge.command_id == data.command_id,
        )
    )
    if previous:
        # A retry returns the same challenge; reusing the command for other data is refused.
        sent = (
            previous.challenged_team_id,
            previous.modality,
            previous.date,
            previous.time,
            previous.location,
            previous.venue,
            previous.notes,
        )
        wanted = (
            data.opponent_team_id,
            data.modality,
            data.date,
            data.time,
            data.location,
            data.venue,
            data.notes,
        )
        if sent != wanted:
            raise Conflict("Este comando já foi usado em outro desafio.")
        return view(session, previous, team_id)
    if data.opponent_team_id == team_id:
        raise Conflict("Seu time não pode desafiar a si mesmo.")
    team, other = teams[team_id], teams.get(data.opponent_team_id)
    if other is None or other.status != "active":
        raise NotFound("Adversário não encontrado.")
    if team.status != "active":
        raise Conflict("Somente times ativos podem desafiar.")
    if not other.accepts_challenges:
        raise Conflict("Este time não está aceitando desafios no momento.")
    if data.modality not in team.modalities or data.modality not in other.modalities:
        raise Conflict("Escolha uma modalidade praticada pelos dois times.")
    now = rules.local_now()
    if rules.started(data.date, data.time, now):
        raise Conflict("Escolha uma data e um horário futuros.")
    equivalent = select(TeamChallenge.id).where(
        pair(team_id, other.id),
        open_challenge(now),
        TeamChallenge.modality == data.modality,
        TeamChallenge.date == data.date,
        TeamChallenge.time == data.time,
    )
    if session.scalar(equivalent):
        raise Conflict("Já existe um desafio pendente com esta proposta entre os times.")
    # Checked last: an invalid request never spends the Free credit.
    month = rules.competence(now)
    limit = ENTITLEMENTS[effective_plan(session, team)].opponent_challenges
    if limit is not None and used_credits(session, team_id, month) >= limit:
        raise Forbidden(
            "Seu time já usou o desafio gratuito deste mês. "
            "No ELEVEN BR PRO os desafios são ilimitados."
        )
    item = TeamChallenge(
        challenger_team_id=team_id,
        challenged_team_id=other.id,
        competence=month,
        charged=limit is not None,
        modality=data.modality,
        date=data.date,
        time=data.time,
        location=data.location,
        venue=data.venue,
        notes=data.notes,
        command_id=data.command_id,
        created_by=user_id,
    )
    session.add(item)
    try:
        session.flush()
    except IntegrityError:
        # Unique indexes back the locks: credit, equivalent proposal or command.
        session.rollback()
        raise Conflict("O desafio não foi enviado: atualize a tela e confira.") from None
    challenge_notice(session, item, Kind.CHALLENGE_RECEIVED, to=other, sender=team, author=user_id)
    result = view(session, item, team_id)
    session.commit()
    return result


def open_fixture(
    session: Session, item: TeamChallenge, teams: dict[UUID, Team], user_id: UUID
) -> TeamFixture:
    """The shared fixture plus one agenda game per team, linked to it (never two fixtures)."""
    challenger, challenged = teams[item.challenger_team_id], teams[item.challenged_team_id]
    home, away = (challenger, challenged) if item.venue == Venue.HOME else (challenged, challenger)
    fixture = TeamFixture(
        challenge_id=item.id,
        home_team_id=home.id,
        away_team_id=away.id,
        modality=item.modality,
        date=item.date,
        time=item.time,
        location=item.location,
        notes=item.notes,
    )
    session.add(fixture)
    session.flush()
    title = f"{home.name} x {away.name}"
    title = title if len(title) <= 100 else title[:99] + "…"
    for team, other in ((challenger, challenged), (challenged, challenger)):
        event = Event(
            team_id=team.id,
            fixture_id=fixture.id,
            kind="JOGO",
            modality=item.modality,
            title=title,
            date=item.date,
            time=item.time,
            location=item.location,
            notes=item.notes,
            opponent=other.name,
        )
        session.add(event)
        session.flush()
        event_notice(session, team, event, user_id, Kind.EVENT_CREATED)
    return fixture


def respond(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    challenge_id: UUID,
    decision: Literal["accept", "reject", "cancel"],
) -> dict[str, object]:
    item = involving(session, team_id, challenge_id)
    teams = acting(session, user_id, team_id, item.challenger_team_id, item.challenged_team_id)
    session.refresh(item)
    sender = decision == "cancel"
    if (item.challenger_team_id if sender else item.challenged_team_id) != team_id:
        raise Forbidden(
            "Somente o time que enviou pode cancelar o desafio."
            if sender
            else "Somente o time desafiado pode aceitar ou recusar."
        )
    final = {
        "accept": ChallengeStatus.ACCEPTED,
        "reject": ChallengeStatus.REJECTED,
        "cancel": ChallengeStatus.CANCELLED,
    }[decision]
    if item.status == final:
        return view(session, item, team_id)  # Repeated request: no second fixture or notice.
    if item.status != ChallengeStatus.PENDING:
        raise Conflict("Este desafio não está mais pendente.")
    if rules.started(item.date, item.time, rules.local_now()):
        raise Conflict("Este desafio expirou: o horário proposto já passou.")
    if decision == "accept":
        if any(team.status != "active" for team in teams.values()):
            raise Conflict("Os dois times precisam estar ativos.")
        open_fixture(session, item, teams, user_id)
    item.status, item.resolved_by, item.resolved_at = final, user_id, datetime.now(UTC)
    receiver = item.challenged_team_id if sender else item.challenger_team_id
    kind = {
        "accept": Kind.CHALLENGE_ACCEPTED,
        "reject": Kind.CHALLENGE_REJECTED,
        "cancel": Kind.CHALLENGE_CANCELLED,
    }[decision]
    challenge_notice(session, item, kind, to=teams[receiver], sender=teams[team_id], author=user_id)
    session.flush()
    result = view(session, item, team_id)
    session.commit()
    return result


def listing(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    direction: Literal["received", "sent"],
    offset: int,
) -> dict[str, object]:
    team = require_membership(session, user_id=user_id, team_id=team_id)
    can_manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)[1]
    column = (
        TeamChallenge.challenged_team_id
        if direction == "received"
        else TeamChallenge.challenger_team_id
    )
    items = session.scalars(
        select(TeamChallenge)
        .where(column == team_id)
        .order_by(TeamChallenge.created_at.desc(), TeamChallenge.id.desc())
        .offset(offset)
        .limit(rules.PAGE_SIZE + 1)
    ).all()
    return {
        "items": challenge_views(session, items[: rules.PAGE_SIZE], team_id, can_manage),
        "has_more": len(items) > rules.PAGE_SIZE,
        "can_manage": can_manage,
    }
