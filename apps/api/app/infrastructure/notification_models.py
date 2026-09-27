from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(600))
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[UUID | None]
    action: Mapped[str | None] = mapped_column(String(40))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
        CheckConstraint(
            "type IN ('TEAM_JOIN_REQUEST', 'TEAM_JOIN_APPROVED', 'TEAM_JOIN_REJECTED', "
            "'EVENT_CREATED', 'EVENT_UPDATED', 'EVENT_CANCELLED', 'ATTENDANCE_REMINDER', "
            "'FINANCE_CHARGE_CREATED', 'FINANCE_PAYMENT_REGISTERED', 'FINANCE_PAYMENT_REVERSED')",
            name="type",
        ),
        CheckConstraint(
            "action IS NULL OR action IN ('OPEN_TEAM', 'OPEN_JOIN_REQUESTS', "
            "'OPEN_EVENT', 'OPEN_FINANCE_CHARGE')",
            name="action",
        ),
        CheckConstraint(
            "(entity_type IS NULL AND entity_id IS NULL) OR "
            "(entity_type IS NOT NULL AND entity_type IN "
            "('team', 'join_request', 'event', 'finance_charge') "
            "AND entity_id IS NOT NULL)",
            name="entity",
        ),
        CheckConstraint("length(trim(title)) > 0 AND length(trim(message)) > 0", name="text"),
        CheckConstraint("length(trim(dedup_key)) > 0", name="dedup"),
        Index("ix_notifications_user_created", "user_id", "created_at", "id"),
        Index("ix_notifications_user_unread", "user_id", postgresql_where=text("read_at IS NULL")),
    )
