"""Unit tests for the exclusive external-tool quota fence service (objective 014)."""

from __future__ import annotations

import uuid
import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceRouteFacts,
    ExternalToolFenceResolveInput,
)
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceActiveError,
    ExternalToolFenceConflictError,
    ExternalToolFenceExhaustedError,
    ExternalToolFenceInvariantError,
    ExternalToolFenceService,
    InvalidExternalToolFenceInputError,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=15)


@dataclass
class FakeDecision:
    allowed: bool = True
    quota_mode: str = "external_tool_fenced"
    effective_tool_call_cap: int = 2
    reason_code: str = "fenced_allowed"
    exclusive_key_fence_required: bool = True
    single_request_overrun_accepted: bool = True
    hold_on_missing_or_ambiguous_final_cost: bool = True
    following_requests_block_after_exhaustion: bool = True


@dataclass
class FakeKey:
    id: uuid.UUID
    status: str = "active"
    key_purpose: str = "standard"
    valid_from: datetime = datetime(2025, 12, 1, tzinfo=UTC)
    valid_until: datetime = datetime(2027, 1, 1, tzinfo=UTC)
    cost_limit_eur: Decimal = Decimal("25")
    token_limit_total: int = 100000
    request_limit_total: int = 1000
    cost_used_eur: Decimal = Decimal("1.25")
    tokens_used_total: int = 100
    requests_used_total: int = 2
    cost_reserved_eur: Decimal = Decimal("0.50")
    tokens_reserved_total: int = 50
    requests_reserved_total: int = 1
    metadata_json: dict[str, object] | None = None
    external_tool_fence_state: str = "none"
    external_tool_fence_reservation_id: uuid.UUID | None = None
    external_tool_fence_request_id: str | None = None
    external_tool_fence_acquired_at: datetime | None = None
    external_tool_fence_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.metadata_json is None:
            self.metadata_json = _fenced_policy()


@dataclass
class FakeReservation:
    id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    endpoint: str
    requested_model: str
    reserved_cost_eur: Decimal
    reserved_tokens: int
    reserved_requests: int
    status: str
    expires_at: datetime
    quota_mode: str = "strict_bounded"
    external_tool_capabilities: list[str] | None = None
    external_tool_destination_ids: list[str] | None = None

    def __post_init__(self) -> None:
        if self.external_tool_capabilities is None:
            self.external_tool_capabilities = []
        if self.external_tool_destination_ids is None:
            self.external_tool_destination_ids = []


@dataclass
class FakeLedger:
    id: uuid.UUID
    quota_reservation_id: uuid.UUID
    request_id: str
    accounting_status: str
    success: bool


class FakeKeyRepo:
    def __init__(self, keys: dict[uuid.UUID, FakeKey]) -> None:
        self.keys = keys
        self.lock_calls: list[uuid.UUID] = []

    async def get_gateway_key_for_update(self, key_id: uuid.UUID):
        self.lock_calls.append(key_id)
        return self.keys.get(key_id)

    async def set_external_tool_fence(
        self,
        key: FakeKey,
        *,
        state: str,
        reservation_id,
        request_id,
        acquired_at,
        expires_at,
    ):
        key.external_tool_fence_state = state
        key.external_tool_fence_reservation_id = reservation_id
        key.external_tool_fence_request_id = request_id
        key.external_tool_fence_acquired_at = acquired_at
        key.external_tool_fence_expires_at = expires_at

    async def add_reserved_counters(
        self,
        key: FakeKey,
        *,
        cost_reserved_eur: Decimal,
        tokens_reserved_total: int,
        requests_reserved_total: int,
    ):
        key.cost_reserved_eur += cost_reserved_eur
        key.tokens_reserved_total += tokens_reserved_total
        key.requests_reserved_total += requests_reserved_total

    async def list_external_tool_fences(self, *, limit: int = 100):
        rows = [k for k in self.keys.values() if k.external_tool_fence_state in ("active", "held")]
        rows.sort(
            key=lambda k: (
                k.external_tool_fence_expires_at is None,
                k.external_tool_fence_expires_at,
            )
        )
        return rows[: max(1, min(limit, 1000))]


class FakeQuotaRepo:
    def __init__(self, reservations: list[FakeReservation] | None = None) -> None:
        self.reservations: dict[uuid.UUID, FakeReservation] = {}
        for row in reservations or []:
            self.reservations[row.id] = row

    async def create_reservation(self, **kwargs):
        row = FakeReservation(
            id=uuid.uuid4(),
            gateway_key_id=kwargs["gateway_key_id"],
            request_id=kwargs["request_id"],
            endpoint=kwargs["endpoint"],
            requested_model=kwargs["requested_model"],
            reserved_cost_eur=kwargs["reserved_cost_eur"],
            reserved_tokens=kwargs["reserved_tokens"],
            reserved_requests=kwargs["reserved_requests"],
            status=kwargs["status"],
            expires_at=kwargs["expires_at"],
            quota_mode=kwargs["quota_mode"],
            external_tool_capabilities=list(kwargs["external_tool_capabilities"]),
            external_tool_destination_ids=list(kwargs["external_tool_destination_ids"]),
        )
        self.reservations[row.id] = row
        return row

    async def get_reservation_by_id_for_update(self, reservation_id: uuid.UUID):
        return self.reservations.get(reservation_id)

    async def get_reservation_by_request_id(self, request_id: str):
        for row in self.reservations.values():
            if row.request_id == request_id:
                return row
        return None


class FakeUsageRepo:
    def __init__(self, ledgers: list[FakeLedger] | None = None) -> None:
        self.ledgers = ledgers or []

    async def get_usage_records_by_reservation_id(self, reservation_id: uuid.UUID):
        return [row for row in self.ledgers if row.quota_reservation_id == reservation_id]


class FakeAuditRepo:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.records.append(kwargs)
        return object()


def _fenced_policy() -> dict[str, object]:
    return {
        "external_tool_policy": {
            "version": 1,
            "mode": "external_tool_fenced",
            "allowed_capabilities": ["provider_web_search", "provider_connector"],
            "allowed_destination_ids": ["connector:abc123", "remote_mcp:svc456"],
            "max_provider_tool_calls_per_request": 2,
            "single_request_overrun_acknowledged": True,
        }
    }


def _route() -> ExternalToolFenceRouteFacts:
    return ExternalToolFenceRouteFacts(
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        provider="test-provider",
        route_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    )


def _input(
    key: FakeKey,
    *,
    request_id: str,
    capabilities: tuple[str, ...] = ("provider_web_search", "provider_connector"),
    destination_ids: tuple[str, ...] = ("connector:abc123",),
    decision: FakeDecision | None = None,
) -> ExternalToolFenceAcquireInput:
    return ExternalToolFenceAcquireInput(
        gateway_key_id=key.id,
        request_id=request_id,
        route=_route(),
        capabilities=capabilities,
        destination_ids=destination_ids,
        decision=decision or FakeDecision(),
        now=NOW,
        ttl=TTL,
    )


def _service(
    key: FakeKey,
    *,
    quota_repo: FakeQuotaRepo | None = None,
    usage_repo: FakeUsageRepo | None = None,
    audit_repo: FakeAuditRepo | None = None,
) -> tuple[ExternalToolFenceService, FakeKeyRepo, FakeQuotaRepo, FakeUsageRepo, FakeAuditRepo]:
    keys_repo = FakeKeyRepo({key.id: key})
    quota_repo = quota_repo or FakeQuotaRepo()
    usage_repo = usage_repo or FakeUsageRepo()
    audit_repo = audit_repo or FakeAuditRepo()
    service = ExternalToolFenceService(
        gateway_keys_repository=keys_repo,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    return service, keys_repo, quota_repo, usage_repo, audit_repo


@pytest.mark.asyncio
async def test_acquire_reserves_exact_full_remaining_balance() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, keys_repo, quota_repo, _usage, audit_repo = _service(key)

    result = await service.acquire(_input(key, request_id="req-1"))

    assert result.fence_state == "active"
    assert result.idempotent is False
    assert result.request_id == "req-1"
    assert result.reserved_cost_eur == Decimal("23.25")
    assert result.reserved_tokens == 99850
    assert result.reserved_requests == 1
    assert result.acquired_at == NOW
    assert result.expires_at == NOW + TTL
    assert result.capabilities == ("provider_connector", "provider_web_search")
    assert result.destination_ids == ("connector:abc123",)

    assert key.external_tool_fence_state == "active"
    assert key.external_tool_fence_request_id == "req-1"
    assert key.external_tool_fence_reservation_id == result.reservation_id
    assert key.external_tool_fence_acquired_at == NOW
    assert key.external_tool_fence_expires_at == NOW + TTL
    assert key.cost_reserved_eur == Decimal("23.75")
    assert key.tokens_reserved_total == 99900
    assert key.requests_reserved_total == 2

    reservation = quota_repo.reservations[result.reservation_id]
    assert reservation.quota_mode == "external_tool_fenced"
    assert reservation.status == "pending"
    assert reservation.external_tool_capabilities == ["provider_connector", "provider_web_search"]
    assert reservation.external_tool_destination_ids == ["connector:abc123"]

    assert audit_repo.records == [
        {
            "action": "external_tool_fence_acquired",
            "entity_type": "gateway_key",
            "entity_id": key.id,
            "request_id": "req-1",
            "note": "external tool fence acquired",
        }
    ]
    assert keys_repo.lock_calls == [key.id]


@pytest.mark.asyncio
async def test_acquire_is_idempotent_for_the_exact_same_request() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, quota_repo, _usage, _audit = _service(key)

    first = await service.acquire(_input(key, request_id="req-1"))
    second = await service.acquire(_input(key, request_id="req-1"))

    assert second.idempotent is True
    assert second.reservation_id == first.reservation_id
    assert len(quota_repo.reservations) == 1
    assert key.cost_reserved_eur == Decimal("23.75")
    assert key.tokens_reserved_total == 99900
    assert key.requests_reserved_total == 2


@pytest.mark.asyncio
async def test_acquire_other_request_id_while_fence_bound_is_rejected() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _quota, _usage, _audit = _service(key)

    await service.acquire(_input(key, request_id="req-1"))

    with pytest.raises(ExternalToolFenceActiveError) as excinfo:
        await service.acquire(_input(key, request_id="req-2"))

    assert excinfo.value.error_code == "external_tool_fence_active"
    assert key.external_tool_fence_request_id == "req-1"


@pytest.mark.asyncio
async def test_acquire_retried_request_id_with_changed_facts_is_conflict() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _quota, _usage, _audit = _service(key)

    await service.acquire(_input(key, request_id="req-1"))

    changed = _input(key, request_id="req-1")
    changed = ExternalToolFenceAcquireInput(
        gateway_key_id=changed.gateway_key_id,
        request_id=changed.request_id,
        route=ExternalToolFenceRouteFacts(
            endpoint=changed.route.endpoint,
            requested_model="other-model",
            provider=changed.route.provider,
            route_id=changed.route.route_id,
        ),
        capabilities=changed.capabilities,
        destination_ids=changed.destination_ids,
        decision=changed.decision,
        now=changed.now,
        ttl=changed.ttl,
    )
    with pytest.raises(ExternalToolFenceConflictError):
        await service.acquire(changed)


@pytest.mark.asyncio
async def test_acquire_rejects_request_id_reused_by_an_existing_reservation() -> None:
    key = FakeKey(id=uuid.uuid4())
    existing = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="req-1",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("0.10"),
        reserved_tokens=10,
        reserved_requests=1,
        status="pending",
        expires_at=NOW + TTL,
    )
    service, _, _, _usage, _audit = _service(key, quota_repo=FakeQuotaRepo([existing]))

    with pytest.raises(ExternalToolFenceConflictError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_request_id_reused"
    assert key.external_tool_fence_state == "none"


@pytest.mark.asyncio
async def test_acquire_rejects_when_no_positive_remaining_balance() -> None:
    key = FakeKey(
        id=uuid.uuid4(),
        cost_limit_eur=Decimal("1.25"),
        cost_used_eur=Decimal("1.25"),
        cost_reserved_eur=Decimal("0"),
    )
    service, _, _quota, _usage, _audit = _service(key)

    with pytest.raises(ExternalToolFenceExhaustedError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_exhausted"
    assert key.external_tool_fence_state == "none"


@pytest.mark.asyncio
async def test_held_fence_blocks_new_acquisition_like_active() -> None:
    key = FakeKey(id=uuid.uuid4())
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="req-held",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("1"),
        reserved_tokens=100,
        reserved_requests=1,
        status="pending",
        expires_at=NOW + TTL,
        quota_mode="external_tool_fenced",
        external_tool_capabilities=["provider_web_search"],
        external_tool_destination_ids=[],
    )
    key.external_tool_fence_state = "held"
    key.external_tool_fence_reservation_id = reservation.id
    key.external_tool_fence_request_id = "req-held"
    key.external_tool_fence_acquired_at = NOW
    key.external_tool_fence_expires_at = NOW + TTL
    service, _, _, _usage, _audit = _service(key, quota_repo=FakeQuotaRepo([reservation]))

    with pytest.raises(ExternalToolFenceActiveError):
        await service.acquire(_input(key, request_id="req-other"))

    assert key.external_tool_fence_state == "held"
    assert key.external_tool_fence_request_id == "req-held"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda decision: FakeDecision(allowed=False),
        lambda decision: FakeDecision(quota_mode="strict_bounded"),
        lambda decision: FakeDecision(exclusive_key_fence_required=False),
        lambda decision: FakeDecision(single_request_overrun_accepted=False),
        lambda decision: FakeDecision(hold_on_missing_or_ambiguous_final_cost=False),
        lambda decision: FakeDecision(following_requests_block_after_exhaustion=False),
    ],
)
async def test_acquire_rejects_decisions_missing_any_fenced_obligation(mutate) -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _quota, _usage, _audit = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError):
        await service.acquire(_input(key, request_id="req-1", decision=mutate(FakeDecision())))

    assert key.external_tool_fence_state == "none"


@pytest.mark.asyncio
async def test_acquire_requires_stored_fenced_policy_superset() -> None:
    key = FakeKey(id=uuid.uuid4())
    key.metadata_json = {"external_tool_policy": {"version": 1, "mode": "strict_bounded"}}
    service, _, _quota, _usage, _audit = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_policy_not_fenced"

    key2 = FakeKey(id=uuid.uuid4())
    key2.metadata_json = {}
    service2, _, _quota2, _usage2, _audit2 = _service(key2)
    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo2:
        await service2.acquire(_input(key2, request_id="req-1"))
    assert excinfo2.value.error_code == "external_tool_fence_policy_missing"

    key3 = FakeKey(id=uuid.uuid4())
    key3.metadata_json = {
        "external_tool_policy": {
            "version": 1,
            "mode": "external_tool_fenced",
            "allowed_capabilities": ["provider_web_search"],
            "allowed_destination_ids": [],
        }
    }
    service3, _, _, _, _ = _service(key3)
    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo3:
        await service3.acquire(_input(key3, request_id="req-1"))
    assert excinfo3.value.error_code == "external_tool_fence_capability_not_permitted"


@pytest.mark.asyncio
async def test_acquire_rejects_invalid_ttl_request_id_and_destination_shape() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _, _, _ = _service(key)

    bad_ttl = _input(key, request_id="req-1")
    bad_ttl = ExternalToolFenceAcquireInput(
        gateway_key_id=bad_ttl.gateway_key_id,
        request_id=bad_ttl.request_id,
        route=bad_ttl.route,
        capabilities=bad_ttl.capabilities,
        destination_ids=bad_ttl.destination_ids,
        decision=bad_ttl.decision,
        now=NOW,
        ttl=timedelta(0),
    )
    with pytest.raises(InvalidExternalToolFenceInputError):
        await service.acquire(bad_ttl)

    with pytest.raises(InvalidExternalToolFenceInputError):
        await service.acquire(_input(key, request_id="  "))

    with pytest.raises(InvalidExternalToolFenceInputError):
        await service.acquire(_input(key, request_id="req-1", destination_ids=("not-opaque",)))

    with pytest.raises(InvalidExternalToolFenceInputError):
        await service.acquire(
            _input(key, request_id="req-1", destination_ids=("remote_mcp:svc456",))
        )

    assert key.external_tool_fence_state == "none"


@pytest.mark.asyncio
async def test_resolve_none_state_is_a_noop() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _quota, _usage, audit_repo = _service(key)

    result = await service.resolve(
        ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
    )

    assert result.fence_state == "none"
    assert result.resolved is False
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_held_state_is_a_noop_and_keeps_blocking() -> None:
    key = FakeKey(id=uuid.uuid4())
    key.external_tool_fence_state = "held"
    key.external_tool_fence_reservation_id = uuid.uuid4()
    key.external_tool_fence_request_id = "req-held"
    key.external_tool_fence_acquired_at = NOW
    key.external_tool_fence_expires_at = NOW + TTL
    service, _, _, _usage, audit_repo = _service(key)

    result = await service.resolve(
        ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-held")
    )

    assert result.fence_state == "held"
    assert result.resolved is False
    assert key.external_tool_fence_state == "held"
    assert audit_repo.records == []


def _bound_key_and_reservation(*, status: str) -> tuple[FakeKey, FakeReservation, FakeLedger]:
    key = FakeKey(id=uuid.uuid4())
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="req-1",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("23.25"),
        reserved_tokens=99850,
        reserved_requests=1,
        status=status,
        expires_at=NOW + TTL,
        quota_mode="external_tool_fenced",
        external_tool_capabilities=["provider_connector", "provider_web_search"],
        external_tool_destination_ids=["connector:abc123"],
    )
    key.external_tool_fence_state = "active"
    key.external_tool_fence_reservation_id = reservation.id
    key.external_tool_fence_request_id = "req-1"
    key.external_tool_fence_acquired_at = NOW
    key.external_tool_fence_expires_at = NOW + TTL
    accounting = "finalized" if status == "finalized" else "failed"
    success = status == "finalized"
    ledger = FakeLedger(
        id=uuid.uuid4(),
        quota_reservation_id=reservation.id,
        request_id="req-1",
        accounting_status=accounting,
        success=success,
    )
    return key, reservation, ledger


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["finalized", "released"])
async def test_resolve_terminal_reservation_clears_fence_and_audits(status: str) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status=status)
    service, _, _, _usage, audit_repo = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )

    result = await service.resolve(
        ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
    )

    assert result.fence_state == "none"
    assert result.resolved is True
    assert key.external_tool_fence_state == "none"
    assert key.external_tool_fence_reservation_id is None
    assert key.external_tool_fence_request_id is None
    assert key.external_tool_fence_acquired_at is None
    assert key.external_tool_fence_expires_at is None
    assert key.cost_reserved_eur == Decimal("0.50")
    assert audit_repo.records == [
        {
            "action": "external_tool_fence_resolved",
            "entity_type": "gateway_key",
            "entity_id": key.id,
            "request_id": "req-1",
            "note": "external tool fence resolved from authoritative terminal evidence",
        }
    ]

    again = await service.resolve(
        ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
    )
    assert again.resolved is False


@pytest.mark.asyncio
async def test_resolve_rejects_non_terminal_reservation() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="pending")
    key.external_tool_fence_state = "active"
    service, _, _, _, _ = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_not_terminal"
    assert key.external_tool_fence_state == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger_count", [0, 2])
async def test_resolve_requires_exactly_one_linked_ledger(ledger_count: int) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    ledgers = [ledger] * ledger_count
    service, _, _, _, _ = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo(ledgers),
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_count"
    assert key.external_tool_fence_state == "active"


@pytest.mark.asyncio
async def test_resolve_rejects_finalized_reservation_with_failed_ledger() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    ledger.accounting_status = "failed"
    ledger.success = False
    service, _, _, _, _ = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_mismatch"
    assert key.external_tool_fence_state == "active"


@pytest.mark.asyncio
async def test_resolve_rejects_request_id_mismatch() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    service, _, _, _, _ = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )

    with pytest.raises(ExternalToolFenceConflictError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-other")
        )

    assert excinfo.value.error_code == "external_tool_fence_resolution_request_mismatch"
    assert key.external_tool_fence_state == "active"


@pytest.mark.asyncio
async def test_resolve_rejects_negative_reserved_counters_without_mutating() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    key.cost_reserved_eur = Decimal("-0.01")
    service, _, _, _, _ = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_counters_inconsistent"
    assert key.external_tool_fence_state == "active"
    assert key.cost_reserved_eur == Decimal("-0.01")


@pytest.mark.asyncio
async def test_list_unresolved_fences_exposes_only_safe_projection_fields() -> None:
    active = FakeKey(id=uuid.uuid4())
    active.external_tool_fence_state = "active"
    active.external_tool_fence_reservation_id = uuid.uuid4()
    active.external_tool_fence_request_id = "req-active"
    active.external_tool_fence_acquired_at = NOW
    active.external_tool_fence_expires_at = NOW + TTL
    held = FakeKey(id=uuid.uuid4())
    held.external_tool_fence_state = "held"
    held.external_tool_fence_reservation_id = uuid.uuid4()
    held.external_tool_fence_request_id = "req-held"
    held.external_tool_fence_acquired_at = NOW
    held.external_tool_fence_expires_at = NOW + timedelta(hours=1)
    plain = FakeKey(id=uuid.uuid4())
    service, keys_repo, _, _, _ = _service(plain)
    keys_repo.keys[active.id] = active
    keys_repo.keys[held.id] = held

    rows = await service.list_unresolved_fences(limit=10)

    assert [row.gateway_key_id for row in rows] == [active.id, held.id]
    assert [row.fence_state for row in rows] == ["active", "held"]
    assert rows[0].request_id == "req-active"
    assert rows[0].expires_at == NOW + TTL
    assert rows[1].expires_at == NOW + timedelta(hours=1)
    for row in rows:
        assert {field.name for field in dataclasses.fields(row)} == {
            "gateway_key_id",
            "fence_state",
            "reservation_id",
            "request_id",
            "acquired_at",
            "expires_at",
        }
