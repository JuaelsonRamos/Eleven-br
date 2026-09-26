from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class EventMatch(Entity, Base):
    __tablename__ = "event_matches"
    team_id: Mapped[UUID]
    event_id: Mapped[UUID]
    formation_id: Mapped[UUID]
    home_formation_team_id: Mapped[UUID]
    away_formation_team_id: Mapped[UUID]
    home_score: Mapped[int] = mapped_column(default=0)
    away_score: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED")
    version: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    corrected_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id"],
            ["event_formations.team_id", "event_formations.event_id", "event_formations.id"],
        ),
        ForeignKeyConstraint(
            ["formation_id", "home_formation_team_id"],
            ["formation_squads.formation_id", "formation_squads.id"],
            name="fk_event_matches_home_squad",
        ),
        ForeignKeyConstraint(
            ["formation_id", "away_formation_team_id"],
            ["formation_squads.formation_id", "formation_squads.id"],
            name="fk_event_matches_away_squad",
        ),
        CheckConstraint("home_formation_team_id <> away_formation_team_id", name="different_teams"),
        CheckConstraint(
            "home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999", name="scores"
        ),
        CheckConstraint(
            "status IN ('SCHEDULED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED')", name="status"
        ),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint(
            "status NOT IN ('IN_PROGRESS', 'FINISHED') OR started_at IS NOT NULL", name="started"
        ),
        CheckConstraint("status <> 'FINISHED' OR finished_at IS NOT NULL", name="finished"),
        Index("ix_event_matches_event_id", "event_id"),
    )
