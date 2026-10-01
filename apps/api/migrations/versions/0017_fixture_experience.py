"""Explicit callups, guest presence and retained bilateral fixture decisions.

Revision ID: 0017
Revises: 0016
Existing fixture answers remain selected; absent answers never imply a callup.
Ordinary peladas keep their existing participation semantics.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

OLD_TYPES = (
    "TEAM_JOIN_REQUEST",
    "TEAM_JOIN_APPROVED",
    "TEAM_JOIN_REJECTED",
    "EVENT_CREATED",
    "EVENT_UPDATED",
    "EVENT_CANCELLED",
    "ATTENDANCE_REMINDER",
    "FINANCE_CHARGE_CREATED",
    "FINANCE_PAYMENT_REGISTERED",
    "FINANCE_PAYMENT_REVERSED",
    "CHALLENGE_RECEIVED",
    "CHALLENGE_ACCEPTED",
    "CHALLENGE_REJECTED",
    "CHALLENGE_CANCELLED",
    "FIXTURE_SCORE_REPORTED",
    "FIXTURE_SCORE_CONFIRMED",
    "FIXTURE_SCORE_DISPUTED",
    "FIXTURE_REVIEW_AVAILABLE",
)
NEW_TYPES = ("FIXTURE_CALLED_UP", "FIXTURE_CALLUP_REMOVED", "FIXTURE_PROPOSAL", "FIXTURE_CHANGED")


def notifications(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        "type", "notifications", "type IN (" + ", ".join(repr(k) for k in kinds) + ")"
    )


def upgrade() -> None:
    op.add_column(
        "events", sa.Column("callup_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "event_attendance",
        sa.Column("called_up", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.drop_constraint(op.f("ck_event_attendance_response"), "event_attendance", type_="check")
    op.create_check_constraint(
        "response", "event_attendance", "response IN ('VOU', 'NAO_VOU', 'PENDENTE')"
    )
    op.execute(
        "UPDATE event_attendance SET called_up = true FROM events "
        "WHERE events.id = event_attendance.event_id AND events.fixture_id IS NOT NULL"
    )
    op.add_column(
        "event_guests", sa.Column("response", sa.String(16), nullable=False, server_default="VOU")
    )
    op.add_column("event_guests", sa.Column("command_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_event_guests_command", "event_guests", ["event_id", "command_id"]
    )
    op.create_check_constraint(
        "response", "event_guests", "response IN ('VOU', 'NAO_VOU', 'PENDENTE')"
    )
    op.add_column(
        "team_fixtures",
        sa.Column("status", sa.String(24), nullable=False, server_default="SCHEDULED"),
    )
    op.add_column(
        "team_fixtures", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_check_constraint(
        "status", "team_fixtures", "status IN ('SCHEDULED', 'CANCELLED', 'WITHDRAWN')"
    )
    op.create_table(
        "fixture_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("fixture_id", sa.Uuid(), sa.ForeignKey("team_fixtures.id"), nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.String(500)),
        sa.Column("before", JSONB(), nullable=False),
        sa.Column("proposed", JSONB(), nullable=False),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("team_id", "command_id", name="uq_fixture_proposals_command"),
        sa.CheckConstraint("kind IN ('CHANGE', 'CANCEL', 'WITHDRAW')", name="kind"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')", name="status"
        ),
    )
    op.create_index(
        "uq_fixture_proposals_pending",
        "fixture_proposals",
        ["fixture_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    notifications(OLD_TYPES + NEW_TYPES)


def downgrade() -> None:
    # Never erase participation or negotiation history that 0016 cannot represent.
    used = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM fixture_proposals) OR "
            "EXISTS (SELECT 1 FROM event_attendance WHERE called_up OR response = 'PENDENTE') OR "
            "EXISTS (SELECT 1 FROM events WHERE callup_version > 1) OR "
            "EXISTS (SELECT 1 FROM event_guests WHERE command_id IS NOT NULL "
            "OR response <> 'VOU') OR "
            "EXISTS (SELECT 1 FROM team_fixtures WHERE version > 1 OR status <> 'SCHEDULED') OR "
            "EXISTS (SELECT 1 FROM notifications WHERE type IN "
            "('FIXTURE_CALLED_UP', 'FIXTURE_CALLUP_REMOVED', "
            "'FIXTURE_PROPOSAL', 'FIXTURE_CHANGED'))"
        )
    )
    if used:
        raise RuntimeError("0017 contém histórico de confrontos; faça rollback só da aplicação.")
    notifications(OLD_TYPES)
    op.drop_table("fixture_proposals")
    op.drop_constraint(op.f("ck_team_fixtures_status"), "team_fixtures", type_="check")
    op.drop_column("team_fixtures", "version")
    op.drop_column("team_fixtures", "status")
    op.drop_constraint(op.f("ck_event_guests_response"), "event_guests", type_="check")
    op.drop_constraint("uq_event_guests_command", "event_guests", type_="unique")
    op.drop_column("event_guests", "command_id")
    op.drop_column("event_guests", "response")
    op.drop_constraint(op.f("ck_event_attendance_response"), "event_attendance", type_="check")
    op.create_check_constraint("response", "event_attendance", "response IN ('VOU', 'NAO_VOU')")
    op.drop_column("event_attendance", "called_up")
    op.drop_column("events", "callup_version")
