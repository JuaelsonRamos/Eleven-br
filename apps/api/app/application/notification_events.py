"""Business event adapters for the in-app notification stream."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.notification_delivery import emit, recipients
from app.domain.notifications import NotificationAction as Action
from app.domain.notifications import NotificationType as Kind
from app.domain.policies import Permission
from app.infrastructure.event_models import Event
from app.infrastructure.finance_models import CashEntry, MonthlyDues
from app.infrastructure.join_models import TeamJoinRequest
from app.infrastructure.models import Player, Team, TeamMembership, User


def join_request(session: Session, team: Team, item: TeamJoinRequest) -> None:
    name = session.scalar(select(Player.display_name).where(Player.user_id == item.user_id))
    emit(
        session,
        users=recipients(session, team, permission=Permission.MANAGE_MEMBERS),
        team_id=team.id,
        kind=Kind.TEAM_JOIN_REQUEST,
        title="Nova solicitação de entrada",
        message=f"{name or 'Um jogador'} solicitou entrada no {team.name}.",
        key=f"join-request:{item.id}",
        entity_type="join_request",
        entity_id=item.id,
        action=Action.OPEN_JOIN_REQUESTS,
    )


def join_resolved(session: Session, team: Team, item: TeamJoinRequest) -> None:
    approved = item.status == "APPROVED"
    emit(
        session,
        users=[item.user_id],
        team_id=team.id,
        kind=Kind.TEAM_JOIN_APPROVED if approved else Kind.TEAM_JOIN_REJECTED,
        title="Entrada aprovada" if approved else "Solicitação não aprovada",
        message=f"Você agora faz parte do {team.name}."
        if approved
        else f"Sua solicitação para entrar no {team.name} não foi aprovada.",
        key=f"join-resolved:{item.id}:{item.status}",
        entity_type="team" if approved else "join_request",
        entity_id=team.id if approved else item.id,
        action=Action.OPEN_TEAM if approved else None,
    )


def event_notice(
    session: Session,
    team: Team,
    event: Event,
    author: UUID,
    kind: Kind,
    *,
    series: bool = False,
) -> None:
    label = "pelada" if event.kind == "PELADA" else "jogo"
    if kind == Kind.EVENT_CREATED:
        title = "Nova pelada" if event.kind == "PELADA" else "Novo jogo"
        message = f"{event.title} • {event.date:%d/%m} às {event.time:%H:%M}"
        key = f"event-created:{event.id}"
    elif kind == Kind.EVENT_UPDATED:
        title = "Pelada atualizada" if event.kind == "PELADA" else "Jogo atualizado"
        message = f"A {event.title} teve informações de participação alteradas."
        key = f"event-updated:{event.id}:{event.updated_at.isoformat()}"
    else:
        title = (
            "Recorrência encerrada"
            if series
            else f"{label.capitalize()} cancelad{'a' if label == 'pelada' else 'o'}"
        )
        message = (
            f"A recorrência de {event.title} foi encerrada. "
            "Datas de hoje em diante foram canceladas."
            if series
            else f"{event.title} de {event.date:%d/%m} foi cancelado."
        )
        key = f"series-cancelled:{event.series_id}" if series else f"event-cancelled:{event.id}"
    emit(
        session,
        users=recipients(session, team, exclude=author),
        team_id=team.id,
        kind=kind,
        title=title,
        message=message,
        key=key,
        entity_type="event",
        entity_id=event.id,
        action=Action.OPEN_EVENT,
    )


def money(value: Decimal) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def finance_notice(
    session: Session,
    dues: MonthlyDues,
    kind: Kind,
    *,
    entry: CashEntry | None = None,
    remaining: Decimal | None = None,
) -> None:
    uid = session.scalar(
        select(User.id)
        .join(Player, Player.user_id == User.id)
        .join(TeamMembership, TeamMembership.player_id == Player.id)
        .where(
            TeamMembership.id == dues.membership_id,
            TeamMembership.team_id == dues.team_id,
            TeamMembership.status == "active",
            User.status == "active",
        )
    )
    if uid is None:
        return
    month = f"{dues.competence:%m/%Y}"
    if kind == Kind.FINANCE_CHARGE_CREATED:
        title, message = "Nova mensalidade", f"Mensalidade de {month} • {money(dues.amount)}"
        key = f"finance-charge:{dues.id}"
    else:
        assert entry is not None
        key = f"{kind.value}:{entry.id}"
        if kind == Kind.FINANCE_PAYMENT_REVERSED:
            title = "Pagamento estornado"
            message = (
                f"O pagamento de {money(entry.amount)} da mensalidade de {month} foi estornado."
            )
        elif remaining == Decimal("0"):
            title = "Mensalidade paga"
            message = (
                f"Pagamento de {money(entry.amount)} registrado. Mensalidade de {month} quitada."
            )
        else:
            assert remaining is not None
            title = "Pagamento registrado"
            message = (
                f"Recebemos {money(entry.amount)} da mensalidade de {month}. "
                f"Saldo restante: {money(remaining)}."
            )
    emit(
        session,
        users=[uid],
        team_id=dues.team_id,
        kind=kind,
        title=title,
        message=message,
        key=key,
        entity_type="finance_charge",
        entity_id=dues.id,
        action=Action.OPEN_FINANCE_CHARGE,
    )
