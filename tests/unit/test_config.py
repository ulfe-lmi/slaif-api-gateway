from pydantic import ValidationError

from slaif_gateway.config import get_settings


def test_default_settings_load(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "development"
    assert settings.APP_BASE_URL == "http://localhost:8000"
    assert settings.PUBLIC_BASE_URL == "http://localhost:8000/v1"


def test_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://example.test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_BASE_URL == "https://example.test"


def test_production_placeholder_secret_fails(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "change-me-please-aaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "this-secret-is-strong-enough-but-has-change-me")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "placeholder" in str(exc)


def test_production_short_secret_fails(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "short")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "also-short")
    get_settings.cache_clear()

    try:
        get_settings()
        assert False, "Expected settings creation to fail"
    except ValidationError as exc:
        assert "at least 32 characters" in str(exc)


def test_production_strong_secrets_succeed(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TOKEN_HMAC_SECRET", "t" * 32)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 40)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.APP_ENV == "production"
    assert len(settings.TOKEN_HMAC_SECRET or "") >= 32
    assert len(settings.ADMIN_SESSION_SECRET or "") >= 32
