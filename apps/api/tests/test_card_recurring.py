"""Recurring hosted card checkout; isolated database and simulated Asaas only."""

from datetime import datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.application.billing_access import access_state
from app.domain.billing import next_month
from app.infrastructure.asaas import Asaas
from app.infrastructure.billing_models import BillingAudit, BillingPayment, BillingSubscription
from tests.test_billing import (  # noqa: F401
    checkout_data,
    enabled_cards,
    payload,
    provider,
    setup,
    webhook,
)


@pytest.fixture
def card(session, provider, enabled_cards, monkeypatch):  # noqa: F811
    owner, team, client, path = setup(session)
    assert client.post(path + "/checkout", json=checkout_data("CREDIT_CARD")).status_code == 200
    subscription = session.scalar(select(BillingSubscription))
    provider["subscriptions"].append(
        {
            "id": "sub_test",
            "customer": "cus_test",
            "externalReference": f"eleven-sub:{subscription.id}",
            "billingType": "CREDIT_CARD",
            "cycle": "MONTHLY",
            "value": 29.99,
        }
    )
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    payment = {
        "id": "pay_test",
        "customer": "cus_test",
        "subscription": "sub_test",
        "value": 29.99,
        "dueDate": today.isoformat(),
        "status": "PENDING",
    }
    provider["payments"].append(payment)
    original = Asaas.request

    def request(self, method, endpoint, data=None, params=None):
        if method == "GET" and endpoint.startswith("/payments/"):
            provider["calls"].append((method, endpoint, data, params))
            return dict(next(p for p in provider["payments"] if endpoint == f"/payments/{p['id']}"))
        return original(self, method, endpoint, data, params)

    monkeypatch.setattr(Asaas, "request", request)
    return team, client, path, subscription, payment


def checkout_event(client, kind):
    return webhook(
        client,
        {"id": str(uuid4()), "event": kind, "checkout": {"id": "checkout_test"}},
    )


@pytest.mark.parametrize(
    "kind,status",
    [
        ("PAYMENT_AWAITING_RISK_ANALYSIS", "AWAITING_RISK_ANALYSIS"),
        ("PAYMENT_APPROVED_BY_RISK_ANALYSIS", "CONFIRMED"),
        ("PAYMENT_REPROVED_BY_RISK_ANALYSIS", "PENDING"),
        ("PAYMENT_CREDIT_CARD_CAPTURE_REFUSED", "PENDING"),
    ],
)
def test_card_analysis_and_capture_never_confirm_a_period(session, card, kind, status):
    team, client, path, subscription, payment = card
    payment["status"] = status
    event = payload(kind)
    assert webhook(client, event).status_code == 200
    assert webhook(client, event).status_code == 200
    assert client.get(path).json()["plan"] == "free"
    row = session.scalar(select(BillingPayment))
    assert row.confirmed_at is None and row.status == status
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1
    assert subscription.provider_id == "sub_test"
    payment["status"] = "CONFIRMED"
    assert webhook(client, payload()).status_code == 200
    assert client.get(path).json()["plan"] == "pro"


@pytest.mark.parametrize("terminal", ["CHECKOUT_CANCELED", "CHECKOUT_EXPIRED", None])
def test_checkout_and_subscription_out_of_order(session, card, provider, terminal):  # noqa: F811
    team, client, path, subscription, payment = card
    if terminal:
        assert checkout_event(client, terminal).status_code == 200
    assert checkout_event(client, "CHECKOUT_PAID").status_code == 200
    assert checkout_event(client, "CHECKOUT_CREATED").status_code == 200
    assert client.get(path).json()["plan"] == "free"
    assert subscription.provider_id is None
    assert (
        webhook(
            client,
            {
                "id": str(uuid4()),
                "event": "SUBSCRIPTION_CREATED",
                "subscription": {"id": "sub_test"},
            },
        ).status_code
        == 200
    )
    payment["status"] = "CONFIRMED"
    event = payload()
    assert webhook(client, event).status_code == 200
    assert webhook(client, event).status_code == 200
    assert (
        webhook(
            client,
            {
                "id": str(uuid4()),
                "event": "SUBSCRIPTION_UPDATED",
                "subscription": {"id": "sub_test"},
            },
        ).status_code
        == 200
    )
    assert subscription.provider_id == "sub_test"
    assert client.get(path).json()["plan"] == "pro"
    assert bool(subscription.cancelled_at) == bool(terminal)
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1
    assert len([c for c in provider["calls"] if c[:2] == ("POST", "/checkouts")]) == 1
    assert len([c for c in provider["calls"] if c[:2] == ("POST", "/customers")]) == 1
    assert not any(c[:2] == ("POST", "/subscriptions") for c in provider["calls"])
    assert client.post(path + "/refresh").status_code == 200
    assert subscription.provider_id == "sub_test"


def test_checkout_cannot_overwrite_review(session, card):
    _, client, path, subscription, _ = card
    subscription.operation_status = "REVIEW"
    session.commit()
    assert checkout_event(client, "CHECKOUT_CREATED").status_code == 200
    assert subscription.operation_status == "REVIEW"
    assert client.get(path).json()["plan"] == "free"


@pytest.mark.parametrize("cancel", [False, True])
def test_monthly_renewal_failure_grace_and_cancellation(session, card, provider, cancel):  # noqa: F811
    team, client, path, subscription, payment = card
    payment["status"] = "CONFIRMED"
    assert webhook(client, payload()).status_code == 200
    due = session.scalar(select(BillingPayment)).period_end
    renewal = {**payment, "id": "pay_second", "dueDate": due.isoformat(), "status": "PENDING"}
    provider["payments"].append(renewal)
    event = payload("PAYMENT_CREATED")
    event["payment"]["id"] = renewal["id"]
    assert webhook(client, event).status_code == 200
    assert client.get(path).json()["renewal_date"] == due.isoformat()
    assert client.get(path).json()["plan"] == "pro"
    clock = datetime.combine(due, time(12), ZoneInfo("America/Sao_Paulo"))
    if cancel:
        assert client.post(path + "/cancel", json={"confirm": True}).status_code == 200
        assert client.get(path).json()["plan"] == "pro"
        assert access_state(session, team, clock)[0].value == "free"
        assert subscription.cancelled_at is not None
        return
    event = {**event, "id": str(uuid4()), "event": "PAYMENT_CREDIT_CARD_CAPTURE_REFUSED"}
    assert webhook(client, event).status_code == 200
    assert access_state(session, team, clock)[0].value == "pro"  # Existing three-day grace.
    assert access_state(session, team, clock + timedelta(days=3))[0].value == "free"
    renewal["status"] = "RECEIVED"
    event = {**event, "id": str(uuid4()), "event": "PAYMENT_RECEIVED"}
    assert webhook(client, event).status_code == 200
    assert access_state(session, team, clock + timedelta(days=3))[0].value == "pro"
    assert access_state(session, team, clock)[2] == next_month(due).isoformat()
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 2


def test_partial_refund_is_audited_and_chargeback_removes_coverage(session, card):
    _, client, path, _, payment = card
    payment["status"] = "RECEIVED"
    assert webhook(client, payload("PAYMENT_RECEIVED")).status_code == 200
    partial = payload("PAYMENT_PARTIALLY_REFUNDED")
    assert webhook(client, partial).status_code == 200
    assert webhook(client, partial).status_code == 200
    assert (
        session.scalar(
            select(func.count())
            .select_from(BillingAudit)
            .where(BillingAudit.action == "PARTIAL_REFUND_REVIEW")
        )
        == 1
    )
    # No new proportional rule: canonical paid coverage remains pending manual review.
    assert client.get(path).json()["plan"] == "pro"
    payment["status"] = "CHARGEBACK_REQUESTED"
    assert webhook(client, payload("PAYMENT_CHARGEBACK_REQUESTED")).status_code == 200
    assert client.get(path).json()["plan"] == "free"
