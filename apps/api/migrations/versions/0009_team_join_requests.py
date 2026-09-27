"""Team join requests; preserves all existing identity and sporting records.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_join_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("membership_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_team_join_requests"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_team_join_requests_team_id_teams"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_team_join_requests_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name="fk_team_join_requests_resolved_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name="fk_join_requests_membership",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="ck_team_join_requests_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND resolved_at IS NULL AND resolved_by IS NULL) OR "
            "(status <> 'PENDING' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)",
            name="ck_team_join_requests_resolution",
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED' AND membership_id IS NOT NULL) OR "
            "(status <> 'APPROVED' AND membership_id IS NULL)",
            name="ck_team_join_requests_approval",
        ),
    )
    op.create_index(
        "uq_join_requests_pending",
        "team_join_requests",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_join_requests_user_created", "team_join_requests", ["user_id", "created_at"]
    )
    op.create_index("ix_join_requests_team_status", "team_join_requests", ["team_id", "status"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM team_join_requests)")):
        raise RuntimeError("Downgrade bloqueado: existem solicitações de entrada a preservar.")
    op.drop_table("team_join_requests")
