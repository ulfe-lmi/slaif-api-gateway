from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.rate_limit_policy import build_rate_limit_policy


def _auth(policy: dict[str, int | None] | None = None) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=Decimal("1.0"),
        token_limit_total=1000,
        request_limit_total=100,
        rate_limit_policy=policy or {},
    )


def test_key_rate_limit_policy_overrides_global_defaults() -> None:
    policy = build_rate_limit_policy(
        authenticated_key=_auth(
            {
                "requests_per_minute": 3,
                "tokens_per_minute": 30,
                "max_concurrent_requests": 2,
            }
        ),
        settings=Settings(
            DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=10,
            DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=100,
            DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS=5,
        ),
    )

    assert policy.requests_per_minute == 3
    assert policy.tokens_per_minute == 30
    assert policy.concurrent_requests == 2


def test_global_defaults_apply_when_key_policy_is_unset() -> None:
    policy = build_rate_limit_policy(
        authenticated_key=_auth(
            {
                "requests_per_minute": None,
                "tokens_per_minute": None,
                "max_concurrent_requests": None,
            }
        ),
        settings=Settings(
            DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=10,
            DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=100,
            DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS=5,
        ),
    )

    assert policy.requests_per_minute == 10
    assert policy.tokens_per_minute == 100
    assert policy.concurrent_requests == 5


def test_no_policy_values_means_no_redis_limit() -> None:
    policy = build_rate_limit_policy(authenticated_key=_auth(), settings=Settings())

    assert policy.has_limits() is False


def test_concurrent_requests_alias_is_supported() -> None:
    policy = build_rate_limit_policy(
        authenticated_key=_auth({"concurrent_requests": 4}),
        settings=Settings(DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS=9),
    )

    assert policy.concurrent_requests == 4
