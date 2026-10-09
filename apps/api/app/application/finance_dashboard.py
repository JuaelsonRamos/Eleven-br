"""Team finance summaries and small audited adjustments. No commercial billing writes."""

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import finance as f
from app.application.finance_commands import (
    CategoryInput,
    EditDuesInput,
    EditEntryInput,
    PreferencesInput,
)
from app.application.finance_writes import audit, check_date
from app.application.team_profiles import membership_context
from app.domain.policies import Conflict, NotFound, Permission
from app.infrastructure.finance_models import (
    CashEntry,
    FinanceAudit,
    FinancePreferences,
    MonthlyDues,
)
from app.infrastructure.models import Player, User

DEFAULT_CATEGORIES = {
    "INCOME": ["Mensalidade", "Contribuição", "Patrocínio", "Inscrição", "Premiação", "Evento"],
    "EXPENSE": [
        "Aluguel de campo",
        "Arbitragem",
        "Goleiro contratado",
        "Uniformes",
        "Material",
        "Churrasco/Confraternização",
        "Inscrição",
    ],
}


def preferences(session: Session, team_id: UUID) -> FinancePreferences | None:
    return session.scalar(select(FinancePreferences).where(FinancePreferences.team_id == team_id))


def categories(session: Session, team_id: UUID) -> dict[str, list[str]]:
    config = preferences(session, team_id)
    result = {kind: list(names) for kind, names in DEFAULT_CATEGORIES.items()}
    for kind in result:
        stored = config.categories.get(kind, []) if config else []
        existing = session.scalars(
            select(CashEntry.category)
            .where(CashEntry.team_id == team_id, CashEntry.kind == kind)
            .distinct()
        )
        for name in [*stored, *existing]:
            if name.casefold() not in {n.casefold() for n in result[kind]}:
                result[kind].append(name)
    return result


def preferences_read(config: FinancePreferences | None) -> dict[str, object]:
    return {
        "opening_balance": f.money(config.opening_balance) if config else "0.00",
        "opening_date": config.opening_date if config else None,
        "share_summary": config.share_summary if config else False,
        "version": config.version if config else 0,
    }


def save_preferences(
    session: Session, user_id: UUID, team_id: UUID, data: PreferencesInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    f.confirmed(data.confirm)
    check_date(data.opening_date)
    item = preferences(session, team_id)
    f.version(item.version if item else 0, data.expected_version)
    before = preferences_read(item)
    if item is None:
        item = FinancePreferences(team_id=team_id, version=1, categories={})
        session.add(item)
    else:
        item.version += 1
    item.opening_balance, item.opening_date, item.share_summary = (
        data.opening_balance,
        data.opening_date,
        data.share_summary,
    )
    # JSON uses strings for dates and money, never floats.
    audit(
        session,
        team_id,
        user_id,
        "PREFERENCES",
        changes={
            "before": {k: str(v) if isinstance(v, date) else v for k, v in before.items()},
            "after": data.model_dump(mode="json"),
        },
    )
    session.flush()
    return preferences_read(item)


def create_category(
    session: Session, user_id: UUID, team_id: UUID, data: CategoryInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    if data.name.casefold() == "outras despesas":
        raise Conflict("Use uma categoria específica para a despesa.")
    current = categories(session, team_id)
    if data.name.casefold() in {n.casefold() for n in current[data.kind]}:
        return dict(current)
    item = preferences(session, team_id)
    if item is None:
        item = FinancePreferences(team_id=team_id, categories={}, version=1)
        session.add(item)
    item.categories = {
        **item.categories,
        data.kind: [*item.categories.get(data.kind, []), data.name],
    }
    audit(session, team_id, user_id, "CATEGORY_CREATED", reason=f"{data.kind}: {data.name}")
    session.flush()
    return dict(categories(session, team_id))


def summary(session: Session, user_id: UUID, team_id: UUID, month: date) -> dict[str, object]:
    team = f.authorize(session, user_id, team_id)
    _, manage = membership_context(session, team, user_id, Permission.MANAGE_FINANCE)
    config = preferences(session, team_id)
    shared = bool(config and config.share_summary)
    if not manage and not shared:
        return {"visible": False}
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    valid = [CashEntry.team_id == team_id, CashEntry.cancelled_at.is_(None)]
    grouped = session.execute(
        select(CashEntry.kind, CashEntry.category, func.sum(CashEntry.amount))
        .where(*valid, CashEntry.entry_date >= month, CashEntry.entry_date <= end)
        .group_by(CashEntry.kind, CashEntry.category)
    ).all()
    income = sum((v for kind, _, v in grouped if kind == "INCOME"), Decimal(0))
    expense = sum((v for kind, _, v in grouped if kind == "EXPENSE"), Decimal(0))
    previous = Decimal(0)
    for kind, amount in session.execute(
        select(CashEntry.kind, func.sum(CashEntry.amount))
        .where(*valid, CashEntry.entry_date < month)
        .group_by(CashEntry.kind)
    ):
        previous += amount if kind == "INCOME" else -amount
    opening = (
        config.opening_balance
        if config and config.opening_date and config.opening_date <= end
        else Decimal(0)
    )
    if config and config.opening_date and config.opening_date < month:
        previous += opening
        opening = Decimal(0)
    result = {
        "visible": True,
        "month": month,
        "balance": f.totals(session, team_id)["balance"],
        "previous_balance": f.money(previous),
        "period_balance": f.money(previous + opening + income - expense),
        "income": f.money(income),
        "expense": f.money(expense),
        "categories": {
            kind: [
                {
                    "name": category,
                    "amount": f.money(value),
                    "percent": f.money(value * 100 / (income if kind == "INCOME" else expense)),
                }
                for k, category, value in grouped
                if k == kind
            ]
            for kind in ("INCOME", "EXPENSE")
        },
    }
    # Players only get aggregates; no individual balances, overdue counts or ledger text.
    if manage:
        sums = (
            select(CashEntry.dues_id, func.sum(CashEntry.amount).label("paid"))
            .where(*valid)
            .group_by(CashEntry.dues_id)
            .subquery()
        )
        rows = session.execute(
            select(MonthlyDues, func.coalesce(sums.c.paid, 0))
            .outerjoin(sums, sums.c.dues_id == MonthlyDues.id)
            .where(MonthlyDues.team_id == team_id, MonthlyDues.competence == month)
        ).all()
        counts = {"PAID": 0, "PENDING": 0, "OVERDUE": 0, "EXEMPT": 0, "CANCELLED": 0}
        outstanding = Decimal(0)
        debtors = set()
        for dues, paid in rows:
            overdue = dues.status == "PENDING" and dues.due_date < date.today()
            counts["OVERDUE" if overdue else dues.status] += 1
            if dues.status == "PENDING":
                outstanding += dues.amount - paid
            if overdue:
                debtors.add(dues.membership_id)
        result.update(
            receivable=f.money(outstanding),
            debtors=len(debtors),
            counts=counts,
            preferences=preferences_read(config),
            choices=categories(session, team_id),
        )
        entries = list(
            session.scalars(
                select(CashEntry)
                .where(*valid, CashEntry.entry_date >= month, CashEntry.entry_date <= end)
                .order_by(CashEntry.entry_date.desc(), CashEntry.created_at.desc(), CashEntry.id)
                .limit(5)
            )
        )
        result["recent"] = f.entry_list(session, entries)
    return result


def get_entry(session: Session, team_id: UUID, entry_id: UUID) -> CashEntry:
    item = session.scalar(
        select(CashEntry).where(CashEntry.team_id == team_id, CashEntry.id == entry_id)
    )
    if item is None:
        raise NotFound("Movimentação não encontrada.")
    return item


def entry_detail(
    session: Session, user_id: UUID, team_id: UUID, entry_id: UUID
) -> dict[str, object]:
    f.authorize(session, user_id, team_id, manage=True)
    item = get_entry(session, team_id, entry_id)
    result = f.entry_list(session, [item])[0]
    result["audit"] = [
        {
            "action": a.action,
            "actor_name": name,
            "created_at": a.created_at,
            "reason": a.reason,
            "changes": a.changes,
        }
        for a, name in session.execute(
            select(
                FinanceAudit, func.coalesce(Player.display_name, User.registration_name, "Conta")
            )
            .join(User, User.id == FinanceAudit.actor_id)
            .outerjoin(Player, Player.user_id == User.id)
            .where(FinanceAudit.team_id == team_id, FinanceAudit.entry_id == entry_id)
            .order_by(FinanceAudit.created_at, FinanceAudit.id)
        )
    ]
    return result


def edit_entry(
    session: Session, user_id: UUID, team_id: UUID, entry_id: UUID, data: EditEntryInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    f.confirmed(data.confirm)
    item = get_entry(session, team_id, entry_id)
    f.version(item.version, data.expected_version)
    if item.cancelled_at or item.dues_id:
        raise Conflict(
            "Pagamento de mensalidade exige estorno e novo registro; "
            "lançamento excluído é somente leitura."
        )
    if data.category.casefold() == "mensalidade":
        raise Conflict("Use o fluxo específico de mensalidade.")
    check_date(data.entry_date)
    before = {k: str(getattr(item, k)) for k in ("amount", "category", "description", "entry_date")}
    item.amount, item.category, item.description, item.entry_date = (
        data.amount,
        data.category,
        data.description or data.category,
        data.entry_date,
    )
    item.version += 1
    audit(
        session,
        team_id,
        user_id,
        "ENTRY_EDITED",
        entry_id=item.id,
        changes={"before": before, "after": data.model_dump(mode="json")},
    )
    session.flush()
    return entry_detail(session, user_id, team_id, item.id)


def edit_dues(
    session: Session, user_id: UUID, team_id: UUID, dues_id: UUID, data: EditDuesInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    f.confirmed(data.confirm)
    item = f.get_dues(session, team_id, dues_id)
    f.version(item.version, data.expected_version)
    if item.status == "CANCELLED":
        raise Conflict("Cobrança removida é somente leitura.")
    paid = f.received(session, item.id)
    if data.amount < paid:
        raise Conflict(
            "O valor não pode ser menor que os pagamentos válidos. Estorne antes de reduzir."
        )
    before = f.money(item.amount)
    item.amount = data.amount
    if item.status != "EXEMPT":
        item.status = "PAID" if paid == data.amount else "PENDING"
    item.version += 1
    audit(
        session,
        team_id,
        user_id,
        "DUES_EDITED",
        dues_id=item.id,
        reason=f"Valor: {before} → {f.money(item.amount)}",
        changes={"before": before, "after": f.money(item.amount)},
    )
    session.flush()
    return f.dues_detail(session, user_id, team_id, item.id)
