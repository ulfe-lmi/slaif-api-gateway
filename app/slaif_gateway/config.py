"""Minimal runtime configuration for the SLAIF API Gateway."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_BASE_URL: str = "https://api.ulfe.slaif.si/v1"
    PUBLIC_BASE_URL: str = "https://api.ulfe.slaif.si/v1"
    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None
    TOKEN_HMAC_SECRET: str | None = None
    ADMIN_SESSION_SECRET: str | None = None

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
