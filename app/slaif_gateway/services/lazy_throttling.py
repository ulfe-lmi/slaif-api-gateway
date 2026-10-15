"""Shared bounded lazy (waiting) throttling admission helper.

This module implements the small shared Redis waiting lease/counter and the
bounded wait-for-admission loop used by the Chat Completions and Responses
rate-limit seams. Waiting is delayed admission only: it never stores request
content, never reserves quota, and never holds a provider call. Only opaque
key/request IDs and timestamps are written to operational Redis state.

The waiting lease is scoped per-key AND deployment-wide: a waiter holds a
lease in a per-key ZSET and in the deployment-wide ZSET, both scored by
lease expiry (bounded expiry recovers crashed-worker leases). Strict FIFO is
not promised; reordering under contention is possible and documented.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.metrics import (
    increment_lazy_throttling_outcome,
    observe_lazy_throttling_wait_seconds,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.rate_limits import (
    LazyThrottlingPolicy,
    RateLimitPolicy,
    RateLimitResult,
)
from slaif_gateway.services.rate_limit_errors import (
    ConcurrencyRateLimitExceededError,
    LazyThrottlingDeadlineExceededError,
    LazyThrottlingWaitingCapacityFullError,
    RateLimitError,
    RedisRateLimitUnavailableError,
    RequestRateLimitExceededError,
    TokenRateLimitExceededError,
)

# Bounded, adaptive retry cadence for the wait loop. The existing denied
# request/token hint is always the full window (not time to boundary) and the
# concurrency TTL is not the earliest actual completion, so fixed long sleeps
# and busy polling are both wrong; this schedule stays between them.
_MIN_SLEEP_SECONDS = 0.05
_INITIAL_SLEEP_SECONDS = 0.1
_MAX_SLEEP_SECONDS = 1.0

# Crash-recovery margin added on top of the max wait so a waiting lease cannot
# expire while its waiter is still eligible (see config validation).
_LEASE_WAIT_MARGIN_SECONDS = 30

_ACQUIRE_WAITING_SCRIPT = """
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", ARGV[1])
redis.call("ZREMRANGEBYSCORE", KEYS[2], "-inf", ARGV[1])
local per_key = redis.call("ZCARD", KEYS[1])
if per_key >= tonumber(ARGV[4]) then
  return 0
end
local total = redis.call("ZCARD", KEYS[2])
if total >= tonumber(ARGV[5]) then
  return 0
end
redis.call("ZADD", KEYS[1], tonumber(ARGV[2]), ARGV[3])
redis.call("ZADD", KEYS[2], tonumber(ARGV[2]), ARGV[3])
redis.call("EXPIRE", KEYS[1], tonumber(ARGV[6]))
redis.call("EXPIRE", KEYS[2], tonumber(ARGV[6]))
return 1
"""

_RELEASE_WAITING_SCRIPT = """
redis.call("ZREM", KEYS[1], ARGV[1])
redis.call("ZREM", KEYS[2], ARGV[1])
return 1
"""

_PER_KEY_WAITING_KEY = "lazywait:{key_id}:waiters"
_GLOBAL_WAITING_KEY = "lazywait:global:waiters"


def per_key_waiting_key(gateway_key_id: Any) -> str:
    return _PER_KEY_WAITING_KEY.format(key_id=gateway_key_id)


def global_waiting_key() -> str:
    return _GLOBAL_WAITING_KEY


class LazyThrottlingAdmission:
    """Manage the bounded Redis waiting lease/counter for one Redis client."""

    def __init__(self, redis_client: Any, *, fail_closed: bool = True) -> None:
        self._redis = redis_client
        self._fail_closed = fail_closed

    @staticmethod
    def _waiter_member(gateway_key_id: Any, request_id: str) -> str:
        # Opaque IDs only; no request body, model, or content is stored.
        return f"{gateway_key_id}:{request_id}"

    async def acquire_waiting_lease(
        self,
        *,
        gateway_key_id: Any,
        request_id: str,
        lease_deadline: datetime,
        max_waiting_per_key: int,
        max_waiting_total: int,
        lease_ttl_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        """Atomically acquire a waiting lease; False when a cap is full.

        A Redis outage during acquisition respects the configured outage
        semantics of the operational limiter: fail-closed raises the existing
        503 unavailable error, fail-open mirrors the existing limiter bypass
        (the waiting cap is operational rate-limit state and is bypassed only
        while that state is already bypassed). The lease never grants
        admission; the limiter alone does.
        """
        now_dt = now or datetime.now(UTC)
        now_ms = int(now_dt.timestamp() * 1000)
        deadline_ms = int(lease_deadline.timestamp() * 1000)
        keys = (
            per_key_waiting_key(gateway_key_id),
            global_waiting_key(),
        )
        try:
            raw = await self._redis.eval(
                _ACQUIRE_WAITING_SCRIPT,
                len(keys),
                *keys,
                now_ms,
                deadline_ms,
                self._waiter_member(gateway_key_id, request_id),
                max_waiting_per_key,
                max_waiting_total,
                lease_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if self._fail_closed:
                raise RedisRateLimitUnavailableError() from exc
            return True
        return str(raw) == "1"

    async def release_waiting_lease(
        self,
        *,
        gateway_key_id: Any,
        request_id: str,
    ) -> None:
        """Release a waiting lease; repeated releases are safe."""
        keys = (
            per_key_waiting_key(gateway_key_id),
            global_waiting_key(),
        )
        await self._redis.eval(
            _RELEASE_WAITING_SCRIPT,
            len(keys),
            *keys,
            self._waiter_member(gateway_key_id, request_id),
        )

    async def count_waiting(
        self,
        *,
        gateway_key_id: Any | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Report current (non-expired) waiting counts for diagnostics."""
        now_dt = now or datetime.now(UTC)
        now_ms = int(now_dt.timestamp() * 1000)
        keys: list[str] = [global_waiting_key()]
        if gateway_key_id is not None:
            keys.append(per_key_waiting_key(gateway_key_id))
        counts: dict[str, int] = {}
        for key in keys:
            await self._redis.zremrangebyscore(key, "-inf", now_ms)
            counts[key] = int(await self._redis.zcard(key) or 0)
        return counts


class LazyThrottlingWaitOutcome:
    """Closed outcome label set for bounded lazy-throttling metrics."""

    ADMITTED = "admitted"
    DEADLINE = "deadline"
    CAPACITY_FULL = "capacity_full"
    CANCELLED = "cancelled"
    REVALIDATION_FAILED = "revalidation_failed"
    NEVER_FIT = "never_fit"


@dataclass(frozen=True)
class LazyAdmissionContext:
    """The admission context the wait loop currently operates under.

    ``policy_result`` and ``route`` are endpoint-specific (the request policy
    result and the route resolution result) and are treated opaquely by this
    shared helper. After a real wait, the caller's revalidation hook rebuilds
    this context from the CURRENT authenticated key so forwarding never relies
    on a stale pre-wait authorization or policy result (R4).
    """

    gateway_key_id: Any
    authenticated_key: Any
    limiter_policy: RateLimitPolicy
    policy_result: Any
    route: Any
    # Current token estimate recomputed from the current policy result; the
    # original pre-wait estimate is only used for the first impossibility
    # check. Retries and post-policy-change impossibility checks use this.
    estimated_tokens: int


@dataclass(frozen=True)
class LazyAdmissionResult:
    """The final limiter result plus the revalidated context that admitted it."""

    result: RateLimitResult
    context: LazyAdmissionContext


async def wait_for_rate_limit_admission(
    *,
    check_and_reserve: Callable[..., Awaitable[RateLimitResult]],
    admission: LazyThrottlingAdmission,
    initial_context: LazyAdmissionContext,
    estimated_tokens: int,
    lazy_policy: LazyThrottlingPolicy,
    request_id: str,
    release_admission_slot: Callable[..., Awaitable[None]] | None = None,
    revalidate: Callable[[LazyAdmissionContext], Awaitable[LazyAdmissionContext]] | None = None,
    max_waiting_total: int,
    lease_ttl_seconds: int,
    now_fn: Callable[[], datetime] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> LazyAdmissionResult:
    """Wait for temporary rate-limit capacity with bounded, honest semantics.

    - The deadline is ``max_wait_seconds`` of MONOTONIC elapsed time from the
      first attempt and is never reset by a policy update or retry. It is
      rechecked after every await (re-validation and admission) before
      accepting an admission.
    - An estimate that strictly exceeds the complete token window capacity can
      never fit a fresh window and fails immediately BEFORE any waiting lease
      is acquired, regardless of which limiter denial occurred first.
      (Equality CAN fit a fresh complete window, so it is not impossible.)
    - The waiting lease is acquired before the first sleep and released on
      every exit (admission, deadline, cancellation, revalidation failure).
      An admission granted after the deadline is cleaned up (slot released)
      before the deadline error propagates.
    - Each retry first re-validates through the caller's ``revalidate`` hook
      (re-authentication, current request policy, route, and boundary checks
      using short sessions) and then runs under the returned context, so the
      CURRENT key/policy/route governs admission. A failed re-validation
      aborts before forwarding.
    - Wall-clock UTC is used only for the shared lease timestamps; the
      elapsed deadline uses a monotonic clock.
    """
    now_fn = now_fn or (lambda: datetime.now(UTC))
    monotonic_fn = monotonic_fn or time.monotonic
    started_wall = now_fn()
    start_mono = monotonic_fn()
    deadline_mono = start_mono + lazy_policy.max_wait_seconds

    # R5 impossibility check BEFORE any waiting lease: an estimate strictly
    # larger than the complete window capacity can never fit a fresh window.
    # (Equality CAN fit a fresh complete window, so it is not impossible.)
    initial_policy = initial_context.limiter_policy
    if initial_policy.tokens_per_minute is not None and estimated_tokens > initial_policy.tokens_per_minute:
        increment_lazy_throttling_outcome(LazyThrottlingWaitOutcome.NEVER_FIT)
        raise TokenRateLimitExceededError(retry_after_seconds=initial_policy.window_seconds)

    lease_ttl = max(lease_ttl_seconds, lazy_policy.max_wait_seconds + _LEASE_WAIT_MARGIN_SECONDS)
    lease_deadline = datetime.fromtimestamp(started_wall.timestamp() + lease_ttl, tz=UTC)
    lease_key_id = initial_context.gateway_key_id

    lease_acquired = False
    context = initial_context
    outcome: str | None = None
    try:
        acquired = await admission.acquire_waiting_lease(
            gateway_key_id=lease_key_id,
            request_id=request_id,
            lease_deadline=lease_deadline,
            max_waiting_per_key=lazy_policy.max_waiting_requests,
            max_waiting_total=max_waiting_total,
            lease_ttl_seconds=lease_ttl,
        )
        if not acquired:
            outcome = LazyThrottlingWaitOutcome.CAPACITY_FULL
            raise LazyThrottlingWaitingCapacityFullError(
                retry_after_seconds=1,
            )
        lease_acquired = True

        delay = _INITIAL_SLEEP_SECONDS
        while True:
            if monotonic_fn() >= deadline_mono:
                outcome = LazyThrottlingWaitOutcome.DEADLINE
                raise LazyThrottlingDeadlineExceededError(
                    retry_after_seconds=1,
                )
            if revalidate is not None:
                try:
                    context = await revalidate(context)
                except (RateLimitError, asyncio.CancelledError):
                    raise
                except Exception:
                    outcome = LazyThrottlingWaitOutcome.REVALIDATION_FAILED
                    raise
            # The re-validation await may have advanced past the deadline.
            if monotonic_fn() >= deadline_mono:
                outcome = LazyThrottlingWaitOutcome.DEADLINE
                raise LazyThrottlingDeadlineExceededError(
                    retry_after_seconds=1,
                )
            # A policy update may have reduced the window capacity (or raised
            # the current estimate): re-check impossibility under the CURRENT
            # context before retrying, so a request that can no longer fit a
            # fresh window fails immediately instead of waiting.
            current_limit = context.limiter_policy.tokens_per_minute
            if current_limit is not None and context.estimated_tokens > current_limit:
                outcome = LazyThrottlingWaitOutcome.NEVER_FIT
                raise TokenRateLimitExceededError(
                    retry_after_seconds=context.limiter_policy.window_seconds,
                )
            try:
                result = await check_and_reserve(
                    gateway_key_id=context.gateway_key_id,
                    request_id=request_id,
                    estimated_tokens=context.estimated_tokens,
                    policy=context.limiter_policy,
                )
            except (
                TokenRateLimitExceededError,
                RequestRateLimitExceededError,
                ConcurrencyRateLimitExceededError,
            ):
                pass
            else:
                # The admission await may have advanced past the deadline;
                # an admission granted after the deadline is not honored and
                # its slot is cleaned up before the deadline error propagates.
                if monotonic_fn() >= deadline_mono:
                    if release_admission_slot is not None:
                        try:
                            await release_admission_slot()
                        except Exception:  # noqa: BLE001 - TTL is the backstop
                            pass
                    outcome = LazyThrottlingWaitOutcome.DEADLINE
                    raise LazyThrottlingDeadlineExceededError(
                        retry_after_seconds=1,
                    )
                outcome = LazyThrottlingWaitOutcome.ADMITTED
                return LazyAdmissionResult(result=result, context=context)

            remaining = deadline_mono - monotonic_fn()
            next_delay = min(delay * 2.0, _MAX_SLEEP_SECONDS)
            await sleep(min(max(next_delay, _MIN_SLEEP_SECONDS), max(remaining, 0.0)))
            delay = next_delay
    except asyncio.CancelledError:
        outcome = LazyThrottlingWaitOutcome.CANCELLED
        raise
    finally:
        if lease_acquired:
            try:
                await admission.release_waiting_lease(
                    gateway_key_id=lease_key_id,
                    request_id=request_id,
                )
            except Exception:  # noqa: BLE001 - lease expiry is the recovery path
                pass
        if outcome is not None:
            try:
                wait_seconds = max(monotonic_fn() - start_mono, 0.0)
                observe_lazy_throttling_wait_seconds(wait_seconds)
                increment_lazy_throttling_outcome(outcome)
            except Exception:  # noqa: BLE001 - metrics must never break admission
                pass


# Mutable usage counters and the temporary limiter configuration are never
# "policy" for admission re-validation: counters change with ordinary use, and
# the current rate-limit configuration already governs each retry through the
# rebuilt limiter policy carried in the admission context.
_KEY_ADMISSION_COMPARE_EXCLUDES = frozenset(
    {
        "cost_used_eur",
        "tokens_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "rate_limit_policy",
    }
)


def policy_changed_while_waiting_error() -> OpenAICompatibleError:
    """Conservative 409 when the CURRENT policy no longer matches pre-wait."""
    return OpenAICompatibleError(
        "Key or rate-limit policy changed while waiting for capacity.",
        status_code=409,
        error_type="invalid_request_error",
        code="policy_changed_while_waiting",
    )


def key_admission_policy_unchanged(original_key: Any, current_key: Any) -> bool:
    """True when every admission-relevant authenticated-key field is unchanged.

    Compares the full key EXCEPT the mutable usage counters and the temporary
    rate-limit configuration (see _KEY_ADMISSION_COMPARE_EXCLUDES), so any
    policy change (endpoints, models, providers, purpose, response policy,
    lazy throttling, validity, ...) conservatively refuses forwarding under
    the former permissions. Mutable usage counters are never compared as
    policy.
    """
    for field in dataclasses.fields(AuthenticatedGatewayKey):
        if field.name in _KEY_ADMISSION_COMPARE_EXCLUDES:
            continue
        if getattr(original_key, field.name) != getattr(current_key, field.name):
            return False
    return True
