"""team_finance

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_membership_permissions_permission"), "membership_permissions", type_="check"
    )
    op.create_check_constraint(
        "permission",
        "membership_permissions",
        "permission IN ('manage_team', 'manage_members', 'manage_events', 'manage_finance')",
    )
    op.create_table(
        "dues_settings",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_dues_settings_amount")),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name=op.f("ck_dues_settings_due_day")),
        sa.CheckConstraint("version > 0", name=op.f("ck_dues_settings_version")),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_dues_settings_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_dues_settings_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dues_settings")),
        sa.UniqueConstraint("team_id", name=op.f("uq_dues_settings_team_id")),
    )
    op.create_table(
        "monthly_dues",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("competence", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
            "status IN ('PENDING', 'PAID', 'EXEMPT', 'CANCELLED')",
            name=op.f("ck_monthly_dues_status"),
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM competence) = 1", name=op.f("ck_monthly_dues_competence")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_monthly_dues_amount")),
        sa.CheckConstraint("version > 0", name=op.f("ck_monthly_dues_version")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_monthly_dues_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name=op.f("fk_monthly_dues_team_id_team_memberships"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_monthly_dues_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_dues")),
        sa.UniqueConstraint("team_id", "id", name=op.f("uq_monthly_dues_team_id")),
        sa.UniqueConstraint(
            "team_id", "membership_id", "competence", name="uq_dues_membership_competence"
        ),
    )
    op.create_index(
        "ix_monthly_dues_team_competence", "monthly_dues", ["team_id", "competence"], unique=False
    )
    op.create_table(
        "cash_entries",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("dues_id", sa.Uuid(), nullable=True),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=16), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
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
            "dues_id IS NULL OR (kind = 'INCOME' AND payment_method IS NOT NULL "
            "AND category = 'Mensalidade')",
            name=op.f("ck_cash_entries_dues_income"),
        ),
        sa.CheckConstraint("kind IN ('INCOME', 'EXPENSE')", name=op.f("ck_cash_entries_kind")),
        sa.CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('PIX', 'CASH', 'CARD', 'OTHER')",
            name=op.f("ck_cash_entries_method"),
        ),
        sa.CheckConstraint(
            "(cancelled_at IS NULL AND cancelled_by IS NULL AND cancellation_reason IS NULL) OR "
            "(cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancellation_reason IS NOT NULL AND length(trim(cancellation_reason)) > 0)",
            name=op.f("ck_cash_entries_cancellation"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_cash_entries_amount")),
        sa.CheckConstraint(
            "length(trim(category)) > 0 AND length(trim(description)) > 0",
            name=op.f("ck_cash_entries_description"),
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"], ["users.id"], name=op.f("fk_cash_entries_cancelled_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_cash_entries_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "dues_id"],
            ["monthly_dues.team_id", "monthly_dues.id"],
            name=op.f("fk_cash_entries_team_id_monthly_dues"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_cash_entries_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_entries")),
        sa.UniqueConstraint("team_id", "command_id", name="uq_cash_command"),
        sa.UniqueConstraint("team_id", "id", name=op.f("uq_cash_entries_team_id")),
    )
    op.create_index("ix_cash_team_date", "cash_entries", ["team_id", "entry_date"], unique=False)
    op.create_index("ix_cash_team_dues", "cash_entries", ["team_id", "dues_id"], unique=False)
    op.create_table(
        "finance_audit",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("dues_id", sa.Uuid(), nullable=True),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_finance_audit_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "dues_id"],
            ["monthly_dues.team_id", "monthly_dues.id"],
            name=op.f("fk_finance_audit_team_id_monthly_dues"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "entry_id"],
            ["cash_entries.team_id", "cash_entries.id"],
            name=op.f("fk_finance_audit_team_id_cash_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_finance_audit_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_audit")),
    )
    op.create_index(
        "ix_finance_audit_team_dues", "finance_audit", ["team_id", "dues_id"], unique=False
    )


def downgrade() -> None:
    for table in ["dues_settings", "monthly_dues", "cash_entries", "finance_audit"]:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Downgrade blocked: financial records must be preserved")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM membership_permissions "
            "WHERE permission = 'manage_finance')"
        )
    ):
        raise RuntimeError("Downgrade blocked: finance grants must be preserved")
    op.drop_constraint(
        op.f("ck_membership_permissions_permission"), "membership_permissions", type_="check"
    )
    op.create_check_constraint(
        "permission",
        "membership_permissions",
        "permission IN ('manage_team', 'manage_members', 'manage_events')",
    )
    op.drop_index("ix_finance_audit_team_dues", table_name="finance_audit")
    op.drop_table("finance_audit")
    op.drop_index("ix_cash_team_dues", table_name="cash_entries")
    op.drop_index("ix_cash_team_date", table_name="cash_entries")
    op.drop_table("cash_entries")
    op.drop_index("ix_monthly_dues_team_competence", table_name="monthly_dues")
    op.drop_table("monthly_dues")
    op.drop_table("dues_settings")
