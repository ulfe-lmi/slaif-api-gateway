import pytest
from pydantic import ValidationError

from slaif_gateway.config import get_settings
from slaif_gateway.utils.secrets import generate_secret_key

_VALID_OPENAI_PROVIDER_KEY = "sk-live-openai-provider-aaaaaaaaaaaa"
_VALID_OPENROUTER_PROVIDER_KEY = "sk-or-live-openrouter-aaaaaaaaaaaa"


def _clear_env(monkeypatch) -> None:
    for env_name in (
        "APP_ENV",
        "APP_BASE_URL",
        "PUBLIC_BASE_URL",
        "ACTIVE_HMAC_KEY_VERSION",
        "TOKEN_HMAC_SECRET_V1",
        "TOKEN_HMAC_SECRET",
        "ADMIN_SESSION_SECRET",
        "ONE_TIME_SECRET_ENCRYPTION_KEY",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "ENABLE_REDIS_RATE_LIMITS",
        "REDIS_CONNECT_TIMEOUT_SECONDS",
        "REDIS_SOCKET_TIMEOUT_SECONDS",
        "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
        "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE",
        "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS",
        "RATE_LIMIT_FAIL_CLOSED",
        "RATE_LIMIT_CONCURRENCY_TTL_SECONDS",
        "RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS",
        "RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS",
        "GATEWAY_KEY_PREFIX",
        "GATEWAY_KEY_ACCEPTED_PREFIXES",
        "DEFAULT_MAX_OUTPUT_TOKENS",
        "HARD_MAX_OUTPUT_TOKENS",
        "HARD_MAX_INPUT_TOKENS",
        "ENABLE_METRICS",
        "ENABLE_EMAIL_DELIVERY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_USE_TLS",
        "SMTP_STARTTLS",
        "SMTP_TIMEOUT_SECONDS",
        "EMAIL_KEY_SECRET_MAX_AGE_SECONDS",
        "METRICS_REQUIRE_AUTH",
        "METRICS_ALLOWED_IPS",
        "REQUEST_ID_HEADER",
        "LOG_LEVEL",
        "STRUCTURED_LOGS",
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "DATABASE_POOL_TIMEOUT_SECONDS",
        "DATABASE_POOL_RECYCLE_SECONDS",
        "DATABASE_POOL_PRE_PING",
        "DATABASE_CONNECT_TIMEOUT_SECONDS",
        "DATABASE_STATEMENT_TIMEOUT_MS",
        "READYZ_INCLUDE_DETAILS",
        "METRICS_PUBLIC_IN_PRODUCTION",
        "ENABLE_ADMIN_DASHBOARD",
        "ADMIN_SESSION_COOKIE_NAME",
        "ADMIN_SESSION_COOKIE_SECURE",
        "ADMIN_SESSION_COOKIE_HTTPONLY",
        "ADMIN_SESSION_COOKIE_SAMESITE",
        "ADMIN_SESSION_TTL_SECONDS",
        "ADMIN_LOGIN_CSRF_COOKIE_NAME",
        "ADMIN_CSRF_TTL_SECONDS",
        "ADMIN_LOGIN_RATE_LIMIT_ENABLED",
        "ADMIN_LOGIN_MAX_FAILED_ATTEMPTS",
        "ADMIN_LOGIN_WINDOW_SECONDS",
        "ADMIN_LOGIN_LOCKOUT_SECONDS",
        "OPENAI_API_KEY",
        "OPENAI_UPSTREAM_API_KEY",
        "OPENROUTER_API_KEY",
        "ENABLE_OPENAI_PROVIDER",
        "ENABLE_OPENROUTER_PROVIDER",
    ):
        monkeypatch.delenv(env_name, raising=False)


def _set_required_production_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "h" * 32)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 32)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", _VALID_OPENAI_PROVIDER_KEY)
    monkeypatch.setenv("OPENROUTER_API_KEY", _VALID_OPENROUTER_PROVIDER_KEY)


def test_default_settings_load(monkeypatch) -> None:
    _clear_env(monkeypatch)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "development"
    assert settings.APP_BASE_URL == "http://localhost:8000"
    assert settings.PUBLIC_BASE_URL == "http://localhost:8000/v1"
    assert settings.DATABASE_POOL_SIZE == 5
    assert settings.DATABASE_MAX_OVERFLOW == 10
    assert settings.DATABASE_POOL_TIMEOUT_SECONDS == 30
    assert settings.DATABASE_POOL_RECYCLE_SECONDS == 1800
    assert settings.DATABASE_POOL_PRE_PING is True
    assert settings.DATABASE_CONNECT_TIMEOUT_SECONDS == 10
    assert settings.DATABASE_STATEMENT_TIMEOUT_MS is None
    assert settings.readyz_include_details() is True
    assert settings.ACTIVE_HMAC_KEY_VERSION == "1"
    assert settings.get_gateway_key_prefix() == "sk-slaif-"
    assert settings.get_gateway_key_accepted_prefixes() == ("sk-slaif-",)
    assert settings.DEFAULT_MAX_OUTPUT_TOKENS == 1024
    assert settings.HARD_MAX_OUTPUT_TOKENS == 4096
    assert settings.HARD_MAX_INPUT_TOKENS == 128000
    assert settings.ENABLE_METRICS is True
    assert settings.metrics_require_auth() is False
    assert settings.REQUEST_ID_HEADER == "X-Request-ID"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.STRUCTURED_LOGS is True
    assert settings.ENABLE_REDIS_RATE_LIMITS is False
    assert settings.REDIS_URL is None
    assert settings.CELERY_BROKER_URL is None
    assert settings.CELERY_RESULT_BACKEND is None
    assert settings.get_celery_broker_url() is None
    assert settings.REDIS_CONNECT_TIMEOUT_SECONDS == 2
    assert settings.REDIS_SOCKET_TIMEOUT_SECONDS == 2
    assert settings.DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE is None
    assert settings.DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE is None
    assert settings.DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS is None
    assert settings.RATE_LIMIT_CONCURRENCY_TTL_SECONDS == 300
    assert settings.RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS == 30
    assert settings.RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS == 30
    assert settings.rate_limit_fail_closed() is False
    assert settings.ENABLE_EMAIL_DELIVERY is False
    assert settings.SMTP_HOST is None
    assert settings.SMTP_PORT == 1025
    assert settings.SMTP_FROM is None
    assert settings.SMTP_USE_TLS is False
    assert settings.SMTP_STARTTLS is False
    assert settings.SMTP_TIMEOUT_SECONDS == 10
    assert settings.EMAIL_KEY_SECRET_MAX_AGE_SECONDS == 86400
    assert settings.ENABLE_ADMIN_DASHBOARD is True
    assert settings.ADMIN_SESSION_COOKIE_NAME == "slaif_admin_session"
    assert settings.admin_session_cookie_secure() is False
    assert settings.ADMIN_SESSION_COOKIE_HTTPONLY is True
    assert settings.ADMIN_SESSION_COOKIE_SAMESITE == "lax"
    assert settings.ADMIN_SESSION_TTL_SECONDS == 28800
    assert settings.ADMIN_LOGIN_CSRF_COOKIE_NAME == "slaif_admin_login_csrf"
    assert settings.ADMIN_CSRF_TTL_SECONDS == 1800
    assert settings.ADMIN_LOGIN_RATE_LIMIT_ENABLED is True
    assert settings.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS == 5
    assert settings.ADMIN_LOGIN_WINDOW_SECONDS == 900
    assert settings.ADMIN_LOGIN_LOCKOUT_SECONDS == 900


def test_metrics_require_auth_defaults_to_production(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.metrics_require_auth() is True
    assert settings.rate_limit_fail_closed() is True
    assert settings.readyz_include_details() is False
    assert settings.admin_session_cookie_secure() is True


def test_admin_session_settings_load_from_environment(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_ADMIN_DASHBOARD", "false")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_NAME", "custom_admin")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_HTTPONLY", "false")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SAMESITE", "strict")
    monkeypatch.setenv("ADMIN_SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("ADMIN_LOGIN_CSRF_COOKIE_NAME", "custom_csrf")
    monkeypatch.setenv("ADMIN_CSRF_TTL_SECONDS", "600")
    monkeypatch.setenv("ADMIN_LOGIN_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("ADMIN_LOGIN_MAX_FAILED_ATTEMPTS", "7")
    monkeypatch.setenv("ADMIN_LOGIN_WINDOW_SECONDS", "1200")
    monkeypatch.setenv("ADMIN_LOGIN_LOCKOUT_SECONDS", "1800")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ENABLE_ADMIN_DASHBOARD is False
    assert settings.ADMIN_SESSION_COOKIE_NAME == "custom_admin"
    assert settings.admin_session_cookie_secure() is True
    assert settings.ADMIN_SESSION_COOKIE_HTTPONLY is False
    assert settings.ADMIN_SESSION_COOKIE_SAMESITE == "strict"
    assert settings.ADMIN_SESSION_TTL_SECONDS == 3600
    assert settings.ADMIN_LOGIN_CSRF_COOKIE_NAME == "custom_csrf"
    assert settings.ADMIN_CSRF_TTL_SECONDS == 600
    assert settings.ADMIN_LOGIN_RATE_LIMIT_ENABLED is False
    assert settings.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS == 7
    assert settings.ADMIN_LOGIN_WINDOW_SECONDS == 1200
    assert settings.ADMIN_LOGIN_LOCKOUT_SECONDS == 1800


def test_admin_session_settings_are_validated(monkeypatch) -> None:
    invalid_cases = (
        ("ADMIN_SESSION_TTL_SECONDS", "0", "ADMIN_SESSION_TTL_SECONDS must be a positive integer"),
        ("ADMIN_CSRF_TTL_SECONDS", "-1", "ADMIN_CSRF_TTL_SECONDS must be a positive integer"),
        (
            "ADMIN_LOGIN_MAX_FAILED_ATTEMPTS",
            "0",
            "ADMIN_LOGIN_MAX_FAILED_ATTEMPTS must be a positive integer",
        ),
        ("ADMIN_LOGIN_WINDOW_SECONDS", "0", "ADMIN_LOGIN_WINDOW_SECONDS must be a positive integer"),
        ("ADMIN_LOGIN_LOCKOUT_SECONDS", "-1", "ADMIN_LOGIN_LOCKOUT_SECONDS must be a positive integer"),
        ("ADMIN_SESSION_COOKIE_NAME", " ", "ADMIN_SESSION_COOKIE_NAME cannot be empty"),
        ("ADMIN_LOGIN_CSRF_COOKIE_NAME", " ", "ADMIN_LOGIN_CSRF_COOKIE_NAME cannot be empty"),
        ("ADMIN_SESSION_COOKIE_SAMESITE", "wide", "ADMIN_SESSION_COOKIE_SAMESITE must be one of"),
    )

    for name, value, message in invalid_cases:
        _clear_env(monkeypatch)
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc:
            get_settings()

        assert message in str(exc.value)


def test_production_samesite_none_requires_secure_when_explicitly_disabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    assert "ADMIN_SESSION_COOKIE_SECURE must be true" in str(exc.value)


def test_redis_rate_limits_require_redis_url_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "REDIS_URL is required" in str(exc)


def test_redis_rate_limit_settings_are_validated(monkeypatch) -> None:
    invalid_cases = (
        ("REDIS_CONNECT_TIMEOUT_SECONDS", "0"),
        ("REDIS_SOCKET_TIMEOUT_SECONDS", "-1"),
        ("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", "0"),
        ("DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE", "-5"),
        ("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS", "0"),
        ("RATE_LIMIT_CONCURRENCY_TTL_SECONDS", "0"),
        ("RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS", "0"),
        ("RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS", "-1"),
    )

    for name, value in invalid_cases:
        _clear_env(monkeypatch)
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        try:
            get_settings()
            assert False, f"Expected settings creation to fail for {name}={value}"
        except ValidationError as exc:
            assert "positive" in str(exc)


def test_redis_rate_limit_settings_load_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_REDIS_RATE_LIMITS", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", "30")
    monkeypatch.setenv("DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE", "12000")
    monkeypatch.setenv("DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS", "4")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_TTL_SECONDS", "120")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS", "15")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS", "45")
    monkeypatch.setenv("RATE_LIMIT_FAIL_CLOSED", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ENABLE_REDIS_RATE_LIMITS is True
    assert settings.REDIS_URL == "redis://localhost:6379/2"
    assert settings.DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE == 30
    assert settings.DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE == 12000
    assert settings.DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS == 4
    assert settings.RATE_LIMIT_CONCURRENCY_TTL_SECONDS == 120
    assert settings.RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS == 15
    assert settings.RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS == 45
    assert settings.rate_limit_fail_closed() is True


def test_celery_broker_defaults_to_redis_url(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/3")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.get_celery_broker_url() == "redis://localhost:6379/3"


def test_celery_broker_can_be_overridden(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/3")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/4")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/5")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.get_celery_broker_url() == "redis://localhost:6379/4"
    assert settings.CELERY_RESULT_BACKEND == "redis://localhost:6379/5"


def test_email_delivery_requires_smtp_host_and_from_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_EMAIL_DELIVERY", "true")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    assert "SMTP_HOST is required" in str(exc.value)

    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_EMAIL_DELIVERY", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    assert "SMTP_FROM is required" in str(exc.value)


def test_email_settings_load_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENABLE_EMAIL_DELIVERY", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_PORT", "1026")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.org")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("EMAIL_KEY_SECRET_MAX_AGE_SECONDS", "3600")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ENABLE_EMAIL_DELIVERY is True
    assert settings.SMTP_HOST == "localhost"
    assert settings.SMTP_PORT == 1026
    assert settings.SMTP_USERNAME == "mailer"
    assert settings.SMTP_PASSWORD == "smtp-secret"
    assert settings.SMTP_FROM == "noreply@example.org"
    assert settings.SMTP_STARTTLS is True
    assert settings.SMTP_TIMEOUT_SECONDS == 3.5
    assert settings.EMAIL_KEY_SECRET_MAX_AGE_SECONDS == 3600


def test_email_settings_validate_positive_numbers(monkeypatch) -> None:
    invalid_cases = (
        ("SMTP_PORT", "0", "SMTP_PORT must be a positive integer"),
        ("SMTP_TIMEOUT_SECONDS", "0", "SMTP_TIMEOUT_SECONDS must be a positive number"),
        (
            "EMAIL_KEY_SECRET_MAX_AGE_SECONDS",
            "0",
            "EMAIL_KEY_SECRET_MAX_AGE_SECONDS must be a positive integer",
        ),
    )

    for name, value, message in invalid_cases:
        _clear_env(monkeypatch)
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc:
            get_settings()

        assert message in str(exc.value)


def test_redis_rate_limit_heartbeat_must_be_less_than_ttl(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_TTL_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS", "30")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    assert "HEARTBEAT_SECONDS must be less than RATE_LIMIT_CONCURRENCY_TTL_SECONDS" in str(exc.value)


def test_metrics_auth_can_be_explicitly_disabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("METRICS_REQUIRE_AUTH", "false")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.metrics_require_auth() is False
    assert settings.get_metrics_allowed_ips() == ()


def test_metrics_public_in_production_can_be_explicitly_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("METRICS_PUBLIC_IN_PRODUCTION", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.metrics_require_auth() is False


def test_readyz_include_details_can_be_explicitly_enabled_in_production(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("READYZ_INCLUDE_DETAILS", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.readyz_include_details() is True


def test_database_pool_settings_are_validated(monkeypatch) -> None:
    invalid_cases = (
        ("DATABASE_POOL_SIZE", "0", "positive"),
        ("DATABASE_MAX_OVERFLOW", "-1", "greater than or equal to 0"),
        ("DATABASE_POOL_TIMEOUT_SECONDS", "0", "positive"),
        ("DATABASE_POOL_RECYCLE_SECONDS", "-5", "positive"),
        ("DATABASE_CONNECT_TIMEOUT_SECONDS", "0", "positive"),
        ("DATABASE_STATEMENT_TIMEOUT_MS", "-1", "positive"),
    )

    for name, value, message in invalid_cases:
        _clear_env(monkeypatch)
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc:
            get_settings()

        assert message in str(exc.value)


def test_database_pool_settings_load_from_environment(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("DATABASE_POOL_SIZE", "7")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("DATABASE_POOL_RECYCLE_SECONDS", "600")
    monkeypatch.setenv("DATABASE_POOL_PRE_PING", "false")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("DATABASE_STATEMENT_TIMEOUT_MS", "25000")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.DATABASE_POOL_SIZE == 7
    assert settings.DATABASE_MAX_OVERFLOW == 3
    assert settings.DATABASE_POOL_TIMEOUT_SECONDS == 12.5
    assert settings.DATABASE_POOL_RECYCLE_SECONDS == 600
    assert settings.DATABASE_POOL_PRE_PING is False
    assert settings.DATABASE_CONNECT_TIMEOUT_SECONDS == 4.5
    assert settings.DATABASE_STATEMENT_TIMEOUT_MS == 25000


def test_metrics_allowed_ips_are_normalized(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("METRICS_ALLOWED_IPS", "127.0.0.1, 10.0.0.5 ")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.get_metrics_allowed_ips() == ("127.0.0.1", "10.0.0.5")


def test_default_output_tokens_must_not_exceed_hard_max(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_MAX_OUTPUT_TOKENS", "4097")
    monkeypatch.setenv("HARD_MAX_OUTPUT_TOKENS", "4096")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "DEFAULT_MAX_OUTPUT_TOKENS must be <= HARD_MAX_OUTPUT_TOKENS" in str(exc)


def test_invalid_zero_or_negative_caps_fail(monkeypatch) -> None:
    invalid_cases = (
        ("DEFAULT_MAX_OUTPUT_TOKENS", "0"),
        ("DEFAULT_MAX_OUTPUT_TOKENS", "-1"),
        ("HARD_MAX_OUTPUT_TOKENS", "0"),
        ("HARD_MAX_OUTPUT_TOKENS", "-1"),
        ("HARD_MAX_INPUT_TOKENS", "0"),
        ("HARD_MAX_INPUT_TOKENS", "-1"),
    )

    for name, value in invalid_cases:
        _clear_env(monkeypatch)
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        try:
            get_settings()
            assert False, f"Expected settings creation to fail for {name}={value}"
        except ValidationError as exc:
            assert "positive integer" in str(exc)


def test_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://example.test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_BASE_URL == "https://example.test"


def test_custom_gateway_prefix_and_accepted_prefixes(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-classroom-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-classroom-,sk-slaif-")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.get_gateway_key_prefix() == "sk-classroom-"
    assert settings.get_gateway_key_accepted_prefixes() == ("sk-classroom-", "sk-slaif-")



def test_accepted_prefixes_must_include_active_prefix(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-ulfe-")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "must include" in str(exc)



def test_invalid_prefixes_fail_validation(monkeypatch) -> None:
    invalid_prefixes = ("prefix-", "sk-slaif", "sk.slaif-", "sk bad-", "sk/slaif-", "")

    for invalid in invalid_prefixes:
        monkeypatch.setenv("GATEWAY_KEY_PREFIX", invalid)
        get_settings.cache_clear()
        try:
            get_settings()
            assert False, f"Expected settings creation to fail for {invalid!r}"
        except ValidationError:
            pass



def test_non_production_can_use_legacy_token_hmac_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "h" * 32)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.get_hmac_secret("1") == "h" * 32
    assert settings.get_active_hmac_secret() == ("1", "h" * 32)



def test_production_placeholder_secret_fails(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "change-me-please-aaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "this-secret-is-strong-enough-but-has-change-me")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "placeholder" in str(exc)



def test_production_short_secret_fails(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "short")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "also-short")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "at least 32 characters" in str(exc)



def test_production_requires_one_time_secret_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "t" * 32)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 40)
    monkeypatch.delenv("ONE_TIME_SECRET_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "ONE_TIME_SECRET_ENCRYPTION_KEY is required" in str(exc)



def test_one_time_secret_key_shape_is_validated_when_set(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", "not-base64")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "ONE_TIME_SECRET_ENCRYPTION_KEY" in str(exc)



def test_production_requires_versioned_hmac_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "h" * 40)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 40)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "TOKEN_HMAC_SECRET_V1" in str(exc)



def test_production_strong_secrets_succeed(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "t" * 32)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 40)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "production"
    assert settings.get_active_hmac_secret() == ("1", "t" * 32)
    assert len(settings.ADMIN_SESSION_SECRET or "") >= 32


def test_production_requires_openai_provider_secret_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    message = str(exc.value)
    assert "OPENAI_UPSTREAM_API_KEY is required" in message


def test_production_rejects_placeholder_openai_provider_secret(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", "sk-test")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    message = str(exc.value)
    assert "OPENAI_UPSTREAM_API_KEY" in message
    assert "placeholder" in message
    assert "sk-test" not in message


def test_production_requires_openrouter_provider_secret_when_enabled(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    assert "OPENROUTER_API_KEY is required" in str(exc.value)


def test_production_rejects_placeholder_openrouter_provider_secret(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder-openrouter-secret")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    message = str(exc.value)
    assert "OPENROUTER_API_KEY" in message
    assert "placeholder" in message
    assert "placeholder-openrouter-secret" not in message


def test_production_disabled_provider_does_not_require_secret(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("ENABLE_OPENAI_PROVIDER", "false")
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ENABLE_OPENAI_PROVIDER is False
    assert settings.OPENAI_UPSTREAM_API_KEY is None


def test_non_production_does_not_require_provider_secrets(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.OPENAI_UPSTREAM_API_KEY is None
    assert settings.OPENROUTER_API_KEY is None


def test_production_rejects_server_side_openai_api_key_misuse(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-provider-value-aaaaaaaa")
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc:
        get_settings()

    message = str(exc.value)
    assert "OPENAI_API_KEY is reserved for clients" in message
    assert "OPENAI_UPSTREAM_API_KEY" in message
    assert "sk-real-provider-value" not in message


def test_production_allows_gateway_key_in_openai_api_key_boundary(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-slaif-public.secret")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "production"
