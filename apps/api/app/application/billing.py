"""Durable commercial commands. Short Team-locked transactions serialize state changes.

Provider I/O never runs inside a database transaction, so a slow Asaas cannot hold
the Team lock or a pooled connection. An intent is committed BEFORE each external
creation (customer_attempted/CREATING) and only the request that claimed it posts.
On timeout/restart, retry only reconciles by external reference: it never repeats an
uncertain POST. Claims without provider proof are resolved by the audited
`python -m app.billing_admin <team> reconcile` (billing_reconciliation).
"""

from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.billing_access import access_state
from app.application.team_profiles import membership_context
from app.application.teams import require_membership
from app.domain.billing import PRO_CODE, PRO_PRICE, BillingRejected, BillingUnavailable
from app.domain.billing import SubscriptionStatus as Status
from app.domain.policies import Conflict, Forbidden, NotFound, Plan
from app.infrastructure.asaas import Asaas
from app.infrastructure.billing_models import BillingAudit, BillingSubscription, TeamBilling
from app.infrastructure.config import Settings
from app.infrastructure.models import Team

CHECKOUT_MINUTES = 60


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    command_id: UUID
    method: Literal["PIX", "CREDIT_CARD"]
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    cpf_cnpj: str = Field(pattern=r"^(\d{11}|\d{14})$")
    confirm: Literal[True]


class Provider:
    """Asaas access refused inside a database transaction.

    A transaction may hold the Team lock and always pins a pooled connection, so a
    slow provider is never awaited inside one. Callers commit before each call.
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.client = Asaas(settings)

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        self.idle()
        return self.client.request(method, path, data, params)

    def list_all(self, path: str, params: dict[str, str | int]) -> list[dict[str, Any]]:
        self.idle()
        return self.client.list_all(path, params)

    def idle(self) -> None:
        if self.session.in_transaction():
            raise RuntimeError("Asaas I/O must not run inside a database transaction.")


def lock_team(session: Session, team_id: UUID) -> None:
    session.execute(select(Team).where(Team.id == team_id).with_for_update())


def authorize(session: Session, user_id: UUID, team_id: UUID, *, write: bool = False) -> Team:
    if write:
        lock_team(session, team_id)
    team = require_membership(session, user_id=user_id, team_id=team_id)
    if write and membership_context(session, team, user_id)[0] != "president":
        raise Forbidden("Somente o Presidente pode contratar ou cancelar o Pro.")
    return team


def audit(
    session: Session,
    team_id: UUID,
    action: str,
    reference: str,
    actor_id: UUID | None = None,
    origin: str = "api",
    reason: str | None = None,
) -> None:
    session.add(
        BillingAudit(
            team_id=team_id,
            actor_id=actor_id,
            action=action,
            origin=origin,
            reference=reference,
            reason=reason,
        )
    )


def latest(session: Session, team_id: UUID) -> BillingSubscription | None:
    return session.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.team_id == team_id)
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .limit(1)
    )


def subscription_of(session: Session, subscription_id: UUID) -> BillingSubscription:
    subscription = session.get(BillingSubscription, subscription_id, populate_existing=True)
    if subscription is None:
        raise NotFound("Assinatura não encontrada.")
    return subscription


def billing_account(session: Session, team_id: UUID) -> TeamBilling:
    account = session.scalar(
        select(TeamBilling)
        .where(TeamBilling.team_id == team_id)
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise NotFound("Cadastro de cobrança não encontrado.")
    return account


def summary(session: Session, user_id: UUID, team_id: UUID) -> dict[str, object]:
    team = authorize(session, user_id, team_id)
    plan, status, expiry = access_state(session, team)
    subscription = latest(session, team_id)
    return {
        "command_id": str(uuid4()),
        "plan": plan.value,
        "plan_code": PRO_CODE if plan == Plan.PRO else "FREE",
        "status": status.value,
        "price": str(PRO_PRICE),
        "expires_at": expiry,
        "next_due_date": expiry if subscription and not subscription.cancelled_at else None,
        "started_at": subscription.started_at.isoformat()
        if subscription and subscription.started_at
        else None,
        "can_manage": membership_context(session, team, user_id, plan=plan)[0] == "president",
        "method": subscription.method if subscription else None,
        "operation_status": subscription.operation_status if subscription else None,
        "cancel_requested": bool(subscription and subscription.cancel_requested),
        "can_cancel": bool(subscription and not subscription.cancelled_at),
        "warning": "Pagamento pendente. Regularize sua assinatura para manter os recursos PRO."
        if status.value == "OVERDUE"
        else None,
    }


def read_summary(session: Session, user_id: UUID, team_id: UUID) -> dict[str, object]:
    """Record observed clock-driven transitions without requiring a scheduler.

    Authorization always derives access from the clock, independently of this audit.
    This public read owns its transaction; nested business operations use summary().
    """
    authorize(session, user_id, team_id)
    lock_team(session, team_id)
    result = summary(session, user_id, team_id)
    account = session.scalar(select(TeamBilling).where(TeamBilling.team_id == team_id))
    if account:
        previous = session.scalar(
            select(BillingAudit)
            .where(BillingAudit.team_id == team_id, BillingAudit.action.like("ACCESS_%"))
            .order_by(BillingAudit.created_at.desc(), BillingAudit.id.desc())
            .limit(1)
        )
        action = "ACCESS_" + str(result["status"])
        if previous is None or previous.action != action:
            audit(session, team_id, action, str(account.id), user_id, origin="access_check")
    session.commit()
    return result


def account_for(session: Session, team: Team, settings: Settings) -> TeamBilling:
    account = session.scalar(select(TeamBilling).where(TeamBilling.team_id == team.id))
    if account is None:
        account = TeamBilling(
            team_id=team.id, environment=settings.asaas_env, grant_active=team.plan == "pro"
        )
        session.add(account)
        session.flush()
        if account.grant_active:
            audit(session, team.id, "LEGACY_PRO_PRESERVED", str(account.id), origin="migration")
    if account.environment != settings.asaas_env:
        raise Conflict("Ambiente de cobrança diferente do cadastro deste time.")
    return account


def begin_checkout(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    data: CheckoutInput,
    settings: Settings,
) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    if (
        not settings.asaas_api_key.get_secret_value()
        or not settings.asaas_webhook_token.get_secret_value()
    ):
        raise BillingUnavailable("Contratação indisponível até a configuração do Asaas.")
    if data.method == "CREDIT_CARD" and not settings.billing_return_url:
        raise BillingUnavailable("Configure a URL HTTPS de retorno do checkout.")
    account_for(session, team, settings)
    if access_state(session, team)[1] == Status.ADMIN_GRANTED:
        raise Conflict("Este time já possui Pro administrativo.")
    subscription = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.team_id == team_id,
            BillingSubscription.command_id == data.command_id,
        )
    )
    if subscription and subscription.method != data.method:
        raise Conflict("Esta operação já foi usada para outra forma de pagamento.")
    if subscription is None:
        current = latest(session, team_id)
        if current and not current.cancelled_at:
            # Different double-click commands still reuse the same live subscription.
            if current.method != data.method:
                raise Conflict(
                    "Conclua ou cancele a contratação atual antes de trocar o pagamento."
                )
            subscription = current
        else:
            subscription = BillingSubscription(
                team_id=team_id,
                command_id=data.command_id,
                method=data.method,
                amount=PRO_PRICE,
                plan_code=PRO_CODE,
            )
            session.add(subscription)
            session.flush()
            audit(session, team_id, "SUBSCRIPTION_STARTED", str(subscription.id), user_id)
    subscription_id = subscription.id
    session.commit()
    provider = Provider(session, settings)
    customer_id = ensure_customer(session, provider, user_id, team_id, subscription_id, data)
    # Claim under the Team lock. Only the claimant posts, after the lock is released.
    authorize(session, user_id, team_id, write=True)
    subscription = subscription_of(session, subscription_id)
    if subscription.cancelled_at or subscription.cancel_requested:
        raise Conflict("A contratação está cancelada ou em cancelamento.")
    if subscription.operation_status != "NEW":
        session.commit()
        return payment_details(session, user_id, team_id, settings)
    subscription.operation_status = "CREATING"
    session.commit()
    path, body = creation_request(data.method, subscription_id, customer_id, settings)
    try:
        created = provider.request("POST", path, body)
    except BillingRejected:
        lock_team(session, team_id)
        subscription = subscription_of(session, subscription_id)
        if subscription.operation_status == "CREATING" and not (
            subscription.provider_id or subscription.checkout_id
        ):
            subscription.operation_status = "NEW"
        audit(session, team_id, "PROVIDER_REJECTED", str(subscription_id))
        session.commit()
        raise
    return record_creation(
        session, provider, user_id, team_id, subscription_id, data.method, str(created["id"])
    )


def ensure_customer(
    session: Session,
    provider: Provider,
    user_id: UUID,
    team_id: UUID,
    subscription_id: UUID,
    data: CheckoutInput,
) -> str:
    """Return the team's Asaas customer, creating it at most once (claim before POST)."""
    customer_id = session.scalar(
        select(TeamBilling.customer_id).where(TeamBilling.team_id == team_id)
    )
    session.commit()
    if customer_id:
        return customer_id
    reference = f"eleven-team:{team_id}"
    matches = provider.list_all("/customers", {"externalReference": reference})
    authorize(session, user_id, team_id, write=True)
    account = billing_account(session, team_id)
    if account.customer_id:
        customer_id = account.customer_id
    elif len(matches) > 1:
        raise Conflict("Mais de um cliente encontrado. Solicite conciliação ao suporte.")
    elif matches:
        customer_id = str(matches[0]["id"])
        account.customer_id = customer_id
    elif account.customer_attempted:
        raise Conflict("Criação do cliente em conciliação. Não será criado outro cliente.")
    else:
        account.customer_attempted = True
    session.commit()
    if customer_id:
        return customer_id
    try:
        created = provider.request(
            "POST",
            "/customers",
            {
                "name": data.name,
                "email": str(data.email),
                "cpfCnpj": data.cpf_cnpj,
                "externalReference": reference,
                "notificationDisabled": True,
            },
        )
    except BillingRejected:
        lock_team(session, team_id)
        billing_account(session, team_id).customer_attempted = False
        audit(session, team_id, "PROVIDER_REJECTED", str(subscription_id))
        session.commit()
        raise
    customer_id = str(created["id"])
    lock_team(session, team_id)
    account = billing_account(session, team_id)
    if account.customer_id not in (None, customer_id):
        raise Conflict("Cliente divergente no Asaas. Solicite conciliação ao suporte.")
    account.customer_id = customer_id
    session.commit()
    return customer_id


def creation_request(
    method: str, subscription_id: UUID, customer_id: str, settings: Settings
) -> tuple[str, dict[str, Any]]:
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    reference = f"eleven-sub:{subscription_id}"
    if method == "PIX":
        return "/subscriptions", {
            "customer": customer_id,
            "billingType": "PIX",
            "value": float(PRO_PRICE),
            "cycle": "MONTHLY",
            "nextDueDate": today,
            "externalReference": reference,
            "description": "ELEVEN BR PRO mensal",
            "fine": {"value": 0},
            "interest": {"value": 0},
        }
    return "/checkouts", {
        "customer": customer_id,
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": CHECKOUT_MINUTES,
        "externalReference": reference,
        "callback": {
            k: settings.billing_return_url for k in ("successUrl", "cancelUrl", "expiredUrl")
        },
        "items": [
            {
                "name": "ELEVEN BR PRO",
                "description": "Assinatura mensal por time",
                "quantity": 1,
                "value": float(PRO_PRICE),
            }
        ],
        "subscription": {"cycle": "MONTHLY", "nextDueDate": today},
    }


def record_creation(
    session: Session,
    provider: Provider,
    user_id: UUID,
    team_id: UUID,
    subscription_id: UUID,
    method: str,
    created_id: str,
) -> dict[str, object]:
    settings = provider.client.settings
    lock_team(session, team_id)
    subscription = subscription_of(session, subscription_id)
    current = subscription.provider_id if method == "PIX" else subscription.checkout_id
    if current is None:
        if method == "PIX":
            subscription.provider_id = created_id
        else:
            subscription.checkout_id = created_id
        subscription.operation_status = "READY"
    orphan = current not in (None, created_id) or subscription.cancelled_at is not None
    stopping = subscription.cancel_requested
    session.commit()
    if orphan:
        # Closed or bound elsewhere while this creation was in flight: never leave it charging.
        stop_remote(
            provider,
            created_id if method == "PIX" else None,
            None if method == "PIX" else created_id,
        )
        raise Conflict("Contratação encerrada durante a criação; a cobrança criada foi cancelada.")
    if stopping:
        # A cancellation arrived while the resource was being created: finish it now.
        return cancel(session, user_id, team_id, settings)
    return payment_details(session, user_id, team_id, settings)


def payment_details(
    session: Session,
    user_id: UUID,
    team_id: UUID,
    settings: Settings,
) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    account = account_for(session, team, settings)
    subscription = latest(session, team_id)
    result = summary(session, user_id, team_id)
    if not subscription or subscription.cancelled_at:
        session.commit()
        return result
    subscription_id, method, amount = subscription.id, subscription.method, subscription.amount
    provider_id, checkout_id = subscription.provider_id, subscription.checkout_id
    creating = subscription.operation_status == "CREATING"
    stopping = subscription.cancel_requested
    customer_id = account.customer_id
    session.commit()
    provider = Provider(session, settings)
    if creating and not provider_id and method == "PIX" and customer_id:
        matches = provider.list_all(
            "/subscriptions",
            {"externalReference": f"eleven-sub:{subscription_id}", "customer": customer_id},
        )
        if len(matches) > 1:
            raise Conflict("Assinaturas divergentes. Solicite conciliação ao suporte.")
        if matches:
            provider_id = adopt_reference(session, team_id, subscription_id, str(matches[0]["id"]))
            creating = False
    if stopping:
        result["notice"] = "Cancelamento em andamento. Confirme o cancelamento para concluí-lo."
        return result
    if checkout_id and not provider_id:
        host = "sandbox.asaas.com" if settings.asaas_env == "sandbox" else "asaas.com"
        result["checkout_url"] = (
            f"https://{host}/checkoutSession/show?id={quote(checkout_id, safe='')}"
        )
    if provider_id:
        payments = provider.list_all(f"/subscriptions/{quote(provider_id, safe='')}/payments", {})
        pending = sorted(
            (p for p in payments if p.get("status") in ("PENDING", "OVERDUE")),
            key=lambda p: str(p.get("dueDate")),
        )
        if pending:
            payment = pending[0]
            result["next_due_date"] = payment.get("dueDate")
            if method == "PIX":
                qr = provider.request(
                    "GET", f"/payments/{quote(str(payment['id']), safe='')}/pixQrCode"
                )
                result["pix"] = {
                    "image": qr.get("encodedImage"),
                    "payload": qr.get("payload"),
                    "expires_at": qr.get("expirationDate"),
                    "amount": str(amount),
                }
    if creating and not provider_id and not checkout_id:
        result["notice"] = (
            "Contratação em conciliação. Não repita a criação; aguarde o webhook ou o suporte."
        )
    return result


def adopt_reference(session: Session, team_id: UUID, subscription_id: UUID, found: str) -> str:
    """Record the subscription the provider proves was created for this intent."""
    lock_team(session, team_id)
    subscription = subscription_of(session, subscription_id)
    if subscription.provider_id not in (None, found):
        raise Conflict("Assinaturas divergentes. Solicite conciliação ao suporte.")
    subscription.provider_id, subscription.operation_status = found, "READY"
    session.commit()
    return found


def stop_remote(provider: Provider, provider_id: str | None, checkout_id: str | None) -> None:
    """Idempotent: Asaas answers 404 (treated as done) for a removed subscription."""
    if provider_id:
        provider.request("DELETE", f"/subscriptions/{quote(provider_id, safe='')}")
    elif checkout_id:
        provider.request("POST", f"/checkouts/{quote(checkout_id, safe='')}/cancel")


def cancel(session: Session, user_id: UUID, team_id: UUID, settings: Settings) -> dict[str, object]:
    team = authorize(session, user_id, team_id, write=True)
    account_for(session, team, settings)
    subscription = latest(session, team_id)
    if not subscription:
        raise NotFound("Assinatura não encontrada.")
    if not subscription.cancelled_at:
        subscription.cancel_requested = True
        subscription_id = subscription.id
        provider_id, checkout_id = subscription.provider_id, subscription.checkout_id
        unsent = subscription.operation_status == "NEW"
        session.commit()
        if not provider_id and not checkout_id and not unsent:
            raise Conflict(
                "Cancelamento aguarda conciliação da contratação. "
                "Atualize a assinatura ou contate o suporte."
            )
        provider = Provider(session, settings)
        stop_remote(provider, provider_id, checkout_id)
        authorize(session, user_id, team_id, write=True)
        subscription = subscription_of(session, subscription_id)
        # A paid checkout may have created its recurrence meanwhile: stop it as well.
        late = subscription.provider_id if subscription.provider_id != provider_id else None
        if not subscription.cancelled_at:
            subscription.cancelled_at = datetime.now(UTC)
            audit(session, team_id, "SUBSCRIPTION_CANCELLED", str(subscription_id), user_id)
        session.commit()
        if late:
            stop_remote(provider, late, None)
    return summary(session, user_id, team_id)


def administrative_grant(
    session: Session,
    team_id: UUID,
    *,
    enabled: bool,
    operator: str,
    reason: str,
    settings: Settings,
    expires_at: datetime | None = None,
) -> None:
    """Trusted internal operation, deliberately not exposed to team administrators."""
    if not operator.strip() or not reason.strip():
        raise Conflict("Concessão exige operador e justificativa.")
    team = session.scalar(select(Team).where(Team.id == team_id).with_for_update())
    if not team:
        raise NotFound("Time não encontrado.")
    current = latest(session, team_id)
    if enabled and current and not current.cancelled_at:
        raise Conflict("Cancele a recorrência antes de conceder Pro sem cobrança.")
    account = account_for(session, team, settings)
    account.grant_active, account.grant_expires_at = enabled, expires_at
    audit(
        session,
        team_id,
        "ADMIN_GRANTED" if enabled else "ADMIN_REVOKED",
        operator[:200],
        origin="operator",
        reason=reason[:300],
    )
    session.commit()
