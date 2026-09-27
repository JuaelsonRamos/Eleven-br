from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class TeamJoinRequest(Entity, Base):
    __tablename__ = "team_join_requests"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    membership_id: Mapped[UUID | None]
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name="fk_join_requests_membership",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="status"
        ),
        CheckConstraint(
            "(status = 'PENDING' AND resolved_at IS NULL AND resolved_by IS NULL) OR "
            "(status <> 'PENDING' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)",
            name="resolution",
        ),
        CheckConstraint(
            "(status = 'APPROVED' AND membership_id IS NOT NULL) OR "
            "(status <> 'APPROVED' AND membership_id IS NULL)",
            name="approval",
        ),
        Index(
            "uq_join_requests_pending",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_join_requests_user_created", "user_id", "created_at"),
        Index("ix_join_requests_team_status", "team_id", "status"),
    )
