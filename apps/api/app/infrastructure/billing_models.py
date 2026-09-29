"""Only provider references and access periods: no card data or raw webhook payloads."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class TeamBilling(Entity, Base):
    __tablename__ = "team_billing"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), unique=True)
    plan_code: Mapped[str] = mapped_column(String(40), default="PRO_MONTHLY")
    provider: Mapped[str] = mapped_column(String(16), default="asaas")
    environment: Mapped[str] = mapped_column(String(16))
    customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    customer_attempted: Mapped[bool] = mapped_column(default=False)
    grant_active: Mapped[bool] = mapped_column(default=False)
    grant_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("environment IN ('sandbox', 'production')", name="environment"),
    )


class BillingSubscription(Entity, Base):
    __tablename__ = "billing_subscriptions"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    command_id: Mapped[UUID]
    method: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    plan_code: Mapped[str] = mapped_column(String(40))
    provider_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    checkout_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    # CREATING is durable before an external POST. UNKNOWN must reconcile, never blindly retry.
    operation_status: Mapped[str] = mapped_column(String(24), default="NEW")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("team_id", "command_id", name="uq_billing_subscriptions_command"),
        CheckConstraint("method IN ('PIX', 'CREDIT_CARD')", name="method"),
        CheckConstraint("amount > 0", name="amount"),
    )


class BillingPayment(Entity, Base):
    __tablename__ = "billing_payments"
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_subscriptions.id"), index=True
    )
    provider_id: Mapped[str] = mapped_column(String(100), unique=True)
    due_date: Mapped[date]
    period_end: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(40))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BillingWebhook(Entity, Base):
    __tablename__ = "billing_webhooks"
    provider: Mapped[str] = mapped_column(String(16), default="asaas")
    event_id: Mapped[str] = mapped_column(String(160), unique=True)
    event_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24))


class BillingAudit(Entity, Base):
    __tablename__ = "billing_audit"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(48))
    origin: Mapped[str] = mapped_column(String(24))
    reference: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(String(300))
