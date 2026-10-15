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

Final opaque-ID cleanup (waiting-lease/slot release awaits) runs under a
separate small bounded bookkeeping allowance so an expired wait budget can
never skip releasing IDs; the allowance is cleanup only, never extra
admission eligibility or provider work.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import types
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
    ClientDisconnectedError,
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

# Separate, bounded bookkeeping allowance for the final opaque-ID cleanup
# (waiting-lease/slot release awaits). The wait budget is exhausted by
# definition when the loop exits at the deadline, so cleanup must not reuse it:
# an expired admission budget must not skip releasing IDs. This allowance is
# cleanup only, never extra admission eligibility or provider work; the bounded
# lease/slot TTLs remain the crash/outage backstop.
_BOOKKEEPING_TIMEOUT_SECONDS = 5.0

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


class _WaitBudgetExhausted(Exception):
    """Internal: a bounded wait step produced no result within the budget.

    Only the wait loop's own budget enforcement raises this. Service errors
    (Redis/DB timeouts, auth failures, ...) are never mapped to it: they
    propagate with their existing semantics.
    """


class LazyThrottlingWaitOutcome:
    """Closed outcome label set for bounded lazy-throttling metrics."""

    ADMITTED = "admitted"
    DEADLINE = "deadline"
    CAPACITY_FULL = "capacity_full"
    CANCELLED = "cancelled"
    REVALIDATION_FAILED = "revalidation_failed"
    NEVER_FIT = "never_fit"


# Small per-probe bound for the transport disconnect probe. The probe uses
# the public ASGI receive with its OWN timeout (distinguished from the wait
# budget): a timeout means "no disconnect message pending yet" for this
# probe cycle, never a deadline.
_TRANSPORT_PROBE_TIMEOUT_SECONDS = 0.05


def make_request_disconnect_probe(request: Any) -> Callable[[], Awaitable[bool]]:
    """Build the transport disconnect probe for one in-flight request.

    Starlette's ``Request.is_disconnected()`` cancels its receive scope
    immediately, so through middleware receive wrappers it can return
    False after the client has actually closed the connection. A bounded
    public ``receive`` with its own small timeout reliably observes the
    ``http.disconnect`` message when it has been delivered.

    The probe must be used only AFTER the request body has already been
    consumed and validated (the gateway waits only at the pre-provider
    admission point, after body parsing): at that point the only
    meaningful pending message is the disconnect signal, so the probe
    never consumes request-body content.
    """

    async def _probe() -> bool:
        try:
            async with asyncio.timeout(_TRANSPORT_PROBE_TIMEOUT_SECONDS):
                message = await request.receive()
        except TimeoutError:
            # Own probe bound expired: no disconnect pending this cycle.
            return False
        except asyncio.CancelledError:
            raise
        return bool(isinstance(message, dict) and message.get("type") == "http.disconnect")

    return _probe


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
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
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
    - When ``is_disconnected`` is supplied (the caller's non-blocking
      transport disconnect probe), a disconnect observed while waiting
      aborts the wait BEFORE any provider work: the waiting lease is
      released, an already-admitted concurrency slot is released, and the
      dedicated ``ClientDisconnectedError`` (a typed closed-client outcome,
      not a fabricated 200 and not a capacity/deadline 429) is raised so
      the request path ends normally. The closed peer cannot receive the
      resulting response. Genuine external task cancellation still
      propagates as ``asyncio.CancelledError`` with the same cleanup.
    - Final opaque-ID bookkeeping (the waiting-lease release, and the slot
      release when cancellation lands after admission) runs under a separate
      small bounded cleanup allowance, because the wait budget is exhausted
      by definition at the deadline. That allowance is cleanup only, never
      extra admission eligibility or provider work (bounded overhead).
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

    context = initial_context
    outcome: str | None = None

    def _remaining_budget() -> float:
        return deadline_mono - monotonic_fn()

    async def _within_budget(coro: Awaitable[Any]) -> Any:
        """Bound one awaited step by the remaining monotonic wait budget.

        Clock comparisons between awaits do not bound time spent INSIDE a
        stalled await (a hung re-validation, a wedged limiter probe, ...). The
        asyncio timeout context enforces the original budget across such
        steps, and its ``expired()`` flag makes the origin provable: it is
        True only for THIS wait's budget expiring. A client service that
        raises its own timeout error (including a built-in TimeoutError) is
        not the budget expiring and propagates unchanged with its existing
        semantics.
        """
        remaining = _remaining_budget()
        if remaining <= 0:
            # The step must not run at all. If the caller already built the
            # coroutine, close it so nothing is left unawaited.
            if isinstance(coro, types.CoroutineType):
                coro.close()
            raise _WaitBudgetExhausted()
        budget = asyncio.timeout(remaining)
        try:
            async with budget:
                return await coro
        except TimeoutError:
            if budget.expired():
                raise _WaitBudgetExhausted() from None
            raise

    async def _bookkeeping(coro: Awaitable[Any]) -> None:
        """Run one final opaque-ID cleanup await under its own small bound.

        The wait budget is already exhausted when the loop exits at the
        deadline, so cleanup must not reuse it: an expired admission budget
        must not skip releasing IDs. This allowance covers cleanup only
        (never extra admission eligibility or provider work); bounded
        lease/slot TTLs remain the crash/outage backstop.
        """
        budget = asyncio.timeout(_BOOKKEEPING_TIMEOUT_SECONDS)
        try:
            async with budget:
                await coro
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass

    def _record_outcome_metrics() -> None:
        if outcome is None:
            return
        try:
            wait_seconds = max(monotonic_fn() - start_mono, 0.0)
            observe_lazy_throttling_wait_seconds(wait_seconds)
            increment_lazy_throttling_outcome(outcome)
        except Exception:  # noqa: BLE001 - metrics must never break admission
            pass

    async def _client_gone() -> bool:
        nonlocal outcome
        if is_disconnected is None:
            return False
        try:
            return bool(await _within_budget(is_disconnected()))
        except _WaitBudgetExhausted:
            outcome = LazyThrottlingWaitOutcome.DEADLINE
            raise LazyThrottlingDeadlineExceededError(retry_after_seconds=1)

    async def _release_admitted_slot_quietly() -> None:
        # Idempotent: safe whether or not the slot was actually reserved.
        if release_admission_slot is None:
            return
        await _bookkeeping(release_admission_slot())

    try:
        try:
            acquired = await _within_budget(
                admission.acquire_waiting_lease(
                    gateway_key_id=lease_key_id,
                    request_id=request_id,
                    lease_deadline=lease_deadline,
                    max_waiting_per_key=lazy_policy.max_waiting_requests,
                    max_waiting_total=max_waiting_total,
                    lease_ttl_seconds=lease_ttl,
                )
            )
        except _WaitBudgetExhausted:
            outcome = LazyThrottlingWaitOutcome.DEADLINE
            raise LazyThrottlingDeadlineExceededError(retry_after_seconds=1)
        if not acquired:
            outcome = LazyThrottlingWaitOutcome.CAPACITY_FULL
            raise LazyThrottlingWaitingCapacityFullError(
                retry_after_seconds=1,
            )

        delay = _INITIAL_SLEEP_SECONDS
        while True:
            # A disconnected client cannot receive any outcome; abort
            # promptly before any further re-validation or provider work
            # with the dedicated closed-client outcome (external task
            # cancellation still propagates as asyncio.CancelledError).
            if await _client_gone():
                outcome = LazyThrottlingWaitOutcome.CANCELLED
                raise ClientDisconnectedError()
            if monotonic_fn() >= deadline_mono:
                outcome = LazyThrottlingWaitOutcome.DEADLINE
                raise LazyThrottlingDeadlineExceededError(
                    retry_after_seconds=1,
                )
            if revalidate is not None:
                try:
                    context = await _within_budget(revalidate(context))
                except _WaitBudgetExhausted:
                    # A re-validation that never yields within the budget
                    # means the bounded wait cannot make progress.
                    outcome = LazyThrottlingWaitOutcome.DEADLINE
                    raise LazyThrottlingDeadlineExceededError(
                        retry_after_seconds=1,
                    )
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
                result = await _within_budget(
                    check_and_reserve(
                        gateway_key_id=context.gateway_key_id,
                        request_id=request_id,
                        estimated_tokens=context.estimated_tokens,
                        policy=context.limiter_policy,
                    )
                )
            except _WaitBudgetExhausted:
                # The limiter may have committed before the stall was
                # observed: clean up idempotently, then fail at the deadline.
                await _release_admitted_slot_quietly()
                outcome = LazyThrottlingWaitOutcome.DEADLINE
                raise LazyThrottlingDeadlineExceededError(
                    retry_after_seconds=1,
                )
            except asyncio.CancelledError:
                # Cancellation may land after the atomic reservation already
                # committed: clean up the possibly active slot before the
                # cancellation propagates.
                await _release_admitted_slot_quietly()
                raise
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
                # A disconnect after admission is the same class of event:
                # the slot is released and nothing is forwarded. If the task
                # is cancelled while the probe itself awaits, the possibly
                # committed slot is still released first.
                try:
                    client_gone = await _client_gone()
                    past_deadline = monotonic_fn() >= deadline_mono
                except asyncio.CancelledError:
                    await _release_admitted_slot_quietly()
                    raise
                if client_gone:
                    await _release_admitted_slot_quietly()
                    outcome = LazyThrottlingWaitOutcome.CANCELLED
                    raise ClientDisconnectedError()
                if past_deadline:
                    await _release_admitted_slot_quietly()
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
        # The lease script may already have been applied to Redis even when
        # the acquisition await is interrupted before its result is observed
        # (task cancellation, client error). ZREM is idempotent, so always
        # attempt the release under the separate bookkeeping allowance (the
        # wait budget is exhausted by definition here and must not be
        # reused); bounded lease expiry remains the last-resort crash/outage
        # recovery path, not the normal cancellation path.
        #
        # This phase runs while the helper still owns the admitted slot (the
        # caller takes ownership only when the result actually reaches it):
        # a cancellation landing here means the admitted result never
        # reached the caller, so the wait ends cancelled, not admitted, and
        # the possibly active slot is still released.
        try:
            await _bookkeeping(
                admission.release_waiting_lease(
                    gateway_key_id=lease_key_id,
                    request_id=request_id,
                )
            )
        except asyncio.CancelledError:
            outcome = LazyThrottlingWaitOutcome.CANCELLED
            await _release_admitted_slot_quietly()
            _record_outcome_metrics()
            raise
        _record_outcome_metrics()


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
