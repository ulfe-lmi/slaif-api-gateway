from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.auth.csrf import CsrfError, create_login_csrf_token, verify_login_csrf_token
from slaif_gateway.config import Settings


def _settings() -> Settings:
    return Settings(APP_ENV="test", ADMIN_SESSION_SECRET="s" * 40, ADMIN_CSRF_TTL_SECONDS=60)


def test_login_csrf_token_generation_and_validation() -> None:
    settings = _settings()
    token = create_login_csrf_token(settings, now=datetime(2026, 1, 1, tzinfo=UTC))

    verify_login_csrf_token(
        settings,
        form_token=token,
        cookie_token=token,
        now=datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC),
    )


def test_login_csrf_missing_token_fails() -> None:
    with pytest.raises(CsrfError):
        verify_login_csrf_token(_settings(), form_token=None, cookie_token=None)


def test_login_csrf_mismatched_cookie_fails() -> None:
    token = create_login_csrf_token(_settings())

    with pytest.raises(CsrfError):
        verify_login_csrf_token(_settings(), form_token=token, cookie_token=f"{token}x")


def test_login_csrf_tampered_token_fails() -> None:
    token = create_login_csrf_token(_settings())
    tampered = f"{token[:-1]}x"

    with pytest.raises(CsrfError):
        verify_login_csrf_token(_settings(), form_token=tampered, cookie_token=tampered)


def test_login_csrf_expired_token_fails() -> None:
    settings = _settings()
    issued_at = datetime(2026, 1, 1, tzinfo=UTC)
    token = create_login_csrf_token(settings, now=issued_at)

    with pytest.raises(CsrfError):
        verify_login_csrf_token(
            settings,
            form_token=token,
            cookie_token=token,
            now=issued_at + timedelta(seconds=61),
        )


def test_login_csrf_token_does_not_expose_admin_secret() -> None:
    settings = _settings()
    token = create_login_csrf_token(settings)

    assert settings.ADMIN_SESSION_SECRET not in token
