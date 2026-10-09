import pytest

from app.billing_sandbox import create_app
from app.infrastructure.config import Settings


@pytest.mark.parametrize(
    "overrides,allowed",
    [
        ({}, True),
        ({"app_env": "development"}, False),
        ({"database_url": "postgresql+psycopg://unused@localhost/eleven"}, False),
        ({"database_url": "postgresql+psycopg://unused@remote/eleven_test"}, False),
        ({"database_url": "postgresql+psycopg://unused@localhost/other_test"}, False),
        ({"asaas_api_key": ""}, False),
        ({"asaas_webhook_token": ""}, False),
        ({"app_env": "production", "asaas_env": "production"}, False),
    ],
)
def test_sandbox_factory_never_targets_production(monkeypatch, overrides, allowed):
    from app.domain import billing as policy

    monkeypatch.setattr(policy, "ENABLED_PAYMENT_METHODS", ("PIX",))

    settings = Settings(
        _env_file=None,
        **{
            "app_env": "test",
            "database_url": "postgresql+psycopg://unused@localhost/eleven_test",
            "jwt_secret": "test-only-" + "x" * 40,
            "asaas_api_key": "test-only-not-a-real-key",
            "asaas_webhook_token": "test-only-" + "x" * 40,
            **overrides,
        },
    )
    monkeypatch.setattr("app.billing_sandbox.get_settings", lambda: settings)
    if allowed:
        from app.main import app

        assert create_app() is app
        assert "/v1/billing/asaas/webhook" in app.openapi()["paths"]
    else:
        with pytest.raises(RuntimeError):
            create_app()
    assert policy.ENABLED_PAYMENT_METHODS == ("PIX",)


@pytest.mark.parametrize(
    "environment,provider,host,database,expected",
    [
        ("development", "sandbox", "localhost", "eleven_test", ("PIX", "CREDIT_CARD")),
        ("test", "sandbox", "127.0.0.1", "eleven_test", ("PIX", "CREDIT_CARD")),
        ("production", "sandbox", "localhost", "eleven_test", ("PIX",)),
        ("production", "production", "localhost", "eleven_test", ("PIX",)),
        ("development", "sandbox", "remote", "eleven_test", ("PIX",)),
        ("development", "sandbox", "localhost", "eleven", ("PIX",)),
    ],
)
def test_payment_methods_are_local_sandbox_only(environment, provider, host, database, expected):
    from app.application.billing import payment_methods

    settings = Settings(
        _env_file=None,
        app_env=environment,
        asaas_env=provider,
        asaas_base_url="",
        database_url=f"postgresql+psycopg://unused@{host}/{database}",
        jwt_secret="test-only-" + "x" * 40,
        dev_verification_codes=False,
        cors_origins=[],
    )
    assert payment_methods(settings) == expected
