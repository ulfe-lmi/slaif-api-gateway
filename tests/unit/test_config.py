from pydantic import ValidationError

from slaif_gateway.config import get_settings
from slaif_gateway.utils.secrets import generate_secret_key


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
        "GATEWAY_KEY_PREFIX",
        "GATEWAY_KEY_ACCEPTED_PREFIXES",
        "DEFAULT_MAX_OUTPUT_TOKENS",
        "HARD_MAX_OUTPUT_TOKENS",
        "HARD_MAX_INPUT_TOKENS",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_default_settings_load(monkeypatch) -> None:
    _clear_env(monkeypatch)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "development"
    assert settings.APP_BASE_URL == "http://localhost:8000"
    assert settings.PUBLIC_BASE_URL == "http://localhost:8000/v1"
    assert settings.ACTIVE_HMAC_KEY_VERSION == "1"
    assert settings.get_gateway_key_prefix() == "sk-slaif-"
    assert settings.get_gateway_key_accepted_prefixes() == ("sk-slaif-",)
    assert settings.DEFAULT_MAX_OUTPUT_TOKENS == 1024
    assert settings.HARD_MAX_OUTPUT_TOKENS == 4096
    assert settings.HARD_MAX_INPUT_TOKENS == 128000


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
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "t" * 32)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 40)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "production"
    assert settings.get_active_hmac_secret() == ("1", "t" * 32)
    assert len(settings.ADMIN_SESSION_SECRET or "") >= 32
