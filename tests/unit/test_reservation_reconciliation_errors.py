from __future__ import annotations

from slaif_gateway.services.reconciliation_errors import (
    ReconciliationInvariantError,
    ReservationNotExpiredError,
    ReservationNotPendingError,
    StaleReservationNotFoundError,
)


def test_reconciliation_errors_expose_safe_metadata() -> None:
    errors = [
        StaleReservationNotFoundError(),
        ReservationNotPendingError(),
        ReservationNotExpiredError(),
        ReconciliationInvariantError(param="cost_reserved_eur"),
    ]

    for error in errors:
        assert error.safe_message
        assert error.error_code
        assert "secret" not in error.safe_message.lower()
        assert "token_hash" not in error.safe_message.lower()


def test_reconciliation_invariant_error_keeps_param() -> None:
    error = ReconciliationInvariantError("Reserved cost counter is invalid", param="cost_reserved_eur")

    assert error.status_code == 500
    assert error.error_type == "server_error"
    assert error.error_code == "reconciliation_invariant_error"
    assert error.param == "cost_reserved_eur"
