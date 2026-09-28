"""Add historical roster adjustment audit without modifying existing sporting records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statistic_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("expected_state", sa.String(64), nullable=False),
        sa.Column("goals_delta", sa.Integer(), nullable=False),
        sa.Column("yellow_cards_delta", sa.Integer(), nullable=False),
        sa.Column("red_cards_delta", sa.Integer(), nullable=False),
        sa.Column("previous_totals", postgresql.JSONB(), nullable=False),
        sa.Column("new_totals", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["team_id", "membership_id"], ["team_memberships.team_id", "team_memberships.id"]
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.UniqueConstraint("team_id", "command_id", name="uq_statistic_adjustments_command"),
        sa.CheckConstraint(
            "goals_delta <> 0 OR yellow_cards_delta <> 0 OR red_cards_delta <> 0", name="nonzero"
        ),
    )
    op.create_index(
        "ix_statistic_adjustments_member", "statistic_adjustments", ["team_id", "membership_id"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM statistic_adjustments)")):
        raise RuntimeError("Downgrade bloqueado: preserve o histórico de ajustes estatísticos.")
    op.drop_table("statistic_adjustments")
