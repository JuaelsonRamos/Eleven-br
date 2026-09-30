"""team_locations

Official team location: IBGE municipality reference table plus the President's
confirmation on teams. Additive: the typed city/UF of existing teams are kept as they
are and stay unconfirmed (search fallback only) until the President confirms; nothing
is converted automatically.

Municipalities come from data/ibge_municipalities.csv, derived from the official IBGE
localidades API (servicodados.ibge.gov.br/api/v1/localidades/municipios), retrieved on
2026-09-30: 5,571 municipalities, including Brasília/DF and Fernando de Noronha/PE.
A later territorial change needs a new migration with the new rows.

Revision ID: 0016
Revises: 0015
"""

import csv
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

DATA = Path(__file__).resolve().parents[1] / "data" / "ibge_municipalities.csv"
EXPECTED = 5571  # Municipalities in the IBGE list retrieved on 2026-09-30.


def official_rows() -> list[dict[str, object]]:
    """Read and check the versioned dataset before any change: never a partial table."""
    if not DATA.is_file():
        raise RuntimeError(
            f"Migration 0016: arquivo {DATA} ausente. Publique apps/api/migrations/data "
            "junto com as migrations (versionado no repositório)."
        )
    with DATA.open(encoding="utf-8", newline="") as handle:
        rows: list[dict[str, object]] = [
            {"code": int(row["code"]), "state": row["state"], "name": row["name"]}
            for row in csv.DictReader(handle)
        ]
    if len(rows) != EXPECTED:
        raise RuntimeError(
            f"Migration 0016: {DATA.name} tem {len(rows)} municípios; esperados {EXPECTED} "
            "(lista oficial do IBGE de 2026-09-30). Restaure o arquivo versionado."
        )
    return rows


def upgrade() -> None:
    rows = official_rows()
    municipalities = op.create_table(
        "municipalities",
        sa.Column("code", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("code"),
        sa.UniqueConstraint("code", "state", "name", name="uq_municipalities_identity"),
        sa.CheckConstraint("code BETWEEN 1100000 AND 5399999", name="code"),
        sa.CheckConstraint("state ~ '^[A-Z]{2}$'", name="state"),
    )
    op.create_index("ix_municipalities_state_name", "municipalities", ["state", "name"])
    op.bulk_insert(municipalities, rows)
    op.add_column("teams", sa.Column("municipality_code", sa.Integer(), nullable=True))
    op.add_column(
        "teams", sa.Column("location_confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_teams_municipality_code"), "teams", ["municipality_code"])
    op.create_check_constraint(
        "location_confirmation",
        "teams",
        "(municipality_code IS NULL) = (location_confirmed_at IS NULL)",
    )
    op.create_foreign_key(
        "fk_teams_municipality",
        "teams",
        "municipalities",
        ["municipality_code", "state", "city"],
        ["code", "state", "name"],
        onupdate="CASCADE",
    )


def downgrade() -> None:
    # Code and confirmation cannot be represented by 0015: refuse instead of discarding
    # them. Legacy text (city/UF) stays in teams, so without confirmations nothing is lost.
    confirmed = op.get_bind().execute(
        sa.text("SELECT count(*) FROM teams WHERE location_confirmed_at IS NOT NULL")
    )
    count = confirmed.scalar_one()
    if count:
        raise RuntimeError(
            f"Downgrade bloqueado: {count} time(s) com localização oficial confirmada pelo "
            "Presidente (municipality_code e location_confirmed_at), que a revisão 0015 não "
            "guarda. A 0016 é aditiva: num rollback da aplicação, mantenha o banco na 0016."
        )
    op.drop_constraint("fk_teams_municipality", "teams", type_="foreignkey")
    op.drop_constraint(op.f("ck_teams_location_confirmation"), "teams", type_="check")
    op.drop_index(op.f("ix_teams_municipality_code"), table_name="teams")
    op.drop_column("teams", "location_confirmed_at")
    op.drop_column("teams", "municipality_code")
    op.drop_index("ix_municipalities_state_name", table_name="municipalities")
    op.drop_table("municipalities")
