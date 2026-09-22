import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Entity:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(16), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    registration_name: Mapped[str | None] = mapped_column(String(80))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="contact_required"),
        CheckConstraint("email IS NULL OR email = lower(email)", name="email_normalized"),
        CheckConstraint("phone IS NULL OR phone ~ '^\\+[1-9][0-9]{7,14}$'", name="phone_e164"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
    )


class Player(Entity, Base):
    __tablename__ = "players"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    photo_url: Mapped[str | None] = mapped_column(String(2048))
    __table_args__ = (CheckConstraint("length(trim(display_name)) > 0", name="name"),)


class Team(Entity, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(10), unique=True)
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    modalities: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    crest_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    plan: Mapped[str] = mapped_column(String(16), server_default="free")
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    president_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name"),
        CheckConstraint("code ~ '^[A-Z0-9]{6,10}$'", name="code"),
        CheckConstraint("state ~ '^[A-Z]{2}$'", name="state"),
        CheckConstraint(
            "cardinality(modalities) > 0 AND array_ndims(modalities) = 1 "
            "AND array_position(modalities, NULL) IS NULL",
            name="modalities_required",
        ),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint("plan IN ('free', 'pro')", name="plan"),
        ForeignKeyConstraint(
            ["id", "president_membership_id"],
            ["team_memberships.team_id", "team_memberships.id"],
            name="fk_team_president_membership",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
    )


class TeamMembership(Entity, Base):
    __tablename__ = "team_memberships"
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), server_default="member")
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    roster_name: Mapped[str | None] = mapped_column(String(80))
    nickname: Mapped[str | None] = mapped_column(String(80))
    contact_phone: Mapped[str | None] = mapped_column(String(16))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    __table_args__ = (
        UniqueConstraint("team_id", "player_id", name="uq_membership_team_player"),
        UniqueConstraint("team_id", "id", name="uq_membership_team_id"),
        CheckConstraint("role IN ('member', 'admin')", name="role"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint("roster_name IS NULL OR length(trim(roster_name)) > 0", name="roster_name"),
        CheckConstraint(
            "contact_email IS NULL OR contact_email = lower(contact_email)", name="email_normalized"
        ),
        CheckConstraint(
            "contact_phone IS NULL OR contact_phone ~ '^\\+[1-9][0-9]{7,14}$'", name="phone_e164"
        ),
        Index("ix_memberships_team_status", "team_id", "status"),
    )


class MembershipPermission(Entity, Base):
    __tablename__ = "membership_permissions"
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_memberships.id", ondelete="CASCADE"), index=True
    )
    permission: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        UniqueConstraint("membership_id", "permission"),
        CheckConstraint("permission IN ('manage_team', 'manage_members')", name="permission"),
    )
