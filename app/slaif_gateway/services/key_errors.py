"""Safe domain errors for gateway key management operations."""

from __future__ import annotations


class KeyManagementError(Exception):
    """Base domain error for administrative gateway-key management failures."""

    status_code = 400
    error_type = "invalid_request_error"
    error_code = "key_management_error"
    message = "Gateway key management operation failed"
    param: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        param: str | None = None,
    ) -> None:
        self.safe_message = message or self.message
        self.param = param if param is not None else self.param
        super().__init__(self.safe_message)


class GatewayKeyNotFoundError(KeyManagementError):
    status_code = 404
    error_code = "gateway_key_not_found"
    message = "Gateway key not found"


class GatewayKeyAlreadyRevokedError(KeyManagementError):
    status_code = 409
    error_code = "gateway_key_already_revoked"
    message = "Gateway key is already revoked"


class GatewayKeyAlreadySuspendedError(KeyManagementError):
    status_code = 409
    error_code = "gateway_key_already_suspended"
    message = "Gateway key is already suspended"


class GatewayKeyAlreadyActiveError(KeyManagementError):
    status_code = 409
    error_code = "gateway_key_already_active"
    message = "Gateway key is already active"


class InvalidGatewayKeyStatusTransitionError(KeyManagementError):
    status_code = 409
    error_code = "invalid_gateway_key_status_transition"
    message = "Invalid gateway key status transition"


class InvalidGatewayKeyValidityError(KeyManagementError):
    error_code = "invalid_gateway_key_validity"
    message = "Invalid gateway key validity window"
    param = "valid_until"


class InvalidGatewayKeyLimitsError(KeyManagementError):
    error_code = "invalid_gateway_key_limits"
    message = "Invalid gateway key limits"


class InvalidGatewayKeyUsageResetError(KeyManagementError):
    error_code = "invalid_gateway_key_usage_reset"
    message = "Invalid gateway key usage reset"


class GatewayKeyRotationError(KeyManagementError):
    error_code = "gateway_key_rotation_failed"
    message = "Gateway key rotation failed"
