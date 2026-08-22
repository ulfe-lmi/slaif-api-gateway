"""Tests for the OIDC service."""

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.oidc_service import OidcAuthService, OidcError



@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "test-secret-for-testing-only")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", "_E3NCz0SPQ3kF_xeyiicBfO5-bV6lZ0Svm72w9gSq7Q=")
    return Settings(
        OIDC_ENABLED=True,
        OIDC_ISSUER_URL="https://idp.example.com/realms/test",
        OIDC_CLIENT_ID="slaif-gateway",
        OIDC_CLIENT_SECRET="test-secret",
        OIDC_REDIRECT_URI="http://localhost:8000/admin/auth/oidc/callback",
    )


@pytest.fixture
def service(settings):
    return OidcAuthService(settings=settings)


def test_pkce_pair_generation(service):
    verifier, challenge = service.generate_pkce_pair()
    assert len(verifier) > 40
    assert len(challenge) > 20
    assert verifier != challenge


def test_state_generation_is_unique(service):
    state_1 = service.generate_state()
    state_2 = service.generate_state()
    assert state_1 != state_2


def test_authorization_url_contains_required_params(service):
    url = service.build_authorization_url(
        authorization_endpoint="https://idp.example.com/authorize",
        state="test-state",
        nonce="test-nonce",
        code_challenge="test-challenge",
    )
    assert "response_type=code" in url
    assert "client_id=slaif-gateway" in url
    assert "code_challenge_method=S256" in url
    assert "state=test-state" in url


def test_oidc_not_enabled_raises(monkeypatch):
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "test-secret-for-testing-only")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", "_E3NCz0SPQ3kF_xeyiicBfO5-bV6lZ0Svm72w9gSq7Q=")
    settings = Settings(OIDC_ENABLED=False)
    service = OidcAuthService(settings=settings)
    with pytest.raises(OidcError, match="not enabled"):
        service._require_enabled()



def test_disabled_service_rejects_discovery(monkeypatch):
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", "test-secret-for-testing-only")
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", "_E3NCz0SPQ3kF_xeyiicBfO5-bV6lZ0Svm72w9gSq7Q=")
    settings = Settings(OIDC_ENABLED=False)
    service = OidcAuthService(settings=settings)
    with pytest.raises(OidcError, match="not enabled"):
        import asyncio
        asyncio.run(service.get_discovery())
