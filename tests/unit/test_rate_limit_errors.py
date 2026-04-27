from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    InvalidRateLimitPolicyError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)


def test_rate_limit_errors_expose_safe_metadata() -> None:
    errors = (
        RedisRateLimitUnavailableError(),
        RequestRateLimitExceededError(retry_after_seconds=60),
        TokenRateLimitExceededError(retry_after_seconds=60),
        ConcurrencyRateLimitExceededError(retry_after_seconds=60),
        InvalidRateLimitPolicyError(param="policy"),
    )

    for error in errors:
        assert error.safe_message
        assert error.error_code
        assert error.error_type in {"server_error", "rate_limit_error", "invalid_request_error"}
        assert "redis://" not in error.safe_message
        assert "sk-" not in error.safe_message
