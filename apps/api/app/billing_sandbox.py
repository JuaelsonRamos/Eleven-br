"""Guarded local API factory for real Asaas Sandbox validation, never production."""

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.infrastructure.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    database = make_url(settings.database_url)
    if (
        settings.app_env != "test"
        or settings.asaas_env != "sandbox"
        or settings.asaas_base_url != "https://api-sandbox.asaas.com/v3"
        or database.database != "eleven_test"
        or database.host not in ("localhost", "127.0.0.1", "::1")
    ):
        raise RuntimeError("Sandbox requires APP_ENV=test and the local eleven_test database.")
    if not (
        settings.asaas_api_key.get_secret_value()
        and settings.asaas_webhook_token.get_secret_value()
    ):
        raise RuntimeError("Configure Sandbox credentials locally before starting this API.")
    # Payment availability is derived from the same environment guard by billing.
    from app.main import app

    return app
