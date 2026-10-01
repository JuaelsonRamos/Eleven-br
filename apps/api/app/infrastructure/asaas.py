"""Small Asaas adapter. Never logs requests or credentials; rejections keep a masked cause."""

import base64
import re
from functools import cache
from pathlib import Path
from time import monotonic
from typing import Any

import httpx

from app.domain.billing import BillingPixPreparing, BillingRejected, BillingUnavailable
from app.infrastructure.config import Settings


class Asaas:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pix_read = False
        self.pix_read_deadline: float | None = None

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        key = self.settings.asaas_api_key.get_secret_value()
        if not key:
            raise BillingUnavailable("Contratação temporariamente indisponível. Tente mais tarde.")
        initial_pix_get = (
            method == "GET"
            and self.pix_read
            and (
                path.endswith("/pixQrCode")
                or (path.startswith("/subscriptions/") and path.endswith("/payments"))
            )
        )
        timeout = 65.0
        if initial_pix_get and self.pix_read_deadline is not None:
            remaining = self.pix_read_deadline - monotonic()
            if remaining <= 0:
                raise BillingPixPreparing("Pix em preparação.")
            # httpx budgets connect/read/write/pool separately; keep each phase short.
            timeout = min(1.0, remaining / 4)
        try:
            # No automatic POST retries or redirects. Ambiguous failures require reconciliation.
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.request(
                    method,
                    self.settings.asaas_base_url + path,
                    headers={"access_token": key, "User-Agent": "ELEVEN-BR/1.0"},
                    json=data,
                    params=params,
                )
            if initial_pix_get and (
                response.status_code in (404, 408, 409, 429) or response.status_code >= 500
            ):
                raise BillingPixPreparing("Pix em preparação.")
            if response.status_code == 400:
                # No documented 400 code safely proves eventual Pix availability.
                # Preserve normal rejection handling, including during a manual refresh.
                raise BillingRejected(
                    "Não foi possível iniciar o pagamento. Confira os dados e tente novamente.",
                    rejection(response),
                )
            if method == "DELETE" and response.status_code == 404:
                return {"deleted": True}
            response.raise_for_status()
            value: dict[str, Any] = response.json()
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (httpx.RequestError, ValueError):
            if initial_pix_get:
                raise BillingPixPreparing("Pix em preparação.") from None
            raise BillingUnavailable(
                "Não foi possível confirmar a operação no Asaas. "
                "Atualize a assinatura antes de tentar novamente."
            ) from None
        except httpx.HTTPStatusError:
            raise BillingUnavailable(
                "Não foi possível confirmar a operação no Asaas. "
                "Atualize a assinatura antes de tentar novamente."
            ) from None

    def list_all(self, path: str, params: dict[str, str | int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for offset in range(0, 1000, 100):
            page = self.request("GET", path, params={**params, "offset": offset, "limit": 100})
            rows.extend(page.get("data", []))
            if not page.get("hasMore", False):
                return rows
        raise BillingUnavailable("Conciliação requer revisão do suporte.")


def rejection(response: httpx.Response) -> str | None:
    """Provider error codes for the audit trail, with e-mails and document numbers masked."""
    try:
        errors = response.json().get("errors") or []
        text = "; ".join(f"{e.get('code')}: {e.get('description')}" for e in errors)
    except (ValueError, AttributeError, TypeError):
        return None
    return re.sub(r"[^\s@]+@[^\s@]+|\d{6,}", "***", text)[:280] or None


ITEM_IMAGE = Path(__file__).with_name("checkout-item.png")


@cache
def item_image() -> str:
    """Official ELEVEN BR logo, proportionally reduced: Asaas requires an image per item."""
    return base64.b64encode(ITEM_IMAGE.read_bytes()).decode("ascii")
