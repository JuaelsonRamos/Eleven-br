"""Opponent challenges, shared fixtures, bilateral scores and reliability reviews."""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class TeamChallenge(Entity, Base):
    """Proposal from one team to another; venue is from the challenger's point of view."""

    __tablename__ = "team_challenges"
    challenger_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    challenged_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    # São Paulo month of sending; `charged` marks the Free monthly challenge credit.
    competence: Mapped[date] = mapped_column(Date)
    charged: Mapped[bool] = mapped_column(Boolean)
    modality: Mapped[str] = mapped_column(String(40))
    date: Mapped[date] = mapped_column(Date)
    time: Mapped[time] = mapped_column(Time(timezone=False))
    location: Mapped[str] = mapped_column(String(200))
    venue: Mapped[str] = mapped_column(String(8))
    notes: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    command_id: Mapped[UUID]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("challenger_team_id", "command_id", name="uq_team_challenges_command"),
        CheckConstraint("challenger_team_id <> challenged_team_id", name="distinct_teams"),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')", name="status"
        ),
        CheckConstraint("venue IN ('HOME', 'AWAY')", name="venue"),
        CheckConstraint("modality IN ('campo', 'society', 'futsal')", name="modality"),
        CheckConstraint("length(trim(location)) > 0", name="location"),
        CheckConstraint(
            "(status = 'PENDING') = (resolved_at IS NULL AND resolved_by IS NULL)",
            name="resolution",
        ),
        CheckConstraint("EXTRACT(DAY FROM competence) = 1", name="competence"),
        Index("ix_team_challenges_challenger", "challenger_team_id", "created_at"),
        Index("ix_team_challenges_challenged", "challenged_team_id", "created_at"),
        # Database guards for concurrent requests: one Free credit per team and month,
        # and never two pending equivalent proposals (same pair, modality and kickoff).
        Index(
            "uq_team_challenges_monthly_credit",
            "challenger_team_id",
            "competence",
            unique=True,
            postgresql_where=text("charged"),
        ),
        Index(
            "uq_team_challenges_pending_proposal",
            text("LEAST(challenger_team_id, challenged_team_id)"),
            text("GREATEST(challenger_team_id, challenged_team_id)"),
            "modality",
            "date",
            "time",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class TeamFixture(Entity, Base):
    """The single shared record of an accepted challenge; each team sees it in its agenda."""

    __tablename__ = "team_fixtures"
    challenge_id: Mapped[UUID] = mapped_column(ForeignKey("team_challenges.id"), unique=True)
    home_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    modality: Mapped[str] = mapped_column(String(40))
    date: Mapped[date] = mapped_column(Date)
    time: Mapped[time] = mapped_column(Time(timezone=False))
    location: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(500))
    result_status: Mapped[str] = mapped_column(String(16), server_default="NONE")
    status: Mapped[str] = mapped_column(String(24), server_default="SCHEDULED")
    version: Mapped[int] = mapped_column(server_default="1")
    # Official score only when both sides agree (VALIDATED).
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('SCHEDULED', 'CANCELLED', 'WITHDRAWN')", name="status"),
        CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
        CheckConstraint(
            "result_status IN ('NONE', 'PENDING', 'VALIDATED', 'DISPUTED')", name="result_status"
        ),
        CheckConstraint(
            "(result_status = 'VALIDATED' AND validated_at IS NOT NULL "
            "AND home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999) OR "
            "(result_status <> 'VALIDATED' AND validated_at IS NULL "
            "AND home_score IS NULL AND away_score IS NULL)",
            name="official_result",
        ),
        Index("ix_team_fixtures_home", "home_team_id", "date"),
        Index("ix_team_fixtures_away", "away_team_id", "date"),
    )


class FixtureScore(Entity, Base):
    """One score per side; CONFIRMED means that side agreed with the other side's report."""

    __tablename__ = "fixture_scores"
    fixture_id: Mapped[UUID] = mapped_column(ForeignKey("team_fixtures.id"))
    side: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16))
    home_score: Mapped[int]
    away_score: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("fixture_id", "side", name="uq_fixture_scores_side"),
        CheckConstraint("side IN ('HOME', 'AWAY')", name="side"),
        CheckConstraint("kind IN ('REPORTED', 'CONFIRMED')", name="kind"),
        CheckConstraint(
            "home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999", name="score"
        ),
    )


class FixtureReview(Entity, Base):
    """Reliability review of the other side by `side`; never changes the sporting result."""

    __tablename__ = "fixture_reviews"
    fixture_id: Mapped[UUID] = mapped_column(ForeignKey("team_fixtures.id"))
    side: Mapped[str] = mapped_column(String(8))
    attended: Mapped[bool] = mapped_column(Boolean)
    punctual: Mapped[bool] = mapped_column(Boolean)
    kept_agreement: Mapped[bool] = mapped_column(Boolean)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("fixture_id", "side", name="uq_fixture_reviews_side"),
        CheckConstraint("side IN ('HOME', 'AWAY')", name="side"),
    )


class FixtureProposal(Entity, Base):
    """Bilateral changes and unilateral withdrawal, retained as the fixture's history."""

    __tablename__ = "fixture_proposals"
    fixture_id: Mapped[UUID] = mapped_column(ForeignKey("team_fixtures.id"))
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    command_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    reason: Mapped[str | None] = mapped_column(String(500))
    before: Mapped[dict[str, object]] = mapped_column(JSONB)
    proposed: Mapped[dict[str, object]] = mapped_column(JSONB)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("team_id", "command_id", name="uq_fixture_proposals_command"),
        CheckConstraint("kind IN ('CHANGE', 'CANCEL', 'WITHDRAW')", name="kind"),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')", name="status"
        ),
        Index(
            "uq_fixture_proposals_pending",
            "fixture_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )
