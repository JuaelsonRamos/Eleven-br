import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from typing import Protocol

from email_validator import EmailNotValidError, validate_email

from app.domain.auth import CODE_MINUTES, DeliveryUnavailable
from app.infrastructure.config import Settings


class VerificationSender(Protocol):
    def send(self, *, contact: str, channel: str, code: str) -> str | None:
        """Deliver a code. Only the explicit local adapter may return it for display."""
        ...


class DevelopmentSender:
    def send(self, *, contact: str, channel: str, code: str) -> str:
        # No external delivery, plaintext database storage, file outbox or logging.
        return code


class SMTPVerificationSender:
    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            if (
                not settings.smtp_host
                or any(c.isspace() or c in "/:@" for c in settings.smtp_host)
                or not settings.smtp_username.strip()
                or not settings.smtp_password.get_secret_value()
                or any(c in settings.smtp_from_name for c in "\r\n")
            ):
                raise ValueError
            self.from_email = validate_email(
                settings.smtp_from_email, check_deliverability=False
            ).normalized
        except (ValueError, EmailNotValidError):
            raise DeliveryUnavailable(
                "Envio de e-mail indisponível: configuração SMTP inválida."
            ) from None

    def send(self, *, contact: str, channel: str, code: str) -> None:
        if channel != "email":
            raise DeliveryUnavailable("Envio de código por este canal indisponível.")
        settings = self.settings
        try:
            recipient = validate_email(contact, check_deliverability=False).normalized
            message = EmailMessage()
            message["From"] = formataddr((settings.smtp_from_name, self.from_email))
            message["To"] = recipient
            message["Subject"] = "Seu código de verificação - ELEVEN BR"
            message.set_content(
                "Olá!\n\nSeu código de verificação do ELEVEN BR é:\n\n"
                f"{code}\n\nO código expira em {CODE_MINUTES} minutos.\n\n"
                "Se você não solicitou este código, ignore esta mensagem.\n\n"
                "ELEVEN BR\nSeu time. Seu jogo.\n"
            )
            message.add_alternative(
                '<!doctype html><html lang="pt-BR"><body>'
                "<p>Olá!</p><p>Seu código de verificação do ELEVEN BR é:</p>"
                '<p style="font-size:32px;font-weight:bold;letter-spacing:6px">'
                f"{escape(code)}</p><p>O código expira em {CODE_MINUTES} minutos.</p>"
                "<p>Se você não solicitou este código, ignore esta mensagem.</p>"
                "<p><strong>ELEVEN BR</strong><br>Seu time. Seu jogo.</p></body></html>",
                subtype="html",
            )
            context = ssl.create_default_context()
            connection: smtplib.SMTP
            if settings.smtp_use_ssl:
                connection = smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                    context=context,
                )
            else:
                connection = smtplib.SMTP(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                )
            with connection as smtp:
                if not settings.smtp_use_ssl:
                    smtp.ehlo()
                    smtp.starttls(context=context)  # Mandatory TLS; never fall back to plaintext.
                    smtp.ehlo()
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                refused = smtp.send_message(
                    message, from_addr=self.from_email, to_addrs=[recipient]
                )
                if refused:
                    raise smtplib.SMTPException("Recipient refused")
        except (OSError, smtplib.SMTPException, ValueError) as error:
            # SMTP replies can echo credentials/message content: never log exception text/traceback.
            logging.getLogger(__name__).warning(
                "Verification SMTP delivery failed (%s)", type(error).__name__
            )
            raise DeliveryUnavailable(
                "Não foi possível enviar o código. Tente novamente mais tarde."
            ) from None


def get_sender(settings: Settings) -> VerificationSender:
    if settings.app_env in ("development", "test") and settings.dev_verification_codes:
        return DevelopmentSender()
    return SMTPVerificationSender(settings)
