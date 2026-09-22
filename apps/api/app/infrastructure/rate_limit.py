from datetime import UTC, datetime, timedelta

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.auth import RateLimited
from app.infrastructure.auth_models import AuthRateLimit
from app.infrastructure.config import Settings
from app.infrastructure.security import secret_digest


def rate_limit(
    session: Session,
    settings: Settings,
    scope: str,
    identity: str,
    *,
    limit: int,
    seconds: int,
) -> None:
    """Atomic shared PostgreSQL counters; commit before work, including rejected requests.

    Call only before domain mutations. Do not trust arbitrary X-Forwarded-For headers.
    """
    now = datetime.now(UTC)
    reset = now + timedelta(seconds=seconds)
    key = secret_digest(f"rate:{scope}:{identity}", settings)
    expired = AuthRateLimit.reset_at <= now
    row = session.execute(
        insert(AuthRateLimit)
        .values(key=key, hits=1, reset_at=reset)
        .on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={
                "hits": case((expired, 1), else_=AuthRateLimit.hits + 1),
                "reset_at": case((expired, reset), else_=AuthRateLimit.reset_at),
            },
        )
        .returning(AuthRateLimit.hits, AuthRateLimit.reset_at)
    ).one()
    session.commit()
    if row.hits > limit:
        raise RateLimited(int((row.reset_at - now).total_seconds()))
