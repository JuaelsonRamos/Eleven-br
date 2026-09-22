"""events_attendance

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_membership_permissions_permission"), "membership_permissions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_membership_permissions_permission"),
        "membership_permissions",
        "permission IN ('manage_team', 'manage_members', 'manage_events')",
    )
    op.create_table(
        "event_series",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("modality", sa.String(40), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date - start_date >= 7",
            name=op.f("ck_event_series_dates"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled')", name=op.f("ck_event_series_status")
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(location)) > 0",
            name=op.f("ck_event_series_required_text"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_event_series_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_series")),
        sa.UniqueConstraint("team_id", "id", name="uq_event_series_team_id"),
    )
    op.create_table(
        "events",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("recurrence_date", sa.Date(), nullable=True),
        sa.Column("modality", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("opponent", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(series_id IS NULL AND recurrence_date IS NULL) OR "
            "(series_id IS NOT NULL AND recurrence_date IS NOT NULL AND kind = 'PELADA')",
            name=op.f("ck_events_recurrence"),
        ),
        sa.CheckConstraint("kind IN ('PELADA', 'JOGO')", name=op.f("ck_events_kind")),
        sa.CheckConstraint("status IN ('open', 'cancelled')", name=op.f("ck_events_status")),
        sa.CheckConstraint(
            "length(trim(title)) > 0 AND length(trim(location)) > 0",
            name=op.f("ck_events_required_text"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "series_id"],
            ["event_series.team_id", "event_series.id"],
            name=op.f("fk_events_team_id_event_series"),
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_events_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("series_id", "recurrence_date", name="uq_events_series_date"),
        sa.UniqueConstraint("team_id", "id", name="uq_events_team_id"),
    )
    op.create_index("ix_events_team_date", "events", ["team_id", "date", "time"], unique=False)
    op.create_table(
        "event_attendance",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("response", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "response IN ('VOU', 'NAO_VOU')", name=op.f("ck_event_attendance_response")
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id"],
            ["events.team_id", "events.id"],
            name=op.f("fk_event_attendance_team_id_events"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name=op.f("fk_event_attendance_team_id_team_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_attendance")),
        sa.UniqueConstraint("event_id", "membership_id", name="uq_event_attendance_member"),
    )
    op.create_table(
        "event_guests",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_event_guests_name")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_event_guests_event_id_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_guests")),
    )
    op.create_index(op.f("ix_event_guests_event_id"), "event_guests", ["event_id"], unique=False)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE event_series, events, event_attendance, event_guests, "
            "membership_permissions IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM events) OR EXISTS (SELECT 1 FROM event_series) OR "
            "EXISTS (SELECT 1 FROM membership_permissions WHERE permission = 'manage_events')"
        )
    ):
        raise RuntimeError("Downgrade blocked: event data cannot be represented by revision 0004")
    op.drop_index(op.f("ix_event_guests_event_id"), table_name="event_guests")
    op.drop_table("event_guests")
    op.drop_table("event_attendance")
    op.drop_index("ix_events_team_date", table_name="events")
    op.drop_table("events")
    op.drop_table("event_series")
    op.drop_constraint(
        op.f("ck_membership_permissions_permission"), "membership_permissions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_membership_permissions_permission"),
        "membership_permissions",
        "permission IN ('manage_team', 'manage_members')",
    )
