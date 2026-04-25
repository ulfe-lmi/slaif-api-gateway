from __future__ import annotations

from slaif_gateway.api.accounting_errors import openai_error_from_accounting_error
from slaif_gateway.services.accounting_errors import InvalidUsageError, UsageMissingError


def test_accounting_error_maps_to_openai_compatible_error() -> None:
    error = openai_error_from_accounting_error(UsageMissingError(param="usage"))

    assert error.status_code == 502
    assert error.error_type == "server_error"
    assert error.code == "usage_missing"
    assert error.param == "usage"


def test_accounting_errors_carry_safe_metadata_only() -> None:
    error = InvalidUsageError("Provider usage token counts must be non-negative", param="total_tokens")

    assert error.safe_message == "Provider usage token counts must be non-negative"
    assert error.error_code == "invalid_usage"
    assert error.param == "total_tokens"
