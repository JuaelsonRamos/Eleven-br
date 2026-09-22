from typing import Protocol

from app.domain.auth import DeliveryUnavailable
from app.infrastructure.config import Settings


class VerificationSender(Protocol):
    def send(self, *, contact: str, channel: str, code: str) -> str | None:
        """Deliver a code. Only the explicit local adapter may return it for display."""
        ...


class DevelopmentSender:
    def send(self, *, contact: str, channel: str, code: str) -> str:
        # No external delivery, plaintext database storage, file outbox or logging.
        return code


def get_sender(settings: Settings) -> VerificationSender:
    if settings.app_env in ("development", "test") and settings.dev_verification_codes:
        return DevelopmentSender()
    # Fail closed until a real provider is selected; never silently simulate production delivery.
    raise DeliveryUnavailable("Envio de código indisponível neste ambiente.")
