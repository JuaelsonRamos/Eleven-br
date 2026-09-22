"""Optional account linkage and team-scoped roster information.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("players", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("team_memberships", sa.Column("roster_name", sa.String(80), nullable=True))
    op.add_column("team_memberships", sa.Column("nickname", sa.String(80), nullable=True))
    op.add_column("team_memberships", sa.Column("contact_phone", sa.String(16), nullable=True))
    op.add_column("team_memberships", sa.Column("contact_email", sa.String(254), nullable=True))
    for name, expression in {
        "roster_name": "roster_name IS NULL OR length(trim(roster_name)) > 0",
        "email_normalized": "contact_email IS NULL OR contact_email = lower(contact_email)",
        "phone_e164": "contact_phone IS NULL OR contact_phone ~ '^\\+[1-9][0-9]{7,14}$'",
    }.items():
        op.create_check_constraint(
            op.f(f"ck_team_memberships_{name}"), "team_memberships", expression
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE players, team_memberships IN ACCESS EXCLUSIVE MODE"))
    has_data = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM players WHERE user_id IS NULL) OR EXISTS "
            "(SELECT 1 FROM team_memberships WHERE roster_name IS NOT NULL OR nickname IS NOT NULL "
            "OR contact_phone IS NOT NULL OR contact_email IS NOT NULL)"
        )
    )
    if has_data:
        raise RuntimeError("Downgrade blocked: roster data cannot be represented by revision 0003")
    for name in ["roster_name", "email_normalized", "phone_e164"]:
        op.drop_constraint(op.f(f"ck_team_memberships_{name}"), "team_memberships", type_="check")
    for name in ["roster_name", "nickname", "contact_phone", "contact_email"]:
        op.drop_column("team_memberships", name)
    op.alter_column("players", "user_id", existing_type=sa.Uuid(), nullable=False)
