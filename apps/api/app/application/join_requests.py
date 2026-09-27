"""Persistent, team-scoped requests. A code discovers identity, never grants access."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.application.notification_events import join_request, join_resolved
from app.application.roster import authorized_team, member_in_team, roster_name
from app.application.sessions import verified
from app.application.teams import add_member
from app.application.verification import mask_contact
from app.domain.policies import Conflict, NotFound
from app.infrastructure.join_models import TeamJoinRequest
from app.infrastructure.models import MembershipPermission, Player, Team, TeamMembership, User

IDENTITY_CONFLICT = (
    "Esta conta já possui uma identidade esportiva com histórico. "
    "A vinculação com outro jogador existente exige unificação de perfis."
)


def has_sporting_links(session: Session, player_id: UUID) -> bool:
    # All sporting data references Membership (including inactive), never User or a name.
    return bool(session.scalar(select(exists().where(TeamMembership.player_id == player_id))))


def target_problem(
    team: Team,
    member: TeamMembership,
    player: Player,
    administrative: set[UUID],
    shared: set[UUID],
) -> str | None:
    if player.user_id:
        return "Este jogador já está vinculado a uma conta."
    if member.status != "active":
        return "Jogador inativo. Reative explicitamente no elenco antes de vincular."
    if (
        member.id == team.president_membership_id
        or member.role != "member"
        or member.id in administrative
    ):
        return (
            "Este vínculo possui responsabilidades administrativas "
            "e não pode ser vinculado por este fluxo."
        )
    if player.id in shared:
        return (
            "Este jogador possui vínculos em outros times. A identidade exige revisão específica."
        )
    return None


def target_restrictions(
    session: Session, team_id: UUID, members: list[TeamMembership]
) -> tuple[set[UUID], set[UUID]]:
    # Fetch flags in batches instead of querying each candidate separately.
    administrative = set(
        session.scalars(
            select(MembershipPermission.membership_id).where(
                MembershipPermission.membership_id.in_([m.id for m in members])
            )
        )
    )
    shared = set(
        session.scalars(
            select(TeamMembership.player_id).where(
                TeamMembership.team_id != team_id,
                TeamMembership.player_id.in_([m.player_id for m in members]),
            )
        )
    )
    return administrative, shared


def public_team(team: Team) -> dict[str, object]:
    return {
        key: getattr(team, key)
        for key in ["id", "name", "code", "city", "state", "modalities", "crest_url"]
    }


def own_membership(session: Session, user_id: UUID, team_id: UUID) -> TeamMembership | None:
    return session.scalar(
        select(TeamMembership)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id, Player.user_id == user_id)
    )


def pending(session: Session, user_id: UUID, team_id: UUID) -> TeamJoinRequest | None:
    return session.scalar(
        select(TeamJoinRequest).where(
            TeamJoinRequest.user_id == user_id,
            TeamJoinRequest.team_id == team_id,
            TeamJoinRequest.status == "PENDING",
        )
    )


def lookup(session: Session, *, user_id: UUID, code: str) -> dict[str, object]:
    team = session.scalar(
        select(Team).where(Team.code == code.strip().upper(), Team.status == "active")
    )
    if team is None:
        raise NotFound("Time não encontrado. Confira o código.")
    member = own_membership(session, user_id, team.id)
    return {
        "team": public_team(team),
        "membership_status": member.status if member else None,
        "pending": pending(session, user_id, team.id) is not None,
    }


def present(item: TeamJoinRequest, team: Team) -> dict[str, object]:
    return {
        "id": item.id,
        "team": public_team(team),
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "resolved_at": item.resolved_at,
    }


def request_entry(
    session: Session, *, user_id: UUID, team_id: UUID, code: str
) -> dict[str, object]:
    team = session.scalar(
        select(Team)
        .where(Team.id == team_id, Team.code == code.strip().upper(), Team.status == "active")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if team is None:
        raise NotFound("Time não encontrado. Confira o código.")
    member = own_membership(session, user_id, team_id)
    if member:
        raise Conflict(
            "Você já faz parte deste time."
            if member.status == "active"
            else "Seu vínculo está inativo. Peça ao responsável para reativá-lo no elenco."
        )
    if pending(session, user_id, team_id):
        raise Conflict("Sua solicitação para este time já está aguardando aprovação.")
    item = TeamJoinRequest(team_id=team_id, user_id=user_id)
    session.add(item)
    session.flush()
    join_request(session, team, item)
    result = present(item, team)
    session.commit()
    return result


def mine(session: Session, *, user_id: UUID, offset: int = 0) -> list[dict[str, object]]:
    rows = session.execute(
        select(TeamJoinRequest, Team)
        .join(Team, Team.id == TeamJoinRequest.team_id)
        .where(TeamJoinRequest.user_id == user_id)
        .order_by(TeamJoinRequest.created_at.desc(), TeamJoinRequest.id)
        .offset(offset)
        .limit(50)
    )
    return [present(item, team) for item, team in rows]


def locked_request(session: Session, team_id: UUID, request_id: UUID) -> TeamJoinRequest:
    item = session.scalar(
        select(TeamJoinRequest)
        .where(TeamJoinRequest.id == request_id, TeamJoinRequest.team_id == team_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise NotFound("Solicitação não encontrada.")
    if item.status != "PENDING":
        raise Conflict("Esta solicitação já foi resolvida. Atualize a lista.")
    return item


def resolve(item: TeamJoinRequest, status: str, actor: UUID) -> None:
    item.status = status
    item.resolved_at = datetime.now(UTC)
    item.resolved_by = actor


def cancel(session: Session, *, user_id: UUID, request_id: UUID) -> dict[str, object]:
    team_id = session.scalar(
        select(TeamJoinRequest.team_id).where(
            TeamJoinRequest.id == request_id, TeamJoinRequest.user_id == user_id
        )
    )
    if team_id is None:
        raise NotFound("Solicitação não encontrada.")
    team = session.scalars(select(Team).where(Team.id == team_id).with_for_update()).one()
    item = locked_request(session, team_id, request_id)
    resolve(item, "CANCELLED", user_id)
    session.flush()
    result = present(item, team)
    session.commit()
    return result


def administrative_item(
    item: TeamJoinRequest, user: User, player: Player | None
) -> dict[str, object]:
    contact, channel = (user.email, "email") if user.email else (user.phone, "phone")
    return {
        "id": item.id,
        "status": item.status,
        "created_at": item.created_at,
        "name": player.display_name if player else user.registration_name or "Jogador",
        "masked_contact": mask_contact(contact or "", channel),
    }


def list_pending(session: Session, *, user_id: UUID, team_id: UUID) -> list[dict[str, object]]:
    authorized_team(session, user_id, team_id, write=True)
    rows = session.execute(
        select(TeamJoinRequest, User, Player)
        .join(User, User.id == TeamJoinRequest.user_id)
        .outerjoin(Player, Player.user_id == User.id)
        .where(TeamJoinRequest.team_id == team_id, TeamJoinRequest.status == "PENDING")
        .order_by(TeamJoinRequest.created_at, TeamJoinRequest.id)
    )
    return [administrative_item(item, user, player) for item, user, player in rows]


def reject(
    session: Session, *, user_id: UUID, team_id: UUID, request_id: UUID, confirm: bool
) -> dict[str, object]:
    team = authorized_team(session, user_id, team_id, write=True)
    item = locked_request(session, team_id, request_id)
    if not confirm:
        raise Conflict("Confirme a recusa da solicitação.")
    resolve(item, "REJECTED", user_id)
    session.flush()
    join_resolved(session, team, item)
    result = present(item, team)
    session.commit()
    return result


def detail(
    session: Session, *, user_id: UUID, team_id: UUID, request_id: UUID
) -> dict[str, object]:
    team = authorized_team(session, user_id, team_id, write=True)
    item = locked_request(session, team_id, request_id)
    user = session.get(User, item.user_id)
    assert user is not None
    source = session.scalar(select(Player).where(Player.user_id == user.id))
    conflict = IDENTITY_CONFLICT if source and has_sporting_links(session, source.id) else None
    rows = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.team_id == team_id, Player.user_id.is_(None))
        .order_by(TeamMembership.status, TeamMembership.roster_name, TeamMembership.id)
    ).all()
    restrictions = target_restrictions(session, team_id, [member for member, _ in rows])
    candidates = []
    for member, player in rows:
        problem = target_problem(team, member, player, *restrictions)
        candidates.append(
            {
                "membership_id": member.id,
                "name": roster_name(member, player),
                "status": member.status,
                "photo_url": player.photo_url,
                "unavailable_reason": problem or conflict,
            }
        )
    return {
        "request": administrative_item(item, user, source),
        "candidates": candidates,
        "identity_conflict": conflict,
    }


def approve(
    session: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    request_id: UUID,
    membership_id: UUID | None,
    confirm: bool,
) -> dict[str, object]:
    try:
        team = authorized_team(session, user_id, team_id, write=True)
        if team.status != "active":
            raise Conflict("Este time não está disponível para novas entradas.")
        item = locked_request(session, team_id, request_id)
        if not confirm:
            raise Conflict("Confirme a aprovação e o jogador escolhido.")
        user = session.scalars(
            select(User)
            .where(User.id == item.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        if user.status != "active" or not verified(user):
            raise Conflict("A conta solicitante não está disponível para aprovação.")
        if own_membership(session, user.id, team_id):
            raise Conflict("Esta conta já possui vínculo neste time. Confira o elenco.")
        source = session.scalar(
            select(Player)
            .where(Player.user_id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if membership_id is None:
            if source is None:
                raise Conflict("O solicitante precisa completar o perfil antes da aprovação.")
            member = add_member(session, team_id=team_id, player_id=source.id)
        else:
            member, target = member_in_team(session, team_id, membership_id)
            if target.user_id:
                raise Conflict("Este jogador já está vinculado a uma conta.")
            target = session.scalars(
                select(Player)
                .where(Player.id == target.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one()
            problem = target_problem(
                team, member, target, *target_restrictions(session, team_id, [member])
            )
            if problem:
                raise Conflict(problem)
            if source and has_sporting_links(session, source.id):
                raise Conflict(IDENTITY_CONFLICT)
            if (
                source
                and source.photo_url
                and target.photo_url
                and source.photo_url != target.photo_url
            ):
                raise Conflict(
                    "A conta e o jogador possuem fotos diferentes. Preserve as imagens "
                    "e resolva a escolha da foto antes de vincular."
                )
            if source:
                # No Membership means no attendance/formation/match/statistic references.
                # Row locks plus the FK also protect against a simultaneous new sporting link.
                if not target.photo_url:
                    target.photo_url = source.photo_url
                session.delete(source)
                session.flush()  # Free the unique User FK before assigning the existing Player.
            target.user_id = user.id
        item.membership_id = member.id
        resolve(item, "APPROVED", user_id)
        session.flush()
        join_resolved(session, team, item)
        result = present(item, team)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
