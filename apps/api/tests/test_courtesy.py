"""Courtesy uses the existing entitlement and never calls the financial provider."""

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app import billing_admin
from app.application.billing import administrative_grant, courtesy_status
from app.application.billing_access import access_state
from app.domain.billing import next_month
from app.domain.policies import ENTITLEMENTS, Conflict, Plan
from app.infrastructure.asaas import Asaas
from app.infrastructure.billing_models import (
    BillingAudit,
    BillingPayment,
    BillingSubscription,
    TeamBilling,
)
from app.infrastructure.config import get_settings
from tests.test_billing import setup


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Courtesy must not call Asaas")

    monkeypatch.setattr(Asaas, "request", forbidden)


@pytest.mark.parametrize("paid", [False, True])
@pytest.mark.parametrize("courtesy", ["none", "permanent", "temporary", "expired", "revoked"])
def test_courtesy_entitlement_combinations(session, paid, courtesy):
    _, team, client, _ = setup(session)
    if paid:
        session.add(TeamBilling(team_id=team.id, environment="production"))
        sub = BillingSubscription(
            team_id=team.id,
            command_id=uuid4(),
            method="PIX",
            amount=29.99,
            plan_code="PRO_MONTHLY",
            operation_status="READY",
            started_at=datetime.now(UTC),
            provider_id="preserved-subscription",
        )
        session.add(sub)
        session.flush()
        session.add(
            BillingPayment(
                subscription_id=sub.id,
                provider_id="preserved-payment",
                due_date=date.today(),
                period_end=next_month(date.today()),
                amount=29.99,
                status="RECEIVED",
                confirmed_at=datetime.now(UTC),
                event_at=datetime.now(UTC),
            )
        )
        session.commit()
    if courtesy != "none":
        expiry = None
        if courtesy in ("temporary", "expired"):
            expiry = datetime.now(UTC) + timedelta(days=1 if courtesy == "temporary" else -1)
        administrative_grant(
            session,
            team.id,
            enabled=True,
            operator="test",
            reason="isolated courtesy",
            settings=get_settings(),
            expires_at=expiry,
        )
        if courtesy == "revoked":
            administrative_grant(
                session,
                team.id,
                enabled=False,
                operator="test",
                reason="isolated revocation",
                settings=get_settings(),
            )
    expected = Plan.PRO if paid or courtesy in ("permanent", "temporary") else Plan.FREE
    assert access_state(session, team)[0] == expected
    assert ENTITLEMENTS[expected].finance == (expected == Plan.PRO)
    assert client.get(f"/v1/teams/{team.id}").json()["plan"] == expected.value
    financial = client.get(f"/v1/teams/{team.id}/finance").json()
    assert financial["enabled"] == (expected == Plan.PRO)
    assert session.scalar(select(func.count()).select_from(BillingSubscription)) == int(paid)
    assert session.scalar(select(func.count()).select_from(BillingPayment)) == int(paid)
    if paid:
        session.refresh(sub)
        assert sub.provider_id == "preserved-subscription" and sub.cancelled_at is None
        assert session.scalar(select(BillingPayment.status)) == "RECEIVED"
        assert session.scalar(select(TeamBilling.environment)) == "production"
    actions = list(session.scalars(select(BillingAudit.action)))
    assert actions.count("ADMIN_GRANTED") == int(courtesy != "none")
    assert actions.count("ADMIN_REVOKED") == int(courtesy == "revoked")


def test_status_cli_is_read_only_and_identifies_courtesy(session, engine, monkeypatch, capsys):
    _, team, _, _ = setup(session)
    administrative_grant(
        session, team.id, enabled=True, operator="test", reason="permanent", settings=get_settings()
    )
    before = session.scalar(select(func.count()).select_from(BillingAudit))
    monkeypatch.setattr(billing_admin, "get_engine", lambda: engine)
    monkeypatch.setattr("sys.argv", ["billing_admin", str(team.id), "status"])
    billing_admin.main()
    result = json.loads(capsys.readouterr().out)
    assert result["entitlement_origin"] == "CORTESIA"
    assert result["courtesy_valid"] and result["courtesy_expires_at"] is None
    assert result["effective_plan"] == "pro"
    assert session.scalar(select(func.count()).select_from(BillingAudit)) == before


def test_courtesy_rejects_ambiguous_timezone_without_changes(session):
    _, team, _, _ = setup(session)
    with pytest.raises(Conflict, match="fuso"):
        administrative_grant(
            session,
            team.id,
            enabled=True,
            operator="test",
            reason="invalid",
            settings=get_settings(),
            expires_at=datetime(2030, 1, 1),
        )
    assert courtesy_status(session, team.id)["effective_plan"] == "free"
    assert session.scalar(select(func.count()).select_from(BillingAudit)) == 0


def test_courtesy_reuses_finance_write_gate_and_preserves_data_on_revocation(session):
    _, team, client, _ = setup(session)
    path = f"/v1/teams/{team.id}/finance/settings"
    data = {"amount": "25.00", "due_day": 10, "active": True, "expected_version": 0}
    assert client.put(path, json=data).status_code == 403
    administrative_grant(
        session,
        team.id,
        enabled=True,
        operator="test",
        reason="finance courtesy",
        settings=get_settings(),
    )
    response = client.put(path, json=data)
    assert response.status_code == 200
    administrative_grant(
        session,
        team.id,
        enabled=False,
        operator="test",
        reason="revoke courtesy",
        settings=get_settings(),
    )
    data["amount"] = "35.00"
    data["expected_version"] = response.json()["version"]
    assert client.put(path, json=data).status_code == 403
    context = client.get(f"/v1/teams/{team.id}/finance").json()
    assert not context["enabled"] and context["settings"]["amount"] == "25.00"
