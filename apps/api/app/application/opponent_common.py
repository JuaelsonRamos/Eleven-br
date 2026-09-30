"""Shared pieces of the opponents center: pair locks, derived states, reliability and views."""

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.application.join_requests import public_team
from app.domain import opponents as rules
from app.domain.opponents import ChallengeStatus, ResultStatus, Side
from app.infrastructure.models import Team
from app.infrastructure.opponent_models import (
    FixtureReview,
    FixtureScore,
    TeamChallenge,
    TeamFixture,
)


def lock_teams(session: Session, *team_ids: UUID) -> dict[UUID, Team]:
    """Writes involving two teams lock both rows in id order: no deadlock between them."""
    teams = session.scalars(
        select(Team)
        .where(Team.id.in_(team_ids))
        .order_by(Team.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    return {team.id: team for team in teams}


def pair(first: UUID, second: UUID) -> ColumnElement[bool]:
    return or_(
        and_(TeamChallenge.challenger_team_id == first, TeamChallenge.challenged_team_id == second),
        and_(TeamChallenge.challenger_team_id == second, TeamChallenge.challenged_team_id == first),
    )


def open_challenge(now: datetime) -> ColumnElement[bool]:
    """Pending and still before the proposed kickoff."""
    return and_(
        TeamChallenge.status == ChallengeStatus.PENDING,
        or_(
            TeamChallenge.date > now.date(),
            and_(TeamChallenge.date == now.date(), TeamChallenge.time > now.time()),
        ),
    )


def used_credits(session: Session, team_id: UUID, month: date) -> int:
    """Free challenge credits spent: challenges actually sent (committed) in the month."""
    return (
        session.scalar(
            select(func.count())
            .select_from(TeamChallenge)
            .where(
                TeamChallenge.challenger_team_id == team_id,
                TeamChallenge.competence == month,
                TeamChallenge.charged,
            )
        )
        or 0
    )


def challenge_state(item: TeamChallenge, now: datetime) -> str:
    # Derived, never stored: a proposal whose kickoff passed can no longer be answered.
    if item.status == ChallengeStatus.PENDING and rules.started(item.date, item.time, now):
        return "EXPIRED"
    return item.status


def reliability(session: Session, team_ids: Sequence[UUID]) -> dict[UUID, dict[str, object]]:
    """Raw verifiable counts only: no score, stars, ranking, cancellations or W.O. yet."""
    ids = list(set(team_ids))
    played = dict.fromkeys(ids, 0)
    reviews = {team_id: [0, 0, 0, 0] for team_id in ids}
    for column, reviewer in (
        (TeamFixture.home_team_id, Side.AWAY),
        (TeamFixture.away_team_id, Side.HOME),
    ):
        for team_id, count in session.execute(
            select(column, func.count())
            .where(column.in_(ids), TeamFixture.result_status == ResultStatus.VALIDATED)
            .group_by(column)
        ).tuples():
            played[team_id] += count
        for team_id, *counts in session.execute(
            select(
                column,
                func.count(),
                func.count().filter(FixtureReview.attended),
                func.count().filter(FixtureReview.punctual),
                func.count().filter(FixtureReview.kept_agreement),
            )
            .join(TeamFixture, TeamFixture.id == FixtureReview.fixture_id)
            .where(column.in_(ids), FixtureReview.side == reviewer)
            .group_by(column)
        ).tuples():
            reviews[team_id] = [a + b for a, b in zip(reviews[team_id], counts, strict=True)]
    result: dict[UUID, dict[str, object]] = {}
    for team_id in ids:
        total, attended, punctual, kept = reviews[team_id]
        result[team_id] = {
            "validated_fixtures": played[team_id],
            "reviews": total,
            "attended": attended,
            "punctual": punctual,
            "kept_agreement": kept,
            "label": "Sem histórico suficiente"
            if not played[team_id]
            else "Ainda sem avaliações"
            if not total
            else None,
        }
    return result


def challenge_views(
    session: Session, items: Sequence[TeamChallenge], team_id: UUID, can_manage: bool
) -> list[dict[str, object]]:
    now = rules.local_now()
    others = {
        item.challenged_team_id if item.challenger_team_id == team_id else item.challenger_team_id
        for item in items
    }
    teams = {team.id: team for team in session.scalars(select(Team).where(Team.id.in_(others)))}
    fixtures = dict(
        session.execute(
            select(TeamFixture.challenge_id, TeamFixture.id).where(
                TeamFixture.challenge_id.in_([item.id for item in items])
            )
        )
        .tuples()
        .all()
    )
    views: list[dict[str, object]] = []
    for item in items:
        sent = item.challenger_team_id == team_id
        state = challenge_state(item, now)
        views.append(
            {
                "id": item.id,
                "direction": "sent" if sent else "received",
                "opponent": public_team(
                    teams[item.challenged_team_id if sent else item.challenger_team_id]
                ),
                "modality": item.modality,
                "date": item.date,
                "time": item.time,
                "location": item.location,
                "notes": item.notes,
                # Stored from the challenger's point of view; shown from the viewer's.
                "venue": item.venue if sent else Side(item.venue).other.value,
                "status": state,
                "created_at": item.created_at,
                "resolved_at": item.resolved_at,
                "fixture_id": fixtures.get(item.id),
                "can_respond": can_manage and not sent and state == ChallengeStatus.PENDING,
                "can_cancel": can_manage and sent and state == ChallengeStatus.PENDING,
            }
        )
    return views


def fixture_views(
    session: Session, items: Sequence[TeamFixture], team_id: UUID
) -> list[dict[str, object]]:
    ids = {item.home_team_id for item in items} | {item.away_team_id for item in items}
    teams = {team.id: team for team in session.scalars(select(Team).where(Team.id.in_(ids)))}
    views: list[dict[str, object]] = []
    for item in items:
        side = Side.HOME if item.home_team_id == team_id else Side.AWAY
        home, away = teams[item.home_team_id], teams[item.away_team_id]
        views.append(
            {
                "id": item.id,
                "side": side.value,
                "opponent": public_team(away if side is Side.HOME else home),
                "home_team": {"id": home.id, "name": home.name},
                "away_team": {"id": away.id, "name": away.name},
                "modality": item.modality,
                "date": item.date,
                "time": item.time,
                "location": item.location,
                "result_status": item.result_status,
                # Official score: present only when both sides agreed.
                "home_score": item.home_score,
                "away_score": item.away_score,
            }
        )
    return views


def score_view(item: FixtureScore | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "home_score": item.home_score,
        "away_score": item.away_score,
        "kind": item.kind,
        "created_at": item.created_at,
    }


def review_view(item: FixtureReview | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "attended": item.attended,
        "punctual": item.punctual,
        "kept_agreement": item.kept_agreement,
        "created_at": item.created_at,
    }
