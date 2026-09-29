"""Commercial subscription vocabulary; independent of the team's internal cashbook."""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.policies import DomainError

PRO_PRICE = Decimal("29.99")
PRO_CODE = "PRO_MONTHLY"
GRACE_DAYS = 3
PIX_SIGNUP_MINUTES = 10


class SubscriptionStatus(StrEnum):
    FREE = "FREE"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"
    ADMIN_GRANTED = "ADMIN_GRANTED"
    EXPIRED = "EXPIRED"
    RECONCILIATION = "RECONCILIATION"


class BillingUnavailable(DomainError):
    pass


class BillingRejected(DomainError):
    """Provider explicitly rejected the request before creating a resource."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail  # Provider cause for the audit trail; never shown to users.


class BillingDivergence(DomainError):
    """Provider data contradicts local references; repeating the same event cannot fix it."""

    def __init__(self, message: str, team_id: UUID) -> None:
        super().__init__(message)
        self.team_id = team_id


def next_month(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, monthrange(year, month)[1]))
