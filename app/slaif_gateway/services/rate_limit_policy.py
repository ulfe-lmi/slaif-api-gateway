"""Policy construction for Redis-backed operational rate limits."""

from __future__ import annotations

from slaif_gateway.config import Settings
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.rate_limits import LazyThrottlingPolicy, RateLimitPolicy


def effective_lazy_throttling_policy(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
) -> LazyThrottlingPolicy:
    """Return the effective per-key lazy-throttling policy.

    A missing or malformed stored policy is always the immediate-reject
    default; wait mode is never inferred from anything other than an
    explicitly validated stored policy.
    """
    if authenticated_key.lazy_throttling is not None:
        return authenticated_key.lazy_throttling
    return LazyThrottlingPolicy(mode="reject")


def build_rate_limit_policy(
    *,
    authenticated_key: AuthenticatedGatewayKey,
    settings: Settings,
) -> RateLimitPolicy:
    """Build the effective Redis rate-limit policy for an authenticated key."""
    key_policy = authenticated_key.rate_limit_policy or {}
    return RateLimitPolicy(
        requests_per_minute=_first_configured(
            key_policy.get("requests_per_minute"),
            settings.DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE,
        ),
        tokens_per_minute=_first_configured(
            key_policy.get("tokens_per_minute"),
            settings.DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE,
        ),
        concurrent_requests=_first_configured(
            key_policy.get("max_concurrent_requests"),
            key_policy.get("concurrent_requests"),
            settings.DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS,
        ),
        window_seconds=_first_configured(key_policy.get("window_seconds"), 60) or 60,
        concurrency_ttl_seconds=settings.RATE_LIMIT_CONCURRENCY_TTL_SECONDS,
        concurrency_heartbeat_seconds=settings.RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS,
        concurrency_ttl_grace_seconds=settings.RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS,
    )


def _first_configured(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None
