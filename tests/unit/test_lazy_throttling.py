"""Focused wait-loop controls for the bounded lazy-throttling helper.

These are pure wait-loop semantics tests against a SMALL lease double (no
Lua interpreter, no Redis, no HTTP/SQL/provider): admission ordering, the
monotonic deadline budget enforced across stalled awaits, disconnect
cancellation, and the four actual task-cancellation await-boundary controls.
Real owned-Redis Lua/capacity behavior is proven separately by the
integration cases.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from slaif_gateway.schemas.rate_limits import (
    LazyThrottlingPolicy,
    RateLimitPolicy,
    RateLimitResult,
)
from slaif_gateway.services import lazy_throttling
from slaif_gateway.services.lazy_throttling import (
    LazyAdmissionContext,
    wait_for_rate_limit_admission,
)
from slaif_gateway.services.rate_limit_errors import (
    ClientDisconnectedError,
    LazyThrottlingDeadlineExceededError,
    LazyThrottlingWaitingCapacityFullError,
    RequestRateLimitExceededError,
    RedisRateLimitUnavailableError,
    TokenRateLimitExceededError,
)


class _Clock:
    """Controllable wall + monotonic clock; sleep advances both."""

    def __init__(self) -> None:
        self.mono = 1000.0
        self.wall = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    async def sleep(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)
        await asyncio.sleep(0)


class _LeaseDouble:
    """Minimal standing-in for the Redis waiting lease (no Lua semantics)."""

    def __init__(self, *, full: bool = False) -> None:
        self.full = full
        self.acquired = False
        self.released = False
        self.lease_ttl_seconds: int | None = None
        self.acquire_block: asyncio.Event | None = None
        self.release_block: asyncio.Event | None = None

    async def acquire_waiting_lease(self, **kwargs: Any) -> bool:
        self.lease_ttl_seconds = kwargs["lease_ttl_seconds"]
        if self.full:
            return False
        if self.acquire_block is not None:
            self.acquired = True
            self.acquire_block.set()
            await self.acquire_block.wait()
        self.acquired = True
        return True

    async def release_waiting_lease(self, **kwargs: Any) -> None:
        self.released = True
        self.acquired = False
        if self.release_block is not None:
            await self.release_block.wait()


def _context(tokens_per_minute: int | None = 500) -> LazyAdmissionContext:
    policy = RateLimitPolicy(requests_per_minute=1, window_seconds=60)
    if tokens_per_minute is not None:
        policy = policy.model_copy(update={"tokens_per_minute": tokens_per_minute})
    return LazyAdmissionContext(
        gateway_key_id=uuid.uuid4(),
        authenticated_key=None,
        limiter_policy=policy,
        policy_result=None,
        route=None,
        estimated_tokens=1,
    )


class _FakeAdmission:
    """The admission surface the wait loop uses, backed by the lease double."""

    def __init__(self, lease: _LeaseDouble) -> None:
        self._lease = lease

    async def acquire_waiting_lease(self, **kwargs: Any) -> bool:
        return await self._lease.acquire_waiting_lease(**kwargs)

    async def release_waiting_lease(self, **kwargs: Any) -> None:
        await self._lease.release_waiting_lease(**kwargs)


def _kwargs(
    lease: _LeaseDouble,
    clock: _Clock,
    *,
    policy: LazyThrottlingPolicy | None = None,
    **extra: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "admission": _FakeAdmission(lease),
        "initial_context": extra.pop("initial_context", _context()),
        "estimated_tokens": extra.pop("estimated_tokens", 1),
        "lazy_policy": policy or LazyThrottlingPolicy(
            mode="wait", max_wait_seconds=1, max_waiting_requests=2
        ),
        "request_id": extra.pop("request_id", "req-test"),
        "max_waiting_total": 256,
        "lease_ttl_seconds": 300,
        "now_fn": clock.now,
        "monotonic_fn": clock.monotonic,
        "sleep": clock.sleep,
    }
    base.update(extra)
    return base


ALLOWED = RateLimitResult(allowed=True)


@pytest.mark.asyncio
async def test_admits_on_first_attempt_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: list[str | None] = []
    monkeypatch.setattr(
        lazy_throttling, "increment_lazy_throttling_outcome", outcomes.append
    )
    lease = _LeaseDouble()
    clock = _Clock()
    revalidations = 0

    async def revalidate(ctx: LazyAdmissionContext) -> LazyAdmissionContext:
        nonlocal revalidations
        revalidations += 1
        return ctx

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        return ALLOWED

    result = await wait_for_rate_limit_admission(
        check_and_reserve=check_and_reserve,
        revalidate=revalidate,
        **_kwargs(lease, clock),
    )
    assert result.result is ALLOWED
    # The loop re-validates before its first retry attempt (the original
    # limiter attempt already happened at the call site).
    assert revalidations == 1
    assert lease.released
    assert not lease.acquired
    assert outcomes == ["admitted"]


@pytest.mark.asyncio
async def test_denials_then_admission_admits_exactly_once() -> None:
    lease = _LeaseDouble()
    clock = _Clock()
    calls = {"check": 0, "revalidate": 0}
    admitted_once = False

    async def revalidate(ctx: LazyAdmissionContext) -> LazyAdmissionContext:
        calls["revalidate"] += 1
        return ctx

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        nonlocal admitted_once
        calls["check"] += 1
        if admitted_once:
            raise AssertionError("admitted more than once")
        if calls["check"] < 3:
            raise RequestRateLimitExceededError(retry_after_seconds=1)
        admitted_once = True
        return ALLOWED

    result = await wait_for_rate_limit_admission(
        check_and_reserve=check_and_reserve,
        revalidate=revalidate,
        **_kwargs(lease, clock),
    )
    assert result.result is ALLOWED
    assert admitted_once
    assert calls["check"] == 3
    # Re-validation runs before every retry after the first attempt.
    assert calls["revalidate"] == 3
    assert lease.released


@pytest.mark.asyncio
async def test_token_impossibility_refuses_before_any_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: list[str | None] = []
    monkeypatch.setattr(
        lazy_throttling, "increment_lazy_throttling_outcome", outcomes.append
    )
    lease = _LeaseDouble()
    clock = _Clock()
    checks = 0

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        nonlocal checks
        checks += 1
        return ALLOWED

    with pytest.raises(TokenRateLimitExceededError) as excinfo:
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            **_kwargs(
                lease,
                clock,
                initial_context=_context(tokens_per_minute=50),
                estimated_tokens=51,
            ),
        )
    # Strictly-over capacity is impossible: refused before the lease and
    # before any limiter attempt, with the window as the honest hint.
    assert excinfo.value.retry_after_seconds == 60
    assert checks == 0
    assert not lease.acquired
    assert not lease.released
    assert outcomes == ["never_fit"]


@pytest.mark.asyncio
async def test_token_impossibility_equality_can_fit() -> None:
    lease = _LeaseDouble()
    clock = _Clock()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        return ALLOWED

    result = await wait_for_rate_limit_admission(
        check_and_reserve=check_and_reserve,
        **_kwargs(
            lease,
            clock,
            initial_context=_context(tokens_per_minute=50),
            estimated_tokens=50,
        ),
    )
    assert result.result is ALLOWED


@pytest.mark.asyncio
async def test_waiting_capacity_full_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: list[str | None] = []
    monkeypatch.setattr(
        lazy_throttling, "increment_lazy_throttling_outcome", outcomes.append
    )
    lease = _LeaseDouble(full=True)
    clock = _Clock()
    checks = 0

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        nonlocal checks
        checks += 1
        return ALLOWED

    with pytest.raises(LazyThrottlingWaitingCapacityFullError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve, **_kwargs(lease, clock)
        )
    assert checks == 0
    assert not lease.acquired
    assert outcomes == ["capacity_full"]


@pytest.mark.asyncio
async def test_deadline_exhaustion_releases_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: list[str | None] = []
    monkeypatch.setattr(
        lazy_throttling, "increment_lazy_throttling_outcome", outcomes.append
    )
    lease = _LeaseDouble()
    clock = _Clock()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        raise RequestRateLimitExceededError(retry_after_seconds=1)

    with pytest.raises(LazyThrottlingDeadlineExceededError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            **_kwargs(lease, clock, policy=LazyThrottlingPolicy(mode="wait")),
        )
    assert lease.released
    assert not lease.acquired
    assert outcomes == ["deadline"]


@pytest.mark.asyncio
async def test_lease_ttl_covers_max_wait_plus_margin() -> None:
    lease = _LeaseDouble()
    clock = _Clock()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        return ALLOWED

    await wait_for_rate_limit_admission(
        check_and_reserve=check_and_reserve,
        **_kwargs(
            lease,
            clock,
            policy=LazyThrottlingPolicy(mode="wait", max_wait_seconds=120),
            lease_ttl_seconds=1,
        ),
    )
    # A waiting lease cannot expire while its waiter is still eligible.
    assert lease.lease_ttl_seconds is not None
    assert lease.lease_ttl_seconds >= 120 + 30


@pytest.mark.asyncio
async def test_stalled_revalidate_hits_deadline_without_manual_cancel() -> None:
    lease = _LeaseDouble()
    clock = _Clock()
    stall = asyncio.Event()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        raise RequestRateLimitExceededError(retry_after_seconds=1)

    async def revalidate(ctx: LazyAdmissionContext) -> LazyAdmissionContext:
        await stall.wait()
        return ctx

    with pytest.raises(LazyThrottlingDeadlineExceededError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            revalidate=revalidate,
            **_kwargs(
                lease,
                clock,
                policy=LazyThrottlingPolicy(mode="wait", max_wait_seconds=1),
                now_fn=lambda: datetime.now(UTC),
                monotonic_fn=lambda: 0.0,
                sleep=asyncio.sleep,
            ),
        )
    assert lease.released


@pytest.mark.asyncio
async def test_stalled_check_hits_deadline_and_releases_slot() -> None:
    lease = _LeaseDouble()
    clock = _Clock()
    stall = asyncio.Event()
    calls = {"check": 0}
    slot_releases = 0

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        calls["check"] += 1
        if calls["check"] == 1:
            raise RequestRateLimitExceededError(retry_after_seconds=1)
        await stall.wait()
        return ALLOWED

    async def release_slot() -> None:
        nonlocal slot_releases
        slot_releases += 1

    with pytest.raises(LazyThrottlingDeadlineExceededError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            release_admission_slot=release_slot,
            **_kwargs(
                lease,
                clock,
                policy=LazyThrottlingPolicy(mode="wait", max_wait_seconds=1),
                now_fn=lambda: datetime.now(UTC),
                monotonic_fn=lambda: 0.0,
                sleep=asyncio.sleep,
            ),
        )
    assert slot_releases == 1
    assert lease.released


@pytest.mark.asyncio
async def test_service_timeout_error_is_not_a_rate_deadline() -> None:
    """A client service can raise the built-in TimeoutError; it must keep
    its own semantics instead of being mapped to the wait deadline."""
    lease = _LeaseDouble()
    clock = _Clock()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        raise RequestRateLimitExceededError(retry_after_seconds=1)

    async def revalidate(ctx: LazyAdmissionContext) -> LazyAdmissionContext:
        await asyncio.sleep(0.008)
        raise TimeoutError("socket timeout")

    with pytest.raises(TimeoutError, match="socket timeout"):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            revalidate=revalidate,
            **_kwargs(lease, clock),
        )
    assert lease.released


@pytest.mark.asyncio
async def test_redis_unavailable_from_revalidate_propagates_unchanged() -> None:
    lease = _LeaseDouble()
    clock = _Clock()

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        raise RequestRateLimitExceededError(retry_after_seconds=1)

    async def revalidate(ctx: LazyAdmissionContext) -> LazyAdmissionContext:
        raise RedisRateLimitUnavailableError()

    with pytest.raises(RedisRateLimitUnavailableError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            revalidate=revalidate,
            **_kwargs(lease, clock),
        )
    assert lease.released


@pytest.mark.asyncio
async def test_disconnect_during_wait_cancels_without_admission() -> None:
    lease = _LeaseDouble()
    clock = _Clock()
    probes = 0
    checks = 0

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        nonlocal checks
        checks += 1
        raise RequestRateLimitExceededError(retry_after_seconds=1)

    async def is_disconnected() -> bool:
        nonlocal probes
        probes += 1
        await asyncio.sleep(0)
        return probes >= 2

    with pytest.raises(ClientDisconnectedError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            is_disconnected=is_disconnected,
            **_kwargs(lease, clock),
        )
    assert checks >= 1
    assert lease.released
    assert not lease.acquired


@pytest.mark.asyncio
async def test_disconnect_after_admission_releases_slot_and_cancels() -> None:
    lease = _LeaseDouble()
    clock = _Clock()
    probes = 0
    calls = {"check": 0}
    slot_releases = 0

    async def check_and_reserve(**_: Any) -> RateLimitResult:
        calls["check"] += 1
        if calls["check"] == 1:
            raise RequestRateLimitExceededError(retry_after_seconds=1)
        return ALLOWED

    async def is_disconnected() -> bool:
        nonlocal probes
        probes += 1
        await asyncio.sleep(0)
        return probes >= 3  # the post-admission probe

    async def release_slot() -> None:
        nonlocal slot_releases
        slot_releases += 1

    with pytest.raises(ClientDisconnectedError):
        await wait_for_rate_limit_admission(
            check_and_reserve=check_and_reserve,
            release_admission_slot=release_slot,
            is_disconnected=is_disconnected,
            **_kwargs(lease, clock),
        )
    assert slot_releases == 1
    assert lease.released


async def _cancel_at(
    signal: asyncio.Event,
    block: asyncio.Event,
    where: str,
    state: dict[str, Any],
    task: asyncio.Task,
) -> dict[str, Any]:
    """Shared driver for the four actual task-cancellation await boundaries."""
    await asyncio.wait_for(signal.wait(), timeout=2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError(f"({where}) cancellation did not propagate")
    assert not state["waiting"] and not state["active"], (where, state)
    block.set()
    return state


async def _run_cancellation_scenario(where: str) -> dict[str, Any]:
    """Small lease double + event gates at ONE controlled await point.

    Mirrors the independently reviewed four-await cancellation control:
    acquisition, admission-call, post-admission probe, and final lease
    release. Real-Redis Lua cleanup is proven by the integration cases.
    """
    signal = asyncio.Event()
    block = asyncio.Event()
    state: dict[str, Any] = {
        "waiting": False,
        "active": False,
        "release_slot_calls": 0,
    }
    probes = 0

    class Lease:
        async def acquire_waiting_lease(self, **kwargs: Any) -> bool:
            state["waiting"] = True
            if where == "acquire":
                signal.set()
                await block.wait()
            return True

        async def release_waiting_lease(self, **kwargs: Any) -> None:
            state["waiting"] = False
            if where == "lease_release":
                signal.set()
                await block.wait()

    async def check(**_: Any) -> RateLimitResult:
        state["active"] = True
        if where == "admission":
            signal.set()
            await block.wait()
        return RateLimitResult(allowed=True)

    async def release() -> None:
        state["release_slot_calls"] += 1
        state["active"] = False

    async def disconnected() -> bool:
        nonlocal probes
        probes += 1
        if where == "post_admission_probe" and probes == 2:
            signal.set()
            await block.wait()
        return False

    context = LazyAdmissionContext(
        gateway_key_id=uuid.uuid4(),
        authenticated_key=None,
        limiter_policy=RateLimitPolicy(concurrent_requests=1),
        policy_result=None,
        route=None,
        estimated_tokens=1,
    )
    task = asyncio.create_task(
        wait_for_rate_limit_admission(
            check_and_reserve=check,
            admission=Lease(),
            initial_context=context,
            estimated_tokens=1,
            lazy_policy=LazyThrottlingPolicy(mode="wait"),
            request_id=where,
            release_admission_slot=release,
            max_waiting_total=256,
            lease_ttl_seconds=300,
            is_disconnected=disconnected,
        )
    )
    return await _cancel_at(signal, block, where, state, task)


@pytest.mark.asyncio
async def test_cancel_during_lease_acquisition() -> None:
    state = await _run_cancellation_scenario("acquire")
    assert not state["waiting"]
    assert not state["active"]


@pytest.mark.asyncio
async def test_cancel_during_admission_call() -> None:
    state = await _run_cancellation_scenario("admission")
    assert not state["waiting"]
    assert not state["active"]
    assert state["release_slot_calls"] == 1


@pytest.mark.asyncio
async def test_cancel_during_post_admission_probe() -> None:
    state = await _run_cancellation_scenario("post_admission_probe")
    assert not state["waiting"]
    assert not state["active"]
    assert state["release_slot_calls"] == 1


@pytest.mark.asyncio
async def test_cancel_during_final_lease_release() -> None:
    state = await _run_cancellation_scenario("lease_release")
    assert not state["waiting"]
    assert not state["active"]
    assert state["release_slot_calls"] == 1
