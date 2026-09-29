from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.application import billing, billing_reconciliation, billing_webhooks
from app.application.billing_access import access_state
from app.application.billing_webhooks import PaymentFacts, apply_payment
from app.application.notification_delivery import recipients
from app.application.teams import add_member
from app.domain.billing import BillingRejected, BillingUnavailable
from app.domain.policies import Conflict, Permission, Role
from app.infrastructure.asaas import Asaas
from app.infrastructure.billing_models import (
    BillingAudit,
    BillingPayment,
    BillingSubscription,
    BillingWebhook,
    TeamBilling,
)
from app.infrastructure.config import get_settings
from tests.conftest import make_player
from tests.test_foundation import make_team
from tests.test_team_profiles import client_for


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("ASAAS_ENV", "sandbox")
    monkeypatch.setenv("ASAAS_API_KEY", "sandbox-test-key-never-real")
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "test-webhook-" + "x" * 32)
    monkeypatch.setenv("BILLING_RETURN_URL", "https://example.com/billing")
    get_settings.cache_clear()
    state = {"calls": [], "customers": [], "subscriptions": [], "payments": [], "status": "PENDING"}

    def request(self, method, path, data=None, params=None):
        state["calls"].append((method, path, data, params))
        if path == "/customers":
            if method == "GET":
                return {"data": state["customers"]}
            item = {"id": "cus_test", **data}
            state["customers"].append(item)
            return item
        if path == "/subscriptions":
            if method == "GET":
                return {"data": state["subscriptions"]}
            item = {"id": "sub_test", **data}
            state["subscriptions"].append(item)
            return item
        if path == "/checkouts":
            return {"id": "checkout_test"}
        if path.endswith("/pixQrCode"):
            return {"encodedImage": "image", "payload": "pix-test", "expirationDate": "2026-12-01"}
        if path.endswith("/payments") or path == "/payments":
            return {"data": state["payments"]}
        if path.startswith("/payments/"):
            return {
                "id": "pay_test",
                "customer": "cus_test",
                "subscription": "sub_test",
                "value": 30,
                "status": state["status"],
                "dueDate": date.today().isoformat(),
            }
        if method == "DELETE" or path.endswith("/cancel"):
            return {"deleted": True}
        if path == "/subscriptions/sub_test":
            return state["subscriptions"][0]
        raise AssertionError((method, path))

    monkeypatch.setattr(Asaas, "request", request)
    return state


def setup(session):
    owner = make_player(session)
    team = make_team(session, owner)
    client = client_for(session, owner)
    return owner, team, client, f"/v1/teams/{team.id}/billing"


def checkout_data(method="PIX"):
    return {
        "command_id": str(uuid4()),
        "method": method,
        "name": "Pagador Teste",
        "email": "payer@example.com",
        "cpf_cnpj": "12345678909",
        "confirm": True,
    }


def payload(kind="PAYMENT_CONFIRMED", event_id=None):
    return {
        "id": event_id or str(uuid4()),
        "event": kind,
        "payment": {"id": "pay_test", "subscription": "sub_test", "customer": "cus_test"},
    }


def webhook(client, data):
    return client.post(
        "/v1/billing/asaas/webhook",
        json=data,
        headers={"asaas-access-token": get_settings().asaas_webhook_token.get_secret_value()},
    )


def reconcile(session, team_id, now=None):
    session.rollback()  # Production sessions end with the request that failed.
    return billing_reconciliation.reconcile(
        session,
        team_id,
        operator="suporte",
        reason="teste isolado",
        settings=get_settings(),
        now=now,
    )


@pytest.mark.parametrize(
    "offset,status,confirmed,cancelled,grant,expected",
    [
        (0, "PENDING", False, False, False, "free"),
        (0, "CONFIRMED", True, False, False, "pro"),
        (1, "CONFIRMED", True, False, False, "pro"),
        (2, "CONFIRMED", True, False, False, "pro"),
        (3, "CONFIRMED", True, False, False, "free"),
        (1, "OVERDUE", False, False, False, "free"),
        (-1, "CONFIRMED", True, True, False, "pro"),
        (0, "CONFIRMED", True, True, False, "free"),
        (-1, "REFUNDED", True, False, False, "free"),
        (-1, "CHARGEBACK_REQUESTED", True, False, False, "free"),
        (3, "PENDING", False, False, True, "pro"),
    ],
)
def test_access_periods(session, offset, status, confirmed, cancelled, grant, expected):
    owner, team, _, _ = setup(session)
    now = datetime(2026, 10, 10, 15, tzinfo=UTC)
    account = TeamBilling(team_id=team.id, environment="sandbox", grant_active=grant)
    sub = BillingSubscription(
        team_id=team.id,
        command_id=uuid4(),
        method="PIX",
        amount=30,
        plan_code="PRO_MONTHLY",
        cancelled_at=now if cancelled else None,
    )
    session.add_all([account, sub])
    session.flush()
    end = now.date() - timedelta(days=offset)
    session.add(
        BillingPayment(
            subscription_id=sub.id,
            provider_id="pay",
            due_date=end - timedelta(days=30),
            period_end=end,
            amount=30,
            status=status,
            confirmed_at=now if confirmed else None,
            event_at=now,
        )
    )
    session.flush()
    assert access_state(session, team, now)[0].value == expected


def test_checkout_dedup_and_payment_success(session, provider):
    _, team, client, path = setup(session)
    data = checkout_data()
    assert client.post(path + "/checkout", json=data).status_code == 200
    assert client.post(path + "/checkout", json=data).status_code == 200
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 200
    assert len(provider["customers"]) == len(provider["subscriptions"]) == 1
    assert client.get(path).json()["plan"] == "free"
    provider["status"] = "CONFIRMED"
    assert webhook(client, payload("PAYMENT_CREATED")).status_code == 200
    assert client.get(path).json()["plan"] == "free"
    event = payload()
    assert webhook(client, event).status_code == 200
    assert webhook(client, event).status_code == 200
    assert client.get(path).json()["plan"] == "pro"
    assert client.get(f"/v1/teams/{team.id}").json()["plan"] == "pro"
    assert client.get(f"/v1/teams/{team.id}/lineups").json()["enabled"] is True
    assert (
        session.scalar(
            select(func.count())
            .select_from(BillingAudit)
            .where(BillingAudit.action == "PAYMENT_CONFIRMED")
        )
        == 1
    )
    assert "sandbox-test-key" not in client.get(path).text


@pytest.mark.parametrize("reversal", ["REFUNDED", "CHARGEBACK_REQUESTED", "DELETED"])
def test_reversal_and_stale_success_cannot_restore(session, provider, reversal):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    provider["status"] = "CONFIRMED"
    webhook(client, payload())
    provider["status"] = reversal
    assert webhook(client, payload("PAYMENT_" + reversal)).status_code == 200
    assert webhook(client, payload()).status_code == 200
    assert client.get(path).json()["plan"] == "free"


def test_webhook_auth_and_rollback(session, provider, monkeypatch):
    _, _, client, path = setup(session)
    assert client.post("/v1/billing/asaas/webhook", json=payload()).status_code == 401
    client.post(path + "/checkout", json=checkout_data())
    original = Asaas.request

    def fail(self, method, path, *args, **kwargs):
        if path == "/payments/pay_test":
            raise BillingUnavailable("Indisponível")
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", fail)
    assert webhook(client, payload()).status_code == 503
    session.rollback()
    assert session.scalar(select(func.count()).select_from(BillingWebhook)) == 0
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 0


def test_only_president_even_with_all_admin_grants(session, provider):
    owner, team, client, path = setup(session)
    team.plan = "pro"
    other = make_player(session)
    add_member(
        session,
        team_id=team.id,
        player_id=other.id,
        role=Role.ADMIN,
        permissions=frozenset(Permission),
    )
    session.commit()
    admin = client_for(session, other)
    assert admin.get(path).status_code == 200
    for action, data in [
        ("checkout", checkout_data()),
        ("cancel", {"confirm": True}),
        ("refresh", {}),
    ]:
        assert admin.post(path + "/" + action, json=data).status_code == 403
    outsider = client_for(session, make_player(session))
    assert outsider.get(path).status_code == 404
    assert provider["calls"] == []


def test_timeout_does_not_repeat_subscription_post(session, provider, monkeypatch):
    _, _, client, path = setup(session)
    original = Asaas.request
    attempts = []

    def fail(self, method, path, *args, **kwargs):
        if method == "POST" and path == "/subscriptions":
            attempts.append(1)
            raise BillingUnavailable("Conciliação pendente")
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", fail)
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 503
    session.rollback()
    result = client.post(path + "/checkout", json=checkout_data())
    assert result.status_code == 200 and "notice" in result.json()
    assert len(attempts) == 1


def test_cancel_preserves_paid_period_and_history(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    provider["status"] = "RECEIVED"
    webhook(client, payload("PAYMENT_RECEIVED"))
    cancelled = client.post(path + "/cancel", json={"confirm": True})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED" and cancelled.json()["plan"] == "pro"
    assert client.post(path + "/cancel", json={"confirm": True}).status_code == 200
    assert len([c for c in provider["calls"] if c[0] == "DELETE"]) == 1
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1


def test_card_uses_hosted_monthly_checkout_no_card_capture(session, provider):
    _, _, client, path = setup(session)
    response = client.post(path + "/checkout", json=checkout_data("CREDIT_CARD"))
    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://sandbox.asaas.com/")
    request = next(c[2] for c in provider["calls"] if c[1] == "/checkouts")
    assert request["subscription"]["cycle"] == "MONTHLY"
    assert request["items"][0]["value"] == 30
    assert "creditCard" not in request


def test_admin_grant_revoke_and_expiration(session, provider):
    _, team, client, path = setup(session)
    for enabled, expected in [(True, "pro"), (False, "free")]:
        billing.administrative_grant(
            session,
            team.id,
            enabled=enabled,
            operator="test-operator",
            reason="isolated fixture",
            settings=get_settings(),
        )
        assert client.get(path).json()["plan"] == expected
    billing.administrative_grant(
        session,
        team.id,
        enabled=True,
        operator="test-operator",
        reason="expired",
        settings=get_settings(),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert client.get(path).json()["plan"] == "free"


def test_concurrent_checkouts_and_duplicate_webhook(engine, session, provider):
    owner, team, _, _ = setup(session)
    owner_id, team_id = owner.user_id, team.id
    session.commit()
    settings = get_settings()

    def start(_):
        with Session(engine) as other:
            try:
                billing.begin_checkout(
                    other, owner_id, team_id, billing.CheckoutInput(**checkout_data()), settings
                )
            except Conflict:
                pass  # A concurrent in-flight intent is safe to reconcile, never duplicate.

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(start, range(2)))
    assert len(provider["customers"]) == len(provider["subscriptions"]) == 1
    provider["status"] = "CONFIRMED"
    event = payload()

    def deliver(_):
        with Session(engine) as other:
            billing_webhooks.process(other, event, settings)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(deliver, range(2)))
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(BillingWebhook)) == 1
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1


def test_explicit_provider_rejection_allows_corrected_retry(session, provider, monkeypatch):
    _, _, client, path = setup(session)
    original = Asaas.request
    failures = [True]

    def reject(self, method, path, *args, **kwargs):
        if path == "/customers" and method == "POST" and failures:
            failures.pop()
            raise BillingRejected("Dados recusados")
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", reject)
    data = checkout_data()
    assert client.post(path + "/checkout", json=data).status_code == 400
    assert client.post(path + "/checkout", json=data).status_code == 200
    assert len(provider["customers"]) == 1


def test_expired_pro_enforced_in_all_team_contracts(session, provider):
    owner, team, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    provider["status"] = "CONFIRMED"
    webhook(client, payload())
    payment = session.scalar(select(BillingPayment))
    payment.due_date, payment.period_end = (
        date.today() - timedelta(days=40),
        date.today() - timedelta(days=5),
    )
    session.commit()
    assert client.get(path).json()["plan"] == "free"
    assert client.get(f"/v1/teams/{team.id}").json()["plan"] == "free"
    assert client.get(f"/v1/teams/{team.id}/administration").json()["active_player_limit"] == 24
    assert client.get(f"/v1/teams/{team.id}/lineups").json()["enabled"] is False
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 1


def test_provider_io_never_holds_the_team_lock(engine, session, provider, monkeypatch):
    _, team, client, path = setup(session)
    team_id, original, methods = team.id, Asaas.request, []

    def unlocked(self, method, path, *args, **kwargs):
        with engine.connect() as other:
            # NOWAIT fails at once if any transaction still holds the Team row lock.
            other.execute(
                text("SELECT id FROM teams WHERE id = :id FOR UPDATE NOWAIT"), {"id": team_id}
            )
            other.rollback()
        methods.append(method)
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", unlocked)
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 200
    assert client.post(path + "/refresh", json={}).status_code == 200
    provider["status"] = "CONFIRMED"
    assert webhook(client, payload()).status_code == 200
    assert client.post(path + "/cancel", json={"confirm": True}).status_code == 200
    assert {"GET", "POST", "DELETE"} <= set(methods)


def test_divergent_webhook_is_parked_then_reconciled(session, provider, monkeypatch):
    _, team, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    original = Asaas.request

    def edited(self, method, path, *args, **kwargs):
        value = original(self, method, path, *args, **kwargs)
        return {**value, "value": 25} if path == "/payments/pay_test" else value

    monkeypatch.setattr(Asaas, "request", edited)
    provider["status"] = "CONFIRMED"
    event_data = payload()
    # A permanent divergence is recorded and acknowledged: it never stalls Asaas retries.
    assert webhook(client, event_data).status_code == 200
    parked = session.scalar(
        select(BillingWebhook).where(BillingWebhook.event_id == event_data["id"])
    )
    assert parked.status == "DIVERGENT"
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == 0
    assert client.get(path).json()["plan"] == "free"
    monkeypatch.setattr(Asaas, "request", original)
    report = reconcile(session, team.id)
    session.refresh(parked)
    assert parked.status == "PROCESSED"
    assert any("reprocessado" in line for line in report)
    assert client.get(path).json()["plan"] == "pro"


def test_reconcile_releases_claims_the_provider_never_fulfilled(session, provider, monkeypatch):
    _, team, client, path = setup(session)
    original, failing = Asaas.request, {"/customers", "/subscriptions"}

    def timeout(self, method, path, *args, **kwargs):
        if method == "POST" and path in failing:
            failing.discard(path)
            raise BillingUnavailable("Tempo esgotado sem criação no Asaas")
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", timeout)
    later = datetime.now(UTC) + timedelta(hours=3)
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 503
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 409
    # A recent claim may still be in flight: nothing is released yet.
    assert "aguarde" in " ".join(reconcile(session, team.id))
    reconcile(session, team.id, later)
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 503
    reconcile(session, team.id, later)
    response = client.post(path + "/checkout", json=checkout_data())
    assert response.status_code == 200 and response.json()["status"] == "PENDING"
    assert len(provider["customers"]) == len(provider["subscriptions"]) == 1
    actions = set(
        session.scalars(select(BillingAudit.action).where(BillingAudit.origin == "operator"))
    )
    assert {"CUSTOMER_CLAIM_RELEASED", "INTENT_ABANDONED"} <= actions


def test_reconcile_records_subscription_created_before_a_lost_response(
    session, provider, monkeypatch
):
    _, team, client, path = setup(session)
    original = Asaas.request

    def lost(self, method, path, *args, **kwargs):
        value = original(self, method, path, *args, **kwargs)
        if method == "POST" and path == "/subscriptions":
            raise BillingUnavailable("Criada no Asaas, resposta perdida")
        return value

    monkeypatch.setattr(Asaas, "request", lost)
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 503
    reconcile(session, team.id)
    subscription = session.scalar(select(BillingSubscription))
    assert (subscription.provider_id, subscription.operation_status) == ("sub_test", "READY")
    assert len(provider["subscriptions"]) == 1


def test_older_observation_never_overwrites_a_newer_refund(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    start = datetime.now(UTC)

    def observed(status, seconds):
        charge = {
            "id": "pay_test",
            "customer": "cus_test",
            "subscription": "sub_test",
            "value": 30,
            "status": status,
            "dueDate": date.today().isoformat(),
        }
        return PaymentFacts(
            "pay_test",
            "sub_test",
            "cus_test",
            start + timedelta(seconds=seconds),
            charge,
            None,
            frozenset(),
        )

    # Fetches run outside the lock, so a success read earlier may be applied later.
    apply_payment(session, observed("REFUNDED", 2), "PAYMENT_REFUNDED", get_settings())
    apply_payment(session, observed("CONFIRMED", 1), "PAYMENT_CONFIRMED", get_settings())
    session.commit()
    assert session.scalar(select(BillingPayment.status)) == "REFUNDED"
    assert client.get(path).json()["plan"] == "free"


def test_plan_decisions_use_a_fixed_number_of_queries(engine, session):
    _, team, _, _ = setup(session)
    session.add(TeamBilling(team_id=team.id, environment="sandbox"))
    for index in range(3):
        old = BillingSubscription(
            team_id=team.id,
            command_id=uuid4(),
            method="PIX",
            amount=30,
            plan_code="PRO_MONTHLY",
            cancelled_at=datetime.now(UTC),
        )
        session.add(old)
        session.flush()
        session.add(
            BillingPayment(
                subscription_id=old.id,
                provider_id=f"pay-{index}",
                due_date=date.today(),
                period_end=date.today(),
                amount=30,
                status="PENDING",
                event_at=datetime.now(UTC),
            )
        )
    session.commit()
    statements = []

    def count(*_):
        statements.append(1)

    def measure():
        session.refresh(team)
        statements.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            recipients(session, team, permission=Permission.MANAGE_MEMBERS)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(statements)

    alone = measure()
    for _ in range(6):
        add_member(session, team_id=team.id, player_id=make_player(session).id)
    session.commit()
    # Members, subscriptions and payments never multiply the billing reads.
    assert measure() == alone <= 5
