from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.billing_reconciliation import reconcile
from app.infrastructure.billing_models import BillingAudit, BillingPayment, BillingWebhook
from app.infrastructure.config import get_settings
from tests.test_billing import enabled_cards, payload, provider, webhook  # noqa: F401
from tests.test_card_recurring import card  # noqa: F401


@pytest.mark.parametrize(
    "status,expected", [("CONFIRMED", "pro"), ("RECEIVED", "pro"), ("PENDING", "free")]
)
def test_canonical_card_import_repeat_and_later_webhook(session, card, provider, status, expected):  # noqa: F811
    team, client, path, subscription, payment = card
    payment.update(status=status, billingType="CREDIT_CARD", checkoutSession="checkout_test")

    def run():
        return reconcile(
            session, team.id, operator="test", reason="canonical sandbox", settings=get_settings()
        )

    assert client.get(path).json()["plan"] == "free"
    run()
    assert subscription.provider_id == "sub_test"
    assert client.get(path).json()["plan"] == expected
    row = session.scalar(select(BillingPayment))
    period = (row.due_date, row.period_end, row.confirmed_at)
    count = session.scalar(select(func.count()).select_from(BillingAudit))
    run()
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1
    assert session.scalar(select(func.count()).select_from(BillingAudit)) == count
    assert session.scalar(select(func.count()).select_from(BillingWebhook)) == 0
    audits = session.scalars(
        select(BillingAudit).where(
            BillingAudit.action.in_(
                [
                    "PAYMENT_CONFIRMED",
                    "ACCESS_ACTIVE",
                    "CANONICAL_PAYMENT_IMPORTED",
                    "RECONCILED_SUBSCRIPTION",
                ]
            )
        )
    ).all()
    assert audits and all(a.origin == "reconciliation" for a in audits)
    if status != "PENDING":
        assert webhook(client, payload()).status_code == 200
        assert (row.due_date, row.period_end, row.confirmed_at) == period
        assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1
    assert not any(c[0] in ("PUT", "DELETE") for c in provider["calls"])
    assert len([c for c in provider["calls"] if c[:2] == ("POST", "/checkouts")]) == 1


@pytest.mark.parametrize(
    "field,value", [("customer", "other"), ("value", 1), ("checkoutSession", "other")]
)
def test_canonical_card_rejects_wrong_binding(session, card, field, value):  # noqa: F811
    team, client, path, subscription, payment = card
    payment.update(status="CONFIRMED", billingType="CREDIT_CARD", checkoutSession="checkout_test")
    payment[field] = value
    reconcile(session, team.id, operator="test", reason="wrong binding", settings=get_settings())
    assert subscription.provider_id is None
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 0
    assert client.get(path).json()["plan"] == "free"


def test_canonical_card_does_not_restore_newer_chargeback(session, card):  # noqa: F811
    team, client, path, _, payment = card
    payment.update(status="CONFIRMED", billingType="CREDIT_CARD", checkoutSession="checkout_test")
    reconcile(session, team.id, operator="test", reason="first", settings=get_settings())
    row = session.scalar(select(BillingPayment))
    row.status = "CHARGEBACK_REQUESTED"
    row.event_at = datetime.now(UTC) + timedelta(minutes=1)
    session.commit()
    reconcile(
        session, team.id, operator="test", reason="older observation", settings=get_settings()
    )
    assert row.status == "CHARGEBACK_REQUESTED"
    assert client.get(path).json()["plan"] == "free"


def test_concurrent_canonical_card_reconciliation(engine, session, card):  # noqa: F811
    team, client, path, _, payment = card
    payment.update(status="CONFIRMED", billingType="CREDIT_CARD", checkoutSession="checkout_test")
    team_id = team.id
    session.commit()
    settings = get_settings()

    def run(_):
        with Session(engine) as other:
            return reconcile(
                other, team_id, operator="test", reason="concurrent", settings=settings
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, range(2)))
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1
    assert (
        session.scalar(
            select(func.count())
            .select_from(BillingAudit)
            .where(BillingAudit.action == "PAYMENT_CONFIRMED")
        )
        == 1
    )
    assert client.get(path).json()["plan"] == "pro"
