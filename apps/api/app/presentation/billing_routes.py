import hmac
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.application import billing, billing_webhooks
from app.infrastructure.config import get_settings
from app.infrastructure.rate_limit import rate_limit
from app.presentation.dependencies import CurrentUser, SessionDep

router = APIRouter(tags=["billing"])


class Confirm(BaseModel):
    confirm: Literal[True]


class Webhook(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    event: str = Field(min_length=1, max_length=80)
    payment: dict[str, Any] | None = None
    subscription: dict[str, Any] | None = None
    checkout: dict[str, Any] | None = None


def limit(session: SessionDep, user: CurrentUser, team_id: UUID) -> None:
    billing.authorize(session, user.id, team_id, write=True)
    rate_limit(session, get_settings(), "billing-team", str(team_id), limit=20, seconds=300)


@router.get("/v1/teams/{team_id}/billing")
def summary(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    return billing.read_summary(session, user.id, team_id)


@router.post("/v1/teams/{team_id}/billing/checkout")
def checkout(
    team_id: UUID, data: billing.CheckoutInput, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    limit(session, user, team_id)
    return billing.begin_checkout(session, user.id, team_id, data, get_settings())


@router.post("/v1/teams/{team_id}/billing/refresh")
def refresh(team_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, object]:
    limit(session, user, team_id)
    return billing.payment_details(session, user.id, team_id, get_settings())


@router.post("/v1/teams/{team_id}/billing/cancel")
def cancel(
    team_id: UUID, data: Confirm, session: SessionDep, user: CurrentUser
) -> dict[str, object]:
    limit(session, user, team_id)
    return billing.cancel(session, user.id, team_id, get_settings())


@router.post("/v1/billing/asaas/webhook")
def webhook(
    data: Webhook, session: SessionDep, asaas_access_token: Annotated[str | None, Header()] = None
) -> dict[str, bool]:
    settings = get_settings()
    expected = settings.asaas_webhook_token.get_secret_value()
    if (
        not expected
        or not asaas_access_token
        or not hmac.compare_digest(asaas_access_token, expected)
    ):
        raise HTTPException(status_code=401, detail="Webhook não autorizado.")
    billing_webhooks.process(session, data.model_dump(exclude_none=True), settings)
    return {"received": True}
