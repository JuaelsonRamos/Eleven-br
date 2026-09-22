"""Authorized team registration and basic profile operations."""

from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.teams import create_team, require_membership
from app.domain.policies import Conflict, Permission, Plan, Role, allows
from app.domain.team_identity import generate_code, normalized
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership


def register_team(
    session: Session, *, user_id: UUID, name: str, city: str, state: str, modalities: list[str]
) -> Team:
    player = session.scalar(select(Player).where(Player.user_id == user_id))
    if player is None:
        raise Conflict("Complete seu perfil antes de criar um time")
    # The unique constraint arbitrates collisions, including simultaneous registrations.
    for _ in range(5):
        try:
            with session.begin_nested():
                team = create_team(
                    session,
                    president=player,
                    name=name,
                    city=city,
                    state=state,
                    modalities=modalities,
                    code=generate_code(),
                    plan=Plan.FREE,
                )
            session.commit()
            return team
        except IntegrityError as error:
            if (
                getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                != "uq_teams_code"
            ):
                raise
    raise Conflict("Não foi possível gerar o código do time. Tente novamente")


def edit_team(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    name: str,
    city: str,
    state: str,
    modalities: list[str],
) -> Team:
    team = require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_TEAM
    )
    team.name, team.city, team.state, team.modalities = name, city, state, modalities
    session.commit()
    return team


def membership_context(
    session: Session,
    team: Team,
    user_id: UUID,
    permission: Permission = Permission.MANAGE_TEAM,
) -> tuple[str, bool]:
    membership = session.scalars(
        select(TeamMembership)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(
            TeamMembership.team_id == team.id,
            Player.user_id == user_id,
            TeamMembership.status == "active",
        )
    ).one()
    president = membership.id == team.president_membership_id
    grants = set(
        session.scalars(
            select(MembershipPermission.permission).where(
                MembershipPermission.membership_id == membership.id
            )
        )
    )
    return (
        "president" if president else membership.role,
        allows(
            Plan(team.plan),
            is_president=president,
            role=Role(membership.role),
            grants=grants,
            permission=permission,
        ),
    )


def similar_teams(
    session: Session, *, name: str, city: str, state: str, modalities: list[str]
) -> list[Team]:
    """Advisory public identity search; never return membership or administration data.

    Compare names ignoring accents/case in the same city, UF and modality.
    Streaming avoids loading an entire region into memory; return at most five matches.
    """
    result: list[Team] = []
    target = normalized(name)
    candidates = session.scalars(
        select(Team)
        .where(
            Team.state == state,
            Team.modalities.overlap(modalities),
            Team.status == "active",
        )
        .order_by(Team.name, Team.id)
        .execution_options(yield_per=100)
    )
    for team in candidates:
        if normalized(team.city) != normalized(city):
            continue
        candidate = normalized(team.name)
        if (
            target in candidate
            or candidate in target
            or SequenceMatcher(None, target, candidate).ratio() >= 0.8
        ):
            result.append(team)
            if len(result) == 5:
                break
    return result
