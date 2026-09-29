"""Authenticated, transactional and idempotent provider event handling.

Canonical provider state is fetched BEFORE the short Team-locked transaction that
deduplicates the event and applies its effects, so provider I/O never holds the lock.
Financial access requires a payment event AND the provider's current payment state.
Observations apply in fetch order: a stale success cannot undo a newer refund/chargeback.
Transient failures return an error for provider retry, without local effects. Provider
data contradicting local references is recorded as DIVERGENT, without effects, and
acknowledged after commit so one event cannot stall the sequential queue; the audited
`python -m app.billing_admin <team> reconcile` reprocesses it with these same rules.
Raw payloads and payer/card data are never persisted.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.application.billing import Provider, audit, lock_team
from app.application.billing_access import access_state
from app.domain.billing import BillingDivergence, next_month
from app.infrastructure.billing_models import (
    BillingPayment,
    BillingSubscription,
    BillingWebhook,
    TeamBilling,
)
from app.infrastructure.config import Settings
from app.infrastructure.models import Team

PAYMENT_EVENTS = frozenset(
    {
        "PAYMENT_CREATED",
        "PAYMENT_CONFIRMED",
        "PAYMENT_RECEIVED",
        "PAYMENT_OVERDUE",
        "PAYMENT_REFUNDED",
        "PAYMENT_DELETED",
        "PAYMENT_CHARGEBACK_REQUESTED",
        "PAYMENT_CHARGEBACK_DISPUTE",
        "PAYMENT_AWAITING_CHARGEBACK_REVERSAL",
        "PAYMENT_UPDATED",
        "PAYMENT_RESTORED",
        "PAYMENT_REFUND_IN_PROGRESS",
    }
)
SUBSCRIPTION_EVENTS = frozenset(
    {
        "SUBSCRIPTION_CREATED",
        "SUBSCRIPTION_UPDATED",
        "SUBSCRIPTION_DELETED",
        "SUBSCRIPTION_INACTIVATED",
    }
)
PAID = frozenset({"CONFIRMED", "RECEIVED"})


@dataclass(frozen=True)
class PaymentFacts:
    """Provider state observed outside any transaction, applied later under the Team lock."""

    payment_id: str
    subscription_ref: str
    customer: str
    observed_at: datetime
    payment: dict[str, Any]
    subscription: dict[str, Any] | None
    via_checkout: frozenset[UUID]


def process(session: Session, payload: dict[str, Any], settings: Settings) -> None:
    event_id, event_type = str(payload["id"]), str(payload["event"])
    resource = (
        payload.get("payment") or payload.get("subscription") or payload.get("checkout") or {}
    )
    duplicate = session.scalar(select(BillingWebhook.id).where(BillingWebhook.event_id == event_id))
    session.commit()
    if duplicate:
        return
    facts = None
    if event_type in PAYMENT_EVENTS:
        facts = payment_facts(session, Provider(session, settings), resource)
    # Concurrent copies serialize on the unique index; rollback leaves the event retryable.
    inserted = session.scalar(
        insert(BillingWebhook)
        .values(event_id=event_id, event_type=event_type, status="PROCESSING")
        .on_conflict_do_nothing(index_elements=[BillingWebhook.event_id])
        .returning(BillingWebhook.id)
    )
    if inserted is None:
        session.commit()
        return
    record = session.get(BillingWebhook, inserted)
    assert record is not None
    record.resource_id = str(resource.get("id", ""))[:100] or None
    try:
        with session.begin_nested():
            if facts is not None:
                apply_payment(session, facts, event_type, settings)
            elif event_type.startswith("CHECKOUT_"):
                checkout_event(session, resource, event_type)
            elif event_type in SUBSCRIPTION_EVENTS:
                subscription_event(session, resource, event_type)
            elif event_type not in PAYMENT_EVENTS:
                record.status = "IGNORED"
    except BillingDivergence as divergence:
        record.status = "DIVERGENT"
        audit(
            session,
            divergence.team_id,
            "WEBHOOK_DIVERGENT",
            event_id,
            origin="webhook",
            reason=str(divergence)[:300],
        )
    if record.status == "PROCESSING":
        record.status = "PROCESSED"
    record.processed_at = datetime.now(UTC)
    session.commit()


def payment_facts(
    session: Session, provider: Provider, event: dict[str, Any]
) -> PaymentFacts | None:
    """Read local references, end the transaction, then query the provider."""
    payment_id = str(event.get("id") or "")
    reference = str(event.get("subscription") or "")
    customer = str(event.get("customer") or "")
    if not payment_id or not reference or not customer:
        return None
    known = session.scalar(
        select(BillingSubscription.id).where(BillingSubscription.provider_id == reference)
    )
    team_id = session.scalar(select(TeamBilling.team_id).where(TeamBilling.customer_id == customer))
    candidates: list[tuple[UUID, str | None]] = []
    if known is None and team_id is not None:
        candidates = [
            (item_id, checkout_id)
            for item_id, checkout_id in session.execute(
                select(BillingSubscription.id, BillingSubscription.checkout_id).where(
                    BillingSubscription.team_id == team_id
                )
            )
        ]
    session.commit()
    if known is None and team_id is None:
        return None  # An unrelated customer in the same Asaas account.
    observed_at = datetime.now(UTC)
    # A deleted resource can still be retrieved by Asaas. If unavailable, retry rather than grant.
    payment = provider.request("GET", f"/payments/{quote(payment_id, safe='')}")
    canonical = None
    via_checkout: set[UUID] = set()
    if known is None:
        canonical = provider.request("GET", f"/subscriptions/{quote(reference, safe='')}")
        for item_id, checkout_id in candidates:
            if checkout_id and canonical.get("externalReference") != f"eleven-sub:{item_id}":
                charges = provider.list_all("/payments", {"checkoutSession": checkout_id})
                if any(
                    p.get("subscription") == reference and p.get("customer") == customer
                    for p in charges
                ):
                    via_checkout.add(item_id)
    return PaymentFacts(
        payment_id,
        reference,
        customer,
        observed_at,
        payment,
        canonical,
        frozenset(via_checkout),
    )


def adopt(session: Session, facts: PaymentFacts) -> BillingSubscription | None:
    """Bind a provider subscription created by this team's own intent or checkout."""
    account = session.scalar(select(TeamBilling).where(TeamBilling.customer_id == facts.customer))
    if account is None:
        return None
    lock_team(session, account.team_id)
    canonical = facts.subscription or {}
    for item in session.scalars(
        select(BillingSubscription).where(BillingSubscription.team_id == account.team_id)
    ):
        matches = (
            canonical.get("externalReference") == f"eleven-sub:{item.id}"
            or item.id in facts.via_checkout
        )
        if (
            matches
            and item.provider_id in (None, facts.subscription_ref)
            and canonical.get("customer") == facts.customer
            and canonical.get("cycle") == "MONTHLY"
            and Decimal(str(canonical.get("value", 0))) == item.amount
            and canonical.get("billingType") == item.method
        ):
            item.provider_id, item.operation_status = facts.subscription_ref, "READY"
            session.flush()
            return item
    # Repeating the same event cannot create a match: park it for reconciliation.
    raise BillingDivergence("Assinatura do Asaas sem correspondência local.", account.team_id)


def apply_payment(session: Session, facts: PaymentFacts, kind: str, settings: Settings) -> None:
    subscription = session.scalar(
        select(BillingSubscription).where(BillingSubscription.provider_id == facts.subscription_ref)
    )
    if subscription is None:
        subscription = adopt(session, facts)
        if subscription is None:
            return
    team = session.scalar(select(Team).where(Team.id == subscription.team_id).with_for_update())
    assert team is not None
    session.refresh(subscription)
    before = access_state(session, team)
    account = session.scalar(select(TeamBilling).where(TeamBilling.team_id == team.id))
    if (
        account is None
        or account.environment != settings.asaas_env
        or account.customer_id != facts.customer
    ):
        raise BillingDivergence("Referências de cobrança divergentes.", team.id)
    payment = facts.payment
    if (
        payment.get("subscription") != subscription.provider_id
        or payment.get("customer") != account.customer_id
        or Decimal(str(payment.get("value", 0))) != subscription.amount
    ):
        raise BillingDivergence("Referências ou valor da cobrança divergentes.", team.id)
    due = date.fromisoformat(str(payment["dueDate"]))
    status = "DELETED" if payment.get("deleted") else str(payment.get("status", "PENDING"))
    row = session.scalar(
        select(BillingPayment).where(BillingPayment.provider_id == facts.payment_id)
    )
    if row is None:
        row = BillingPayment(
            subscription_id=subscription.id,
            provider_id=facts.payment_id,
            due_date=due,
            period_end=next_month(due),
            amount=subscription.amount,
            status=status,
            event_at=facts.observed_at,
        )
        session.add(row)
    elif row.subscription_id != subscription.id:
        raise BillingDivergence("Cobrança vinculada a outra assinatura.", team.id)
    elif facts.observed_at > row.event_at:
        # Only a newer observation replaces the status; an older fetch may arrive late.
        if row.status != status:
            audit(session, team.id, "PAYMENT_" + status, row.provider_id, origin="webhook")
        row.status, row.event_at = status, facts.observed_at
    # CREATED (even if provider already reports paid) cannot activate by itself.
    if (
        kind in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
        and status in PAID
        and row.confirmed_at is None
    ):
        row.confirmed_at = datetime.now(UTC)
        subscription.started_at = subscription.started_at or row.confirmed_at
        audit(session, team.id, "PAYMENT_CONFIRMED", row.provider_id, origin="webhook")
    session.flush()
    after = access_state(session, team)
    if before[:2] != after[:2]:
        audit(session, team.id, "ACCESS_" + after[1].value, row.provider_id, origin="webhook")


def checkout_event(session: Session, resource: dict[str, Any], kind: str) -> None:
    item = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.checkout_id == str(resource.get("id", ""))
        )
    )
    if item is None and resource.get("externalReference"):
        for candidate in session.scalars(
            select(BillingSubscription).where(
                BillingSubscription.method == "CREDIT_CARD",
                BillingSubscription.checkout_id.is_(None),
            )
        ):
            if resource["externalReference"] == f"eleven-sub:{candidate.id}":
                item = candidate
                break
    if item is None:
        return
    lock_team(session, item.team_id)
    item.checkout_id = str(resource["id"])
    item.operation_status = "READY"
    # Checkout PAID is not used to grant a period; the payment webhook supplies the charge.
    if kind in {"CHECKOUT_CANCELED", "CHECKOUT_EXPIRED"} and not item.provider_id:
        item.cancelled_at = item.cancelled_at or datetime.now(UTC)
        audit(session, item.team_id, kind, item.checkout_id, origin="webhook")


def subscription_event(session: Session, resource: dict[str, Any], kind: str) -> None:
    item = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.provider_id == str(resource.get("id", ""))
        )
    )
    if item is None:
        return  # PAYMENT_* reconciles the association when delivery order is inverted.
    lock_team(session, item.team_id)
    if kind in {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"}:
        item.cancelled_at = item.cancelled_at or datetime.now(UTC)
        audit(session, item.team_id, kind, str(item.provider_id), origin="webhook")
