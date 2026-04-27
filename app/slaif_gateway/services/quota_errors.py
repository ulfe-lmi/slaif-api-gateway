"""Domain errors for quota reservation workflows."""

from __future__ import annotations


class QuotaError(Exception):
    """Base safe quota domain error."""

    status_code = 500
    error_type = "server_error"
    error_code = "quota_error"
    message = "Quota reservation failed"

    def __init__(self, message: str | None = None, *, param: str | None = None) -> None:
        self.safe_message = message or self.message
        self.param = param
        super().__init__(self.safe_message)


class QuotaLimitExceededError(QuotaError):
    """Raised when a reservation would exceed a configured hard limit."""

    status_code = 429
    error_type = "rate_limit_error"
    error_code = "quota_limit_exceeded"
    message = "Quota limit exceeded"


class QuotaReservationExpiredError(QuotaError):
    """Raised when operating on an expired reservation."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "quota_reservation_expired"
    message = "Quota reservation has expired"


class QuotaReservationNotFoundError(QuotaError):
    """Raised when a reservation row cannot be found."""

    status_code = 500
    error_type = "server_error"
    error_code = "quota_reservation_not_found"
    message = "Quota reservation was not found"


class InvalidQuotaEstimateError(QuotaError):
    """Raised when a caller supplies a negative or otherwise invalid estimate."""

    status_code = 400
    error_type = "invalid_request_error"
    error_code = "invalid_quota_estimate"
    message = "Invalid quota estimate"


class QuotaConcurrencyError(QuotaError):
    """Raised when an atomic quota update cannot be completed."""

    status_code = 409
    error_type = "server_error"
    error_code = "quota_concurrency_error"
    message = "Quota reservation could not be completed due to a concurrent update"


class QuotaCounterInvariantError(QuotaError):
    """Raised when quota counter mutation would violate persisted invariants."""

    status_code = 500
    error_type = "server_error"
    error_code = "quota_counter_invariant_error"
    message = "Quota counter invariant violation"


class KeyNotReservableError(QuotaError):
    """Raised when the current key row state cannot accept reservations."""

    status_code = 403
    error_type = "permission_error"
    error_code = "key_not_reservable"
    message = "Gateway key cannot reserve quota"
