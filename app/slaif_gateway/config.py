"""Runtime configuration for the SLAIF API Gateway."""

from __future__ import annotations

import base64
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PRODUCTION_SECRET_LENGTH = 32
_ONE_TIME_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    """Environment-backed application settings."""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:8000/v1"

    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None

    TOKEN_HMAC_SECRET: str | None = None
    TOKEN_HMAC_KEY_VERSION: str = "v1"
    ADMIN_SESSION_SECRET: str | None = None

    ONE_TIME_SECRET_ENCRYPTION_KEY: str | None = None
    ONE_TIME_SECRET_KEY_VERSION: str = "v1"

    OPENAI_UPSTREAM_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None

    ENABLE_OPENAI_PROVIDER: bool = True
    ENABLE_OPENROUTER_PROVIDER: bool = True
    ENABLE_ADMIN_DASHBOARD: bool = True
    ENABLE_METRICS: bool = True

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Enforce minimum secret requirements for production."""
        if self.APP_ENV.lower() == "production":
            self._validate_production_secret("TOKEN_HMAC_SECRET", self.TOKEN_HMAC_SECRET)
            self._validate_production_secret("ADMIN_SESSION_SECRET", self.ADMIN_SESSION_SECRET)
            self._validate_required_encryption_key(
                "ONE_TIME_SECRET_ENCRYPTION_KEY",
                self.ONE_TIME_SECRET_ENCRYPTION_KEY,
            )

        if self.ONE_TIME_SECRET_ENCRYPTION_KEY:
            self._validate_encryption_key_shape(self.ONE_TIME_SECRET_ENCRYPTION_KEY)

        return self

    @staticmethod
    def _validate_production_secret(name: str, value: str | None) -> None:
        if not value:
            raise ValueError(f"{name} is required when APP_ENV=production")

        normalized = value.lower()
        if "change-me" in normalized:
            raise ValueError(f"{name} cannot contain placeholder text in production")

        if len(value) < _MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                f"{name} must be at least {_MIN_PRODUCTION_SECRET_LENGTH} characters in production"
            )

    @staticmethod
    def _validate_required_encryption_key(name: str, value: str | None) -> None:
        if not value:
            raise ValueError(f"{name} is required when APP_ENV=production")

    @staticmethod
    def _validate_encryption_key_shape(value: str) -> None:
        padding = "=" * (-len(value) % 4)
        try:
            key_bytes = base64.urlsafe_b64decode(value + padding)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "ONE_TIME_SECRET_ENCRYPTION_KEY must be base64url-encoded 32-byte key material"
            ) from exc

        if len(key_bytes) != _ONE_TIME_SECRET_KEY_BYTES:
            raise ValueError("ONE_TIME_SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
