"""President-only team roles: administrators and presidency transfer.

Reuses the foundation structures instead of a parallel model: TeamMembership.role,
MembershipPermission grants, ENTITLEMENTS/ensure_admin_slot and the deferred composite
FK Team.president_membership_id. Writes take the Team lock, revalidate the current
state and record TeamAudit in the same transaction. Memberships are never deleted or
recreated, so sporting, financial and attendance history stays attached to them.
"""

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plan
from app.application.roster import (
    RosterPerson,
    authorized_team,
    member_grants,
    member_in_team,
    person,
)
from app.application.team_audit import record
from app.application.team_profiles import membership_context
from app.application.teams import ensure_admin_slot
from app.domain.policies import ENTITLEMENTS, Conflict, Forbidden, Permission, Role
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership, User


def president_team(session: Session, user_id: UUID, team_id: UUID) -> Team:
    """Team lock plus current-President check. Administrative grants never suffice."""
    team = authorized_team(session, user_id, team_id, write=True)
    if membership_context(session, team, user_id)[0] != "president":
        raise Forbidden(
            "Somente o Presidente pode definir administradores ou transferir a Presidência."
        )
    return team


def active_account(session: Session, player: Player) -> bool:
    """Only a person who can sign in may administer or preside over the team."""
    user = session.get(User, player.user_id) if player.user_id else None
    return user is not None and user.status == "active"


def set_role(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    membership_id: UUID,
    *,
    role: Role,
    permissions: frozenset[Permission],
    version: int,
) -> RosterPerson:
    team = president_team(session, user_id, team_id)
    member, player = member_in_team(session, team_id, membership_id)
    if member.id == team.president_membership_id:
        raise Conflict("O Presidente já administra todas as áreas do time.")
    current = member_grants(session, member.id)
    wanted = sorted(permission.value for permission in permissions) if role == Role.ADMIN else []
    if member.role == role.value and current == wanted:
        return person(team, member, player, contacts=True, grants=current)
    if member.roster_version != version:
        raise Conflict("O cadastro mudou. Atualize antes de salvar.")
    if role == Role.ADMIN:
        if member.status != "active":
            raise Conflict("Somente jogadores ativos podem administrar o time.")
        if not active_account(session, player):
            raise Conflict(
                "Somente jogadores com conta ativa no ELEVEN BR podem administrar o time."
            )
        if not ENTITLEMENTS[effective_plan(session, team)].granular_permissions:
            raise Conflict(
                "Administradores são um recurso ELEVEN PRO. "
                "No Free, somente o Presidente administra o time."
            )
        if member.role != Role.ADMIN.value:
            ensure_admin_slot(session, team)
    action = (
        "ADMIN_REVOKED"
        if role == Role.MEMBER
        else "ADMIN_GRANTED"
        if member.role != Role.ADMIN.value
        else "ADMIN_PERMISSIONS_CHANGED"
    )
    record(
        session,
        team_id,
        user_id,
        member.id,
        action,
        {"role": member.role, "permissions": current},
        {"role": role.value, "permissions": wanted},
    )
    session.execute(
        delete(MembershipPermission).where(MembershipPermission.membership_id == member.id)
    )
    session.add_all(
        MembershipPermission(membership_id=member.id, permission=value) for value in wanted
    )
    member.role = role.value
    member.roster_version += 1
    session.flush()
    result = person(team, member, player, contacts=True, grants=wanted)
    session.commit()
    return result


def transfer_presidency(
    session: Session, user_id: UUID, team_id: UUID, membership_id: UUID, *, confirm: bool
) -> Team:
    team = president_team(session, user_id, team_id)
    if not confirm:
        raise Conflict("Confirme a transferência da Presidência.")
    successor, player = member_in_team(session, team_id, membership_id)
    if successor.id == team.president_membership_id:
        raise Conflict("Este jogador já é o Presidente do time.")
    if successor.status != "active":
        raise Conflict("Somente jogadores ativos podem assumir a Presidência.")
    if not active_account(session, player):
        raise Conflict("A Presidência exige um jogador com conta ativa no ELEVEN BR.")
    previous = session.get(TeamMembership, team.president_membership_id)
    assert previous is not None
    record(
        session,
        team_id,
        user_id,
        team_id,
        "PRESIDENCY_TRANSFERRED",
        {
            "president_membership_id": str(previous.id),
            "previous_role": previous.role,
            "previous_permissions": member_grants(session, previous.id),
            "successor_role": successor.role,
            "successor_permissions": member_grants(session, successor.id),
        },
        {
            "president_membership_id": str(successor.id),
            "previous_role": Role.MEMBER.value,
            "successor_role": Role.MEMBER.value,
        },
    )
    # The Presidency carries every permission; neither side keeps stale grants.
    session.execute(
        delete(MembershipPermission).where(
            MembershipPermission.membership_id.in_([previous.id, successor.id])
        )
    )
    previous.role = successor.role = Role.MEMBER.value
    previous.roster_version += 1
    successor.roster_version += 1
    # Same deferred composite FK: exactly one President, always from this team.
    team.president_membership_id = successor.id
    session.flush()
    session.commit()
    return team
