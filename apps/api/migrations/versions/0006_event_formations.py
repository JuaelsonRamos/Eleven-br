"""event_formations

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_guests", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("uq_event_guests_scope", "event_guests", ["event_id", "id"])
    op.create_table(
        "event_formations",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("team_count", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("roster_fingerprint", sa.String(length=64), nullable=False),
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
        sa.CheckConstraint("method = 'random'", name=op.f("ck_event_formations_method")),
        sa.CheckConstraint(
            "team_count BETWEEN 2 AND 32", name=op.f("ck_event_formations_team_count")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_event_formations_version")),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id"],
            ["events.team_id", "events.id"],
            name=op.f("fk_event_formations_team_id_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_formations")),
        sa.UniqueConstraint("event_id", name=op.f("uq_event_formations_event_id")),
        sa.UniqueConstraint("team_id", "event_id", "id", name="uq_event_formations_scope"),
    )
    op.create_table(
        "formation_squads",
        sa.Column("formation_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("number BETWEEN 1 AND 32", name=op.f("ck_formation_squads_number")),
        sa.ForeignKeyConstraint(
            ["formation_id"],
            ["event_formations.id"],
            name=op.f("fk_formation_squads_formation_id_event_formations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formation_squads")),
        sa.UniqueConstraint("formation_id", "id", name="uq_formation_squads_scope"),
        sa.UniqueConstraint("formation_id", "number", name="uq_formation_squads_number"),
    )
    op.create_table(
        "formation_participants",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("formation_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=True),
        sa.Column("guest_id", sa.Uuid(), nullable=True),
        sa.Column("squad_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("goalkeeper", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_formation_participants_name")),
        sa.CheckConstraint(
            "num_nonnulls(membership_id, guest_id) = 1",
            name=op.f("ck_formation_participants_source"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "guest_id"],
            ["event_guests.event_id", "event_guests.id"],
            name=op.f("fk_formation_participants_event_id_event_guests"),
        ),
        sa.ForeignKeyConstraint(
            ["formation_id", "squad_id"],
            ["formation_squads.formation_id", "formation_squads.id"],
            name=op.f("fk_formation_participants_formation_id_formation_squads"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id"],
            ["event_formations.team_id", "event_formations.event_id", "event_formations.id"],
            name=op.f("fk_formation_participants_team_id_event_formations"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name=op.f("fk_formation_participants_team_id_team_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formation_participants")),
        sa.UniqueConstraint("formation_id", "guest_id", name="uq_formation_participants_guest"),
        sa.UniqueConstraint(
            "formation_id", "membership_id", name="uq_formation_participants_member"
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE event_formations, formation_squads, formation_participants, "
            "event_guests IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM event_formations) OR "
            "EXISTS (SELECT 1 FROM event_guests WHERE removed_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Downgrade blocked: formation or removed guest data would be lost")
    op.drop_table("formation_participants")
    op.drop_table("formation_squads")
    op.drop_table("event_formations")
    op.drop_constraint("uq_event_guests_scope", "event_guests", type_="unique")
    op.drop_column("event_guests", "removed_at")
