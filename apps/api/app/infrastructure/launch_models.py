"""Recovery and team administration records; sporting history stays relational."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class PasswordRecovery(Entity, Base):
    __tablename__ = "password_recoveries"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    handle_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(254))
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("attempts BETWEEN 0 AND 5", name="attempts"),)


class TeamAudit(Entity, Base):
    __tablename__ = "team_audit"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    entity_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict[str, object]] = mapped_column(JSONB)
    after: Mapped[dict[str, object]] = mapped_column(JSONB)


class Lineup(Entity, Base):
    __tablename__ = "lineups"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    event_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(80))
    modality: Mapped[str] = mapped_column(String(40))
    formation: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(default=1)
    command_id: Mapped[UUID]
    creation_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("team_id", "id", name="uq_lineups_team_id"),
        UniqueConstraint("team_id", "command_id", name="uq_lineups_command"),
        ForeignKeyConstraint(["team_id", "event_id"], ["events.team_id", "events.id"]),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("modality IN ('campo', 'society', 'futsal')", name="modality"),
    )


class LineupPosition(Entity, Base):
    __tablename__ = "lineup_positions"
    team_id: Mapped[UUID]
    lineup_id: Mapped[UUID]
    membership_id: Mapped[UUID]
    slot: Mapped[int]
    __table_args__ = (
        ForeignKeyConstraint(["team_id", "lineup_id"], ["lineups.team_id", "lineups.id"]),
        ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        UniqueConstraint("lineup_id", "slot", name="uq_lineup_slot"),
        UniqueConstraint("lineup_id", "membership_id", name="uq_lineup_member"),
        CheckConstraint("slot >= 0 AND slot < 11", name="slot"),
    )
