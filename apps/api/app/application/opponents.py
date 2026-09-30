"""Opponents center: preferences, compatible search and public profiles.

Searching and opening profiles never use credit; the Free credit is spent only when a
new challenge is sent (see `challenges.create`).
"""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, SQLColumnExpression, and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plan
from app.application.events import authorize
from app.application.join_requests import public_team
from app.application.municipalities import official
from app.application.opponent_common import (
    challenge_views,
    fixture_views,
    open_challenge,
    pair,
    reliability,
    review_view,
    used_credits,
)
from app.application.team_audit import record
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain import opponents as rules
from app.domain.opponents import Side
from app.domain.policies import ENTITLEMENTS, Conflict, NotFound, Permission, Plan
from app.domain.team_identity import STATES, Modality
from app.infrastructure.models import Team
from app.infrastructure.opponent_models import FixtureReview, TeamChallenge, TeamFixture

# Free-text cities are compared without accents, case or repeated spaces; data is unchanged.
ACCENTS = "ÁÀÂÃÄÅáàâãäåÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÕÖóòôõöÚÙÛÜúùûüÇçÑñÝýÿ"
PLAIN = "AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCcNnYyy"
TIERS = ("city", "state", "other")
Category = Literal["male", "female", "mixed", "all"]


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepts_challenges: bool = Field(strict=True)


def city_key(value: SQLColumnExpression[str]) -> ColumnElement[str]:
    collapsed = func.regexp_replace(func.trim(value), r"\s+", " ", "g")
    return func.lower(func.translate(collapsed, ACCENTS, PLAIN))


def located_in(code: int | None, name: str) -> ColumnElement[bool]:
    """Same municipality: IBGE code when the team is confirmed. Transitional fallback:
    unconfirmed legacy teams (either side) compare the typed city text. Removing the
    fallback later means comparing codes only."""
    typed = city_key(Team.city) == city_key(literal(name))
    if code is None:
        return typed
    return or_(Team.municipality_code == code, and_(Team.municipality_code.is_(None), typed))


def credits(session: Session, team: Team, plan: Plan) -> dict[str, object]:
    """Free: one challenge sent per São Paulo month; PRO: unlimited (limit None)."""
    month = rules.competence(rules.local_now())
    limit = ENTITLEMENTS[plan].opponent_challenges
    used = used_credits(session, team.id, month)
    return {
        "limit": limit,
        "used": used,
        "remaining": None if limit is None else max(0, limit - used),
        "competence": month,
    }


def central(session: Session, user_id: UUID, team_id: UUID) -> dict[str, object]:
    team = require_membership(session, user_id=user_id, team_id=team_id)
    plan = effective_plan(session, team)
    can_manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS, plan)[1]
    pending = session.scalar(
        select(func.count())
        .select_from(TeamChallenge)
        .where(TeamChallenge.challenged_team_id == team.id, open_challenge(rules.local_now()))
    )
    return {
        "team": public_team(team),
        "accepts_challenges": team.accepts_challenges,
        "can_manage": can_manage,
        "plan": plan.value,
        "credits": credits(session, team, plan),
        "pending_received": pending or 0,
    }


def update_settings(
    session: Session, user_id: UUID, team_id: UUID, data: SettingsInput
) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True, manage=True)
    if team.accepts_challenges != data.accepts_challenges:
        # Existing challenges and fixtures stay; only discovery and new challenges change.
        record(
            session,
            team_id,
            user_id,
            team_id,
            "OPPONENT_SETTINGS_UPDATED",
            {"accepts_challenges": team.accepts_challenges},
            {"accepts_challenges": data.accepts_challenges},
        )
        team.accepts_challenges = data.accepts_challenges
    session.commit()
    return central(session, user_id, team_id)


def search(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    *,
    modality: Modality,
    category: Category,
    state: str | None,
    municipality: int | None,
    offset: int,
) -> dict[str, object]:
    """Compatibility first (modality, then category), then city → UF → other UFs."""
    team = authorize(session, user_id, team_id, manage=True)
    if modality not in team.modalities:
        raise Conflict("Escolha uma modalidade do seu time.")
    if state is not None and state not in STATES:
        raise Conflict("Informe uma UF válida.")
    if municipality is not None and state is None:
        raise Conflict("Informe a UF da cidade.")
    same_state = Team.state == team.state
    tier = case(
        (and_(same_state, located_in(team.municipality_code, team.city)), 0),
        (same_state, 1),
        else_=2,
    )
    conditions = [
        Team.id != team.id,
        Team.status == "active",
        Team.accepts_challenges.is_(True),
        Team.modalities.contains([modality]),
    ]
    # Unknown category is never treated as compatible: it comes after, identified.
    unknown = case((Team.category.is_(None), 1), else_=0)
    if category != rules.ALL_CATEGORIES:
        conditions.append(or_(Team.category == category, Team.category.is_(None)))
    if state is not None:
        conditions.append(Team.state == state)
        if municipality is not None:
            place = official(session, state, municipality)
            conditions.append(located_in(place.code, place.name))
    ranked = [tier] if category == rules.ALL_CATEGORIES else [unknown, tier]
    rows = session.execute(
        select(Team, tier)
        .where(*conditions)
        .order_by(*ranked, func.lower(Team.name), Team.id)
        .offset(offset)
        .limit(rules.PAGE_SIZE + 1)
    ).all()
    page = [(found, TIERS[level]) for found, level in rows[: rules.PAGE_SIZE]]
    ids = [found.id for found, _ in page]
    indicators = reliability(session, ids)
    pending = {
        row.challenger_team_id if row.challenged_team_id == team.id else row.challenged_team_id
        for row in session.scalars(
            select(TeamChallenge).where(
                open_challenge(rules.local_now()),
                or_(
                    and_(
                        TeamChallenge.challenger_team_id == team.id,
                        TeamChallenge.challenged_team_id.in_(ids),
                    ),
                    and_(
                        TeamChallenge.challenged_team_id == team.id,
                        TeamChallenge.challenger_team_id.in_(ids),
                    ),
                ),
            )
        )
    }
    return {
        "filters": {
            "modality": modality,
            "category": category,
            "state": state,
            "municipality": municipality,
        },
        "location": {"city": team.city, "state": team.state},
        "items": [
            {
                "team": public_team(found),
                "tier": level,
                "category_known": found.category is not None,
                "reliability": indicators[found.id],
                "pending_challenge": found.id in pending,
            }
            for found, level in page
        ],
        "has_more": len(rows) > rules.PAGE_SIZE,
    }


def profile(session: Session, user_id: UUID, team_id: UUID, opponent_id: UUID) -> dict[str, object]:
    """Public identity, reliability and shared history; never uses credit."""
    team = require_membership(session, user_id=user_id, team_id=team_id)
    other = session.get(Team, opponent_id)
    if other is None or other.id == team.id or other.status != "active":
        raise NotFound("Adversário não encontrado.")
    plan = effective_plan(session, team)
    can_manage = membership_context(session, team, user_id, Permission.MANAGE_EVENTS, plan)[1]
    challenges = session.scalars(
        select(TeamChallenge)
        .where(pair(team.id, other.id))
        .order_by(TeamChallenge.created_at.desc(), TeamChallenge.id.desc())
        .limit(20)
    ).all()
    fixtures = session.scalars(
        select(TeamFixture)
        .where(
            or_(
                and_(TeamFixture.home_team_id == team.id, TeamFixture.away_team_id == other.id),
                and_(TeamFixture.home_team_id == other.id, TeamFixture.away_team_id == team.id),
            )
        )
        .order_by(TeamFixture.date.desc(), TeamFixture.time.desc(), TeamFixture.id)
        .limit(20)
    ).all()
    reviews = {
        (review.fixture_id, review.side): review
        for review in session.scalars(
            select(FixtureReview).where(FixtureReview.fixture_id.in_([f.id for f in fixtures]))
        )
    }
    fixture_items = fixture_views(session, fixtures, team.id)
    for fixture, view in zip(fixtures, fixture_items, strict=True):
        side = Side.HOME if fixture.home_team_id == team.id else Side.AWAY
        view["reviews"] = {
            "mine": review_view(reviews.get((fixture.id, side.value))),
            "theirs": review_view(reviews.get((fixture.id, side.other.value))),
        }
    compatible = [modality for modality in team.modalities if modality in other.modalities]
    balance = credits(session, team, plan)
    return {
        "team": public_team(other),
        "accepts_challenges": other.accepts_challenges,
        "reliability": reliability(session, [other.id])[other.id],
        "compatible_modalities": compatible,
        "pending_challenge": session.scalar(
            select(TeamChallenge.id)
            .where(pair(team.id, other.id), open_challenge(rules.local_now()))
            .limit(1)
        )
        is not None,
        "credits": balance,
        "can_challenge": can_manage
        and team.status == "active"
        and other.accepts_challenges
        and bool(compatible)
        and balance["remaining"] != 0,
        "history": {
            "challenges": challenge_views(session, challenges, team.id, can_manage),
            "fixtures": fixture_items,
        },
        "command_id": uuid4(),
    }
