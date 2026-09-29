"""Small Asaas adapter. Never logs requests, provider error bodies or credentials."""

from typing import Any

import httpx

from app.domain.billing import BillingRejected, BillingUnavailable
from app.infrastructure.config import Settings


class Asaas:
    def __init__(self, settings: Settings):
        self.settings = settings

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
        try:
            # No automatic POST retries or redirects. Ambiguous failures require reconciliation.
            with httpx.Client(timeout=65, follow_redirects=False) as client:
                response = client.request(
                    method,
                    self.settings.asaas_base_url + path,
                    headers={"access_token": key, "User-Agent": "ELEVEN-BR/1.0"},
                    json=data,
                    params=params,
                )
            if response.status_code == 400:
                raise BillingRejected("Confira os dados de cobrança. O Asaas recusou a operação.")
            if method == "DELETE" and response.status_code == 404:
                return {"deleted": True}
            response.raise_for_status()
            value: dict[str, Any] = response.json()
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (httpx.HTTPError, ValueError):
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
