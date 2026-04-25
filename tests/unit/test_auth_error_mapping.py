from __future__ import annotations

from slaif_gateway.api.auth_errors import openai_error_from_auth_error
from slaif_gateway.api.errors import openai_error_response
from slaif_gateway.services.auth_service import (
    GatewayKeyDigestMismatchError,
    GatewayKeyExpiredError,
    GatewayKeyRevokedError,
    GatewayKeySuspendedError,
    MissingTokenHmacSecretError,
)


def test_auth_error_mapping_produces_openai_error_shape() -> None:
    exc = openai_error_from_auth_error(GatewayKeyDigestMismatchError())
    response = openai_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.code,
    )

    assert response.status_code == 401
    body = response.body.decode("utf-8")
    assert '"error"' in body
    assert "gateway_key_invalid_digest" in body


def test_auth_error_mapping_status_and_type_by_domain_exception() -> None:
    suspended = openai_error_from_auth_error(GatewayKeySuspendedError())
    revoked = openai_error_from_auth_error(GatewayKeyRevokedError())
    expired = openai_error_from_auth_error(GatewayKeyExpiredError())
    misconfigured = openai_error_from_auth_error(MissingTokenHmacSecretError())

    assert suspended.status_code == 403
    assert suspended.error_type == "permission_error"
    assert revoked.status_code == 403
    assert expired.status_code == 401
    assert misconfigured.status_code == 500


def test_auth_error_mapping_never_contains_plaintext_or_hash_material() -> None:
    exc = openai_error_from_auth_error(GatewayKeyDigestMismatchError())
    response = openai_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.code,
    )

    payload = response.body.decode("utf-8")
    assert "sk-slaif-" not in payload
    assert "token_hash" not in payload
