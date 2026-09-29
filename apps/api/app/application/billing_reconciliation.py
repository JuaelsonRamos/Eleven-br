"""Audited operator reconciliation of commercial state, by internal team UUID.

Replaces manual SQL after ambiguous provider calls or parked webhooks. It never
creates provider resources: it records references the provider proves, releases
claims the provider proves unfulfilled once no request can still be in flight,
stops recurrences the team already cancelled, refreshes payment statuses in
observation order and reprocesses DIVERGENT webhook events with the webhook rules.
Coverage still requires a PAYMENT_CONFIRMED/RECEIVED event: this never grants Pro.
Provider I/O runs outside transactions; each change is a short Team-locked commit.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.billing import (
    CHECKOUT_MINUTES,
    Provider,
    audit,
    billing_account,
    lock_team,
    stop_remote,
    subscription_of,
)
from app.application.billing_access import access_state
from app.application.billing_expiration import expire_initial_pix
from app.application.billing_webhooks import PAID, apply_payment, payment_facts
from app.domain.billing import BillingDivergence, BillingUnavailable, next_month
from app.domain.policies import Conflict, NotFound
from app.infrastructure.billing_models import (
    BillingAudit,
    BillingPayment,
    BillingSubscription,
    BillingWebhook,
    TeamBilling,
)
from app.infrastructure.config import Settings
from app.infrastructure.models import Team

# Provider calls time out after 65 s, so an older unresolved claim is no longer in flight.
CLAIM_WINDOW = timedelta(minutes=15)
# A card intent without reference never exposed its URL; its checkout expires unpaid.
CHECKOUT_WINDOW = timedelta(minutes=2 * CHECKOUT_MINUTES)


def reconcile(
    session: Session,
    team_id: UUID,
    *,
    operator: str,
    reason: str,
    settings: Settings,
    now: datetime | None = None,
) -> list[str]:
    if not operator.strip() or not reason.strip():
        raise Conflict("Conciliação exige operador e justificativa.")
    if session.get(Team, team_id) is None:
        raise NotFound("Time não encontrado.")
    account = session.scalar(select(TeamBilling).where(TeamBilling.team_id == team_id))
    if account is None:
        session.commit()
        return ["Time sem cadastro comercial: nada a conciliar."]
    if account.environment != settings.asaas_env:
        raise Conflict("Ambiente de cobrança diferente do cadastro deste time.")
    session.commit()
    job = Reconciliation(
        session, team_id, settings, f"{operator.strip()}: {reason.strip()}"[:300], now
    )
    job.customer()
    job.subscriptions()
    job.webhooks()
    return job.report or ["Nenhuma divergência encontrada."]


class Reconciliation:
    def __init__(
        self,
        session: Session,
        team_id: UUID,
        settings: Settings,
        reason: str,
        now: datetime | None,
    ) -> None:
        self.session, self.team_id, self.settings = session, team_id, settings
        self.provider = Provider(session, settings)
        self.reason, self.now = reason, now or datetime.now(UTC)
        self.customer_id: str | None = None
        self.report: list[str] = []

    def record(self, action: str, reference: str, message: str) -> None:
        audit(self.session, self.team_id, action, reference, origin="operator", reason=self.reason)
        self.report.append(message)

    def customer(self) -> None:
        self.customer_id = self.session.scalar(
            select(TeamBilling.customer_id).where(TeamBilling.team_id == self.team_id)
        )
        self.session.commit()
        if self.customer_id:
            return
        reference = f"eleven-team:{self.team_id}"
        matches = self.provider.list_all("/customers", {"externalReference": reference})
        lock_team(self.session, self.team_id)
        account = billing_account(self.session, self.team_id)
        if account.customer_id:
            self.customer_id = account.customer_id
        elif len(matches) > 1:
            self.report.append("Mais de um cliente no Asaas para este time: resolva no painel.")
        elif matches:
            self.customer_id = account.customer_id = str(matches[0]["id"])
            self.record("RECONCILED_CUSTOMER", self.customer_id, "Cliente do Asaas vinculado.")
        elif account.customer_attempted and account.updated_at <= self.now - CLAIM_WINDOW:
            account.customer_attempted = False
            self.record(
                "CUSTOMER_CLAIM_RELEASED",
                str(account.id),
                "Cliente inexistente no Asaas: nova contratação liberada.",
            )
        elif account.customer_attempted:
            self.report.append("Criação de cliente recente: aguarde alguns minutos e repita.")
        self.session.commit()

    def subscriptions(self) -> None:
        rows = self.session.execute(
            select(
                BillingSubscription.id,
                BillingSubscription.provider_id,
                BillingSubscription.checkout_id,
                BillingSubscription.operation_status,
                BillingSubscription.cancelled_at,
            )
            .where(BillingSubscription.team_id == self.team_id)
            .order_by(BillingSubscription.created_at, BillingSubscription.id)
        ).all()
        self.session.commit()
        for item_id, provider_id, checkout_id, status, cancelled_at in rows:
            try:
                if status == "REVIEW":
                    self.report.append(f"Assinatura {item_id}: pagamento em revisão; não cancelar.")
                    continue
                if not (cancelled_at or provider_id or checkout_id) and status == "CREATING":
                    provider_id = self.intent(item_id)
                elif cancelled_at and provider_id:
                    self.stop(provider_id)
                if provider_id:
                    self.payments(item_id, provider_id)
                expire_initial_pix(self.session, self.team_id, item_id, self.settings, self.now)
            except BillingUnavailable:
                self.session.rollback()
                self.report.append(f"Asaas indisponível para a assinatura {item_id}: repita.")

    def intent(self, item_id: UUID) -> str | None:
        """Resolve a creation claim whose provider response was never recorded."""
        method = self.session.scalars(
            select(BillingSubscription.method).where(BillingSubscription.id == item_id)
        ).one()
        self.session.commit()
        found: dict[str, Any] | None = None
        if method == "PIX" and self.customer_id:
            matches = self.provider.list_all(
                "/subscriptions",
                {"externalReference": f"eleven-sub:{item_id}", "customer": self.customer_id},
            )
            if len(matches) > 1:
                self.report.append(f"Mais de uma assinatura no Asaas para {item_id}: revise.")
                return None
            found = matches[0] if matches else None
        window = CLAIM_WINDOW if method == "PIX" else CHECKOUT_WINDOW
        lock_team(self.session, self.team_id)
        item = subscription_of(self.session, item_id)
        adopted = None
        if item.cancelled_at or item.provider_id or item.checkout_id:
            pass  # Resolved meanwhile by the checkout request or a webhook.
        elif found is not None and (
            found.get("customer") == self.customer_id
            and found.get("cycle") == "MONTHLY"
            and Decimal(str(found.get("value", 0))) == item.amount
            and found.get("billingType") == item.method
        ):
            adopted = item.provider_id = str(found["id"])
            item.operation_status = "READY"
            self.record("RECONCILED_SUBSCRIPTION", adopted, f"Assinatura {adopted} vinculada.")
        elif found is not None:
            self.report.append(f"Assinatura {found.get('id')} diverge da contratação: revise.")
        elif item.updated_at <= self.now - window:
            item.cancelled_at = datetime.now(UTC)
            self.record(
                "INTENT_ABANDONED",
                str(item_id),
                "Contratação não criada no Asaas: encerrada; o Presidente pode assinar de novo.",
            )
        else:
            self.report.append("Contratação recente em andamento: aguarde alguns minutos e repita.")
        self.session.commit()
        return adopted

    def stop(self, provider_id: str) -> None:
        """A locally cancelled subscription must not keep charging at the provider."""
        path = f"/subscriptions/{quote(provider_id, safe='')}"
        canonical = self.provider.request("GET", path)
        if canonical.get("deleted") or canonical.get("status") in ("INACTIVE", "EXPIRED"):
            return
        stop_remote(self.provider, provider_id, None)
        lock_team(self.session, self.team_id)
        self.record(
            "RECURRENCE_STOPPED", provider_id, f"Recorrência {provider_id} interrompida no Asaas."
        )
        self.session.commit()

    def payments(self, item_id: UUID, provider_id: str) -> None:
        """Refresh statuses from the provider; confirmation still needs its payment event."""
        observed_at = datetime.now(UTC)
        charges = self.provider.list_all(
            f"/subscriptions/{quote(provider_id, safe='')}/payments", {}
        )
        team = self.session.scalar(select(Team).where(Team.id == self.team_id).with_for_update())
        assert team is not None
        item = subscription_of(self.session, item_id)
        before = access_state(self.session, team)
        for charge in charges:
            charge_id = str(charge.get("id") or "")
            if (
                not charge_id
                or charge.get("subscription") not in (None, provider_id)
                or charge.get("customer") != self.customer_id
                or Decimal(str(charge.get("value", 0))) != item.amount
            ):
                self.report.append(f"Cobrança {charge_id} diverge da assinatura: revise.")
                continue
            status = "DELETED" if charge.get("deleted") else str(charge.get("status", "PENDING"))
            row = self.session.scalar(
                select(BillingPayment).where(BillingPayment.provider_id == charge_id)
            )
            if row is None:
                due = date.fromisoformat(str(charge["dueDate"]))
                row = BillingPayment(
                    subscription_id=item.id,
                    provider_id=charge_id,
                    due_date=due,
                    period_end=next_month(due),
                    amount=item.amount,
                    status=status,
                    event_at=observed_at,
                )
                self.session.add(row)
                self.record("PAYMENT_" + status, charge_id, f"Cobrança {charge_id} registrada.")
            elif row.subscription_id != item.id:
                self.report.append(f"Cobrança {charge_id} vinculada a outra assinatura: revise.")
                continue
            elif observed_at > row.event_at and row.status != status:
                row.status, row.event_at = status, observed_at
                self.record("PAYMENT_" + status, charge_id, f"Cobrança {charge_id}: {status}.")
            if status in PAID and row.confirmed_at is None:
                self.report.append(
                    f"Cobrança {charge_id} paga no Asaas sem evento de confirmação recebido: "
                    "verifique a fila de webhooks. O acesso não foi alterado."
                )
        self.session.flush()
        after = access_state(self.session, team)
        if before[:2] != after[:2]:
            self.record("ACCESS_" + after[1].value, provider_id, f"Acesso: {after[1].value}.")
        self.session.commit()

    def webhooks(self) -> None:
        parked = self.session.execute(
            select(
                BillingWebhook.id,
                BillingWebhook.event_id,
                BillingWebhook.event_type,
                BillingWebhook.resource_id,
            )
            .join(BillingAudit, BillingAudit.reference == BillingWebhook.event_id)
            .where(
                BillingAudit.team_id == self.team_id,
                BillingAudit.action == "WEBHOOK_DIVERGENT",
                BillingWebhook.status == "DIVERGENT",
            )
            .distinct()
        ).all()
        self.session.commit()
        for webhook_id, event_id, kind, payment_id in parked:
            try:
                self.reprocess(webhook_id, event_id, kind, payment_id)
            except BillingUnavailable:
                self.session.rollback()
                self.report.append(f"Asaas indisponível para o evento {event_id}: repita.")

    def reprocess(self, webhook_id: UUID, event_id: str, kind: str, payment_id: str | None) -> None:
        facts = None
        if payment_id:
            path = f"/payments/{quote(payment_id, safe='')}"
            canonical = self.provider.request("GET", path)
            event = {
                "id": payment_id,
                "subscription": canonical.get("subscription"),
                "customer": canonical.get("customer"),
            }
            facts = payment_facts(self.session, self.provider, event)
        record = self.session.scalar(
            select(BillingWebhook).where(BillingWebhook.id == webhook_id).with_for_update()
        )
        if record is None or record.status != "DIVERGENT":
            self.session.commit()
            return
        try:
            with self.session.begin_nested():
                if facts is not None:
                    apply_payment(self.session, facts, kind, self.settings)
        except BillingDivergence as divergence:
            self.report.append(f"Evento {event_id} continua divergente: {divergence}")
        else:
            state = (
                self.session.scalar(
                    select(BillingSubscription.operation_status).where(
                        BillingSubscription.provider_id == facts.subscription_ref
                    )
                )
                if facts
                else None
            )
            record.status = "RECONCILIATION" if state == "REVIEW" else "PROCESSED"
            record.processed_at = datetime.now(UTC)
            self.record("WEBHOOK_REPROCESSED", event_id, f"Evento {event_id} reprocessado.")
        self.session.commit()
