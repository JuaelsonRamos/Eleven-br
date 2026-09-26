from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class MatchEvent(Entity, Base):
    __tablename__ = "match_events"
    team_id: Mapped[UUID]
    event_id: Mapped[UUID]
    match_id: Mapped[UUID]
    formation_id: Mapped[UUID]
    squad_id: Mapped[UUID]
    type: Mapped[str] = mapped_column(String(32))
    participant_id: Mapped[UUID]
    assist_participant_id: Mapped[UUID | None]
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id", "match_id"],
            [
                "event_matches.team_id",
                "event_matches.event_id",
                "event_matches.formation_id",
                "event_matches.id",
            ],
            name="fk_match_events_match_scope",
        ),
        ForeignKeyConstraint(
            ["formation_id", "squad_id", "participant_id"],
            [
                "formation_participants.formation_id",
                "formation_participants.squad_id",
                "formation_participants.id",
            ],
            name="fk_match_events_participant",
        ),
        ForeignKeyConstraint(
            ["formation_id", "squad_id", "assist_participant_id"],
            [
                "formation_participants.formation_id",
                "formation_participants.squad_id",
                "formation_participants.id",
            ],
            name="fk_match_events_assist",
        ),
        CheckConstraint("type IN ('GOAL', 'YELLOW_CARD', 'RED_CARD')", name="type"),
        CheckConstraint("assist_participant_id IS NULL OR type = 'GOAL'", name="assist_goal"),
        CheckConstraint(
            "assist_participant_id IS NULL OR assist_participant_id <> participant_id",
            name="different_assist",
        ),
        Index("ix_match_events_match_id", "match_id"),
    )
