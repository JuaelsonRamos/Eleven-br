"""Preserve the existing modality as a PostgreSQL array, available on every plan.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "teams",
        "modality",
        new_column_name="modalities",
        existing_type=sa.String(40),
        type_=postgresql.ARRAY(sa.String(40)),
        existing_nullable=False,
        postgresql_using="ARRAY[modality]::varchar(40)[]",
    )
    op.create_check_constraint(
        op.f("ck_teams_modalities_required"),
        "teams",
        "cardinality(modalities) > 0 AND array_ndims(modalities) = 1 "
        "AND array_position(modalities, NULL) IS NULL",
    )


def downgrade() -> None:
    # Never silently discard a team's additional modalities on rollback.
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE teams IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM teams WHERE cardinality(modalities) <> 1)")
    ):
        raise RuntimeError("Downgrade blocked: teams with multiple modalities must be preserved")
    op.drop_constraint(op.f("ck_teams_modalities_required"), "teams", type_="check")
    op.alter_column(
        "teams",
        "modalities",
        new_column_name="modality",
        existing_type=postgresql.ARRAY(sa.String(40)),
        type_=sa.String(40),
        existing_nullable=False,
        postgresql_using="modalities[1]",
    )
