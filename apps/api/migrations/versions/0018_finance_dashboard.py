"""Finance dashboard preferences and retained editing/recurrence metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dues_settings",
        sa.Column("repeat_monthly", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("dues_settings", sa.Column("next_competence", sa.Date(), nullable=True))
    op.add_column(
        "cash_entries", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("finance_audit", sa.Column("changes", JSONB(), nullable=True))
    op.create_table(
        "finance_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False, unique=True),
        sa.Column("opening_balance", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("opening_date", sa.Date(), nullable=True),
        sa.Column("share_summary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("categories", JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM finance_preferences) OR EXISTS "
            "(SELECT 1 FROM dues_settings WHERE repeat_monthly OR next_competence IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM finance_audit WHERE changes IS NOT NULL)"
        )
    ):
        raise RuntimeError("Cannot discard Finance 2.0 financial records")
    op.drop_table("finance_preferences")
    op.drop_column("finance_audit", "changes")
    op.drop_column("cash_entries", "version")
    op.drop_column("dues_settings", "next_competence")
    op.drop_column("dues_settings", "repeat_monthly")
