"""Close unpaid initial Pix intents; the access deadline itself needs no worker.

No provider I/O under a transaction. EXPIRING claims serialize cleanup; ambiguous
payments are preserved for review, never refunded or used to grant access here.
Pending charges are removed before the recurrence: Asaas refuses to remove a paid
charge, so a payment racing with this cleanup keeps its subscription for review.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.application.billing import (
    Provider,
    audit,
    billing_account,
    lock_team,
    stop_remote,
    subscription_of,
)
from app.application.billing_access import pix_expired
from app.domain.billing import BillingRejected, BillingUnavailable
from app.infrastructure.billing_models import BillingPayment
from app.infrastructure.config import Settings

OPEN = ("PENDING", "OVERDUE")
# Each provider call times out after 65 s, so an older EXPIRING claim is no longer in flight.
CLAIM = timedelta(minutes=15)


def review(session: Session, team_id: UUID, subscription_id: UUID, reason: str) -> None:
    item = subscription_of(session, subscription_id)
    if item.operation_status != "REVIEW":
        item.operation_status = "REVIEW"
        audit(
            session, team_id, "PIX_EXPIRY_REVIEW", str(item.id), origin="expiration", reason=reason
        )


def expire_initial_pix(
    session: Session,
    team_id: UUID,
    subscription_id: UUID,
    settings: Settings,
    now: datetime | None = None,
) -> None:
    """Called by authorized billing operations or the trusted reconciliation command."""
    now = now or datetime.now(UTC)
    lock_team(session, team_id)
    item = subscription_of(session, subscription_id)
    account = billing_account(session, team_id)
    if item.team_id != team_id or account.environment != settings.asaas_env:
        raise BillingUnavailable("Referências de contratação divergentes.")
    # A cancelled attempt already stopped its recurrence or awaits operator reconciliation.
    if not pix_expired(item, now) or item.operation_status == "REVIEW" or item.cancelled_at:
        session.commit()
        return
    if item.operation_status == "EXPIRING" and item.updated_at > now - CLAIM:
        session.commit()
        return
    paid = session.scalar(
        select(BillingPayment.id).where(
            BillingPayment.subscription_id == item.id,
            BillingPayment.status.not_in((*OPEN, "DELETED")),
        )
    )
    if paid:
        review(session, team_id, item.id, "Pagamento existente: encerramento automático bloqueado.")
        session.commit()
        return
    provider_id, customer_id, amount = item.provider_id, account.customer_id, item.amount
    if not provider_id:
        if item.operation_status == "NEW":  # No creation request was ever sent.
            item.operation_status, item.cancelled_at = "EXPIRED", now
            audit(session, team_id, "PIX_SIGNUP_EXPIRED", str(item.id), origin="expiration")
        # Unknown creation must first be reconciled; never assume a timed-out POST failed.
        session.commit()
        return
    item.operation_status = "EXPIRING"
    flag_modified(item, "operation_status")  # A stale claim taken over gets a new updated_at.
    audit(session, team_id, "PIX_EXPIRY_STARTED", str(item.id), origin="expiration")
    session.commit()
    provider = Provider(session, settings)
    path = f"/subscriptions/{quote(provider_id, safe='')}/payments"

    def ours(charge: dict[str, Any]) -> bool:
        return (
            charge.get("status") in (*OPEN, "DELETED")
            and charge.get("customer") == customer_id
            and charge.get("subscription") == provider_id
            and Decimal(str(charge.get("value", 0))) == amount
        )

    try:
        charges = provider.list_all(path, {})
        if not all(ours(charge) for charge in charges):
            reason = "Asaas informa pagamento ou cobrança divergente."
            settle(session, team_id, subscription_id, now, reason)
            return
        # A payment confirmed meanwhile moved the claim to REVIEW: keep the recurrence.
        lock_team(session, team_id)
        claimed = subscription_of(session, subscription_id).operation_status == "EXPIRING"
        session.commit()
        if not claimed:
            return
        for charge in charges:
            if charge.get("status") in OPEN and not charge.get("deleted"):
                charge_id = quote(str(charge["id"]), safe="")
                provider.request("DELETE", f"/payments/{charge_id}")
        stop_remote(provider, provider_id, None)
        remaining = provider.list_all(path, {})
    except BillingRejected:
        # Asaas refuses to remove a charge paid meanwhile: preserve everything for review.
        session.rollback()
        settle(session, team_id, subscription_id, now, "Asaas recusou o encerramento remoto.")
        return
    except BillingUnavailable:
        session.rollback()
        lock_team(session, team_id)
        item = subscription_of(session, subscription_id)
        if item.operation_status == "EXPIRING":
            # Retryable, not cancelled: no new recurrence starts before this one is closed.
            item.operation_status = "EXPIRED"
            audit(session, team_id, "PIX_EXPIRY_RETRY", str(item.id), origin="expiration")
        session.commit()
        raise
    outcome = None
    if any(charge.get("status") not in (*OPEN, "DELETED") for charge in remaining):
        outcome = "Pagamento observado durante o encerramento."
    elif any(charge.get("status") in OPEN and not charge.get("deleted") for charge in remaining):
        outcome = "Asaas ainda informa cobrança pendente após a remoção."
    settle(session, team_id, subscription_id, now, outcome)


def settle(
    session: Session, team_id: UUID, subscription_id: UUID, now: datetime, reason: str | None
) -> None:
    """Record the cleanup outcome unless a payment event already moved the claim."""
    lock_team(session, team_id)
    item = subscription_of(session, subscription_id)
    if item.operation_status == "EXPIRING" and not item.started_at:
        if reason:
            review(session, team_id, item.id, reason)
        else:
            item.operation_status, item.cancelled_at = "EXPIRED", now
            audit(session, team_id, "PIX_SIGNUP_EXPIRED", str(item.id), origin="expiration")
    session.commit()
