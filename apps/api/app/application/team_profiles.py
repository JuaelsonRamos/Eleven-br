"""Authorized team registration and basic profile operations."""

from datetime import UTC, datetime
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plan
from app.application.municipalities import official
from app.application.teams import create_team, require_membership
from app.domain.policies import Conflict, Permission, Plan, Role, allows
from app.domain.team_identity import generate_code, normalized
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership, User


def register_team(
    session: Session,
    *,
    user_id: UUID,
    name: str,
    state: str,
    municipality_code: int,
    modalities: list[str],
    category: str | None = None,
) -> Team:
    # Only an official IBGE municipality of the chosen UF; never free text.
    place = official(session, state, municipality_code)
    # Serialize creation with replacement of an empty signup Player during approval.
    session.execute(select(User).where(User.id == user_id).with_for_update())
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
                    city=place.name,
                    state=place.state,
                    modalities=modalities,
                    code=generate_code(),
                    plan=Plan.FREE,
                )
                team.category = category
                # Chosen from the official list at creation: born confirmed, no second step.
                team.municipality_code = place.code
                team.location_confirmed_at = datetime.now(UTC)
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
    modalities: list[str],
    category: str | None = None,
    city: str | None = None,
    state: str | None = None,
    municipality_code: int | None = None,
) -> Team:
    team = require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_TEAM
    )
    # Location changes only through the President's confirmation (team_locations); older
    # clients may resend the current location unchanged.
    sent = {"city": city, "state": state, "municipality_code": municipality_code}
    if any(value is not None and value != getattr(team, key) for key, value in sent.items()):
        raise Conflict("A localização do time é confirmada e alterada somente pelo Presidente.")
    team.name, team.modalities = name, modalities
    if category is not None:
        team.category = category
    session.commit()
    return team


def membership_context(
    session: Session,
    team: Team,
    user_id: UUID,
    permission: Permission = Permission.MANAGE_TEAM,
    plan: Plan | None = None,
) -> tuple[str, bool]:
    """Pass `plan` when the caller already computed it to avoid repeating billing reads."""
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
            plan or effective_plan(session, team),
            is_president=president,
            role=Role(membership.role),
            grants=grants,
            permission=permission,
        ),
    )


def similar_teams(
    session: Session,
    *,
    name: str,
    state: str,
    municipality_code: int,
    modalities: list[str],
    category: str | None = None,
) -> list[Team]:
    """Advisory public identity search; never return membership or administration data.

    Compare names ignoring accents/case in the same municipality, UF and modality
    (unconfirmed legacy teams: typed city).
    Streaming avoids loading an entire region into memory; return at most five matches.
    """
    place = official(session, state, municipality_code)
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
        if team.municipality_code is not None:
            if team.municipality_code != place.code:
                continue
        elif normalized(team.city) != normalized(place.name):
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
