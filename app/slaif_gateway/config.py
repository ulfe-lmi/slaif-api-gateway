"""Runtime configuration for the SLAIF API Gateway."""

from __future__ import annotations

import base64
import os
import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PRODUCTION_SECRET_LENGTH = 32
_MIN_PROVIDER_SECRET_LENGTH = 20
_ONE_TIME_SECRET_KEY_BYTES = 32
_GATEWAY_PREFIX_PATTERN = re.compile(r"^sk-[a-z0-9-]+-$")
_PLACEHOLDER_SECRET_SUBSTRINGS = (
    "change-me",
    "changeme",
    "placeholder",
    "example",
    "dummy",
)


class Settings(BaseSettings):
    """Environment-backed application settings."""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:8000/v1"

    DATABASE_URL: str | None = None
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT_SECONDS: float = 30
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_CONNECT_TIMEOUT_SECONDS: float = 10
    DATABASE_STATEMENT_TIMEOUT_MS: int | None = None
    REDIS_URL: str | None = None
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    ENABLE_REDIS_RATE_LIMITS: bool = False
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 2
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 2
    DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE: int | None = None
    DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE: int | None = None
    DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS: int | None = None
    RATE_LIMIT_FAIL_CLOSED: bool | None = None
    RATE_LIMIT_CONCURRENCY_TTL_SECONDS: int = 300
    RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS: int = 30
    RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS: int = 30

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
    ADMIN_SESSION_COOKIE_NAME: str = "slaif_admin_session"
    ADMIN_SESSION_COOKIE_SECURE: bool | None = None
    ADMIN_SESSION_COOKIE_HTTPONLY: bool = True
    ADMIN_SESSION_COOKIE_SAMESITE: str = "lax"
    ADMIN_SESSION_TTL_SECONDS: int = 28800
    ADMIN_LOGIN_CSRF_COOKIE_NAME: str = "slaif_admin_login_csrf"
    ADMIN_CSRF_TTL_SECONDS: int = 1800
    ADMIN_LOGIN_RATE_LIMIT_ENABLED: bool = True
    ADMIN_LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    ADMIN_LOGIN_WINDOW_SECONDS: int = 900
    ADMIN_LOGIN_LOCKOUT_SECONDS: int = 900
    ENABLE_EMAIL_DELIVERY: bool = False
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = False
    SMTP_STARTTLS: bool = False
    SMTP_TIMEOUT_SECONDS: float = 10
    EMAIL_KEY_SECRET_MAX_AGE_SECONDS: int = 86400
    ENABLE_METRICS: bool = True
    METRICS_REQUIRE_AUTH: bool | None = None
    METRICS_PUBLIC_IN_PRODUCTION: bool = False
    METRICS_ALLOWED_IPS: str | None = None
    READYZ_INCLUDE_DETAILS: bool | None = None
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
            self._validate_production_provider_secrets()
            self._validate_openai_api_key_boundary()

        if self.ONE_TIME_SECRET_ENCRYPTION_KEY:
            self._validate_encryption_key_shape(self.ONE_TIME_SECRET_ENCRYPTION_KEY)

        self._validate_request_caps()
        self._validate_request_id_header()
        self._validate_database_settings()
        self._validate_redis_rate_limit_settings()
        self._validate_admin_session_settings()
        self._validate_email_settings()
        return self

    def _validate_database_settings(self) -> None:
        if self.DATABASE_POOL_SIZE <= 0:
            raise ValueError("DATABASE_POOL_SIZE must be a positive integer")
        if self.DATABASE_MAX_OVERFLOW < 0:
            raise ValueError("DATABASE_MAX_OVERFLOW must be greater than or equal to 0")
        if self.DATABASE_POOL_TIMEOUT_SECONDS <= 0:
            raise ValueError("DATABASE_POOL_TIMEOUT_SECONDS must be a positive number")
        if self.DATABASE_POOL_RECYCLE_SECONDS <= 0:
            raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be a positive integer")
        if self.DATABASE_CONNECT_TIMEOUT_SECONDS <= 0:
            raise ValueError("DATABASE_CONNECT_TIMEOUT_SECONDS must be a positive number")
        if self.DATABASE_STATEMENT_TIMEOUT_MS is not None and self.DATABASE_STATEMENT_TIMEOUT_MS <= 0:
            raise ValueError("DATABASE_STATEMENT_TIMEOUT_MS must be a positive integer when set")

    def _validate_redis_rate_limit_settings(self) -> None:
        if self.ENABLE_REDIS_RATE_LIMITS and not self.REDIS_URL:
            raise ValueError("REDIS_URL is required when ENABLE_REDIS_RATE_LIMITS=true")

        if self.REDIS_CONNECT_TIMEOUT_SECONDS <= 0:
            raise ValueError("REDIS_CONNECT_TIMEOUT_SECONDS must be a positive number")
        if self.REDIS_SOCKET_TIMEOUT_SECONDS <= 0:
            raise ValueError("REDIS_SOCKET_TIMEOUT_SECONDS must be a positive number")

        for name in (
            "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
            "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE",
            "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS",
            "RATE_LIMIT_CONCURRENCY_TTL_SECONDS",
            "RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS",
            "RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS",
        ):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be a positive integer when set")

        if self.RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS >= self.RATE_LIMIT_CONCURRENCY_TTL_SECONDS:
            raise ValueError(
                "RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS must be less than "
                "RATE_LIMIT_CONCURRENCY_TTL_SECONDS"
            )

    def _validate_email_settings(self) -> None:
        if self.SMTP_PORT <= 0:
            raise ValueError("SMTP_PORT must be a positive integer")
        if self.SMTP_TIMEOUT_SECONDS <= 0:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be a positive number")
        if self.EMAIL_KEY_SECRET_MAX_AGE_SECONDS <= 0:
            raise ValueError("EMAIL_KEY_SECRET_MAX_AGE_SECONDS must be a positive integer")
        if self.ENABLE_EMAIL_DELIVERY:
            if not self.SMTP_HOST:
                raise ValueError("SMTP_HOST is required when ENABLE_EMAIL_DELIVERY=true")
            if not self.SMTP_FROM:
                raise ValueError("SMTP_FROM is required when ENABLE_EMAIL_DELIVERY=true")

    def _validate_admin_session_settings(self) -> None:
        if self.ADMIN_SESSION_TTL_SECONDS <= 0:
            raise ValueError("ADMIN_SESSION_TTL_SECONDS must be a positive integer")
        if self.ADMIN_CSRF_TTL_SECONDS <= 0:
            raise ValueError("ADMIN_CSRF_TTL_SECONDS must be a positive integer")
        if self.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS <= 0:
            raise ValueError("ADMIN_LOGIN_MAX_FAILED_ATTEMPTS must be a positive integer")
        if self.ADMIN_LOGIN_WINDOW_SECONDS <= 0:
            raise ValueError("ADMIN_LOGIN_WINDOW_SECONDS must be a positive integer")
        if self.ADMIN_LOGIN_LOCKOUT_SECONDS <= 0:
            raise ValueError("ADMIN_LOGIN_LOCKOUT_SECONDS must be a positive integer")

        if not self.ADMIN_SESSION_COOKIE_NAME.strip():
            raise ValueError("ADMIN_SESSION_COOKIE_NAME cannot be empty")
        if not self.ADMIN_LOGIN_CSRF_COOKIE_NAME.strip():
            raise ValueError("ADMIN_LOGIN_CSRF_COOKIE_NAME cannot be empty")
        self.ADMIN_SESSION_COOKIE_NAME = self.ADMIN_SESSION_COOKIE_NAME.strip()
        self.ADMIN_LOGIN_CSRF_COOKIE_NAME = self.ADMIN_LOGIN_CSRF_COOKIE_NAME.strip()

        same_site = self.ADMIN_SESSION_COOKIE_SAMESITE.strip().lower()
        if same_site not in {"lax", "strict", "none"}:
            raise ValueError("ADMIN_SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
        self.ADMIN_SESSION_COOKIE_SAMESITE = same_site

        if (
            self.APP_ENV.lower() == "production"
            and same_site == "none"
            and self.ADMIN_SESSION_COOKIE_SECURE is False
        ):
            raise ValueError("ADMIN_SESSION_COOKIE_SECURE must be true in production when SameSite=None")

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

        if is_placeholder_secret(value):
            raise ValueError(f"{name} cannot contain placeholder text in production")

        if len(value) < _MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                f"{name} must be at least {_MIN_PRODUCTION_SECRET_LENGTH} characters in production"
            )

    def _validate_production_provider_secrets(self) -> None:
        if self.ENABLE_OPENAI_PROVIDER:
            validate_provider_secret_present(
                "OPENAI_UPSTREAM_API_KEY",
                self.OPENAI_UPSTREAM_API_KEY,
            )
        if self.ENABLE_OPENROUTER_PROVIDER:
            validate_provider_secret_present(
                "OPENROUTER_API_KEY",
                self.OPENROUTER_API_KEY,
            )

    def _validate_openai_api_key_boundary(self) -> None:
        client_key = os.getenv("OPENAI_API_KEY")
        if not client_key:
            return
        if looks_like_real_upstream_openai_key(
            client_key,
            gateway_prefixes=self.get_gateway_key_accepted_prefixes(),
        ):
            raise ValueError(
                "OPENAI_API_KEY is reserved for clients; use OPENAI_UPSTREAM_API_KEY for "
                "the gateway's upstream OpenAI provider key"
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
        if self.APP_ENV.lower() == "production":
            return not self.METRICS_PUBLIC_IN_PRODUCTION
        return False

    def readyz_include_details(self) -> bool:
        """Return whether /readyz should expose detailed revision information."""
        if self.READYZ_INCLUDE_DETAILS is not None:
            return self.READYZ_INCLUDE_DETAILS
        return self.APP_ENV.lower() != "production"

    def get_metrics_allowed_ips(self) -> tuple[str, ...]:
        """Return normalized IP allowlist entries for /metrics."""
        if not self.METRICS_ALLOWED_IPS:
            return ()
        return tuple(item.strip() for item in self.METRICS_ALLOWED_IPS.split(",") if item.strip())

    def rate_limit_fail_closed(self) -> bool:
        """Return Redis rate-limit failure policy for the current environment."""
        if self.RATE_LIMIT_FAIL_CLOSED is not None:
            return self.RATE_LIMIT_FAIL_CLOSED
        return self.APP_ENV.lower() == "production"

    def admin_session_cookie_secure(self) -> bool:
        """Return whether admin session cookies should use Secure."""
        if self.ADMIN_SESSION_COOKIE_SECURE is not None:
            return self.ADMIN_SESSION_COOKIE_SECURE
        return self.APP_ENV.lower() == "production"

    def get_celery_broker_url(self) -> str | None:
        """Return Celery broker URL, defaulting to Redis when configured."""
        return self.CELERY_BROKER_URL or self.REDIS_URL


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def is_placeholder_secret(value: str | None) -> bool:
    """Return whether a configured secret is an obvious placeholder."""
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in {"test", "sk-test"}:
        return True
    if normalized.startswith("sk-test"):
        return True
    return any(placeholder in normalized for placeholder in _PLACEHOLDER_SECRET_SUBSTRINGS)


def validate_provider_secret_present(name: str, value: str | None) -> None:
    """Validate that an enabled production provider has plausible secret material."""
    if value is None or not value.strip():
        raise ValueError(f"{name} is required in production when the provider is enabled")
    if is_placeholder_secret(value):
        raise ValueError(f"{name} cannot contain placeholder text in production")
    if any(ch.isspace() for ch in value.strip()):
        raise ValueError(f"{name} cannot contain whitespace")
    if len(value.strip()) < _MIN_PROVIDER_SECRET_LENGTH:
        raise ValueError(
            f"{name} must be at least {_MIN_PROVIDER_SECRET_LENGTH} characters in production"
        )


def looks_like_real_upstream_openai_key(
    value: str | None,
    *,
    gateway_prefixes: tuple[str, ...] = ("sk-slaif-",),
) -> bool:
    """Conservatively detect likely server-side provider keys in OPENAI_API_KEY."""
    if value is None:
        return False
    normalized = value.strip()
    if not normalized.startswith("sk-"):
        return False
    if is_placeholder_secret(normalized):
        return False
    if len(normalized) < _MIN_PROVIDER_SECRET_LENGTH:
        return False
    return not any(normalized.startswith(prefix) for prefix in gateway_prefixes)
