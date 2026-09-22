"""Team-scoped roster operations. No global player lookup or automatic account linkage."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.team_profiles import membership_context
from app.application.teams import (
    add_member,
    ensure_active_slot,
    ensure_admin_slot,
    require_membership,
)
from app.domain.policies import ENTITLEMENTS, Conflict, Forbidden, NotFound, Permission, Plan, Role
from app.domain.team_identity import normalized
from app.infrastructure.models import Player, Team, TeamMembership


@dataclass
class RosterPerson:
    membership_id: UUID
    player_id: UUID
    name: str
    nickname: str | None
    phone: str | None
    email: str | None
    photo_url: str | None
    status: str
    account_linked: bool
    is_president: bool


@dataclass
class RosterSnapshot:
    items: list[RosterPerson]
    active_count: int
    inactive_count: int
    active_limit: int
    can_manage: bool
    plan: str


@dataclass
class SimilarPlayer:
    membership_id: UUID
    name: str
    status: str
    account_linked: bool
    reasons: list[str]


def authorized_team(session: Session, user_id: UUID, team_id: UUID, *, write: bool) -> Team:
    if write:
        # All additions/status changes serialize on the SAME lock as the foundation primitive.
        team = session.scalar(
            select(Team)
            .where(Team.id == team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if team is None:
            raise NotFound("Time não encontrado")
    return require_membership(
        session,
        user_id=user_id,
        team_id=team_id,
        permission=Permission.MANAGE_MEMBERS if write else None,
    )


def roster_name(membership: TeamMembership, player: Player) -> str:
    return player.display_name if player.user_id else membership.roster_name or player.display_name


def person(
    team: Team, membership: TeamMembership, player: Player, *, contacts: bool
) -> RosterPerson:
    linked = player.user_id is not None
    return RosterPerson(
        membership.id,
        player.id,
        roster_name(membership, player),
        membership.nickname,
        membership.contact_phone if contacts and not linked else None,
        membership.contact_email if contacts and not linked else None,
        player.photo_url,
        membership.status,
        linked,
        membership.id == team.president_membership_id,
    )


def member_in_team(
    session: Session, team_id: UUID, membership_id: UUID
) -> tuple[TeamMembership, Player]:
    row = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id, TeamMembership.id == membership_id)
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise NotFound("Jogador não encontrado neste elenco")
    return row._tuple()


def list_roster(session: Session, *, user_id: UUID, team_id: UUID, status: str) -> RosterSnapshot:
    team = authorized_team(session, user_id, team_id, write=False)
    _, can_manage = membership_context(session, team, user_id, Permission.MANAGE_MEMBERS)
    rows = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id)
    ).all()
    items = [person(team, member, player, contacts=can_manage) for member, player in rows]
    active = sum(item.status == "active" for item in items)
    return RosterSnapshot(
        sorted(
            [item for item in items if status == "all" or item.status == status],
            key=lambda item: (normalized(item.name), str(item.membership_id)),
        ),
        active,
        len(items) - active,
        ENTITLEMENTS[Plan(team.plan)].active_players,
        can_manage,
        team.plan,
    )


def get_person(
    session: Session, *, user_id: UUID, team_id: UUID, membership_id: UUID
) -> RosterPerson:
    team = authorized_team(session, user_id, team_id, write=False)
    _, can_manage = membership_context(session, team, user_id, Permission.MANAGE_MEMBERS)
    member, player = member_in_team(session, team_id, membership_id)
    return person(team, member, player, contacts=can_manage)


def find_similar(
    session: Session,
    *,
    team_id: UUID,
    name: str,
    phone: str | None,
    email: str | None,
    exclude: UUID | None = None,
) -> list[SimilarPlayer]:
    """Called only after authorization. Include inactive players; never inspect another roster."""
    rows = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id)
        .order_by(TeamMembership.id)
    ).all()
    matches: list[SimilarPlayer] = []
    for member, player in rows:
        if member.id == exclude:
            continue
        candidate = roster_name(member, player)
        reasons = []
        if SequenceMatcher(None, normalized(name), normalized(candidate)).ratio() >= 0.8:
            reasons.append("nome")
        if phone and phone == member.contact_phone:
            reasons.append("telefone")
        if email and email == member.contact_email:
            reasons.append("e-mail")
        if reasons:
            matches.append(
                SimilarPlayer(
                    member.id, candidate, member.status, player.user_id is not None, reasons
                )
            )
    # Exact contacts deserve prominence. Response stays small without hiding contact matches.
    matches.sort(key=lambda item: (not any(reason != "nome" for reason in item.reasons), item.name))
    return matches[:5]


def similar_players(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    name: str,
    phone: str | None,
    email: str | None,
    exclude: UUID | None = None,
) -> list[SimilarPlayer]:
    require_membership(
        session, user_id=user_id, team_id=team_id, permission=Permission.MANAGE_MEMBERS
    )
    if exclude:
        member_in_team(session, team_id, exclude)
    return find_similar(
        session, team_id=team_id, name=name, phone=phone, email=email, exclude=exclude
    )


def add_player(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    name: str,
    nickname: str | None,
    phone: str | None,
    email: str | None,
    confirm_duplicate: bool,
) -> RosterPerson:
    team = authorized_team(session, user_id, team_id, write=True)
    ensure_active_slot(session, team)
    if not confirm_duplicate and find_similar(
        session, team_id=team_id, name=name, phone=phone, email=email
    ):
        raise Conflict("Encontramos um jogador parecido neste elenco. Confirme a inclusão.")
    player = Player(display_name=name, user_id=None)
    session.add(player)
    session.flush()
    member = add_member(session, team_id=team_id, player_id=player.id)
    member.roster_name, member.nickname = name, nickname
    member.contact_phone, member.contact_email = phone, email
    session.flush()
    result = person(team, member, player, contacts=True)
    session.commit()
    return result


def edit_player(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    membership_id: UUID,
    updates: dict[str, str | None],
    confirm_duplicate: bool,
) -> RosterPerson:
    team = authorized_team(session, user_id, team_id, write=True)
    member, player = member_in_team(session, team_id, membership_id)
    if player.user_id and any(field in updates for field in ("name", "phone", "email")):
        raise Forbidden(
            "Nome e contatos da conta são controlados pelo próprio jogador. "
            "Edite apenas o apelido neste time."
        )
    if not player.user_id:
        name = updates.get("name") or roster_name(member, player)
        phone = updates.get("phone", member.contact_phone)
        email = updates.get("email", member.contact_email)
        if not confirm_duplicate and find_similar(
            session, team_id=team_id, name=name, phone=phone, email=email, exclude=member.id
        ):
            raise Conflict("Encontramos um jogador parecido neste elenco. Confirme a alteração.")
        member.roster_name, member.contact_phone, member.contact_email = name, phone, email
    if "nickname" in updates:
        member.nickname = updates["nickname"]
    session.flush()
    result = person(team, member, player, contacts=True)
    session.commit()
    return result


def change_status(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    membership_id: UUID,
    activate: bool,
) -> RosterPerson:
    team = authorized_team(session, user_id, team_id, write=True)
    member, player = member_in_team(session, team_id, membership_id)
    if not activate and member.id == team.president_membership_id:
        raise Conflict("Transfira a presidência antes de inativar este jogador.")
    if activate and member.status != "active":
        ensure_active_slot(session, team)
        if member.role == Role.ADMIN.value and member.id != team.president_membership_id:
            ensure_admin_slot(session, team)
    member.status = "active" if activate else "inactive"
    session.flush()
    result = person(team, member, player, contacts=True)
    session.commit()
    return result
