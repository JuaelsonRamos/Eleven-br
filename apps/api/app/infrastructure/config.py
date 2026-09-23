from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = "eleven-br"
    jwt_audience: str = "eleven-mobile"
    cors_origins: list[str] = []
    dev_verification_codes: bool = False
    media_root: Path = ROOT / ".local" / "media"

    @field_validator("media_root")
    @classmethod
    def resolve_media_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @model_validator(mode="after")
    def secure_configuration(self) -> Self:
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
