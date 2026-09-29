"""Financial commands serialize on Team; callers commit once, or roll back everything."""

import calendar
import hashlib
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import finance as f
from app.application.finance_commands import (
    CancelEntryInput,
    DuesActionInput,
    EntryInput,
    GenerateInput,
    PaymentInput,
    SettingsInput,
)
from app.application.notification_events import finance_notice
from app.application.roster import roster_name
from app.domain.notifications import NotificationType
from app.domain.policies import Conflict, NotFound
from app.infrastructure.finance_models import CashEntry, DuesSettings, FinanceAudit, MonthlyDues
from app.infrastructure.models import Player, TeamMembership


def audit(
    session: Session,
    team_id: UUID,
    user_id: UUID,
    action: str,
    *,
    dues_id: UUID | None = None,
    entry_id: UUID | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        FinanceAudit(
            team_id=team_id,
            actor_id=user_id,
            action=action,
            dues_id=dues_id,
            entry_id=entry_id,
            reason=reason,
        )
    )


def settings(
    session: Session, user_id: UUID, team_id: UUID, data: SettingsInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    item = session.scalar(select(DuesSettings).where(DuesSettings.team_id == team_id))
    f.version(item.version if item else 0, data.expected_version)
    if item is None:
        item = DuesSettings(team_id=team_id)
        session.add(item)
    else:
        item.version += 1
    item.amount, item.due_day, item.active, item.updated_by = (
        data.amount,
        data.due_day,
        data.active,
        user_id,
    )
    audit(
        session,
        team_id,
        user_id,
        "SETTINGS",
        reason=f"BRL {f.money(data.amount)}; dia {data.due_day}; ativa={data.active}",
    )
    session.flush()
    return f.settings_read(item)


def generation(
    session: Session, user_id: UUID, team_id: UUID, competence: date
) -> tuple[dict[str, object], list[UUID], DuesSettings]:
    f.authorize_write(session, user_id, team_id)
    config = session.scalar(select(DuesSettings).where(DuesSettings.team_id == team_id))
    if not config or not config.active:
        raise Conflict("Configure e ative a mensalidade antes de gerar cobranças.")
    active = list(
        session.scalars(
            select(TeamMembership.id)
            .where(TeamMembership.team_id == team_id, TeamMembership.status == "active")
            .order_by(TeamMembership.id)
        )
    )
    existing = set(
        session.scalars(
            select(MonthlyDues.membership_id).where(
                MonthlyDues.team_id == team_id, MonthlyDues.competence == competence
            )
        )
    )
    eligible = [member for member in active if member not in existing]
    due_date = competence.replace(
        day=min(config.due_day, calendar.monthrange(competence.year, competence.month)[1])
    )
    token = hashlib.sha256(
        f"{team_id}|{competence}|{config.version}|{config.amount}|{due_date}|{eligible}".encode()
    ).hexdigest()
    return (
        {
            "count": len(eligible),
            "ignored": len(active) - len(eligible),
            "total": f.money(config.amount * len(eligible)),
            "due_date": due_date,
            "amount": f.money(config.amount),
            "preview_token": token,
        },
        eligible,
        config,
    )


def generate(
    session: Session, user_id: UUID, team_id: UUID, data: GenerateInput
) -> dict[str, object]:
    preview, members, config = generation(session, user_id, team_id, data.competence)
    f.confirmed(data.confirm)
    if preview["preview_token"] != data.preview_token:
        raise Conflict("A previsão mudou. Confira a quantidade e o valor novamente.")
    for membership_id in members:
        item = MonthlyDues(
            team_id=team_id,
            membership_id=membership_id,
            competence=data.competence,
            amount=config.amount,
            due_date=preview["due_date"],
            created_by=user_id,
        )
        session.add(item)
        session.flush()
        audit(session, team_id, user_id, "GENERATED", dues_id=item.id)
        finance_notice(session, item, NotificationType.FINANCE_CHARGE_CREATED)
    session.flush()
    return preview


def check_date(value: date) -> None:
    if value > date.today():
        raise Conflict("Informe a data em que o pagamento ou lançamento já ocorreu.")


def existing_command(session: Session, team_id: UUID, command_id: UUID) -> CashEntry | None:
    return session.scalar(
        select(CashEntry).where(CashEntry.team_id == team_id, CashEntry.command_id == command_id)
    )


def pay(
    session: Session, user_id: UUID, team_id: UUID, dues_id: UUID, data: PaymentInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    item = f.get_dues(session, team_id, dues_id)
    f.confirmed(data.confirm)
    old = existing_command(session, team_id, data.command_id)
    if old:
        if (
            old.dues_id != item.id
            or old.amount != data.amount
            or old.entry_date != data.entry_date
            or old.payment_method != data.payment_method
            or old.note != data.note
        ):
            raise Conflict("Este identificador já foi usado com outros dados.")
        return f.dues_detail(session, user_id, team_id, item.id)
    f.version(item.version, data.expected_version)
    if item.status != "PENDING":
        raise Conflict("Somente cobranças pendentes podem receber pagamentos.")
    check_date(data.entry_date)
    paid = f.received(session, item.id)
    if data.amount > item.amount - paid:
        raise Conflict("O pagamento não pode ultrapassar o saldo devedor.")
    member, player = session.execute(
        select(TeamMembership, Player)
        .join(Player, Player.id == TeamMembership.player_id)
        .where(TeamMembership.id == item.membership_id)
    ).one()
    entry = CashEntry(
        team_id=team_id,
        dues_id=item.id,
        command_id=data.command_id,
        kind="INCOME",
        category="Mensalidade",
        description=f"Mensalidade {roster_name(member, player)} — {item.competence:%m/%Y}",
        amount=data.amount,
        entry_date=data.entry_date,
        payment_method=data.payment_method,
        note=data.note,
        created_by=user_id,
    )
    session.add(entry)
    item.status = "PAID" if paid + data.amount == item.amount else "PENDING"
    item.version += 1
    session.flush()
    finance_notice(
        session,
        item,
        NotificationType.FINANCE_PAYMENT_REGISTERED,
        entry=entry,
        remaining=item.amount - paid - data.amount,
    )
    audit(
        session, team_id, user_id, "PAYMENT", dues_id=item.id, entry_id=entry.id, reason=data.note
    )
    session.flush()
    return f.dues_detail(session, user_id, team_id, item.id)


def dues_action(
    session: Session, user_id: UUID, team_id: UUID, dues_id: UUID, data: DuesActionInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    item = f.get_dues(session, team_id, dues_id)
    f.confirmed(data.confirm)
    f.version(item.version, data.expected_version)
    if data.action == "undo_exemption":
        if item.status != "EXEMPT":
            raise Conflict("Esta cobrança não está isenta.")
        item.status = "PENDING"
    else:
        if item.status == "CANCELLED":
            raise Conflict("Esta cobrança já foi cancelada.")
        if f.received(session, item.id):
            raise Conflict("Estorne os pagamentos válidos antes de isentar ou cancelar a cobrança.")
        if data.action == "exempt" and item.status != "PENDING":
            raise Conflict("Somente cobrança pendente pode ser isenta.")
        if data.action == "cancel" and not data.reason:
            raise Conflict("Informe o motivo do cancelamento.")
        item.status = "EXEMPT" if data.action == "exempt" else "CANCELLED"
    item.version += 1
    audit(session, team_id, user_id, data.action.upper(), dues_id=item.id, reason=data.reason)
    session.flush()
    return f.dues_detail(session, user_id, team_id, item.id)


def manual_entry(
    session: Session, user_id: UUID, team_id: UUID, data: EntryInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    f.confirmed(data.confirm)
    old = existing_command(session, team_id, data.command_id)
    fields = data.model_dump(exclude={"confirm", "command_id"})
    if old:
        if old.dues_id or any(getattr(old, key) != value for key, value in fields.items()):
            raise Conflict("Este identificador já foi usado com outros dados.")
        return f.entry_read(old)
    check_date(data.entry_date)
    item = CashEntry(team_id=team_id, command_id=data.command_id, created_by=user_id, **fields)
    session.add(item)
    session.flush()
    audit(session, team_id, user_id, "MANUAL_ENTRY", entry_id=item.id)
    session.flush()
    return f.entry_read(item)


def cancel_entry(
    session: Session, user_id: UUID, team_id: UUID, entry_id: UUID, data: CancelEntryInput
) -> dict[str, object]:
    f.authorize_write(session, user_id, team_id)
    item = session.scalar(
        select(CashEntry)
        .where(CashEntry.team_id == team_id, CashEntry.id == entry_id)
        .with_for_update()
    )
    if not item:
        raise NotFound("Lançamento não encontrado.")
    f.confirmed(data.confirm)
    if item.cancelled_at:
        raise Conflict("Este lançamento já foi estornado.")
    dues = f.get_dues(session, team_id, item.dues_id) if item.dues_id else None
    if dues:
        if data.expected_dues_version is None:
            raise Conflict("Atualize a cobrança antes de estornar o pagamento.")
        f.version(dues.version, data.expected_dues_version)
        dues.version += 1
        dues.status = "PENDING"
    item.cancelled_at, item.cancelled_by, item.cancellation_reason = (
        datetime.now(UTC),
        user_id,
        data.reason,
    )
    audit(
        session,
        team_id,
        user_id,
        "REVERSAL",
        dues_id=item.dues_id,
        entry_id=item.id,
        reason=data.reason,
    )
    session.flush()
    if dues:
        finance_notice(session, dues, NotificationType.FINANCE_PAYMENT_REVERSED, entry=item)
    return f.entry_read(item)
