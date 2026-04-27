"""Domain errors for Redis-backed operational rate limiting."""

from __future__ import annotations


class RateLimitError(Exception):
    """Base safe rate-limit domain error."""

    status_code = 500
    error_type = "server_error"
    error_code = "rate_limit_error"
    message = "Rate limit check failed"
    retry_after_seconds: int | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
        param: str | None = None,
    ) -> None:
        self.safe_message = message or self.message
        self.retry_after_seconds = retry_after_seconds
        self.param = param
        super().__init__(self.safe_message)


class RedisRateLimitUnavailableError(RateLimitError):
    """Raised when Redis is unavailable and fail-closed mode is active."""

    status_code = 503
    error_type = "server_error"
    error_code = "redis_rate_limit_unavailable"
    message = "Rate limit service is unavailable"


class RequestRateLimitExceededError(RateLimitError):
    """Raised when the per-window request limit is exceeded."""

    status_code = 429
    error_type = "rate_limit_error"
    error_code = "request_rate_limit_exceeded"
    message = "Request rate limit exceeded"


class TokenRateLimitExceededError(RateLimitError):
    """Raised when the per-window token limit is exceeded."""

    status_code = 429
    error_type = "rate_limit_error"
    error_code = "token_rate_limit_exceeded"
    message = "Token rate limit exceeded"


class ConcurrencyRateLimitExceededError(RateLimitError):
    """Raised when the concurrent request limit is exceeded."""

    status_code = 429
    error_type = "rate_limit_error"
    error_code = "concurrency_rate_limit_exceeded"
    message = "Concurrent request limit exceeded"


class InvalidRateLimitPolicyError(RateLimitError):
    """Raised when a caller supplies an invalid rate-limit policy."""

    status_code = 400
    error_type = "invalid_request_error"
    error_code = "invalid_rate_limit_policy"
    message = "Invalid rate limit policy"


class RateLimitReleaseError(RateLimitError):
    """Raised when releasing a concurrency reservation fails."""

    status_code = 500
    error_type = "server_error"
    error_code = "rate_limit_release_failed"
    message = "Rate limit reservation could not be released"
