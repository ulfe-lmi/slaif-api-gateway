"""Minimal runtime configuration for the SLAIF API Gateway."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_base_url: str = "https://api.ulfe.slaif.si/v1"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
