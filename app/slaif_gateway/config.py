"""Runtime configuration for the SLAIF API Gateway."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Environment-backed application settings."""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:8000/v1"

    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None

    TOKEN_HMAC_SECRET: str | None = None
    ADMIN_SESSION_SECRET: str | None = None

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
        if self.APP_ENV.lower() != "production":
            return self

        self._validate_production_secret("TOKEN_HMAC_SECRET", self.TOKEN_HMAC_SECRET)
        self._validate_production_secret("ADMIN_SESSION_SECRET", self.ADMIN_SESSION_SECRET)
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
