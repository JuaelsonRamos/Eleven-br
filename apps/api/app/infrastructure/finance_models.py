"""Internal BRL ledger. No gateway credentials, mutable balance or Player ownership."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class DuesSettings(Entity, Base):
    __tablename__ = "dues_settings"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    due_day: Mapped[int]
    active: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(server_default="1")
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    repeat_monthly: Mapped[bool] = mapped_column(Boolean, server_default="false")
    next_competence: Mapped[date | None]
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day"),
        CheckConstraint("version > 0", name="version"),
    )


class MonthlyDues(Entity, Base):
    __tablename__ = "monthly_dues"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    membership_id: Mapped[UUID]
    competence: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    version: Mapped[int] = mapped_column(server_default="1")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        UniqueConstraint(
            "team_id", "membership_id", "competence", name="uq_dues_membership_competence"
        ),
        UniqueConstraint("team_id", "id"),
        CheckConstraint("EXTRACT(DAY FROM competence) = 1", name="competence"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("status IN ('PENDING', 'PAID', 'EXEMPT', 'CANCELLED')", name="status"),
        Index("ix_monthly_dues_team_competence", "team_id", "competence"),
    )


class CashEntry(Entity, Base):
    __tablename__ = "cash_entries"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    dues_id: Mapped[UUID | None]
    command_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    entry_date: Mapped[date]
    payment_method: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(server_default="1")
    __table_args__ = (
        ForeignKeyConstraint(["team_id", "dues_id"], ["monthly_dues.team_id", "monthly_dues.id"]),
        UniqueConstraint("team_id", "id"),
        UniqueConstraint("team_id", "command_id", name="uq_cash_command"),
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("kind IN ('INCOME', 'EXPENSE')", name="kind"),
        CheckConstraint(
            "length(trim(category)) > 0 AND length(trim(description)) > 0", name="description"
        ),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('PIX', 'CASH', 'CARD', 'OTHER')",
            name="method",
        ),
        CheckConstraint(
            "dues_id IS NULL OR (kind = 'INCOME' AND payment_method IS NOT NULL "
            "AND category = 'Mensalidade')",
            name="dues_income",
        ),
        CheckConstraint(
            "(cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_reason IS NULL) OR "
            "(cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancellation_reason IS NOT NULL AND length(trim(cancellation_reason)) > 0)",
            name="cancellation",
        ),
        Index("ix_cash_team_dues", "team_id", "dues_id"),
        Index("ix_cash_team_date", "team_id", "entry_date"),
    )


class FinanceAudit(Entity, Base):
    __tablename__ = "finance_audit"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    dues_id: Mapped[UUID | None]
    entry_id: Mapped[UUID | None]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(500))
    changes: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))
    __table_args__ = (
        ForeignKeyConstraint(["team_id", "dues_id"], ["monthly_dues.team_id", "monthly_dues.id"]),
        ForeignKeyConstraint(["team_id", "entry_id"], ["cash_entries.team_id", "cash_entries.id"]),
        Index("ix_finance_audit_team_dues", "team_id", "dues_id"),
    )


class FinancePreferences(Entity, Base):
    __tablename__ = "finance_preferences"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), unique=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default="0")
    opening_date: Mapped[date | None]
    share_summary: Mapped[bool] = mapped_column(Boolean, server_default="false")
    categories: Mapped[dict[str, list[str]]] = mapped_column(JSONB, server_default="{}")
    version: Mapped[int] = mapped_column(server_default="1")
