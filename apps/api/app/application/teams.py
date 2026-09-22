from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.policies import (
    ENTITLEMENTS,
    Conflict,
    Forbidden,
    NotFound,
    Permission,
    Plan,
    Role,
    allows,
)
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership


def create_team(
    session: Session,
    *,
    president: Player,
    name: str,
    code: str,
    city: str,
    state: str,
    modalities: list[str],
    plan: Plan = Plan.FREE,
) -> Team:
    """Atomic foundation primitive, not a complete team registration workflow.

    The caller owns the transaction. The deferred FK is checked at commit.
    """
    team_id, membership_id = uuid4(), uuid4()
    team = Team(
        id=team_id,
        name=name,
        code=code,
        city=city,
        state=state,
        modalities=modalities,
        plan=plan.value,
        president_membership_id=membership_id,
    )
    session.add(team)
    session.flush()
    session.add(
        TeamMembership(
            id=membership_id,
            team_id=team_id,
            player_id=president.id,
            role=Role.MEMBER.value,
        )
    )
    session.flush()
    return team


def add_member(
    session: Session,
    *,
    team_id: UUID,
    player_id: UUID,
    role: Role = Role.MEMBER,
    permissions: frozenset[Permission] = frozenset(),
) -> TeamMembership:
    """Internal primitive. Lock the team before counting to serialize competing joins.

    Future public write use cases must authorize the actor before calling this primitive.
    """
    team = session.scalar(select(Team).where(Team.id == team_id).with_for_update())
    if team is None:
        raise NotFound("Time não encontrado")
    ensure_active_slot(session, team)
    if permissions and role != Role.ADMIN:
        raise Conflict("Permissões administrativas exigem vínculo administrativo")
    if role == Role.ADMIN:
        ensure_admin_slot(session, team)
    membership = TeamMembership(team_id=team_id, player_id=player_id, role=role.value)
    session.add(membership)
    session.flush()
    session.add_all(
        [
            MembershipPermission(membership_id=membership.id, permission=permission.value)
            for permission in permissions
        ]
    )
    session.flush()
    return membership


def active_count(session: Session, team_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.status == "active",
            )
        )
        or 0
    )


def ensure_active_slot(session: Session, team: Team) -> None:
    """Caller must hold the team row lock before checking capacity and writing."""
    limit = ENTITLEMENTS[Plan(team.plan)].active_players
    if active_count(session, team.id) >= limit:
        raise Conflict(
            f"Seu time atingiu o limite de {limit} jogadores ativos do plano {team.plan.title()}. "
            "Inative um jogador para liberar uma vaga."
        )


def ensure_admin_slot(session: Session, team: Team) -> None:
    """Keep existing administrator limits when reactivating a preserved admin role."""
    admins = (
        session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team.id,
                TeamMembership.status == "active",
                TeamMembership.role == Role.ADMIN.value,
                TeamMembership.id != team.president_membership_id,
            )
        )
        or 0
    )
    if admins >= ENTITLEMENTS[Plan(team.plan)].administrators:
        raise Conflict("Limite de administradores do plano atingido")


def visible_teams(session: Session, user_id: UUID) -> list[Team]:
    return list(
        session.scalars(
            select(Team)
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .join(Player, Player.id == TeamMembership.player_id)
            .where(Player.user_id == user_id, TeamMembership.status == "active")
            .order_by(Team.name, Team.id)
        )
    )


def require_membership(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    permission: Permission | None = None,
) -> Team:
    row = session.execute(
        select(Team, TeamMembership)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(Team.id == team_id, Player.user_id == user_id, TeamMembership.status == "active")
    ).first()
    # Same response for absent and unauthorized teams prevents ID enumeration.
    if row is None:
        raise NotFound("Time não encontrado")
    team, membership = row._tuple()
    if permission:
        grants = set(
            session.scalars(
                select(MembershipPermission.permission).where(
                    MembershipPermission.membership_id == membership.id,
                )
            )
        )
        if not allows(
            Plan(team.plan),
            is_president=team.president_membership_id == membership.id,
            role=Role(membership.role),
            grants=grants,
            permission=permission,
        ):
            raise Forbidden("Sem permissão para esta ação")
    return team
