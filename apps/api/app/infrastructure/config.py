from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = "eleven-br"
    jwt_audience: str = "eleven-mobile"
    cors_origins: list[str] = []
    dev_verification_codes: bool = False
    sms_provider: Literal["", "zenvia"] = ""
    zenvia_api_token: SecretStr = SecretStr("")
    zenvia_sms_from: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""
    smtp_from_name: str = "ELEVEN BR"
    smtp_use_ssl: bool = True
    smtp_timeout_seconds: float = Field(default=15, gt=0, le=60)
    media_root: Path = ROOT / ".local" / "media"
    asaas_env: Literal["sandbox", "production"] = "sandbox"
    asaas_api_key: SecretStr = SecretStr("")
    asaas_webhook_token: SecretStr = SecretStr("")
    asaas_base_url: str = ""
    billing_return_url: str = ""

    @field_validator("media_root")
    @classmethod
    def resolve_media_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @model_validator(mode="after")
    def secure_configuration(self) -> Self:
        expected = (
            "https://api-sandbox.asaas.com/v3"
            if self.asaas_env == "sandbox"
            else "https://api.asaas.com/v3"
        )
        if self.asaas_base_url and self.asaas_base_url.rstrip("/") != expected:
            raise ValueError("ASAAS_BASE_URL must match the official ASAAS_ENV endpoint")
        self.asaas_base_url = expected
        webhook_secret = self.asaas_webhook_token.get_secret_value()
        if webhook_secret and len(webhook_secret) < 32:
            raise ValueError("ASAAS_WEBHOOK_TOKEN must contain at least 32 characters")
        if self.asaas_env == "production" and self.app_env != "production":
            raise ValueError("Asaas production is forbidden outside APP_ENV=production")
        if self.billing_return_url and not self.billing_return_url.startswith("https://"):
            raise ValueError("BILLING_RETURN_URL must use HTTPS")
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-with"):
            raise ValueError("Configure JWT_SECRET with a random secret (32+ characters)")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
        if self.app_env == "production" and any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise ValueError("Production CORS origins must use HTTPS")
        if self.app_env == "production" and self.dev_verification_codes:
            raise ValueError("DEV_VERIFICATION_CODES cannot be enabled in production")
        if "*" in self.cors_origins:
            raise ValueError("Use explicit CORS origins for credentialed requests")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
