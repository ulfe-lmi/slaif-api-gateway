"""Safe schemas for Redis-backed operational rate limiting."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


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


class LazyThrottlingPolicy(BaseModel):
    """Per-key opt-in lazy (waiting) throttling policy.

    ``reject`` (the default and the safe fallback for any malformed stored
    value) keeps the existing immediate 429 behavior. ``wait`` admits a
    bounded asynchronous wait for temporary capacity before the provider is
    executed. Waiting never relaxes hard quotas, security, or accounting.

    The model is strict: unknown fields are refused and the numeric fields
    accept only true integers (no bool, float, or string coercion). Callers
    that hold digit strings (for example admin form values) must parse them
    explicitly before constructing the policy.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str = "reject"
    max_wait_seconds: StrictInt = 30
    max_waiting_requests: StrictInt = 2

    @field_validator("mode")
    @classmethod
    def _mode_known(cls, value: str) -> str:
        if not isinstance(value, str) or value not in ("reject", "wait"):
            raise ValueError("lazy throttling mode must be 'reject' or 'wait'")
        return value

    @field_validator("max_wait_seconds", "max_waiting_requests")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("lazy throttling values must be positive when set")
        return value

    def is_wait_mode(self) -> bool:
        return self.mode == "wait"

    def to_metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "max_wait_seconds": self.max_wait_seconds,
            "max_waiting_requests": self.max_waiting_requests,
        }


def parse_lazy_throttling_policy_metadata(
    raw: object,
    *,
    max_wait_seconds_ceiling: int,
    max_waiting_per_key_ceiling: int,
) -> LazyThrottlingPolicy | None:
    """Safely parse stored lazy-throttling metadata.

    Missing or malformed values never grant waiting: the result is ``None``
    (callers treat it as the default immediate-reject policy). Unknown keys,
    booleans, zero/negative, non-integer, or ceiling-exceeding values all
    refuse the wait mode.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    if any(not isinstance(k, str) for k in raw):
        return None
    allowed = {"mode", "max_wait_seconds", "max_waiting_requests"}
    if not set(raw) <= allowed:
        return None
    mode = raw.get("mode", "reject")
    if not isinstance(mode, str) or mode not in ("reject", "wait"):
        return None
    max_wait = raw.get("max_wait_seconds", 30)
    max_waiting = raw.get("max_waiting_requests", 2)
    for value in (max_wait, max_waiting):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
    if max_wait > max_wait_seconds_ceiling or max_waiting > max_waiting_per_key_ceiling:
        return None
    try:
        return LazyThrottlingPolicy(
            mode=mode,
            max_wait_seconds=max_wait,
            max_waiting_requests=max_waiting,
        )
    except ValueError:
        return None


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
