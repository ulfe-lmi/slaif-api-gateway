"""Domain errors for usage accounting workflows."""

from __future__ import annotations


class AccountingError(Exception):
    """Base safe accounting domain error."""

    status_code = 500
    error_type = "server_error"
    error_code = "accounting_error"
    message = "Accounting failed"

    def __init__(self, message: str | None = None, *, param: str | None = None) -> None:
        self.safe_message = message or self.message
        self.param = param
        super().__init__(self.safe_message)


class UsageMissingError(AccountingError):
    status_code = 502
    error_code = "usage_missing"
    message = "Provider response did not include required usage metadata"


class InvalidUsageError(AccountingError):
    status_code = 502
    error_code = "invalid_usage"
    message = "Provider response included invalid usage metadata"


class ReservationFinalizationError(AccountingError):
    status_code = 409
    error_code = "reservation_finalization_error"
    message = "Quota reservation could not be finalized"


class ReservationAlreadyFinalizedError(ReservationFinalizationError):
    error_code = "reservation_already_finalized"
    message = "Quota reservation is not pending"


class LedgerWriteError(AccountingError):
    status_code = 500
    error_code = "ledger_write_error"
    message = "Usage ledger record could not be written"


class ActualCostExceededReservationError(ReservationFinalizationError):
    error_code = "actual_cost_exceeded_reservation"
    message = "Actual usage exceeded the quota reservation"


class UnsupportedProviderCostError(AccountingError):
    status_code = 502
    error_code = "unsupported_provider_cost"
    message = "Actual cost could not be computed from configured pricing"
