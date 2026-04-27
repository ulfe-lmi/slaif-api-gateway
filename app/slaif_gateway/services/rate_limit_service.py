"""Redis-backed temporary operational rate-limit service."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError

from slaif_gateway.schemas.rate_limits import RateLimitPolicy, RateLimitResult
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    InvalidRateLimitPolicyError,
    RateLimitReleaseError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)

_RESERVE_SCRIPT = """
local request_key = KEYS[1]
local token_key = KEYS[2]
local concurrency_key = KEYS[3]

local now_ms = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local request_limit = tonumber(ARGV[3])
local token_limit = tonumber(ARGV[4])
local concurrency_limit = tonumber(ARGV[5])
local estimated_tokens = tonumber(ARGV[6])
local request_id = ARGV[7]
local concurrency_ttl_seconds = tonumber(ARGV[8])
local concurrency_ttl_grace_seconds = tonumber(ARGV[9])

local window_ms = window_seconds * 1000
local reset_ms = now_ms + window_ms
local concurrency_expiry_ms = now_ms + (concurrency_ttl_seconds * 1000)

if concurrency_limit > 0 then
  redis.call("ZREMRANGEBYSCORE", concurrency_key, "-inf", now_ms)
  local existing = redis.call("ZSCORE", concurrency_key, request_id)
  local current_concurrency = redis.call("ZCARD", concurrency_key)
  if not existing and current_concurrency >= concurrency_limit then
    local retry_after = concurrency_ttl_seconds
    local earliest = redis.call("ZRANGE", concurrency_key, 0, 0, "WITHSCORES")
    if earliest[2] then
      retry_after = math.max(math.ceil((tonumber(earliest[2]) - now_ms) / 1000), 1)
      reset_ms = tonumber(earliest[2])
    end
    return {0, "concurrency", 0, 0, current_concurrency, reset_ms, retry_after, 0}
  end
end

local current_requests = tonumber(redis.call("GET", request_key) or "0")
if request_limit > 0 and current_requests + 1 > request_limit then
  return {0, "requests", math.max(request_limit - current_requests, 0), 0, 0, reset_ms, window_seconds, 0}
end

local current_tokens = tonumber(redis.call("GET", token_key) or "0")
if token_limit > 0 and current_tokens + estimated_tokens > token_limit then
  return {0, "tokens", 0, math.max(token_limit - current_tokens, 0), 0, reset_ms, window_seconds, 0}
end

if request_limit > 0 then
  current_requests = redis.call("INCRBY", request_key, 1)
  redis.call("EXPIRE", request_key, window_seconds)
end

if token_limit > 0 then
  current_tokens = redis.call("INCRBY", token_key, estimated_tokens)
  redis.call("EXPIRE", token_key, window_seconds)
end

local concurrency_in_use = 0
local concurrency_expiry_return_ms = 0
if concurrency_limit > 0 then
  redis.call("ZADD", concurrency_key, concurrency_expiry_ms, request_id)
  redis.call("EXPIRE", concurrency_key, concurrency_ttl_seconds + concurrency_ttl_grace_seconds)
  concurrency_in_use = redis.call("ZCARD", concurrency_key)
  concurrency_expiry_return_ms = concurrency_expiry_ms
end

local remaining_requests = 0
if request_limit > 0 then
  remaining_requests = math.max(request_limit - current_requests, 0)
end

local remaining_tokens = 0
if token_limit > 0 then
  remaining_tokens = math.max(token_limit - current_tokens, 0)
end

return {1, "allowed", remaining_requests, remaining_tokens, concurrency_in_use, reset_ms, 0, concurrency_expiry_return_ms}
"""

_HEARTBEAT_SCRIPT = """
local concurrency_key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local request_id = ARGV[2]
local concurrency_ttl_seconds = tonumber(ARGV[3])
local concurrency_ttl_grace_seconds = tonumber(ARGV[4])

redis.call("ZREMRANGEBYSCORE", concurrency_key, "-inf", now_ms)
local existing = redis.call("ZSCORE", concurrency_key, request_id)
if not existing then
  return {0, "missing", 0}
end

local concurrency_expiry_ms = now_ms + (concurrency_ttl_seconds * 1000)
redis.call("ZADD", concurrency_key, concurrency_expiry_ms, request_id)
redis.call("EXPIRE", concurrency_key, concurrency_ttl_seconds + concurrency_ttl_grace_seconds)
return {1, "refreshed", concurrency_expiry_ms}
"""

_DEFAULT_CONCURRENCY_TTL_SECONDS = 300
_DEFAULT_CONCURRENCY_HEARTBEAT_SECONDS = 30
_DEFAULT_CONCURRENCY_TTL_GRACE_SECONDS = 30


class RedisRateLimitService:
    """Check and reserve Redis-backed temporary rate-limit capacity."""

    def __init__(self, redis_client: Any, *, fail_closed: bool = True) -> None:
        self._redis = redis_client
        self._fail_closed = fail_closed

    async def check_and_reserve(
        self,
        *,
        gateway_key_id: uuid.UUID,
        request_id: str,
        estimated_tokens: int,
        policy: RateLimitPolicy,
        now: datetime | None = None,
    ) -> RateLimitResult:
        """Atomically check and reserve temporary rate-limit capacity."""
        self._validate_inputs(request_id=request_id, estimated_tokens=estimated_tokens, policy=policy)
        if not policy.has_limits():
            return RateLimitResult(allowed=True)

        now_dt = now or datetime.now(UTC)
        now_ms = int(now_dt.timestamp() * 1000)
        window_start = int(now_dt.timestamp()) // policy.window_seconds
        keys = self._keys(gateway_key_id=gateway_key_id, window_start=window_start)
        concurrency_ttl_seconds = _policy_concurrency_ttl_seconds(policy)

        try:
            raw = await self._redis.eval(
                _RESERVE_SCRIPT,
                len(keys),
                *keys,
                now_ms,
                policy.window_seconds,
                policy.requests_per_minute or 0,
                policy.tokens_per_minute or 0,
                policy.concurrent_requests or 0,
                estimated_tokens,
                request_id,
                concurrency_ttl_seconds,
                _policy_concurrency_ttl_grace_seconds(policy),
            )
        except RedisError as exc:
            return self._handle_unavailable(exc)
        except Exception as exc:  # noqa: BLE001
            return self._handle_unavailable(exc)

        result = _normalize_result(raw)
        allowed = result[0] == "1"
        limit_type = result[1]
        remaining_requests = _int_or_none(result[2], policy.requests_per_minute)
        remaining_tokens = _int_or_none(result[3], policy.tokens_per_minute)
        concurrent_in_use = _int_or_none(result[4], policy.concurrent_requests)
        reset_at = _datetime_from_millis(int(result[5]))
        retry_after = int(result[6]) or None
        concurrency_slot_expires_at = _datetime_from_millis(int(result[7])) if int(result[7]) else None

        if allowed:
            return RateLimitResult(
                allowed=True,
                remaining_requests=remaining_requests,
                remaining_tokens=remaining_tokens,
                concurrent_in_use=concurrent_in_use,
                reset_at=reset_at,
                concurrency_slot_expires_at=concurrency_slot_expires_at,
            )

        if limit_type == "requests":
            raise RequestRateLimitExceededError(retry_after_seconds=retry_after)
        if limit_type == "tokens":
            raise TokenRateLimitExceededError(retry_after_seconds=retry_after)
        if limit_type == "concurrency":
            raise ConcurrencyRateLimitExceededError(retry_after_seconds=retry_after)

        raise InvalidRateLimitPolicyError("Unknown rate-limit result")

    async def release_concurrency(
        self,
        *,
        gateway_key_id: uuid.UUID,
        request_id: str,
    ) -> None:
        """Release a concurrent request slot; repeated releases are safe."""
        if not request_id:
            raise InvalidRateLimitPolicyError("request_id is required", param="request_id")

        key = self._concurrency_key(gateway_key_id)
        try:
            await self._redis.zrem(key, request_id)
        except RedisError as exc:
            raise RateLimitReleaseError() from exc
        except Exception as exc:  # noqa: BLE001
            raise RateLimitReleaseError() from exc

    async def heartbeat_concurrency(
        self,
        *,
        gateway_key_id: uuid.UUID,
        request_id: str,
        policy: RateLimitPolicy,
        now: datetime | None = None,
    ) -> RateLimitResult:
        """Refresh an existing active concurrent request slot."""
        if not request_id:
            raise InvalidRateLimitPolicyError("request_id is required", param="request_id")
        _validate_concurrency_timing(policy)
        if policy.concurrent_requests is None:
            return RateLimitResult(allowed=True)

        now_dt = now or datetime.now(UTC)
        now_ms = int(now_dt.timestamp() * 1000)
        ttl_seconds = _policy_concurrency_ttl_seconds(policy)
        key = self._concurrency_key(gateway_key_id)
        try:
            raw = await self._redis.eval(
                _HEARTBEAT_SCRIPT,
                1,
                key,
                now_ms,
                request_id,
                ttl_seconds,
                _policy_concurrency_ttl_grace_seconds(policy),
            )
        except RedisError as exc:
            raise RateLimitReleaseError("Rate limit concurrency heartbeat failed") from exc
        except Exception as exc:  # noqa: BLE001
            raise RateLimitReleaseError("Rate limit concurrency heartbeat failed") from exc

        result = _normalize_heartbeat_result(raw)
        if result[0] != "1":
            raise RateLimitReleaseError("Rate limit concurrency slot no longer exists")
        return RateLimitResult(
            allowed=True,
            concurrency_slot_expires_at=_datetime_from_millis(int(result[2])),
        )

    async def cleanup_expired_concurrency(
        self,
        *,
        gateway_key_id: uuid.UUID,
        window_seconds: int = 60,
        now: datetime | None = None,
    ) -> int:
        """Remove stale concurrency slots for a key."""
        if window_seconds <= 0:
            raise InvalidRateLimitPolicyError("window_seconds must be positive", param="window_seconds")
        now_dt = now or datetime.now(UTC)
        cutoff_ms = int(now_dt.timestamp() * 1000)
        key = self._concurrency_key(gateway_key_id)
        try:
            removed = await self._redis.zremrangebyscore(key, "-inf", cutoff_ms)
        except RedisError as exc:
            raise RateLimitReleaseError() from exc
        except Exception as exc:  # noqa: BLE001
            raise RateLimitReleaseError() from exc
        return int(removed or 0)

    def _handle_unavailable(self, exc: Exception) -> RateLimitResult:
        if self._fail_closed:
            raise RedisRateLimitUnavailableError() from exc
        return RateLimitResult(allowed=True, degraded=True)

    @staticmethod
    def _validate_inputs(*, request_id: str, estimated_tokens: int, policy: RateLimitPolicy) -> None:
        if not request_id:
            raise InvalidRateLimitPolicyError("request_id is required", param="request_id")
        if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int):
            raise InvalidRateLimitPolicyError("estimated_tokens must be an integer", param="estimated_tokens")
        if estimated_tokens < 0:
            raise InvalidRateLimitPolicyError("estimated_tokens must be non-negative", param="estimated_tokens")
        if policy.window_seconds <= 0:
            raise InvalidRateLimitPolicyError("window_seconds must be positive", param="window_seconds")
        _validate_concurrency_timing(policy)

    @staticmethod
    def _keys(*, gateway_key_id: uuid.UUID, window_start: int) -> tuple[str, str, str]:
        key_id = str(gateway_key_id)
        return (
            f"rate:{key_id}:requests:{window_start}",
            f"rate:{key_id}:tokens:{window_start}",
            RedisRateLimitService._concurrency_key(gateway_key_id),
        )

    @staticmethod
    def _concurrency_key(gateway_key_id: uuid.UUID) -> str:
        return f"rate:{gateway_key_id}:concurrency"


def _normalize_result(raw: Any) -> list[str]:
    if not isinstance(raw, list | tuple) or len(raw) != 8:
        raise InvalidRateLimitPolicyError("Unexpected rate-limit result")
    normalized: list[str] = []
    for item in raw:
        if isinstance(item, bytes):
            normalized.append(item.decode("utf-8"))
        else:
            normalized.append(str(item))
    return normalized


def _normalize_heartbeat_result(raw: Any) -> list[str]:
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        raise InvalidRateLimitPolicyError("Unexpected rate-limit heartbeat result")
    normalized: list[str] = []
    for item in raw:
        if isinstance(item, bytes):
            normalized.append(item.decode("utf-8"))
        else:
            normalized.append(str(item))
    return normalized


def _int_or_none(value: str, configured_limit: int | None) -> int | None:
    if configured_limit is None:
        return None
    return int(value)


def _datetime_from_millis(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _policy_concurrency_ttl_seconds(policy: RateLimitPolicy) -> int:
    return policy.concurrency_ttl_seconds or _DEFAULT_CONCURRENCY_TTL_SECONDS


def _policy_concurrency_heartbeat_seconds(policy: RateLimitPolicy) -> int:
    return policy.concurrency_heartbeat_seconds or _DEFAULT_CONCURRENCY_HEARTBEAT_SECONDS


def _policy_concurrency_ttl_grace_seconds(policy: RateLimitPolicy) -> int:
    return policy.concurrency_ttl_grace_seconds or _DEFAULT_CONCURRENCY_TTL_GRACE_SECONDS


def _validate_concurrency_timing(policy: RateLimitPolicy) -> None:
    ttl_seconds = _policy_concurrency_ttl_seconds(policy)
    heartbeat_seconds = _policy_concurrency_heartbeat_seconds(policy)
    grace_seconds = _policy_concurrency_ttl_grace_seconds(policy)
    if ttl_seconds <= 0:
        raise InvalidRateLimitPolicyError(
            "concurrency_ttl_seconds must be positive",
            param="concurrency_ttl_seconds",
        )
    if heartbeat_seconds <= 0:
        raise InvalidRateLimitPolicyError(
            "concurrency_heartbeat_seconds must be positive",
            param="concurrency_heartbeat_seconds",
        )
    if heartbeat_seconds >= ttl_seconds:
        raise InvalidRateLimitPolicyError(
            "concurrency_heartbeat_seconds must be less than concurrency_ttl_seconds",
            param="concurrency_heartbeat_seconds",
        )
    if grace_seconds <= 0:
        raise InvalidRateLimitPolicyError(
            "concurrency_ttl_grace_seconds must be positive",
            param="concurrency_ttl_grace_seconds",
        )


def current_time_seconds() -> int:
    """Return monotonic-ish wall-clock seconds for tests and observability."""
    return int(time.time())
