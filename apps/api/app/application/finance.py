"""Team-scoped financial reads; all amounts are exact BRL decimal strings."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.billing_access import effective_plan
from app.application.roster import roster_name
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain.billing import PRO_PRICE
from app.domain.policies import ENTITLEMENTS, Conflict, Forbidden, NotFound, Permission
from app.infrastructure.finance_models import CashEntry, DuesSettings, FinanceAudit, MonthlyDues
from app.infrastructure.models import Player, Team, TeamMembership, User


def money(value: Decimal) -> str:
    return format(value, ".2f")


def authorize(session: Session, user_id: UUID, team_id: UUID, *, manage: bool = False) -> Team:
    # Reads also take the existing Team lock so multi-query snapshots are consistent.
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
        permission=Permission.MANAGE_FINANCE if manage else None,
    )


def enabled(session: Session, team: Team) -> bool:
    return ENTITLEMENTS[effective_plan(session, team)].finance


def authorize_write(session: Session, user_id: UUID, team_id: UUID) -> Team:
    """Financial operations are ELEVEN BR PRO; data kept while Free stays intact and readable."""
    team = authorize(session, user_id, team_id, manage=True)
    if not enabled(session, team):
        raise Forbidden("Financeiro é um recurso ELEVEN BR PRO.")
    return team


def version(current: int, expected: int) -> None:
    if current != expected:
        raise Conflict("Os dados mudaram. Atualize antes de confirmar novamente.")


def confirmed(value: bool) -> None:
    if not value:
        raise Conflict("Confira os dados e confirme a operação financeira.")


def settings_read(item: DuesSettings | None) -> dict[str, object]:
    return {
        "amount": money(item.amount) if item else "0.00",
        "due_day": item.due_day if item else 10,
        "active": item.active if item else False,
        "version": item.version if item else 0,
    }


def context(session: Session, user_id: UUID, team_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    _, manage = membership_context(session, team, user_id, Permission.MANAGE_FINANCE)
    result: dict[str, object] = {"can_manage": manage, "currency": "BRL"}
    result["enabled"] = enabled(session, team)
    if not result["enabled"]:
        result["pro_price"] = str(PRO_PRICE)
    if manage:
        result["command_id"] = str(uuid4())
        result["settings"] = settings_read(
            session.scalar(select(DuesSettings).where(DuesSettings.team_id == team_id))
        )
        result["totals"] = totals(session, team_id)
    return result


def totals(session: Session, team_id: UUID) -> dict[str, str]:
    values = {
        kind: amount
        for kind, amount in session.execute(
            select(CashEntry.kind, func.sum(CashEntry.amount))
            .where(CashEntry.team_id == team_id, CashEntry.cancelled_at.is_(None))
            .group_by(CashEntry.kind)
        ).all()
    }
    income, expense = values.get("INCOME", Decimal(0)), values.get("EXPENSE", Decimal(0))
    return {"income": money(income), "expense": money(expense), "balance": money(income - expense)}


def entry_read(item: CashEntry) -> dict[str, object]:
    return {
        **{
            key: getattr(item, key)
            for key in (
                "id",
                "dues_id",
                "kind",
                "category",
                "description",
                "entry_date",
                "payment_method",
                "note",
                "created_by",
                "created_at",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
            )
        },
        "amount": money(item.amount),
        "source": "DUES" if item.dues_id else "MANUAL",
    }


def entry_list(session: Session, entries: list[CashEntry]) -> list[dict[str, object]]:
    actors = {entry.created_by for entry in entries} | {
        entry.cancelled_by for entry in entries if entry.cancelled_by
    }
    names = {
        user_id: name
        for user_id, name in session.execute(
            select(User.id, func.coalesce(Player.display_name, User.registration_name, "Conta"))
            .outerjoin(Player, Player.user_id == User.id)
            .where(User.id.in_(actors))
        )
    }
    return [
        {
            **entry_read(entry),
            "created_by_name": names.get(entry.created_by),
            "cancelled_by_name": names.get(entry.cancelled_by) if entry.cancelled_by else None,
        }
        for entry in entries
    ]


def received(session: Session, dues_id: UUID) -> Decimal:
    return session.scalar(
        select(func.coalesce(func.sum(CashEntry.amount), 0)).where(
            CashEntry.dues_id == dues_id, CashEntry.cancelled_at.is_(None)
        )
    ) or Decimal(0)


def dues_read(
    item: MonthlyDues, member: TeamMembership, player: Player, paid: Decimal
) -> dict[str, object]:
    remaining = item.amount - paid if item.status in ("PENDING", "PAID") else Decimal(0)
    return {
        "id": item.id,
        "membership_id": item.membership_id,
        "name": roster_name(member, player),
        "competence": item.competence,
        "due_date": item.due_date,
        "amount": money(item.amount),
        "received": money(paid),
        "remaining": money(remaining),
        "status": item.status,
        "overdue": item.status == "PENDING" and item.due_date < date.today(),
        "version": item.version,
    }


def own_id(session: Session, team_id: UUID, user_id: UUID) -> UUID:
    return session.scalars(
        select(TeamMembership.id)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(
            TeamMembership.team_id == team_id,
            Player.user_id == user_id,
            TeamMembership.status == "active",
        )
    ).one()


def dues_page(
    session: Session, user_id: UUID, team_id: UUID, *, competence: date | None, offset: int
) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    _, manage = membership_context(session, team, user_id, Permission.MANAGE_FINANCE)
    conditions = [MonthlyDues.team_id == team_id]
    if not manage:
        conditions.append(MonthlyDues.membership_id == own_id(session, team_id, user_id))
    if competence:
        conditions.append(MonthlyDues.competence == competence)
    sums = (
        select(CashEntry.dues_id, func.sum(CashEntry.amount).label("paid"))
        .where(CashEntry.team_id == team_id, CashEntry.cancelled_at.is_(None))
        .group_by(CashEntry.dues_id)
        .subquery()
    )
    rows = session.execute(
        select(MonthlyDues, TeamMembership, Player, func.coalesce(sums.c.paid, 0))
        .join(TeamMembership, MonthlyDues.membership_id == TeamMembership.id)
        .join(Player, Player.id == TeamMembership.player_id)
        .outerjoin(sums, sums.c.dues_id == MonthlyDues.id)
        .where(*conditions)
        .order_by(MonthlyDues.competence.desc(), MonthlyDues.id)
        .offset(offset)
        .limit(51)
    ).all()
    counts = {"PAID": 0, "PENDING": 0, "OVERDUE": 0, "EXEMPT": 0, "CANCELLED": 0}
    for status, due_date, count in session.execute(
        select(MonthlyDues.status, MonthlyDues.due_date, func.count())
        .where(*conditions)
        .group_by(MonthlyDues.status, MonthlyDues.due_date)
    ):
        counts["OVERDUE" if status == "PENDING" and due_date < date.today() else status] += count
    return {
        "items": [dues_read(*row) for row in rows[:50]],
        "has_more": len(rows) > 50,
        "counts": counts,
    }


def get_dues(session: Session, team_id: UUID, dues_id: UUID) -> MonthlyDues:
    item = session.scalar(
        select(MonthlyDues)
        .where(MonthlyDues.team_id == team_id, MonthlyDues.id == dues_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise NotFound("Cobrança não encontrada.")
    return item


def dues_detail(session: Session, user_id: UUID, team_id: UUID, dues_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    _, manage = membership_context(session, team, user_id, Permission.MANAGE_FINANCE)
    item = get_dues(session, team_id, dues_id)
    if not manage and item.membership_id != own_id(session, team_id, user_id):
        raise NotFound("Cobrança não encontrada.")
    member, player = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.id == item.membership_id)
    ).one()
    result = dues_read(item, member, player, received(session, item.id))
    if manage:
        result["command_id"] = str(uuid4())
    result["payments"] = entry_list(
        session,
        list(
            session.scalars(
                select(CashEntry)
                .where(CashEntry.team_id == team_id, CashEntry.dues_id == item.id)
                .order_by(CashEntry.created_at, CashEntry.id)
            )
        ),
    )
    result["audit"] = [
        {
            **{key: getattr(audit, key) for key in ("action", "actor_id", "created_at", "reason")},
            "actor_name": name,
        }
        for audit, name in session.execute(
            select(
                FinanceAudit, func.coalesce(Player.display_name, User.registration_name, "Conta")
            )
            .join(User, User.id == FinanceAudit.actor_id)
            .outerjoin(Player, Player.user_id == User.id)
            .where(FinanceAudit.team_id == team_id, FinanceAudit.dues_id == item.id)
            .order_by(FinanceAudit.created_at, FinanceAudit.id)
        )
    ]
    return result


def cash_page(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    *,
    start: date | None,
    end: date | None,
    kind: str | None,
    category: str | None,
    offset: int,
) -> dict[str, object]:
    authorize(session, user_id, team_id, manage=True)
    if start and end and start > end:
        raise Conflict("A data inicial deve ser anterior à final.")
    conditions = [CashEntry.team_id == team_id]
    if start:
        conditions.append(CashEntry.entry_date >= start)
    if end:
        conditions.append(CashEntry.entry_date <= end)
    if kind:
        conditions.append(CashEntry.kind == kind)
    if category:
        conditions.append(CashEntry.category == category)
    items = list(
        session.scalars(
            select(CashEntry)
            .where(*conditions)
            .order_by(CashEntry.entry_date.desc(), CashEntry.created_at.desc(), CashEntry.id)
            .offset(offset)
            .limit(51)
        )
    )
    return {
        "items": entry_list(session, items[:50]),
        "has_more": len(items) > 50,
        "totals": totals(session, team_id),
        "categories": list(
            session.scalars(
                select(CashEntry.category)
                .where(CashEntry.team_id == team_id)
                .distinct()
                .order_by(CashEntry.category)
            )
        ),
    }
