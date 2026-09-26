"""match_events

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_event_matches_scope", "event_matches", ["team_id", "event_id", "formation_id", "id"]
    )
    op.create_unique_constraint(
        "uq_formation_participants_scope",
        "formation_participants",
        ["formation_id", "squad_id", "id"],
    )
    op.create_table(
        "match_events",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("formation_id", sa.Uuid(), nullable=False),
        sa.Column("squad_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("assist_participant_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
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
            "assist_participant_id IS NULL OR type = 'GOAL'",
            name=op.f("ck_match_events_assist_goal"),
        ),
        sa.CheckConstraint(
            "type IN ('GOAL', 'YELLOW_CARD', 'RED_CARD')", name=op.f("ck_match_events_type")
        ),
        sa.CheckConstraint(
            "assist_participant_id IS NULL OR assist_participant_id <> participant_id",
            name=op.f("ck_match_events_different_assist"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_match_events_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["formation_id", "squad_id", "assist_participant_id"],
            [
                "formation_participants.formation_id",
                "formation_participants.squad_id",
                "formation_participants.id",
            ],
            name="fk_match_events_assist",
        ),
        sa.ForeignKeyConstraint(
            ["formation_id", "squad_id", "participant_id"],
            [
                "formation_participants.formation_id",
                "formation_participants.squad_id",
                "formation_participants.id",
            ],
            name="fk_match_events_participant",
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id", "match_id"],
            [
                "event_matches.team_id",
                "event_matches.event_id",
                "event_matches.formation_id",
                "event_matches.id",
            ],
            name="fk_match_events_match_scope",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_match_events_updated_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_events")),
    )
    op.create_index("ix_match_events_match_id", "match_events", ["match_id"], unique=False)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE match_events IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM match_events)")):
        raise RuntimeError("Downgrade blocked: match event history would be lost")
    op.drop_index("ix_match_events_match_id", table_name="match_events")
    op.drop_table("match_events")
    op.drop_constraint("uq_formation_participants_scope", "formation_participants", type_="unique")
    op.drop_constraint("uq_event_matches_scope", "event_matches", type_="unique")
