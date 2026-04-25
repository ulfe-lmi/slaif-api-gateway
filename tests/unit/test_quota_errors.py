from __future__ import annotations

from slaif_gateway.api.quota_errors import openai_error_from_quota_error
from slaif_gateway.services.quota_errors import (
    InvalidQuotaEstimateError,
    QuotaConcurrencyError,
    QuotaLimitExceededError,
    QuotaReservationNotFoundError,
)


def test_quota_limit_exceeded_maps_to_openai_rate_limit_error() -> None:
    error = openai_error_from_quota_error(
        QuotaLimitExceededError("Cost quota limit exceeded", param="cost_limit_eur")
    )

    assert error.status_code == 429
    assert error.error_type == "rate_limit_error"
    assert error.code == "quota_limit_exceeded"
    assert error.param == "cost_limit_eur"


def test_invalid_quota_estimate_maps_to_invalid_request_error() -> None:
    error = openai_error_from_quota_error(InvalidQuotaEstimateError(param="estimated_tokens"))

    assert error.status_code == 400
    assert error.error_type == "invalid_request_error"
    assert error.code == "invalid_quota_estimate"
    assert error.param == "estimated_tokens"


def test_quota_concurrency_error_is_safe_server_error() -> None:
    error = openai_error_from_quota_error(QuotaConcurrencyError())

    assert error.status_code == 409
    assert error.error_type == "server_error"
    assert error.code == "quota_concurrency_error"


def test_missing_reservation_is_internal_server_error() -> None:
    error = openai_error_from_quota_error(QuotaReservationNotFoundError())

    assert error.status_code == 500
    assert error.error_type == "server_error"
    assert error.code == "quota_reservation_not_found"

