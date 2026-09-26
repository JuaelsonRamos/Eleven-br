"""event_matches

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_matches",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("formation_id", sa.Uuid(), nullable=False),
        sa.Column("home_formation_team_id", sa.Uuid(), nullable=False),
        sa.Column("away_formation_team_id", sa.Uuid(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corrected_by_user_id", sa.Uuid(), nullable=True),
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
            "status <> 'FINISHED' OR finished_at IS NOT NULL",
            name=op.f("ck_event_matches_finished"),
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED')",
            name=op.f("ck_event_matches_status"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('IN_PROGRESS', 'FINISHED') OR started_at IS NOT NULL",
            name=op.f("ck_event_matches_started"),
        ),
        sa.CheckConstraint(
            "home_formation_team_id <> away_formation_team_id",
            name=op.f("ck_event_matches_different_teams"),
        ),
        sa.CheckConstraint(
            "home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999",
            name=op.f("ck_event_matches_scores"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_event_matches_version")),
        sa.ForeignKeyConstraint(
            ["corrected_by_user_id"],
            ["users.id"],
            name=op.f("fk_event_matches_corrected_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["formation_id", "away_formation_team_id"],
            ["formation_squads.formation_id", "formation_squads.id"],
            name="fk_event_matches_away_squad",
        ),
        sa.ForeignKeyConstraint(
            ["formation_id", "home_formation_team_id"],
            ["formation_squads.formation_id", "formation_squads.id"],
            name="fk_event_matches_home_squad",
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id", "formation_id"],
            ["event_formations.team_id", "event_formations.event_id", "event_formations.id"],
            name=op.f("fk_event_matches_team_id_event_formations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_matches")),
    )
    op.create_index("ix_event_matches_event_id", "event_matches", ["event_id"], unique=False)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE event_matches IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM event_matches)")):
        raise RuntimeError("Downgrade blocked: match history would be lost")
    op.drop_index("ix_event_matches_event_id", table_name="event_matches")
    op.drop_table("event_matches")
