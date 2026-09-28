import smtplib
import socket
import ssl
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.auth import CODE_MINUTES, DeliveryUnavailable
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_session
from app.infrastructure.delivery import DevelopmentSender, SMTPVerificationSender, get_sender
from app.main import create_app


def settings(**changes):
    return Settings(
        _env_file=None,
        **{
            "database_url": "postgresql+psycopg://localhost/unused_test",
            "jwt_secret": "test-only-secret-" + "x" * 40,
            "app_env": "production",
            "cors_origins": [],
            "dev_verification_codes": False,
            "smtp_host": "smtp.example.com",
            "smtp_username": "sender@example.com",
            "smtp_password": "smtp-test-secret",
            "smtp_from_email": "sender@example.com",
            **changes,
        },
    )


@pytest.mark.parametrize("env", ["development", "test"])
def test_development_requires_explicit_opt_in(env):
    sender = get_sender(settings(app_env=env, dev_verification_codes=True))
    assert isinstance(sender, DevelopmentSender)
    assert sender.send(contact="local", channel="phone", code="123456") == "123456"
    assert isinstance(get_sender(settings(app_env=env)), SMTPVerificationSender)
    with pytest.raises(DeliveryUnavailable):
        get_sender(settings(app_env=env, smtp_host=""))


def test_production_cannot_enable_development_codes():
    with pytest.raises(ValidationError):
        settings(dev_verification_codes=True)


def test_password_recovery_uses_existing_secure_mail_sender(monkeypatch):
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    assert (
        get_sender(settings()).send(
            contact="recipient@example.com",
            channel="email",
            code="123456",
            purpose="password_reset",
        )
        is None
    )
    message = smtp.send_message.call_args.args[0]
    assert "recuperação de senha" in str(message["Subject"])
    assert "123456" in message.get_body(preferencelist=("plain",)).get_content()


@pytest.mark.parametrize("use_ssl", [True, False])
def test_secure_delivery_message_and_no_returned_code(monkeypatch, use_ssl):
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(smtplib, "SMTP_SSL" if use_ssl else "SMTP", factory)
    sender = get_sender(settings(smtp_use_ssl=use_ssl, smtp_port=465 if use_ssl else 587))
    assert isinstance(sender, SMTPVerificationSender)
    assert sender.send(contact="recipient@example.com", channel="email", code="123456") is None
    smtp.login.assert_called_once_with("sender@example.com", "smtp-test-secret")
    kwargs = factory.call_args.kwargs
    context = kwargs["context"] if use_ssl else smtp.starttls.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert kwargs["timeout"] == 15
    if not use_ssl:
        assert [call[0] for call in smtp.method_calls] == [
            "ehlo",
            "starttls",
            "ehlo",
            "login",
            "send_message",
        ]
    message = smtp.send_message.call_args.args[0]
    assert str(message["To"]) == "recipient@example.com"
    assert str(message["From"]) == "ELEVEN BR <sender@example.com>"
    assert str(message["Subject"]) == "Seu código de verificação - ELEVEN BR"
    for subtype in ["plain", "html"]:
        body = message.get_body(preferencelist=(subtype,)).get_content()
        assert "123456" in body and f"{CODE_MINUTES} minutos" in body
    assert smtp.send_message.call_args.kwargs == {
        "from_addr": "sender@example.com",
        "to_addrs": ["recipient@example.com"],
    }
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "error",
    [
        socket.gaierror("private"),
        TimeoutError("private"),
        ssl.SSLError("private"),
        smtplib.SMTPAuthenticationError(535, b"smtp-test-secret 123456"),
        smtplib.SMTPRecipientsRefused({"private": "123456"}),
    ],
)
def test_delivery_failure_is_sanitized(monkeypatch, caplog, error):
    factory = MagicMock(side_effect=error)
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    with pytest.raises(DeliveryUnavailable) as caught:
        get_sender(settings()).send(contact="recipient@example.com", channel="email", code="123456")
    for secret in ["private", "smtp-test-secret", "123456", "recipient@example.com"]:
        assert secret not in str(caught.value) and secret not in caplog.text
    assert caught.value.__suppress_context__


def test_starttls_failure_never_authenticates_or_sends(monkeypatch):
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.starttls.side_effect = smtplib.SMTPNotSupportedError("TLS unavailable")
    monkeypatch.setattr(smtplib, "SMTP", factory)
    with pytest.raises(DeliveryUnavailable):
        get_sender(settings(smtp_use_ssl=False)).send(
            contact="recipient@example.com", channel="email", code="123456"
        )
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "field,value",
    [
        ("smtp_host", ""),
        ("smtp_host", "smtp://invalid"),
        ("smtp_username", ""),
        ("smtp_password", ""),
        ("smtp_from_email", "invalid"),
        ("smtp_from_name", "Name\r\nBcc: hidden@example.com"),
    ],
)
def test_invalid_configuration_never_falls_back(field, value):
    with pytest.raises(DeliveryUnavailable):
        get_sender(settings(**{field: value}))


def test_phone_fails_before_connection(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    with pytest.raises(DeliveryUnavailable):
        get_sender(settings()).send(contact="+5511999999999", channel="phone", code="123456")
    factory.assert_not_called()


def test_production_registration_does_not_return_code(session, monkeypatch):
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings()
    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/register",
            json={
                "name": "Teste SMTP",
                "contact": "recipient@example.com",
                "password": "test-password-123",
                "password_confirmation": "test-password-123",
            },
        )
    assert response.status_code == 201, response.text
    assert "development_code" not in response.json()
    smtp.send_message.assert_called_once()


@pytest.mark.parametrize("stage", ["login", "send_message"])
def test_session_failure_closes_connection(monkeypatch, stage):
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    getattr(smtp, stage).side_effect = smtplib.SMTPException("sensitive reply")
    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    with pytest.raises(DeliveryUnavailable):
        get_sender(settings()).send(contact="recipient@example.com", channel="email", code="123456")
    factory.return_value.__exit__.assert_called_once()
