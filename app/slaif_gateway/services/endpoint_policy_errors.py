"""Domain errors for endpoint allow-list enforcement."""

from __future__ import annotations


class EndpointPolicyError(Exception):
    """Base domain error for safe endpoint policy failures."""

    status_code = 403
    error_type = "permission_error"
    error_code = "endpoint_not_allowed"
    message = "The requested endpoint is not allowed for this key"

    def __init__(self, message: str | None = None) -> None:
        self.safe_message = message or self.message
        super().__init__(self.safe_message)


class EndpointNotAllowedError(EndpointPolicyError):
    """Raised when an authenticated key is not allowed to call an endpoint."""

