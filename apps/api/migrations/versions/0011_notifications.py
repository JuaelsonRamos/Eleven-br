"""Persistent user notifications and event creation retry keys.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("creation_key", sa.Uuid(), nullable=True))
    op.add_column("events", sa.Column("creation_hash", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_events_creation_key", "events", ["team_id", "creation_key"])
    op.create_check_constraint(
        "creation_key", "events", "(creation_key IS NULL) = (creation_hash IS NULL)"
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("message", sa.String(600), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(40), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedup_key", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
        sa.CheckConstraint(
            "type IN ('TEAM_JOIN_REQUEST', 'TEAM_JOIN_APPROVED', 'TEAM_JOIN_REJECTED', "
            "'EVENT_CREATED', 'EVENT_UPDATED', 'EVENT_CANCELLED', 'ATTENDANCE_REMINDER', "
            "'FINANCE_CHARGE_CREATED', 'FINANCE_PAYMENT_REGISTERED', 'FINANCE_PAYMENT_REVERSED')",
            name="type",
        ),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('OPEN_TEAM', 'OPEN_JOIN_REQUESTS', "
            "'OPEN_EVENT', 'OPEN_FINANCE_CHARGE')",
            name="action",
        ),
        sa.CheckConstraint(
            "(entity_type IS NULL AND entity_id IS NULL) OR "
            "(entity_type IS NOT NULL AND entity_type IN "
            "('team', 'join_request', 'event', 'finance_charge') "
            "AND entity_id IS NOT NULL)",
            name="entity",
        ),
        sa.CheckConstraint("length(trim(title)) > 0 AND length(trim(message)) > 0", name="text"),
        sa.CheckConstraint("length(trim(dedup_key)) > 0", name="dedup"),
    )
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at", "id"]
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notifications) OR "
            "EXISTS (SELECT 1 FROM events WHERE creation_key IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Downgrade bloqueado: preserve o histórico de notificações e idempotência."
        )
    op.drop_table("notifications")
    op.drop_constraint(op.f("ck_events_creation_key"), "events", type_="check")
    op.drop_constraint("uq_events_creation_key", "events", type_="unique")
    op.drop_column("events", "creation_hash")
    op.drop_column("events", "creation_key")
