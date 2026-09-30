"""opponents_challenges

Additive: challenges (with the Free monthly challenge credit), one shared fixture per
accepted challenge, bilateral scores, reliability reviews and the "accept challenges"
preference. Searching opponents stores nothing.
Free-text games (`events.opponent`) are untouched; `events.fixture_id` stays empty for them.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

OLD_TYPES = (
    "type IN ('TEAM_JOIN_REQUEST', 'TEAM_JOIN_APPROVED', 'TEAM_JOIN_REJECTED', "
    "'EVENT_CREATED', 'EVENT_UPDATED', 'EVENT_CANCELLED', 'ATTENDANCE_REMINDER', "
    "'FINANCE_CHARGE_CREATED', 'FINANCE_PAYMENT_REGISTERED', 'FINANCE_PAYMENT_REVERSED')"
)
NEW_TYPES = (
    "type IN ('TEAM_JOIN_REQUEST', 'TEAM_JOIN_APPROVED', 'TEAM_JOIN_REJECTED', "
    "'EVENT_CREATED', 'EVENT_UPDATED', 'EVENT_CANCELLED', 'ATTENDANCE_REMINDER', "
    "'FINANCE_CHARGE_CREATED', 'FINANCE_PAYMENT_REGISTERED', 'FINANCE_PAYMENT_REVERSED', "
    "'CHALLENGE_RECEIVED', 'CHALLENGE_ACCEPTED', 'CHALLENGE_REJECTED', 'CHALLENGE_CANCELLED', "
    "'FIXTURE_SCORE_REPORTED', 'FIXTURE_SCORE_CONFIRMED', 'FIXTURE_SCORE_DISPUTED', "
    "'FIXTURE_REVIEW_AVAILABLE')"
)
OLD_ACTIONS = (
    "action IS NULL OR action IN ('OPEN_TEAM', 'OPEN_JOIN_REQUESTS', "
    "'OPEN_EVENT', 'OPEN_FINANCE_CHARGE')"
)
NEW_ACTIONS = (
    "action IS NULL OR action IN ('OPEN_TEAM', 'OPEN_JOIN_REQUESTS', "
    "'OPEN_EVENT', 'OPEN_FINANCE_CHARGE', 'OPEN_CHALLENGE', 'OPEN_FIXTURE')"
)
OLD_ENTITIES = (
    "(entity_type IS NULL AND entity_id IS NULL) OR "
    "(entity_type IS NOT NULL AND entity_type IN "
    "('team', 'join_request', 'event', 'finance_charge') "
    "AND entity_id IS NOT NULL)"
)
NEW_ENTITIES = (
    "(entity_type IS NULL AND entity_id IS NULL) OR "
    "(entity_type IS NOT NULL AND entity_type IN "
    "('team', 'join_request', 'event', 'finance_charge', 'challenge', 'fixture') "
    "AND entity_id IS NOT NULL)"
)


def entity() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def replace_notification_checks(types: str, actions: str, entities: str) -> None:
    for name, condition in (("type", types), ("action", actions), ("entity", entities)):
        op.drop_constraint(op.f(f"ck_notifications_{name}"), "notifications", type_="check")
        op.create_check_constraint(name, "notifications", condition)


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column(
            "accepts_challenges", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_table(
        "team_challenges",
        sa.Column("challenger_team_id", sa.Uuid(), nullable=False),
        sa.Column("challenged_team_id", sa.Uuid(), nullable=False),
        sa.Column("competence", sa.Date(), nullable=False),
        sa.Column("charged", sa.Boolean(), nullable=False),
        sa.Column("modality", sa.String(40), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("venue", sa.String(8), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *entity(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["challenger_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["challenged_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.UniqueConstraint("challenger_team_id", "command_id", name="uq_team_challenges_command"),
        sa.CheckConstraint("challenger_team_id <> challenged_team_id", name="distinct_teams"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')", name="status"
        ),
        sa.CheckConstraint("venue IN ('HOME', 'AWAY')", name="venue"),
        sa.CheckConstraint("modality IN ('campo', 'society', 'futsal')", name="modality"),
        sa.CheckConstraint("length(trim(location)) > 0", name="location"),
        sa.CheckConstraint(
            "(status = 'PENDING') = (resolved_at IS NULL AND resolved_by IS NULL)",
            name="resolution",
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM competence) = 1", name="competence"),
    )
    op.create_index(
        "ix_team_challenges_challenger", "team_challenges", ["challenger_team_id", "created_at"]
    )
    op.create_index(
        "ix_team_challenges_challenged", "team_challenges", ["challenged_team_id", "created_at"]
    )
    # One Free credit per team and month; never two pending equivalent proposals.
    op.create_index(
        "uq_team_challenges_monthly_credit",
        "team_challenges",
        ["challenger_team_id", "competence"],
        unique=True,
        postgresql_where=sa.text("charged"),
    )
    op.create_index(
        "uq_team_challenges_pending_proposal",
        "team_challenges",
        [
            sa.text("LEAST(challenger_team_id, challenged_team_id)"),
            sa.text("GREATEST(challenger_team_id, challenged_team_id)"),
            "modality",
            "date",
            "time",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "team_fixtures",
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("home_team_id", sa.Uuid(), nullable=False),
        sa.Column("away_team_id", sa.Uuid(), nullable=False),
        sa.Column("modality", sa.String(40), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("result_status", sa.String(16), server_default="NONE", nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        *entity(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["challenge_id"], ["team_challenges.id"]),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"]),
        sa.UniqueConstraint("challenge_id"),
        sa.CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
        sa.CheckConstraint(
            "result_status IN ('NONE', 'PENDING', 'VALIDATED', 'DISPUTED')", name="result_status"
        ),
        sa.CheckConstraint(
            "(result_status = 'VALIDATED' AND validated_at IS NOT NULL "
            "AND home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999) OR "
            "(result_status <> 'VALIDATED' AND validated_at IS NULL "
            "AND home_score IS NULL AND away_score IS NULL)",
            name="official_result",
        ),
    )
    op.create_index("ix_team_fixtures_home", "team_fixtures", ["home_team_id", "date"])
    op.create_index("ix_team_fixtures_away", "team_fixtures", ["away_team_id", "date"])
    op.create_table(
        "fixture_scores",
        sa.Column("fixture_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        *entity(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["fixture_id"], ["team_fixtures.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("fixture_id", "side", name="uq_fixture_scores_side"),
        sa.CheckConstraint("side IN ('HOME', 'AWAY')", name="side"),
        sa.CheckConstraint("kind IN ('REPORTED', 'CONFIRMED')", name="kind"),
        sa.CheckConstraint(
            "home_score BETWEEN 0 AND 999 AND away_score BETWEEN 0 AND 999", name="score"
        ),
    )
    op.create_table(
        "fixture_reviews",
        sa.Column("fixture_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("attended", sa.Boolean(), nullable=False),
        sa.Column("punctual", sa.Boolean(), nullable=False),
        sa.Column("kept_agreement", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        *entity(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["fixture_id"], ["team_fixtures.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("fixture_id", "side", name="uq_fixture_reviews_side"),
        sa.CheckConstraint("side IN ('HOME', 'AWAY')", name="side"),
    )
    op.add_column("events", sa.Column("fixture_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(None, "events", "team_fixtures", ["fixture_id"], ["id"])
    op.create_unique_constraint("uq_events_team_fixture", "events", ["team_id", "fixture_id"])
    op.create_check_constraint(
        "fixture", "events", "fixture_id IS NULL OR (kind = 'JOGO' AND series_id IS NULL)"
    )
    replace_notification_checks(NEW_TYPES, NEW_ACTIONS, NEW_ENTITIES)


def downgrade() -> None:
    connection = op.get_bind()
    for query in (
        "SELECT EXISTS (SELECT 1 FROM team_challenges)",
        "SELECT EXISTS (SELECT 1 FROM events WHERE fixture_id IS NOT NULL)",
        "SELECT EXISTS (SELECT 1 FROM teams WHERE NOT accepts_challenges)",
        "SELECT EXISTS (SELECT 1 FROM notifications WHERE type LIKE 'CHALLENGE%' "
        "OR type LIKE 'FIXTURE%')",
    ):
        if connection.execute(sa.text(query)).scalar():
            raise RuntimeError("Downgrade blocked: preserve challenges, fixtures and preferences")
    replace_notification_checks(OLD_TYPES, OLD_ACTIONS, OLD_ENTITIES)
    op.drop_constraint(op.f("ck_events_fixture"), "events", type_="check")
    op.drop_constraint("uq_events_team_fixture", "events", type_="unique")
    op.drop_constraint(op.f("fk_events_fixture_id_team_fixtures"), "events", type_="foreignkey")
    op.drop_column("events", "fixture_id")
    op.drop_table("fixture_reviews")
    op.drop_table("fixture_scores")
    op.drop_index("ix_team_fixtures_away", table_name="team_fixtures")
    op.drop_index("ix_team_fixtures_home", table_name="team_fixtures")
    op.drop_table("team_fixtures")
    op.drop_index("uq_team_challenges_pending_proposal", table_name="team_challenges")
    op.drop_index("uq_team_challenges_monthly_credit", table_name="team_challenges")
    op.drop_index("ix_team_challenges_challenged", table_name="team_challenges")
    op.drop_index("ix_team_challenges_challenger", table_name="team_challenges")
    op.drop_table("team_challenges")
    op.drop_column("teams", "accepts_challenges")
