"""Bounded GET-only recovery after an initial Pix subscription was persisted."""

from decimal import Decimal
from time import monotonic, sleep
from urllib.parse import quote

from app.application.billing import Provider
from app.domain.billing import BillingPixPreparing

ATTEMPTS = 3
INTERVAL = 0.5
BUDGET_SECONDS = 6.0
PREPARING = (
    "Seu PIX está sendo preparado. Aguarde alguns instantes e toque em "
    "Atualizar assinatura para consultar o mesmo pagamento."
)


def initial_pix(
    provider: Provider, provider_id: str, amount: Decimal, *, retry: bool
) -> dict[str, object]:
    """Never creates anything. Refresh performs one GET sequence on the saved ID."""
    provider.idle()
    deadline = monotonic() + BUDGET_SECONDS
    previous = provider.client.pix_read_deadline
    previous_read = provider.client.pix_read
    provider.client.pix_read = True
    # Manual refresh retains its normal timeout and never repeats a GET automatically.
    provider.client.pix_read_deadline = deadline if retry else None
    try:
        for attempt in range(ATTEMPTS if retry else 1):
            if attempt:
                remaining = deadline - monotonic()
                if remaining <= INTERVAL:
                    break
                sleep(INTERVAL)
            try:
                payments = provider.list_all(
                    f"/subscriptions/{quote(provider_id, safe='')}/payments", {}
                )
                pending = sorted(
                    (
                        p
                        for p in payments
                        if p.get("status") in ("PENDING", "OVERDUE") and not p.get("deleted")
                    ),
                    key=lambda p: str(p.get("dueDate")),
                )
                if not pending:
                    if payments:
                        return {}  # E.g. already paid: only its webhook can grant PRO.
                    continue
                qr = provider.request(
                    "GET", f"/payments/{quote(str(pending[0]['id']), safe='')}/pixQrCode"
                )
                if qr.get("encodedImage") and qr.get("payload"):
                    return {
                        "pix": {
                            "image": qr["encodedImage"],
                            "payload": qr["payload"],
                            "expires_at": qr.get("expirationDate"),
                            "amount": str(amount),
                        }
                    }
            except BillingPixPreparing:
                pass  # No provider bodies/payer data logged, and no mutation of the intent.
        return {"notice": PREPARING}
    finally:
        provider.client.pix_read_deadline = previous
        provider.client.pix_read = previous_read
