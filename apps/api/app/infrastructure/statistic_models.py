"""Append-only administrative deltas; match records remain the sporting source."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class StatisticAdjustment(Entity, Base):
    __tablename__ = "statistic_adjustments"
    team_id: Mapped[UUID]
    membership_id: Mapped[UUID]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    command_id: Mapped[UUID]
    expected_state: Mapped[str] = mapped_column(String(64))
    goals_delta: Mapped[int] = mapped_column(Integer)
    yellow_cards_delta: Mapped[int] = mapped_column(Integer)
    red_cards_delta: Mapped[int] = mapped_column(Integer)
    previous_totals: Mapped[dict[str, int]] = mapped_column(JSONB)
    new_totals: Mapped[dict[str, int]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        UniqueConstraint("team_id", "command_id", name="uq_statistic_adjustments_command"),
        CheckConstraint(
            "goals_delta <> 0 OR yellow_cards_delta <> 0 OR red_cards_delta <> 0", name="nonzero"
        ),
        Index("ix_statistic_adjustments_member", "team_id", "membership_id"),
    )
