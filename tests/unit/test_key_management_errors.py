from __future__ import annotations

from slaif_gateway.api.errors import openai_error_response
from slaif_gateway.api.key_errors import openai_error_from_key_management_error
from slaif_gateway.services.key_errors import (
    GatewayKeyAlreadyRevokedError,
    GatewayKeyNotFoundError,
    GatewayKeyRotationError,
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyValidityError,
)


def test_key_management_errors_carry_safe_metadata() -> None:
    not_found = GatewayKeyNotFoundError()
    already_revoked = GatewayKeyAlreadyRevokedError()
    invalid_limits = InvalidGatewayKeyLimitsError("cost_limit_eur must be positive", param="cost_limit_eur")
    rotation = GatewayKeyRotationError()

    assert not_found.status_code == 404
    assert not_found.error_type == "invalid_request_error"
    assert not_found.error_code == "gateway_key_not_found"
    assert already_revoked.status_code == 409
    assert invalid_limits.param == "cost_limit_eur"
    assert rotation.error_code == "gateway_key_rotation_failed"


def test_key_management_error_mapping_produces_openai_shape() -> None:
    exc = openai_error_from_key_management_error(
        InvalidGatewayKeyValidityError("valid_until must be after valid_from", param="valid_until")
    )
    response = openai_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.code,
        param=exc.param,
    )

    assert response.status_code == 400
    body = response.body.decode("utf-8")
    assert '"error"' in body
    assert "invalid_gateway_key_validity" in body
    assert "valid_until" in body


def test_key_management_errors_do_not_expose_secret_material() -> None:
    exc = openai_error_from_key_management_error(GatewayKeyNotFoundError())
    response = openai_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.code,
        param=exc.param,
    )

    payload = response.body.decode("utf-8")
    assert "sk-slaif-" not in payload
    assert "token_hash" not in payload
    assert "encrypted_payload" not in payload
    assert "nonce" not in payload
