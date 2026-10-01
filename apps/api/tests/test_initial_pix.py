"""Initial Pix GET recovery, isolated DB/provider, with no real sleeps or payments."""

from collections import Counter
from time import monotonic

import httpx
import pytest
from sqlalchemy import func, select

from app.application import billing_pix
from app.domain.billing import BillingPixPreparing, BillingRejected, BillingUnavailable
from app.infrastructure.asaas import Asaas
from app.infrastructure.billing_models import BillingAudit, BillingSubscription
from app.infrastructure.config import get_settings
from tests.test_billing import (  # noqa: F401
    checkout_data,
    payload,
    pending_pix,
    provider,
    setup,
    webhook,
)

REAL_ASAAS_REQUEST = Asaas.request


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("ASAAS_ENV", "sandbox")
    monkeypatch.setenv("ASAAS_API_KEY", "isolated-test-key")
    monkeypatch.setenv("ASAAS_BASE_URL", "https://api-sandbox.asaas.com/v3")
    get_settings.cache_clear()
    client = Asaas(get_settings())
    client.pix_read = True
    yield client
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "scenario", ["immediate", "list_delayed", "qr_delayed", "qr_never", "empty_qr", "list_never"]
)
def test_initial_pix_recovers_only_gets_and_refresh_keeps_same_subscription(
    session,
    provider,  # noqa: F811
    monkeypatch,
    scenario,
):
    _, _, client, path = setup(session)
    pending_pix(provider)
    original = Asaas.request
    counts = Counter()
    waits = []
    monkeypatch.setattr(billing_pix, "sleep", waits.append)

    def sequence(self, method, target, *args, **kwargs):
        result = original(self, method, target, *args, **kwargs)
        if method == "GET" and target == "/subscriptions/sub_test/payments":
            counts["list"] += 1
            if scenario == "list_never" or (scenario == "list_delayed" and counts["list"] == 1):
                return {"data": []}
        if target.endswith("/pixQrCode"):
            assert method == "GET"
            counts["qr"] += 1
            if scenario == "qr_never" or (scenario == "qr_delayed" and counts["qr"] < 3):
                raise BillingPixPreparing("Not available yet")
            if scenario == "empty_qr":
                return {"encodedImage": None, "payload": None}
        return result

    monkeypatch.setattr(Asaas, "request", sequence)
    response = client.post(path + "/checkout", json=checkout_data())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["plan"] == "free" and result["status"] == "PENDING"
    assert counts["list"] == {"immediate": 1, "list_delayed": 2}.get(scenario, 3)
    assert len(waits) == counts["list"] - 1
    assert all(wait == 0.5 for wait in waits)
    if scenario in ("qr_never", "empty_qr", "list_never"):
        assert "pix" not in result and "sendo preparado" in result["notice"]
        before = counts["list"]
        assert "sendo preparado" in client.post(path + "/refresh", json={}).json()["notice"]
        assert counts["list"] == before + 1  # Refresh does not start another retry loop.
    else:
        assert result["pix"]["payload"] == "pix-test" and result["pix"]["amount"] == "29.99"
    item = session.scalar(select(BillingSubscription))
    assert item.provider_id == "sub_test" and item.operation_status == "READY"
    assert not item.cancelled_at and not item.cancel_requested and not item.started_at
    assert (
        session.scalar(
            select(func.count())
            .select_from(BillingAudit)
            .where(
                BillingAudit.action.in_(
                    ("PROVIDER_REJECTED", "SUBSCRIPTION_CANCELLED", "PIX_SIGNUP_EXPIRED")
                )
            )
        )
        == 0
    )
    monkeypatch.setattr(Asaas, "request", original)
    refreshed = client.post(path + "/refresh", json={})
    assert refreshed.status_code == 200 and refreshed.json()["pix"]["payload"] == "pix-test"
    assert len(provider["customers"]) == len(provider["subscriptions"]) == 1
    posts = [call[1] for call in provider["calls"] if call[0] == "POST"]
    assert posts == ["/customers", "/subscriptions"]
    assert all(
        call[1] == "/subscriptions/sub_test/payments"
        for call in provider["calls"]
        if call[1].endswith("/payments")
    )
    provider["status"] = "RECEIVED"
    assert webhook(client, payload("PAYMENT_RECEIVED")).status_code == 200
    assert client.get(path).json()["plan"] == "pro"


@pytest.mark.parametrize("status", [404, 408, 409, 429, 503])
def test_adapter_marks_only_scoped_initial_qr_get_as_preparing(adapter, monkeypatch, status):
    calls = []

    def respond(self, method, url, **kwargs):
        calls.append(method)
        assert self.timeout.read <= 1
        return httpx.Response(status, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", respond)
    adapter.pix_read_deadline = monotonic() + 6
    with pytest.raises(BillingPixPreparing):
        adapter.request("GET", "/payments/pay_test/pixQrCode")
    assert calls == ["GET"]  # Adapter never retries on its own.


@pytest.mark.parametrize("status", [400, 503])
def test_post_errors_are_not_retried_or_downgraded_to_preparing(adapter, monkeypatch, status):
    calls = []

    def respond(self, method, url, **kwargs):
        calls.append(method)
        assert self.timeout.read == 65
        return httpx.Response(status, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", respond)
    adapter.pix_read_deadline = monotonic() + 6
    with pytest.raises(BillingRejected if status == 400 else BillingUnavailable) as failure:
        adapter.request("POST", "/subscriptions", {})
    assert not isinstance(failure.value, BillingPixPreparing)
    assert calls == ["POST"]


def test_initial_pix_budget_stops_before_another_get(session, provider, monkeypatch):  # noqa: F811
    from app.application.billing import Provider

    pending_pix(provider)
    clock = iter([0.0, 7.0])
    monkeypatch.setattr(billing_pix, "monotonic", lambda: next(clock))
    original = Asaas.request

    def not_ready(self, method, path, *args, **kwargs):
        original(self, method, path, *args, **kwargs)
        raise BillingPixPreparing("Preparing")

    monkeypatch.setattr(Asaas, "request", not_ready)
    client = Provider(session, get_settings())
    from decimal import Decimal

    result = billing_pix.initial_pix(client, "sub_test", Decimal("29.99"), retry=True)
    assert "sendo preparado" in result["notice"]
    assert len(provider["calls"]) == 1
    assert client.client.pix_read_deadline is None


@pytest.mark.parametrize("status", [401, 403])
def test_configuration_errors_are_not_hidden_as_pix_preparation(adapter, monkeypatch, status):
    calls = []

    def respond(self, method, url, **kwargs):
        calls.append(method)
        return httpx.Response(status, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", respond)
    adapter.pix_read_deadline = monotonic() + 6
    with pytest.raises(BillingUnavailable) as failure:
        adapter.request("GET", "/payments/pay_test/pixQrCode")
    assert not isinstance(failure.value, BillingPixPreparing)
    assert calls == ["GET"]


def test_scoped_get_timeout_is_transient(adapter, monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("isolated timeout")

    monkeypatch.setattr(httpx.Client, "request", timeout)
    adapter.pix_read_deadline = monotonic() + 6
    with pytest.raises(BillingPixPreparing):
        adapter.request("GET", "/subscriptions/sub_test/payments")


def test_manual_refresh_keeps_normal_read_timeout(adapter, monkeypatch):
    calls = []

    def respond(self, method, url, **kwargs):
        assert self.timeout.read == 65
        calls.append(method)
        return httpx.Response(404, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", respond)
    with pytest.raises(BillingPixPreparing):
        adapter.request("GET", "/payments/pay_test/pixQrCode")
    assert calls == ["GET"]


@pytest.mark.parametrize("stage", ["creation", "refresh"])
@pytest.mark.parametrize("code", ["invalid_object", "unknown_code"])
def test_definitive_qr_400_is_not_preparing_and_preserves_existing_intent(
    session,
    provider,  # noqa: F811
    monkeypatch,
    stage,
    code,
):
    _, _, client, path = setup(session)
    pending_pix(provider)
    original = Asaas.request
    if stage == "refresh":
        assert client.post(path + "/checkout", json=checkout_data()).status_code == 200
    queries = []
    original_http_request = httpx.Client.request
    monkeypatch.setattr(billing_pix, "sleep", lambda _: pytest.fail("400 must not be retried"))

    def refused(self, method, url, **kwargs):
        if not str(url).endswith("/pixQrCode"):
            return original_http_request(self, method, url, **kwargs)
        assert method == "GET" and url.endswith("/pixQrCode")
        queries.append(url)
        return httpx.Response(
            400,
            json={"errors": [{"code": code, "description": "Invalid resource"}]},
            request=httpx.Request(method, url),
        )

    def qr_error(self, method, target, *args, **kwargs):
        if target.endswith("/pixQrCode"):
            return REAL_ASAAS_REQUEST(self, method, target, *args, **kwargs)
        return original(self, method, target, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", refused)
    monkeypatch.setattr(Asaas, "request", qr_error)
    response = client.post(
        path + ("/checkout" if stage == "creation" else "/refresh"),
        json=checkout_data() if stage == "creation" else {},
    )
    assert response.status_code == 400
    assert "Confira os dados" in response.json()["detail"]
    assert "prepar" not in response.text and len(queries) == 1
    assert code not in response.text and "Invalid resource" not in response.text
    item = session.scalar(select(BillingSubscription))
    assert item.provider_id == "sub_test" and item.operation_status == "READY"
    assert not item.cancelled_at and not item.started_at and not item.cancel_requested
    assert client.get(path).json()["plan"] == "free"
    monkeypatch.setattr(Asaas, "request", original)
    recovered = client.post(path + "/refresh", json={})
    assert recovered.status_code == 200 and recovered.json()["pix"]["payload"] == "pix-test"
    assert [c[1] for c in provider["calls"] if c[0] == "POST"] == ["/customers", "/subscriptions"]
    assert len(provider["customers"]) == len(provider["subscriptions"]) == 1
    assert session.scalar(select(func.count()).select_from(BillingSubscription)) == 1
    session.refresh(item)
    assert item.provider_id == "sub_test" and item.operation_status == "READY"
