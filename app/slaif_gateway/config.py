"""Runtime configuration for the SLAIF API Gateway."""

from __future__ import annotations

import base64
import os
import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PRODUCTION_SECRET_LENGTH = 32
_ONE_TIME_SECRET_KEY_BYTES = 32
_GATEWAY_PREFIX_PATTERN = re.compile(r"^sk-[a-z0-9-]+-$")


class Settings(BaseSettings):
    """Environment-backed application settings."""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:8000/v1"

    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None

    ACTIVE_HMAC_KEY_VERSION: str = "1"
    TOKEN_HMAC_SECRET_V1: str | None = None
    TOKEN_HMAC_SECRET: str | None = None
    ADMIN_SESSION_SECRET: str | None = None

    ONE_TIME_SECRET_ENCRYPTION_KEY: str | None = None
    ONE_TIME_SECRET_KEY_VERSION: str = "v1"

    OPENAI_UPSTREAM_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None

    ENABLE_OPENAI_PROVIDER: bool = True
    ENABLE_OPENROUTER_PROVIDER: bool = True
    ENABLE_ADMIN_DASHBOARD: bool = True
    ENABLE_METRICS: bool = True
    METRICS_REQUIRE_AUTH: bool | None = None
    METRICS_ALLOWED_IPS: str | None = None
    REQUEST_ID_HEADER: str = "X-Request-ID"
    LOG_LEVEL: str = "INFO"
    STRUCTURED_LOGS: bool = True
    GATEWAY_KEY_PREFIX: str = "sk-slaif-"
    GATEWAY_KEY_ACCEPTED_PREFIXES: str | None = None
    DEFAULT_MAX_OUTPUT_TOKENS: int = 1024
    HARD_MAX_OUTPUT_TOKENS: int = 4096
    HARD_MAX_INPUT_TOKENS: int = 128000

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Enforce minimum secret requirements for production."""
        self._validate_gateway_key_prefix(self.GATEWAY_KEY_PREFIX)
        accepted_prefixes = self.get_gateway_key_accepted_prefixes()
        if self.get_gateway_key_prefix() not in accepted_prefixes:
            raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES must include GATEWAY_KEY_PREFIX")

        if self.APP_ENV.lower() == "production":
            version = self.ACTIVE_HMAC_KEY_VERSION.strip()
            if not version:
                raise ValueError("ACTIVE_HMAC_KEY_VERSION is required when APP_ENV=production")

            active_secret = self.get_hmac_secret(version)
            self._validate_production_secret(
                f"TOKEN_HMAC_SECRET_V{version}",
                active_secret,
            )
            self._validate_production_secret("ADMIN_SESSION_SECRET", self.ADMIN_SESSION_SECRET)
            self._validate_required_encryption_key(
                "ONE_TIME_SECRET_ENCRYPTION_KEY",
                self.ONE_TIME_SECRET_ENCRYPTION_KEY,
            )

        if self.ONE_TIME_SECRET_ENCRYPTION_KEY:
            self._validate_encryption_key_shape(self.ONE_TIME_SECRET_ENCRYPTION_KEY)

        self._validate_request_caps()
        self._validate_request_id_header()
        return self

    def _validate_request_caps(self) -> None:
        if self.DEFAULT_MAX_OUTPUT_TOKENS <= 0:
            raise ValueError("DEFAULT_MAX_OUTPUT_TOKENS must be a positive integer")
        if self.HARD_MAX_OUTPUT_TOKENS <= 0:
            raise ValueError("HARD_MAX_OUTPUT_TOKENS must be a positive integer")
        if self.HARD_MAX_INPUT_TOKENS <= 0:
            raise ValueError("HARD_MAX_INPUT_TOKENS must be a positive integer")
        if self.DEFAULT_MAX_OUTPUT_TOKENS > self.HARD_MAX_OUTPUT_TOKENS:
            raise ValueError("DEFAULT_MAX_OUTPUT_TOKENS must be <= HARD_MAX_OUTPUT_TOKENS")

    def _validate_request_id_header(self) -> None:
        header = self.REQUEST_ID_HEADER.strip()
        if not header:
            raise ValueError("REQUEST_ID_HEADER cannot be empty")
        if any(ch.isspace() for ch in header):
            raise ValueError("REQUEST_ID_HEADER cannot contain whitespace")
        if any(ord(ch) < 33 or ord(ch) == 127 for ch in header):
            raise ValueError("REQUEST_ID_HEADER cannot contain control characters")
        self.REQUEST_ID_HEADER = header

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

    @staticmethod
    def _validate_gateway_key_prefix(prefix: str) -> None:
        if not prefix:
            raise ValueError("Gateway key prefix cannot be empty")
        if any(ch.isspace() for ch in prefix):
            raise ValueError("Gateway key prefix cannot contain whitespace")
        if "." in prefix:
            raise ValueError("Gateway key prefix cannot contain '.'")
        if "/" in prefix or "\\" in prefix:
            raise ValueError("Gateway key prefix cannot contain slash characters")
        if '"' in prefix or "'" in prefix:
            raise ValueError("Gateway key prefix cannot contain quotes")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in prefix):
            raise ValueError("Gateway key prefix cannot contain control characters")
        if not _GATEWAY_PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(
                "Gateway key prefix must start with 'sk-', end with '-', and use lowercase "
                "ASCII letters, digits, and hyphens only"
            )

    def get_gateway_key_prefix(self) -> str:
        """Return active gateway key prefix after validation."""
        prefix = self.GATEWAY_KEY_PREFIX.strip()
        self._validate_gateway_key_prefix(prefix)
        return prefix

    def get_gateway_key_accepted_prefixes(self) -> tuple[str, ...]:
        """Return normalized accepted gateway key prefixes."""
        raw = self.GATEWAY_KEY_ACCEPTED_PREFIXES
        if raw is None:
            prefixes = (self.get_gateway_key_prefix(),)
        else:
            prefixes = tuple(item.strip() for item in raw.split(",") if item.strip())
            if not prefixes:
                raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES cannot be empty")

        for prefix in prefixes:
            self._validate_gateway_key_prefix(prefix)

        if self.get_gateway_key_prefix() not in prefixes:
            raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES must include GATEWAY_KEY_PREFIX")

        return prefixes

    def get_hmac_secret(self, version: str) -> str | None:
        """Return configured HMAC secret for the requested version."""
        normalized = version.strip()
        if not normalized:
            return None

        versioned_name = f"TOKEN_HMAC_SECRET_V{normalized}"
        versioned_secret = os.getenv(versioned_name) or getattr(self, versioned_name, None)
        if versioned_secret:
            return versioned_secret

        if self.APP_ENV.lower() != "production" and normalized == "1" and self.TOKEN_HMAC_SECRET:
            return self.TOKEN_HMAC_SECRET

        return None

    def get_active_hmac_secret(self) -> tuple[str, str]:
        """Return active HMAC version and secret."""
        version = self.ACTIVE_HMAC_KEY_VERSION.strip()
        if not version:
            raise ValueError("ACTIVE_HMAC_KEY_VERSION cannot be empty")

        secret = self.get_hmac_secret(version)
        if not secret:
            raise ValueError(f"TOKEN_HMAC_SECRET_V{version} is required for active HMAC version")
        return version, secret

    def metrics_require_auth(self) -> bool:
        """Return whether /metrics should require explicit exposure controls."""
        if self.METRICS_REQUIRE_AUTH is not None:
            return self.METRICS_REQUIRE_AUTH
        return self.APP_ENV.lower() == "production"

    def get_metrics_allowed_ips(self) -> tuple[str, ...]:
        """Return normalized IP allowlist entries for /metrics."""
        if not self.METRICS_ALLOWED_IPS:
            return ()
        return tuple(item.strip() for item in self.METRICS_ALLOWED_IPS.split(",") if item.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
