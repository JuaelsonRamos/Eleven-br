"""Official fixture results validated by both teams, and reliability reviews.

Only equal scores from both sides become official. A pending or disputed result is never
official, silence never confirms and no rule resolves a dispute automatically.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.events import authorize
from app.application.notification_events import fixture_notice
from app.application.opponent_common import (
    fixture_views,
    lock_teams,
    review_view,
    score_view,
)
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain import opponents as rules
from app.domain.notifications import NotificationType as Kind
from app.domain.opponents import ResultStatus, Side
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.event_models import Event
from app.infrastructure.opponent_models import (
    FixtureProposal,
    FixtureReview,
    FixtureScore,
    TeamFixture,
)


class ScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_score: int = Field(ge=0, le=999, strict=True)
    away_score: int = Field(ge=0, le=999, strict=True)


class ReviewInput(BaseModel):
    """Yes/no reliability answers only; no free-text comments in this phase."""

    model_config = ConfigDict(extra="forbid")
    attended: bool = Field(strict=True)
    punctual: bool = Field(strict=True)  # Kept the agreed time.
    kept_agreement: bool = Field(strict=True)


def involving(session: Session, team_id: UUID, fixture_id: UUID) -> TeamFixture:
    item = session.scalar(
        select(TeamFixture).where(
            TeamFixture.id == fixture_id,
            or_(TeamFixture.home_team_id == team_id, TeamFixture.away_team_id == team_id),
        )
    )
    if item is None:
        raise NotFound("Confronto não encontrado.")
    return item


def side_of(fixture: TeamFixture, team_id: UUID) -> Side:
    return Side.HOME if fixture.home_team_id == team_id else Side.AWAY


def present(
    session: Session, fixture: TeamFixture, team_id: UUID, can_manage: bool
) -> dict[str, object]:
    side = side_of(fixture, team_id)
    scores = {
        row.side: row
        for row in session.scalars(
            select(FixtureScore).where(FixtureScore.fixture_id == fixture.id)
        )
    }
    reviews = {
        row.side: row
        for row in session.scalars(
            select(FixtureReview).where(FixtureReview.fixture_id == fixture.id)
        )
    }
    mine, theirs = scores.get(side), scores.get(side.other)
    status = fixture.result_status
    started = rules.started(fixture.date, fixture.time, rules.local_now())
    return {
        **fixture_views(session, [fixture], team_id)[0],
        "version": fixture.version,
        "command_id": uuid4(),
        "can_change": can_manage and fixture.status == "SCHEDULED" and status == ResultStatus.NONE,
        "proposals": [
            {
                "id": p.id,
                "team_id": p.team_id,
                "kind": p.kind,
                "status": p.status,
                "reason": p.reason,
                "before": p.before,
                "proposed": p.proposed,
                "created_at": p.created_at,
                "resolved_at": p.resolved_at,
                "created_by": p.created_by,
                "resolved_by": p.resolved_by,
            }
            for p in session.scalars(
                select(FixtureProposal)
                .where(FixtureProposal.fixture_id == fixture.id)
                .order_by(FixtureProposal.created_at.desc(), FixtureProposal.id)
            )
        ],
        "notes": fixture.notes,
        "challenge_id": fixture.challenge_id,
        "event_id": session.scalar(
            select(Event.id).where(Event.team_id == team_id, Event.fixture_id == fixture.id)
        ),
        "started": started,
        "scores": {"mine": score_view(mine), "theirs": score_view(theirs)},
        "reviews": {
            "mine": review_view(reviews.get(side)),
            "theirs": review_view(reviews.get(side.other)),
        },
        "can_manage": can_manage,
        "can_report": can_manage
        and fixture.status == "SCHEDULED"
        and started
        and mine is None
        and status in (ResultStatus.NONE, ResultStatus.PENDING),
        "can_confirm": can_manage
        and fixture.status == "SCHEDULED"
        and mine is None
        and theirs is not None
        and status == ResultStatus.PENDING,
        "can_review": can_manage and status == ResultStatus.VALIDATED and side not in reviews,
    }


def listing(session: Session, user_id: UUID, team_id: UUID, offset: int) -> dict[str, object]:
    require_membership(session, user_id=user_id, team_id=team_id)
    items = session.scalars(
        select(TeamFixture)
        .where(or_(TeamFixture.home_team_id == team_id, TeamFixture.away_team_id == team_id))
        .order_by(TeamFixture.date.desc(), TeamFixture.time.desc(), TeamFixture.id)
        .offset(offset)
        .limit(rules.PAGE_SIZE + 1)
    ).all()
    return {
        "items": fixture_views(session, items[: rules.PAGE_SIZE], team_id),
        "has_more": len(items) > rules.PAGE_SIZE,
    }


def detail(session: Session, user_id: UUID, team_id: UUID, fixture_id: UUID) -> dict[str, object]:
    team = require_membership(session, user_id=user_id, team_id=team_id)
    fixture = involving(session, team_id, fixture_id)
    can_manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS)[1]
    return present(session, fixture, team_id, can_manage)


def submit(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    fixture_id: UUID,
    data: ScoreInput,
    *,
    confirmation: bool,
) -> dict[str, object]:
    """Report (or contest with another score) or confirm the other side's report."""
    fixture = involving(session, team_id, fixture_id)
    teams = lock_teams(session, fixture.home_team_id, fixture.away_team_id)
    require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_EVENTS
    )
    session.refresh(fixture)
    if fixture.status != "SCHEDULED":
        raise Conflict("Confronto cancelado ou com desistência não aceita placar.")
    if session.scalar(
        select(FixtureProposal.id).where(
            FixtureProposal.fixture_id == fixture.id, FixtureProposal.status == "PENDING"
        )
    ):
        raise Conflict("Resolva a proposta pendente antes de informar o placar.")
    side = side_of(fixture, team_id)
    scores = {
        row.side: row
        for row in session.scalars(
            select(FixtureScore).where(FixtureScore.fixture_id == fixture.id)
        )
    }
    mine, theirs = scores.get(side), scores.get(side.other)
    wanted = (data.home_score, data.away_score)
    if mine:
        if (mine.home_score, mine.away_score) == wanted:
            return present(session, fixture, team_id, True)  # Retry: no duplicated effects.
        if fixture.result_status == ResultStatus.VALIDATED:
            raise Conflict("Resultado validado não pode ser alterado.")
        raise Conflict("Seu time já informou o placar deste confronto.")
    if confirmation:
        if theirs is None or fixture.result_status != ResultStatus.PENDING:
            raise Conflict("Não há placar aguardando a confirmação do seu time.")
        if (theirs.home_score, theirs.away_score) != wanted:
            raise Conflict("O placar informado mudou. Atualize antes de confirmar.")
    elif not rules.started(fixture.date, fixture.time, rules.local_now()):
        raise Conflict("O placar só pode ser informado a partir do horário do jogo.")
    session.add(
        FixtureScore(
            fixture_id=fixture.id,
            side=side,
            kind="CONFIRMED" if confirmation else "REPORTED",
            home_score=data.home_score,
            away_score=data.away_score,
            created_by=user_id,
        )
    )
    other = fixture.away_team_id if side is Side.HOME else fixture.home_team_id
    if theirs is None:
        fixture.result_status = ResultStatus.PENDING
        fixture_notice(
            session,
            fixture,
            Kind.FIXTURE_SCORE_REPORTED,
            to=other,
            teams=teams,
            author=user_id,
            score=wanted,
        )
    elif (theirs.home_score, theirs.away_score) == wanted:
        fixture.result_status = ResultStatus.VALIDATED
        fixture.home_score, fixture.away_score = wanted
        fixture.validated_at = datetime.now(UTC)
        fixture_notice(
            session,
            fixture,
            Kind.FIXTURE_SCORE_CONFIRMED,
            to=other,
            teams=teams,
            author=user_id,
            score=wanted,
        )
        for recipient in (fixture.home_team_id, fixture.away_team_id):
            fixture_notice(
                session,
                fixture,
                Kind.FIXTURE_REVIEW_AVAILABLE,
                to=recipient,
                teams=teams,
                author=user_id,
            )
    else:
        # Different scores: recorded as a dispute, never official, never auto-resolved.
        fixture.result_status = ResultStatus.DISPUTED
        fixture_notice(
            session,
            fixture,
            Kind.FIXTURE_SCORE_DISPUTED,
            to=other,
            teams=teams,
            author=user_id,
            score=wanted,
        )
    session.flush()
    result = present(session, fixture, team_id, True)
    session.commit()
    return result


def review(
    session: Session, user_id: UUID, team_id: UUID, fixture_id: UUID, data: ReviewInput
) -> dict[str, object]:
    authorize(session, user_id, team_id, write=True, manage=True)
    fixture = involving(session, team_id, fixture_id)
    if fixture.result_status != ResultStatus.VALIDATED:
        raise Conflict("A avaliação é liberada depois do resultado validado pelos dois times.")
    side = side_of(fixture, team_id)
    answers = (data.attended, data.punctual, data.kept_agreement)
    existing = session.scalar(
        select(FixtureReview).where(
            FixtureReview.fixture_id == fixture.id, FixtureReview.side == side
        )
    )
    if existing:
        if (existing.attended, existing.punctual, existing.kept_agreement) == answers:
            return present(session, fixture, team_id, True)
        raise Conflict("Seu time já avaliou este adversário neste confronto.")
    # The reviewed team is always the other side: a team never reviews itself.
    session.add(
        FixtureReview(
            fixture_id=fixture.id,
            side=side,
            attended=data.attended,
            punctual=data.punctual,
            kept_agreement=data.kept_agreement,
            created_by=user_id,
        )
    )
    session.flush()
    result = present(session, fixture, team_id, True)
    session.commit()
    return result
