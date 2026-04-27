"""Domain errors for quota reservation reconciliation."""

from __future__ import annotations


class ReconciliationError(Exception):
    """Base safe reconciliation domain error."""

    status_code = 500
    error_type = "server_error"
    error_code = "reconciliation_error"
    message = "Reservation reconciliation failed"

    def __init__(self, message: str | None = None, *, param: str | None = None) -> None:
        self.safe_message = message or self.message
        self.param = param
        super().__init__(self.safe_message)


class StaleReservationNotFoundError(ReconciliationError):
    """Raised when the requested reservation cannot be found."""

    error_code = "stale_reservation_not_found"
    message = "Quota reservation was not found"


class ReservationNotPendingError(ReconciliationError):
    """Raised when a reconciliation target is no longer pending."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "reservation_not_pending"
    message = "Quota reservation is not pending"


class ReservationNotExpiredError(ReconciliationError):
    """Raised when a pending reservation has not expired yet."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "reservation_not_expired"
    message = "Quota reservation has not expired"


class ReconciliationInvariantError(ReconciliationError):
    """Raised when reconciliation would violate quota/accounting invariants."""

    error_code = "reconciliation_invariant_error"
    message = "Reservation reconciliation invariant violation"


class ProviderCompletedRecoveryNotFoundError(ReconciliationError):
    """Raised when a provider-completed recovery row cannot be found."""

    status_code = 404
    error_type = "invalid_request_error"
    error_code = "provider_completed_recovery_not_found"
    message = "Provider-completed recovery row was not found"


class ProviderCompletedRecoveryNotRepairableError(ReconciliationError):
    """Raised when a recovery row cannot be safely repaired."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "provider_completed_recovery_not_repairable"
    message = "Provider-completed recovery row is not repairable"


class ProviderCompletedRecoveryMetadataMissingError(ReconciliationError):
    """Raised when recovery metadata is insufficient for finalization."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "provider_completed_recovery_metadata_missing"
    message = "Provider-completed recovery metadata is missing"


class ProviderCompletedRecoveryInvariantError(ReconciliationError):
    """Raised when provider-completed repair would violate invariants."""

    error_code = "provider_completed_recovery_invariant_error"
    message = "Provider-completed recovery invariant violation"


class ProviderCompletedRecoveryAlreadyReconciledError(ReconciliationError):
    """Raised when a recovery row has already been reconciled."""

    status_code = 409
    error_type = "invalid_request_error"
    error_code = "provider_completed_recovery_already_reconciled"
    message = "Provider-completed recovery row is already reconciled"
