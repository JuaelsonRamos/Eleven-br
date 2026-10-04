"""Zenvia v2 SMS delivery; no automatic retries or sensitive logging."""

import httpx

from app.domain.auth import DeliveryUnavailable
from app.infrastructure.config import Settings

SMS_URL = "https://api.zenvia.com/v2/channels/sms/messages"
SMS_TIMEOUT_SECONDS = 10.0


class ZenviaSMSVerificationSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(
        self, *, contact: str, channel: str, code: str, purpose: str = "verify_contact"
    ) -> str | None:
        token = self.settings.zenvia_api_token.get_secret_value()
        sender = self.settings.zenvia_sms_from.strip()
        if channel != "phone" or self.settings.sms_provider != "zenvia":
            raise DeliveryUnavailable("Envio de código por este canal indisponível.")
        if not token.strip() or not sender:
            raise DeliveryUnavailable("Envio de SMS indisponível: configuração incompleta.")
        try:
            response = httpx.post(
                SMS_URL,
                headers={"X-API-TOKEN": token},
                json={
                    "from": sender,
                    "to": contact,
                    "contents": [
                        {
                            "type": "text",
                            "text": (
                                f"ELEVEN BR: seu código de verificação é {code}. "
                                "Não compartilhe este código."
                            ),
                        }
                    ],
                },
                timeout=SMS_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError):
            # Provider bodies/exceptions can contain credentials, recipient or OTP.
            raise DeliveryUnavailable(
                "Não foi possível enviar o código por SMS. Tente novamente mais tarde."
            ) from None
        try:
            data = response.json()
        except ValueError:
            return None
        message_id = data.get("id") if isinstance(data, dict) else None
        return message_id if isinstance(message_id, str) else None
