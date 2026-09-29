"""One access decision for API presentation, permissions and paid capabilities.

Expiration is evaluated on every access, even when no webhook/job runs that day.
Legacy Team.plan is respected only until a billing record is explicitly created.
Billing rows for any number of teams load in at most three queries (no N+1).
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.billing import GRACE_DAYS, PIX_SIGNUP_MINUTES
from app.domain.billing import SubscriptionStatus as Status
from app.domain.policies import Plan
from app.infrastructure.billing_models import BillingPayment, BillingSubscription, TeamBilling
from app.infrastructure.models import Team

Access = tuple[Plan, Status, str | None]
REVERSALS = (
    "REFUNDED",
    "CHARGEBACK_REQUESTED",
    "CHARGEBACK_DISPUTE",
    "AWAITING_CHARGEBACK_REVERSAL",
)


def pix_deadline(subscription: BillingSubscription | None) -> datetime | None:
    if subscription and subscription.method == "PIX" and not subscription.started_at:
        return subscription.created_at + timedelta(minutes=PIX_SIGNUP_MINUTES)
    return None


def pix_expired(subscription: BillingSubscription | None, now: datetime) -> bool:
    deadline = pix_deadline(subscription)
    return deadline is not None and now >= deadline


def access_states(
    session: Session, teams: Iterable[Team], now: datetime | None = None
) -> dict[UUID, Access]:
    by_id = {team.id: team for team in teams}
    if not by_id:
        return {}
    now = now or datetime.now(UTC)
    accounts = {
        account.team_id: account
        for account in session.scalars(
            select(TeamBilling).where(TeamBilling.team_id.in_(list(by_id)))
        )
    }
    billed = [team_id for team_id, account in accounts.items() if not granted(account, now)]
    subscriptions: dict[UUID, list[BillingSubscription]] = defaultdict(list)
    if billed:
        for subscription in session.scalars(
            select(BillingSubscription)
            .where(BillingSubscription.team_id.in_(billed))
            .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        ):
            subscriptions[subscription.team_id].append(subscription)
    payments: dict[UUID, list[BillingPayment]] = defaultdict(list)
    ids = [item.id for items in subscriptions.values() for item in items]
    if ids:
        for payment in session.scalars(
            select(BillingPayment)
            .where(BillingPayment.subscription_id.in_(ids))
            .order_by(BillingPayment.due_date.desc())
        ):
            payments[payment.subscription_id].append(payment)
    return {
        team_id: decide(team, accounts.get(team_id), subscriptions.get(team_id, []), payments, now)
        for team_id, team in by_id.items()
    }


def granted(account: TeamBilling, now: datetime) -> bool:
    return account.grant_active and (
        account.grant_expires_at is None or now < account.grant_expires_at
    )


def decide(
    team: Team,
    account: TeamBilling | None,
    subscriptions: list[BillingSubscription],
    payments: dict[UUID, list[BillingPayment]],
    now: datetime,
) -> Access:
    if account is None:
        plan = Plan(team.plan)
        return plan, Status.ADMIN_GRANTED if plan == Plan.PRO else Status.FREE, None
    if granted(account, now):
        grant_end = account.grant_expires_at
        return Plan.PRO, Status.ADMIN_GRANTED, grant_end.isoformat() if grant_end else None
    if not subscriptions:
        return Plan.FREE, Status.FREE, None
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    # A cancelled paid period can overlap a later pending renewal. Keep paid coverage.
    fallback = Status.PENDING
    for index, subscription in enumerate(subscriptions):
        if subscription.operation_status == "REVIEW" or pix_expired(subscription, now):
            if not index:
                if subscription.operation_status == "REVIEW":
                    fallback = Status.RECONCILIATION
                elif subscription.cancelled_at and subscription.operation_status != "EXPIRED":
                    fallback = Status.CANCELLED  # Closed by the president/provider, not the clock.
                else:
                    fallback = Status.EXPIRED
            continue  # Late/ambiguous first payments never grant coverage.
        charges = payments.get(subscription.id, [])
        paid = [p for p in charges if p.confirmed_at and p.status in ("CONFIRMED", "RECEIVED")]
        covered = [p for p in paid if p.due_date <= today < p.period_end]
        if covered:
            expiry = max(p.period_end for p in covered).isoformat()
            return (
                Plan.PRO,
                Status.CANCELLED if subscription.cancelled_at else Status.ACTIVE,
                expiry,
            )
        expired_paid = [p for p in paid if p.period_end <= today]
        if expired_paid and not subscription.cancelled_at:
            last = max(expired_paid, key=lambda p: p.period_end)
            revoked = any(p.due_date >= last.period_end and p.status in REVERSALS for p in charges)
            if not revoked and today < last.period_end + timedelta(days=GRACE_DAYS):
                return Plan.PRO, Status.OVERDUE, last.period_end.isoformat()
        if index:
            continue  # Older contracts may grant paid coverage, but not replace the current status.
        if subscription.cancelled_at:
            fallback = Status.CANCELLED
        elif expired_paid or any(p.status in REVERSALS for p in charges):
            fallback = Status.SUSPENDED
        elif any(p.due_date < today for p in charges):
            fallback = Status.OVERDUE
    return Plan.FREE, fallback, None


def access_state(session: Session, team: Team, now: datetime | None = None) -> Access:
    return access_states(session, [team], now)[team.id]


def effective_plan(session: Session, team: Team) -> Plan:
    return access_state(session, team)[0]


def effective_plans(session: Session, teams: Iterable[Team]) -> dict[UUID, Plan]:
    """Plans for several teams at once; use it instead of effective_plan inside loops."""
    return {team_id: state[0] for team_id, state in access_states(session, teams).items()}


def team_has_pro_access(session: Session, team_id: UUID) -> bool:
    team = session.get(Team, team_id)
    return team is not None and effective_plan(session, team) == Plan.PRO
