"""Persistence for contact verification, revocable sessions and shared abuse limits."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.models import Base, Entity


class VerificationChallenge(Entity, Base):
    __tablename__ = "verification_challenges"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    handle_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    contact: Mapped[str] = mapped_column(String(254))
    channel: Mapped[str] = mapped_column(String(8))
    purpose: Mapped[str] = mapped_column(String(24), default="verify_contact")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'phone')", name="channel"),
        CheckConstraint("purpose = 'verify_contact'", name="purpose"),
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="attempts"),
    )


class AuthSession(Entity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    transport: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("transport IN ('web', 'native')", name="transport"),)


class RefreshToken(Entity, Base):
    __tablename__ = "refresh_tokens"
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (CheckConstraint("hits > 0", name="hits"),)
