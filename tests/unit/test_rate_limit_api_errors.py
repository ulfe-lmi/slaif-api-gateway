from __future__ import annotations

from slaif_gateway.api.rate_limit_errors import openai_error_from_rate_limit_error
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    InvalidRateLimitPolicyError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)


def test_rate_limit_exceeded_errors_map_to_openai_429() -> None:
    for exc in (
        RequestRateLimitExceededError(retry_after_seconds=60),
        TokenRateLimitExceededError(retry_after_seconds=60),
        ConcurrencyRateLimitExceededError(retry_after_seconds=60),
    ):
        error = openai_error_from_rate_limit_error(exc)

        assert error.status_code == 429
        assert error.error_type == "rate_limit_error"
        assert error.code == exc.error_code


def test_redis_unavailable_maps_to_server_error() -> None:
    error = openai_error_from_rate_limit_error(RedisRateLimitUnavailableError())

    assert error.status_code == 503
    assert error.error_type == "server_error"
    assert error.code == "redis_rate_limit_unavailable"


def test_invalid_rate_limit_policy_maps_to_safe_error() -> None:
    error = openai_error_from_rate_limit_error(
        InvalidRateLimitPolicyError("Invalid rate limit policy", param="rate_limit")
    )

    assert error.status_code == 400
    assert error.error_type == "invalid_request_error"
    assert error.param == "rate_limit"
