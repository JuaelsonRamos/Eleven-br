import base64
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select, text, update
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
            item = {
                "id": "sub_test"
                if not state["subscriptions"]
                else f"sub_{len(state['subscriptions'])}",
                **data,
            }
            state["subscriptions"].append(item)
            return item
        if path == "/checkouts":
            return {"id": "checkout_test"}
        if path.endswith("/pixQrCode"):
            return {"encodedImage": "image", "payload": "pix-test", "expirationDate": "2026-12-01"}
        if path.endswith("/payments") or path == "/payments":
            return {"data": state["payments"]}
        if method == "DELETE" and path.startswith("/payments/"):
            for charge in state["payments"]:
                if path == f"/payments/{charge['id']}":
                    if charge.get("status") not in ("PENDING", "OVERDUE"):
                        raise BillingRejected("Asaas não remove cobrança paga.")
                    charge["deleted"] = True
            return {"deleted": True}
        if path.startswith("/payments/"):
            return {
                "id": "pay_test",
                "customer": "cus_test",
                "subscription": "sub_test",
                "value": 29.99,
                "status": state["status"],
                "dueDate": date.today().isoformat(),
            }
        if method == "DELETE" or path.endswith("/cancel"):
            for charge in state["payments"]:
                if charge.get("status") in ("PENDING", "OVERDUE"):
                    charge["status"] = "DELETED"
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
        started_at=now if confirmed else None,
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
    assert provider["subscriptions"][0]["value"] == 29.99
    assert provider["subscriptions"][0]["cycle"] == "MONTHLY"
    assert client.get(path).json()["price"] == "29.99"
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
    player = make_player(session)
    add_member(session, team_id=team.id, player_id=player.id)
    session.commit()
    for viewer in (admin, client_for(session, player)):
        assert viewer.get(path).json()["can_manage"] is False
        for action, data in [
            ("checkout", checkout_data()),
            ("cancel", {"confirm": True}),
            ("refresh", {}),
        ]:
            assert viewer.post(path + "/" + action, json=data).status_code == 403
    assert client.get(path).json()["can_manage"] is True
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
    # The paid period stays PRO; a new contract now would charge it twice.
    for method in ("PIX", "CREDIT_CARD"):
        again = client.post(path + "/checkout", json=checkout_data(method))
        assert again.status_code == 409 and "já está pago até" in again.json()["detail"]
    assert client.get(path).json()["plan"] == "pro"
    assert len(provider["subscriptions"]) == 1
    assert not any(c[:2] == ("POST", "/checkouts") for c in provider["calls"])


def test_card_uses_hosted_monthly_checkout_no_card_capture(session, provider):
    _, _, client, path = setup(session)
    response = client.post(path + "/checkout", json=checkout_data("CREDIT_CARD"))
    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://sandbox.asaas.com/")
    request = next(c[2] for c in provider["calls"] if c[1] == "/checkouts")
    assert request["subscription"]["cycle"] == "MONTHLY"
    assert request["items"][0]["value"] == 29.99
    # Asaas requires an item image: the official logo, never card data.
    assert base64.b64decode(request["items"][0]["imageBase64"]).startswith(b"\x89PNG")
    assert request["customer"] == "cus_test" and "customerData" not in request
    assert request["minutesToExpire"] == 60
    assert "creditCard" not in request


def test_existing_intent_keeps_its_original_price_on_retry(session, provider):
    _, team, client, path = setup(session)
    data = checkout_data()
    session.add(TeamBilling(team_id=team.id, environment="sandbox"))
    session.add(
        BillingSubscription(
            team_id=team.id,
            command_id=data["command_id"],
            method="PIX",
            amount=30,
            plan_code="PRO_MONTHLY",
        )
    )
    session.commit()
    response = client.post(path + "/checkout", json=data)
    assert response.status_code == 200
    assert response.json()["price"] == "29.99"
    assert provider["subscriptions"][0]["value"] == 30
    assert provider["subscriptions"][0]["cycle"] == "MONTHLY"


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
            "value": 29.99,
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


def age_pix(session, minutes=11):
    item = session.scalar(
        select(BillingSubscription).order_by(BillingSubscription.created_at.desc())
    )
    item.created_at = datetime.now(UTC) - timedelta(minutes=minutes)
    session.commit()
    return item


def pending_pix(provider):
    provider["payments"] = [
        {
            "id": "pay_test",
            "status": "PENDING",
            "customer": "cus_test",
            "subscription": "sub_test",
            "value": 29.99,
            "dueDate": date.today().isoformat(),
        }
    ]


def deleted(provider, path="/subscriptions/sub_test"):
    return len([c for c in provider["calls"] if c[:2] == ("DELETE", path)])


def test_initial_pix_window_boundaries(session, provider):
    _, team, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    start = session.scalar(select(BillingSubscription.created_at))
    summary = client.get(path).json()
    deadline = datetime.fromisoformat(summary["signup_expires_at"])
    assert timedelta(0) <= start + timedelta(minutes=10) - deadline < timedelta(milliseconds=1)
    # Three fractional digits and an explicit offset: Hermes and browsers parse them alike.
    for stamp in (summary["signup_expires_at"], summary["server_time"]):
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d", stamp)
    for elapsed, expected in [
        (timedelta(minutes=9, seconds=59), "PENDING"),
        (timedelta(minutes=10), "EXPIRED"),
    ]:
        plan, status, _ = access_state(session, team, start + elapsed)
        assert (plan.value, status.value) == ("free", expected)


def test_pix_deadline_is_persistent_and_enforced_without_frontend(session, provider):
    _, _, client, path = setup(session)
    pending_pix(provider)
    first = client.post(path + "/checkout", json=checkout_data()).json()
    assert first["signup_expires_at"] and first["pix"]["expires_at"] == "2026-12-01"
    # The Asaas QR validity is returned untouched; the initial charge is not a "next charge".
    assert first["status"] == "PENDING" and first["next_due_date"] is None
    age_pix(session, 9)
    active = client.post(path + "/refresh", json={}).json()
    assert active["pix"] and not active["signup_expired"] and active["plan"] == "free"
    age_pix(session)
    # No callback, timer or cleanup has run: the persisted timestamp already blocks access.
    summary = client.get(path).json()
    assert summary["signup_expired"] and summary["status"] == "EXPIRED"
    assert summary["plan"] == "free" and not summary["can_retry_pix"]
    expired = client.post(path + "/refresh", json={}).json()
    assert "pix" not in expired and expired["can_retry_pix"]
    assert expired["operation_status"] == "EXPIRED"
    # The old charge is removed before the recurrence, so the old QR is no longer payable.
    assert deleted(provider, "/payments/pay_test") == deleted(provider) == 1
    client.post(path + "/refresh", json={})
    assert deleted(provider, "/payments/pay_test") == deleted(provider) == 1


def test_expired_pix_allows_new_command_only_after_remote_close(session, provider):
    _, _, client, path = setup(session)
    old_command = checkout_data()
    client.post(path + "/checkout", json=old_command)
    old = age_pix(session)
    fresh = checkout_data()
    response = client.post(path + "/checkout", json=fresh)
    assert response.status_code == 200
    assert not response.json()["signup_expired"]
    assert len(provider["subscriptions"]) == 2
    calls = [c[:2] for c in provider["calls"]]
    posts = [i for i, call in enumerate(calls) if call == ("POST", "/subscriptions")]
    # The expired recurrence is closed at the provider before the new one is created.
    assert posts[0] < calls.index(("DELETE", "/subscriptions/sub_test")) < posts[1]
    session.refresh(old)
    assert old.cancelled_at and old.operation_status == "EXPIRED"
    assert client.post(path + "/checkout", json=fresh).status_code == 200
    assert client.post(path + "/checkout", json=old_command).status_code == 409
    assert len(provider["subscriptions"]) == 2


@pytest.mark.parametrize("closed", [False, True])
def test_late_payment_is_retained_for_review_never_grants_pro(session, provider, closed):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    if closed:
        assert client.post(path + "/refresh", json={}).json()["can_retry_pix"]
    provider["status"] = "CONFIRMED"
    event_data = payload()
    assert webhook(client, event_data).status_code == 200
    assert webhook(client, event_data).status_code == 200
    summary = client.get(path).json()
    assert summary["plan"] == "free" and summary["status"] == "RECONCILIATION"
    assert not summary["can_retry_pix"]
    assert session.scalar(select(BillingPayment.confirmed_at))
    assert session.scalar(select(BillingWebhook.status)) == "RECONCILIATION"
    assert session.scalar(select(BillingSubscription.started_at)) is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(BillingAudit)
            .where(BillingAudit.action == "PIX_LATE_PAYMENT_REVIEW")
        )
        == 1
    )
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 409
    assert client.post(path + "/cancel", json={"confirm": True}).status_code == 409


def test_payment_within_window_activates_monthly_pro(session, provider):
    _, _, client, path = setup(session)
    pending_pix(provider)
    first = client.post(path + "/checkout", json=checkout_data()).json()
    assert first["pix"]["amount"] == "29.99" and first["plan"] == "free"
    age_pix(session, 9)
    provider["status"] = "CONFIRMED"
    provider["payments"][0]["status"] = "CONFIRMED"
    assert webhook(client, payload()).status_code == 200
    active = client.get(path).json()
    assert (active["plan"], active["status"]) == ("pro", "ACTIVE")
    assert active["signup_expires_at"] is None and active["next_due_date"]
    age_pix(session, 60)
    assert client.post(path + "/refresh", json={}).json()["plan"] == "pro"
    assert session.scalar(select(BillingSubscription.operation_status)) == "READY"
    assert not any(c[0] == "DELETE" for c in provider["calls"])
    created = provider["subscriptions"][0]
    assert (created["billingType"], created["cycle"], created["value"]) == ("PIX", "MONTHLY", 29.99)


def test_payment_racing_with_expiry_keeps_the_subscription(session, provider, monkeypatch):
    _, _, client, path = setup(session)
    pending_pix(provider)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    original = Asaas.request

    def paid_meanwhile(self, method, path, *args, **kwargs):
        if (method, path) == ("DELETE", "/payments/pay_test"):
            provider["payments"][0]["status"] = "RECEIVED"  # Paid after the listing.
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", paid_meanwhile)
    result = client.post(path + "/refresh", json={}).json()
    assert (result["plan"], result["status"]) == ("free", "RECONCILIATION")
    assert "pix" not in result and not result["can_retry_pix"] and result["warning"]
    assert deleted(provider) == 0  # A paid recurrence is never cancelled by the cleanup.
    provider["status"] = "RECEIVED"
    assert webhook(client, payload("PAYMENT_RECEIVED")).status_code == 200
    assert client.get(path).json()["plan"] == "free"
    assert session.scalar(select(BillingPayment.status)) == "RECEIVED"
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 409
    assert len(provider["subscriptions"]) == 1


def test_confirmation_during_expiry_claim_never_cancels(engine, session, provider, monkeypatch):
    _, _, client, path = setup(session)
    pending_pix(provider)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    original, settings, delivered = Asaas.request, get_settings(), []

    def confirmed_meanwhile(self, method, path, *args, **kwargs):
        result = original(self, method, path, *args, **kwargs)
        if (method, path) == ("GET", "/subscriptions/sub_test/payments") and not delivered:
            # The listing is already stale: the webhook confirms the charge right after it.
            delivered.append(True)
            provider["status"] = "RECEIVED"
            with Session(engine) as other:
                billing_webhooks.process(other, payload("PAYMENT_RECEIVED"), settings)
        return result

    monkeypatch.setattr(Asaas, "request", confirmed_meanwhile)
    result = client.post(path + "/refresh", json={}).json()
    assert (result["plan"], result["status"]) == ("free", "RECONCILIATION")
    assert deleted(provider) == deleted(provider, "/payments/pay_test") == 0
    session.expire_all()
    assert session.scalar(select(BillingWebhook.status)) == "RECONCILIATION"
    assert session.scalar(select(BillingPayment.confirmed_at))


def test_expiry_claim_serializes_cleanup(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    item = age_pix(session)
    item.operation_status = "EXPIRING"  # Another request is closing it right now.
    session.commit()
    calls = len(provider["calls"])
    busy = client.post(path + "/refresh", json={}).json()
    assert busy["notice"] and not busy["can_retry_pix"] and busy["plan"] == "free"
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 409
    assert provider["calls"][calls:] == []
    stale = func.now() - timedelta(minutes=16)  # The claimant crashed; no call is in flight.
    session.execute(update(BillingSubscription).values(updated_at=stale))
    session.commit()
    assert client.post(path + "/refresh", json={}).json()["can_retry_pix"]
    assert deleted(provider) == 1


def test_cancelled_attempt_is_not_rewritten_after_its_deadline(session, provider):
    _, team, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    assert client.post(path + "/cancel", json={"confirm": True}).json()["status"] == "CANCELLED"
    item = age_pix(session)
    cancelled_at, calls = item.cancelled_at, len(provider["calls"])
    refreshed = client.post(path + "/refresh", json={}).json()
    assert refreshed["status"] == "CANCELLED" and "notice" not in refreshed
    assert provider["calls"][calls:] == []
    reconcile(session, team.id)
    session.refresh(item)
    assert (item.cancelled_at, item.operation_status) == (cancelled_at, "READY")
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 200
    assert len(provider["subscriptions"]) == 2


def test_reconcile_closes_expired_pix_while_the_app_is_closed(session, provider):
    _, team, client, path = setup(session)
    pending_pix(provider)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    reconcile(session, team.id)
    assert deleted(provider, "/payments/pay_test") == deleted(provider) == 1
    summary = client.get(path).json()
    assert (summary["plan"], summary["status"]) == ("free", "EXPIRED")
    assert summary["can_retry_pix"]


def test_paid_subscription_and_future_monthly_pix_do_not_expire(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    provider["status"] = "RECEIVED"
    assert webhook(client, payload("PAYMENT_RECEIVED")).status_code == 200
    age_pix(session, 60)
    pending_pix(provider)
    result = client.post(path + "/refresh", json={}).json()
    assert result["plan"] == "pro" and result["pix"]
    assert result["signup_expires_at"] is None and not result["signup_expired"]
    assert not any(c[0] == "DELETE" for c in provider["calls"])


def test_provider_paid_without_webhook_blocks_expiry_cancellation(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    pending_pix(provider)
    provider["payments"][0]["status"] = "RECEIVED"
    result = client.post(path + "/refresh", json={}).json()
    assert result["status"] == "RECONCILIATION" and result["plan"] == "free"
    assert "pix" not in result and not result["can_retry_pix"]
    assert not any(c[0] == "DELETE" for c in provider["calls"])


@pytest.mark.parametrize(
    "failing", [("GET", "/payments"), ("DELETE", "/payments/"), ("DELETE", "/subscriptions/")]
)
def test_remote_failure_keeps_expired_intent_and_blocks_new_recurrence(
    session, provider, monkeypatch, failing
):
    _, _, client, path = setup(session)
    pending_pix(provider)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    original = Asaas.request

    def fail(self, method, path, *args, **kwargs):
        if method == failing[0] and failing[1] in path:
            raise BillingUnavailable("Indisponível")
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", fail)
    assert client.post(path + "/refresh", json={}).status_code == 503
    assert client.post(path + "/checkout", json=checkout_data()).status_code == 503
    assert len(provider["subscriptions"]) == 1 and deleted(provider) == 0
    summary = client.get(path).json()
    assert (summary["plan"], summary["status"]) == ("free", "EXPIRED")
    assert summary["signup_expired"] and not summary["can_retry_pix"]
    monkeypatch.setattr(Asaas, "request", original)
    assert client.post(path + "/refresh", json={}).json()["can_retry_pix"]
    assert deleted(provider) == 1


def test_concurrent_expiry_and_new_checkout_do_not_duplicate(engine, session, provider):
    owner, team, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data())
    age_pix(session)
    owner_id, team_id = owner.user_id, team.id
    session.commit()

    def start(_):
        with Session(engine) as other:
            try:
                billing.begin_checkout(
                    other,
                    owner_id,
                    team_id,
                    billing.CheckoutInput(**checkout_data()),
                    get_settings(),
                )
            except Conflict:
                pass

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(start, range(2)))
    assert len(provider["subscriptions"]) == 2
    assert deleted(provider) == 1


def test_card_ignores_initial_pix_deadline(session, provider):
    _, _, client, path = setup(session)
    client.post(path + "/checkout", json=checkout_data("CREDIT_CARD"))
    age_pix(session)
    result = client.post(path + "/refresh", json={}).json()
    assert result["checkout_url"] and result["signup_expires_at"] is None
    assert not result["signup_expired"]


def test_asaas_refusal_keeps_a_masked_cause_and_a_friendly_message(monkeypatch):
    monkeypatch.setenv("ASAAS_ENV", "sandbox")
    monkeypatch.setenv("ASAAS_API_KEY", "sandbox-test-key-never-real")
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "test-webhook-" + "x" * 32)
    get_settings.cache_clear()
    body = {
        "errors": [
            {"code": "invalid_object", "description": "Imagem ausente. a@example.com 12345678909"}
        ]
    }

    def respond(self, method, url, **kwargs):
        return httpx.Response(400, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", respond)
    with pytest.raises(BillingRejected) as refused:
        Asaas(get_settings()).request("POST", "/checkouts", {"items": []})
    assert (
        str(refused.value)
        == "Não foi possível iniciar o pagamento. Confira os dados e tente novamente."
    )
    assert refused.value.detail == "invalid_object: Imagem ausente. *** ***"
    get_settings.cache_clear()


@pytest.mark.parametrize("retry", ["CREDIT_CARD", "PIX"])
def test_card_refusal_never_blocks_a_safe_retry(session, provider, monkeypatch, retry):
    _, _, client, path = setup(session)
    original, refusals = Asaas.request, [True]

    def refuse_once(self, method, path, *args, **kwargs):
        if (method, path) == ("POST", "/checkouts") and refusals:
            refusals.pop()
            raise BillingRejected(
                "Não foi possível iniciar o pagamento. Confira os dados e tente novamente.",
                "invalid_object: imagem ausente",
            )
        return original(self, method, path, *args, **kwargs)

    monkeypatch.setattr(Asaas, "request", refuse_once)
    refused = client.post(path + "/checkout", json=checkout_data("CREDIT_CARD"))
    assert (refused.status_code, refused.json()["detail"]) == (
        400,
        "Não foi possível iniciar o pagamento. Confira os dados e tente novamente.",
    )
    item = session.scalar(select(BillingSubscription))
    assert (item.operation_status, item.provider_id, item.checkout_id) == ("NEW", None, None)
    assert (
        session.scalar(
            select(BillingAudit.reason).where(BillingAudit.action == "PROVIDER_REJECTED")
        )
        == "invalid_object: imagem ausente"
    )
    summary = client.get(path).json()
    assert (summary["status"], summary["plan"], summary["can_cancel"]) == ("FREE", "free", False)
    pending_pix(provider)
    retried = client.post(path + "/checkout", json=checkout_data(retry))
    assert retried.status_code == 200, retried.text
    assert retried.json()["plan"] == "free"  # Nothing is PRO before a confirmed payment.
    session.expire_all()
    live = session.scalars(
        select(BillingSubscription).where(BillingSubscription.cancelled_at.is_(None))
    ).all()
    assert len(live) == 1 and live[0].method == retry
    if retry == "CREDIT_CARD":
        assert live[0].id == item.id  # The never-sent attempt is reused, not duplicated.
        assert (live[0].checkout_id, live[0].operation_status) == ("checkout_test", "READY")
        assert retried.json()["checkout_url"].endswith("id=checkout_test")
    else:
        assert item.cancelled_at  # Superseded and kept for audit, never deleted.
        assert live[0].provider_id == "sub_test" and len(provider["subscriptions"]) == 1
        assert retried.json()["pix"]["amount"] == "29.99"
    created = [c for c in provider["calls"] if c[:2] == ("POST", "/checkouts")]
    assert len(created) == (1 if retry == "CREDIT_CARD" else 0)
