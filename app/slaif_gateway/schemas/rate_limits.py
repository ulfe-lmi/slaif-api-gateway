"""Safe schemas for Redis-backed operational rate limiting."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RateLimitPolicy(BaseModel):
    """Per-key temporary rate-limit policy."""

    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    concurrent_requests: int | None = None
    window_seconds: int = 60
    concurrency_ttl_seconds: int | None = None
    concurrency_heartbeat_seconds: int | None = None
    concurrency_ttl_grace_seconds: int | None = None

    @field_validator(
        "requests_per_minute",
        "tokens_per_minute",
        "concurrent_requests",
    )
    @classmethod
    def _optional_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("rate-limit values must be positive when set")
        return value

    @field_validator("window_seconds")
    @classmethod
    def _window_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("window_seconds must be positive")
        return value

    @field_validator(
        "concurrency_ttl_seconds",
        "concurrency_heartbeat_seconds",
        "concurrency_ttl_grace_seconds",
    )
    @classmethod
    def _optional_concurrency_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("concurrency timing values must be positive when set")
        return value

    def has_limits(self) -> bool:
        """Return whether the policy enforces any Redis-backed limit."""
        return any(
            value is not None
            for value in (
                self.requests_per_minute,
                self.tokens_per_minute,
                self.concurrent_requests,
            )
        )


class RateLimitRequest(BaseModel):
    """Input payload for a Redis rate-limit reservation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gateway_key_id: uuid.UUID
    request_id: str = Field(min_length=1)
    estimated_tokens: int = Field(ge=0)
    policy: RateLimitPolicy


class RateLimitResult(BaseModel):
    """Result of a rate-limit check/reservation."""

    allowed: bool
    limit_type: str | None = None
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    concurrent_in_use: int | None = None
    reset_at: datetime | None = None
    concurrency_slot_expires_at: datetime | None = None
    retry_after_seconds: int | None = None
    degraded: bool = False
