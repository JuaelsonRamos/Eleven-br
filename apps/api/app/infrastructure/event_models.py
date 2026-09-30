"""Persistent occurrences, generated from a weekly template within a bounded window."""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure import opponent_models  # noqa: F401  # Registers the fixture FK target.
from app.infrastructure.models import Base, Entity


class EventSeries(Entity, Base):
    __tablename__ = "event_series"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    modality: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(100))
    time: Mapped[time] = mapped_column(Time(timezone=False))
    location: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    __table_args__ = (
        UniqueConstraint("team_id", "id", name="uq_event_series_team_id"),
        CheckConstraint("end_date IS NULL OR end_date - start_date >= 7", name="dates"),
        CheckConstraint("status IN ('active', 'cancelled')", name="status"),
        CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(location)) > 0", name="required_text"
        ),
    )


class Event(Entity, Base):
    __tablename__ = "events"
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    creation_key: Mapped[UUID | None]
    creation_hash: Mapped[str | None] = mapped_column(String(64))
    series_id: Mapped[UUID | None]
    recurrence_date: Mapped[date | None] = mapped_column(Date)
    modality: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(100))
    date: Mapped[date] = mapped_column(Date)
    time: Mapped[time] = mapped_column(Time(timezone=False))
    location: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(2000))
    opponent: Mapped[str | None] = mapped_column(String(100))
    # Official fixture between two registered teams; free-text games keep it empty.
    fixture_id: Mapped[UUID | None] = mapped_column(ForeignKey("team_fixtures.id"))
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    __table_args__ = (
        UniqueConstraint("team_id", "id", name="uq_events_team_id"),
        UniqueConstraint("team_id", "creation_key", name="uq_events_creation_key"),
        UniqueConstraint("team_id", "fixture_id", name="uq_events_team_fixture"),
        CheckConstraint(
            "fixture_id IS NULL OR (kind = 'JOGO' AND series_id IS NULL)", name="fixture"
        ),
        CheckConstraint("(creation_key IS NULL) = (creation_hash IS NULL)", name="creation_key"),
        UniqueConstraint("series_id", "recurrence_date", name="uq_events_series_date"),
        ForeignKeyConstraint(["team_id", "series_id"], ["event_series.team_id", "event_series.id"]),
        CheckConstraint("kind IN ('PELADA', 'JOGO')", name="kind"),
        CheckConstraint("status IN ('open', 'cancelled')", name="status"),
        CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(location)) > 0", name="required_text"
        ),
        CheckConstraint(
            "(series_id IS NULL AND recurrence_date IS NULL) OR "
            "(series_id IS NOT NULL AND recurrence_date IS NOT NULL AND kind = 'PELADA')",
            name="recurrence",
        ),
        Index("ix_events_team_date", "team_id", "date", "time"),
    )


class EventAttendance(Entity, Base):
    __tablename__ = "event_attendance"
    team_id: Mapped[UUID]
    event_id: Mapped[UUID]
    membership_id: Mapped[UUID]
    response: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        ForeignKeyConstraint(["team_id", "event_id"], ["events.team_id", "events.id"]),
        ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        UniqueConstraint("event_id", "membership_id", name="uq_event_attendance_member"),
        CheckConstraint("response IN ('VOU', 'NAO_VOU')", name="response"),
    )


class EventGuest(Entity, Base):
    __tablename__ = "event_guests"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name"),
        UniqueConstraint("event_id", "id", name="uq_event_guests_scope"),
    )
