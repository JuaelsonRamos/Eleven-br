from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class Formation(Entity, Base):
    __tablename__ = "event_formations"
    team_id: Mapped[UUID]
    event_id: Mapped[UUID] = mapped_column(unique=True)
    version: Mapped[int]
    team_count: Mapped[int]
    method: Mapped[str] = mapped_column(String(24))
    roster_fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(["team_id", "event_id"], ["events.team_id", "events.id"]),
        UniqueConstraint("team_id", "event_id", "id", name="uq_event_formations_scope"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("team_count BETWEEN 2 AND 32", name="team_count"),
        CheckConstraint("method = 'random'", name="method"),
    )


class FormationSquad(Entity, Base):
    __tablename__ = "formation_squads"
    formation_id: Mapped[UUID] = mapped_column(ForeignKey("event_formations.id"))
    number: Mapped[int]
    __table_args__ = (
        UniqueConstraint("formation_id", "id", name="uq_formation_squads_scope"),
        UniqueConstraint("formation_id", "number", name="uq_formation_squads_number"),
        CheckConstraint("number BETWEEN 1 AND 32", name="number"),
    )


class FormationParticipant(Entity, Base):
    __tablename__ = "formation_participants"
    team_id: Mapped[UUID]
    event_id: Mapped[UUID]
    formation_id: Mapped[UUID]
    membership_id: Mapped[UUID | None]
    guest_id: Mapped[UUID | None]
    squad_id: Mapped[UUID | None]
    name: Mapped[str] = mapped_column(String(80))
    goalkeeper: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id"],
            ["event_formations.team_id", "event_formations.event_id", "event_formations.id"],
        ),
        ForeignKeyConstraint(
            ["formation_id", "squad_id"], ["formation_squads.formation_id", "formation_squads.id"]
        ),
        ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        ForeignKeyConstraint(
            ["event_id", "guest_id"], ["event_guests.event_id", "event_guests.id"]
        ),
        UniqueConstraint("formation_id", "membership_id", name="uq_formation_participants_member"),
        UniqueConstraint("formation_id", "guest_id", name="uq_formation_participants_guest"),
        CheckConstraint("num_nonnulls(membership_id, guest_id) = 1", name="source"),
        CheckConstraint("length(trim(name)) > 0", name="name"),
    )
