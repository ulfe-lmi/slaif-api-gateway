"""Unit tests for the exclusive external-tool quota fence service (objective 014)."""

from __future__ import annotations

import dataclasses
import types
import uuid
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
    ExternalToolFenceOccupiedError,
    ExternalToolFenceService,
    InvalidExternalToolFenceInputError,
)
from slaif_gateway.services.external_tool_policy_contract import ExternalToolAdmissionDecision

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=15)
ROUTE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _decision_fields() -> dict[str, object]:
    return {
        "allowed": True,
        "quota_mode": "external_tool_fenced",
        "effective_tool_call_cap": 2,
        "reason_code": "external_tool_fenced_allowed",
        "exclusive_key_fence_required": True,
        "single_request_overrun_accepted": True,
        "hold_on_missing_or_ambiguous_final_cost": True,
        "following_requests_block_after_exhaustion": True,
    }


def _decision(**overrides: object) -> ExternalToolAdmissionDecision:
    """Build the exact positive objective-012 fenced admission decision."""
    fields = _decision_fields()
    fields.update(overrides)
    return ExternalToolAdmissionDecision(**fields)


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
    cost_reserved_eur: Decimal = Decimal("0")
    tokens_reserved_total: int = 0
    requests_reserved_total: int = 0
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
    external_tool_provider: str | None = None
    external_tool_route_id: uuid.UUID | None = None

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
    gateway_key_id: uuid.UUID | None = None
    endpoint: str = "/v1/chat/completions"
    provider: str = "test-provider"
    requested_model: str | None = "gpt-test-mini"


def _set_acquire_cost_reserved(key: FakeKey) -> None:
    key.cost_reserved_eur = Decimal("0.50")


def _set_acquire_tokens_reserved(key: FakeKey) -> None:
    key.tokens_reserved_total = 50


def _set_acquire_requests_reserved(key: FakeKey) -> None:
    key.requests_reserved_total = 1


def _set_resolve_cost_reserved(key: FakeKey) -> None:
    key.cost_reserved_eur = Decimal("0.01")


def _set_resolve_tokens_reserved(key: FakeKey) -> None:
    key.tokens_reserved_total = 1


def _set_resolve_requests_reserved(key: FakeKey) -> None:
    key.requests_reserved_total = 1


class FakeKeyRepo:
    def __init__(self, keys: dict[uuid.UUID, FakeKey], *, events: list[str] | None = None) -> None:
        self.keys = keys
        self.lock_calls: list[uuid.UUID] = []
        self.events = events

    async def get_gateway_key_for_update(self, key_id: uuid.UUID):
        self.lock_calls.append(key_id)
        if self.events is not None:
            self.events.append("key")
        return self.keys.get(key_id)

    async def get_gateway_key_by_id(self, key_id: uuid.UUID):
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
    def __init__(
        self,
        reservations: list[FakeReservation] | None = None,
        *,
        events: list[str] | None = None,
    ) -> None:
        self.reservations: dict[uuid.UUID, FakeReservation] = {}
        self.events = events
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
            external_tool_provider=kwargs.get("external_tool_provider"),
            external_tool_route_id=kwargs.get("external_tool_route_id"),
        )
        self.reservations[row.id] = row
        return row

    async def get_reservation_by_id_for_update(self, reservation_id: uuid.UUID):
        if self.events is not None:
            self.events.append("reservation")
        return self.reservations.get(reservation_id)

    async def get_reservation_by_id(self, reservation_id: uuid.UUID):
        return self.reservations.get(reservation_id)

    async def get_reservation_by_request_id(self, request_id: str):
        for row in self.reservations.values():
            if row.request_id == request_id:
                return row
        return None

    async def list_reservations_for_key(
        self,
        gateway_key_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        rows = [r for r in self.reservations.values() if r.gateway_key_id == gateway_key_id]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return rows


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


def _fenced_policy(**overrides: object) -> dict[str, object]:
    policy = {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": [
            "provider_web_search",
            "provider_connector",
            "provider_remote_mcp",
        ],
        "allowed_destination_ids": ["connector:abc123", "remote_mcp:svc456"],
        "max_provider_tool_calls_per_request": 2,
        "single_request_overrun_acknowledged": True,
    }
    policy.update(overrides)
    return {"external_tool_policy": policy}


def _strict_policy() -> dict[str, object]:
    return {
        "external_tool_policy": {
            "version": 1,
            "mode": "strict_bounded",
            "allowed_capabilities": [],
            "allowed_destination_ids": [],
            "max_provider_tool_calls_per_request": 0,
            "single_request_overrun_acknowledged": False,
        }
    }


def _route(**overrides: object) -> ExternalToolFenceRouteFacts:
    facts = dict(
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        provider="test-provider",
        route_id=ROUTE_ID,
    )
    facts.update(overrides)
    return ExternalToolFenceRouteFacts(**facts)


def _input(
    key: FakeKey,
    *,
    request_id: str,
    capabilities: tuple[str, ...] = ("provider_web_search", "provider_connector"),
    destination_ids: tuple[str, ...] = ("connector:abc123",),
    decision: object = None,
    route: ExternalToolFenceRouteFacts | None = None,
    now: datetime = NOW,
    ttl: timedelta = TTL,
) -> ExternalToolFenceAcquireInput:
    return ExternalToolFenceAcquireInput(
        gateway_key_id=key.id,
        request_id=request_id,
        route=route or _route(),
        capabilities=capabilities,
        destination_ids=destination_ids,
        decision=_decision() if decision is None else decision,
        now=now,
        ttl=ttl,
    )


def _service(
    key: FakeKey,
    *,
    quota_repo: FakeQuotaRepo | None = None,
    usage_repo: FakeUsageRepo | None = None,
    audit_repo: FakeAuditRepo | None = None,
    events: list[str] | None = None,
) -> tuple[ExternalToolFenceService, FakeKeyRepo, FakeQuotaRepo, FakeUsageRepo, FakeAuditRepo]:
    keys_repo = FakeKeyRepo({key.id: key}, events=events)
    quota_repo = quota_repo or FakeQuotaRepo(events=events)
    usage_repo = usage_repo or FakeUsageRepo()
    audit_repo = audit_repo or FakeAuditRepo()
    service = ExternalToolFenceService(
        gateway_keys_repository=keys_repo,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    return service, keys_repo, quota_repo, usage_repo, audit_repo


# -- acquisition: positive -------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_reserves_exact_full_remaining_balance() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, keys_repo, quota_repo, _usage, audit_repo = _service(key)

    result = await service.acquire(_input(key, request_id="req-1"))

    assert result.fence_state == "active"
    assert result.idempotent is False
    assert result.request_id == "req-1"
    assert result.reserved_cost_eur == Decimal("23.75")
    assert result.reserved_tokens == 99900
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
    assert key.requests_reserved_total == 1

    reservation = quota_repo.reservations[result.reservation_id]
    assert reservation.quota_mode == "external_tool_fenced"
    assert reservation.status == "pending"
    assert reservation.external_tool_capabilities == ["provider_connector", "provider_web_search"]
    assert reservation.external_tool_destination_ids == ["connector:abc123"]
    assert reservation.external_tool_provider == "test-provider"
    assert reservation.external_tool_route_id == ROUTE_ID

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
    service, _, quota_repo, _usage, audit_repo = _service(key)

    first = await service.acquire(_input(key, request_id="req-1"))
    second = await service.acquire(_input(key, request_id="req-1"))

    assert second.idempotent is True
    assert second.reservation_id == first.reservation_id
    assert len(quota_repo.reservations) == 1
    assert key.cost_reserved_eur == Decimal("23.75")
    assert key.tokens_reserved_total == 99900
    assert key.requests_reserved_total == 1
    assert len(audit_repo.records) == 1


# -- acquisition: fencing and retry identity --------------------------------


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
@pytest.mark.parametrize("changed_field", ["endpoint", "requested_model", "provider", "route_id"])
async def test_acquire_retried_request_id_with_changed_facts_is_conflict(changed_field: str) -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, quota_repo, _usage, audit_repo = _service(key)

    await service.acquire(_input(key, request_id="req-1"))

    if changed_field == "endpoint":
        route = _route(endpoint="/v1/other")
    elif changed_field == "requested_model":
        route = _route(requested_model="other-model")
    elif changed_field == "provider":
        route = _route(provider="other-provider")
    else:
        route = _route(route_id=uuid.uuid4())

    with pytest.raises(ExternalToolFenceConflictError):
        await service.acquire(_input(key, request_id="req-1", route=route))

    # The failed retry must not mutate counters, reservations, or audit state.
    assert key.external_tool_fence_request_id == "req-1"
    assert key.cost_reserved_eur == Decimal("23.75")
    assert key.tokens_reserved_total == 99900
    assert key.requests_reserved_total == 1
    assert len(quota_repo.reservations) == 1
    assert len(audit_repo.records) == 1


@pytest.mark.asyncio
async def test_acquire_rejects_request_id_reused_by_terminal_reservation() -> None:
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
        status="finalized",
        expires_at=NOW + TTL,
    )
    service, _, _, _usage, _audit = _service(key, quota_repo=FakeQuotaRepo([existing]))

    with pytest.raises(ExternalToolFenceConflictError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_request_id_reused"
    assert key.external_tool_fence_state == "none"


# -- acquisition: exclusivity ----------------------------------------------


@pytest.mark.asyncio
async def test_acquire_blocks_when_ordinary_pending_reservation_exists() -> None:
    key = FakeKey(id=uuid.uuid4())
    ordinary = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="req-ordinary",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("0.10"),
        reserved_tokens=10,
        reserved_requests=1,
        status="pending",
        expires_at=NOW + TTL,
        quota_mode="strict_bounded",
    )
    service, _, quota_repo, _usage, audit_repo = _service(key, quota_repo=FakeQuotaRepo([ordinary]))

    with pytest.raises(ExternalToolFenceOccupiedError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_pending_reservation"
    assert key.external_tool_fence_state == "none"
    assert key.external_tool_fence_reservation_id is None
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert len(quota_repo.reservations) == 1
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bump",
    [
        _set_acquire_cost_reserved,
        _set_acquire_tokens_reserved,
        _set_acquire_requests_reserved,
    ],
)
async def test_acquire_blocks_when_reserved_counters_nonzero(bump) -> None:
    key = FakeKey(id=uuid.uuid4())
    bump(key)
    service, _, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(ExternalToolFenceOccupiedError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_counters_nonzero"
    assert key.external_tool_fence_state == "none"
    assert len(quota_repo.reservations) == 0
    assert audit_repo.records == []


# -- acquisition: decision, policy, and route fact validation --------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda decision: dataclasses.replace(decision, allowed=False),
            "external_tool_fence_decision_denied",
        ),
        (
            lambda decision: dataclasses.replace(decision, quota_mode="strict_bounded"),
            "external_tool_fence_decision_not_fenced",
        ),
        (
            lambda decision: dataclasses.replace(decision, effective_tool_call_cap=0),
            "external_tool_fence_decision_call_cap",
        ),
        (
            lambda decision: dataclasses.replace(decision, effective_tool_call_cap=-1),
            "external_tool_fence_decision_call_cap",
        ),
        (
            lambda decision: dataclasses.replace(decision, reason_code="fenced_allowed"),
            "external_tool_fence_decision_reason",
        ),
        (
            lambda decision: dataclasses.replace(decision, exclusive_key_fence_required=False),
            "external_tool_fence_decision_obligations",
        ),
        (
            lambda decision: dataclasses.replace(decision, single_request_overrun_accepted=False),
            "external_tool_fence_decision_obligations",
        ),
        (
            lambda decision: dataclasses.replace(decision, hold_on_missing_or_ambiguous_final_cost=False),
            "external_tool_fence_decision_obligations",
        ),
        (
            lambda decision: dataclasses.replace(
                decision, following_requests_block_after_exhaustion=False
            ),
            "external_tool_fence_decision_obligations",
        ),
    ],
)
async def test_acquire_rejects_incomplete_positive_fenced_decision(mutate, code) -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1", decision=mutate(_decision())))

    assert excinfo.value.error_code == code
    assert key.external_tool_fence_state == "none"
    assert len(quota_repo.reservations) == 0
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wrong_decision",
    [
        lambda: types.SimpleNamespace(**_decision_fields()),
        lambda: dict(_decision_fields()),
        object,
    ],
)
async def test_acquire_rejects_wrong_decision_object_type(wrong_decision) -> None:
    key = FakeKey(id=uuid.uuid4())
    service, keys_repo, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1", decision=wrong_decision()))

    assert excinfo.value.error_code == "external_tool_fence_decision_type"
    assert keys_repo.lock_calls == []
    assert key.external_tool_fence_state == "none"
    assert len(quota_repo.reservations) == 0
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored", "code"),
    [
        (None, "external_tool_fence_policy_not_fenced"),
        ("garbage", "external_tool_fence_policy_invalid"),
        (
            {"version": 1, "mode": "strict_bounded"},
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 2,
                "mode": "external_tool_fenced",
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 1,
                "single_request_overrun_acknowledged": True,
            },
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": [
                    "provider_web_search",
                    "provider_web_search",
                    "provider_connector",
                ],
                "allowed_destination_ids": ["connector:abc123"],
                "max_provider_tool_calls_per_request": 2,
                "single_request_overrun_acknowledged": True,
            },
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 10**9,
                "single_request_overrun_acknowledged": True,
            },
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 1,
                "single_request_overrun_acknowledged": False,
            },
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 1,
                "mode": "external_tool_fenced",
                "allowed_capabilities": [],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 0,
                "single_request_overrun_acknowledged": True,
            },
            "external_tool_fence_policy_invalid",
        ),
        (
            {
                "version": 1,
                "mode": "strict_bounded",
                "allowed_capabilities": [],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 0,
                "single_request_overrun_acknowledged": False,
            },
            "external_tool_fence_policy_not_fenced",
        ),
    ],
)
async def test_acquire_fails_closed_on_invalid_or_nonfenced_stored_policy(stored, code) -> None:
    key = FakeKey(id=uuid.uuid4())
    key.metadata_json = (
        {"external_tool_policy": stored} if stored is not None else {}
    )
    service, _, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == code
    assert key.external_tool_fence_state == "none"
    assert len(quota_repo.reservations) == 0
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_acquire_rejects_requested_capability_not_in_stored_policy() -> None:
    key = FakeKey(id=uuid.uuid4())
    key.metadata_json = _fenced_policy(
        allowed_capabilities=["provider_web_search"],
        allowed_destination_ids=[],
    )
    service, _, _, _usage, _audit = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1"))

    assert excinfo.value.error_code == "external_tool_fence_capability_not_permitted"


@pytest.mark.asyncio
async def test_acquire_rejects_duplicate_request_capabilities_before_mutation() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, keys_repo, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(
            _input(
                key,
                request_id="req-duplicate-capability",
                capabilities=("provider_web_search", "provider_web_search"),
                destination_ids=(),
            )
        )

    assert excinfo.value.error_code == "external_tool_fence_capability_duplicate"
    assert keys_repo.lock_calls == []
    assert quota_repo.reservations == {}
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_acquire_rejects_requested_destination_not_in_stored_policy() -> None:
    key = FakeKey(id=uuid.uuid4())
    key.metadata_json = _fenced_policy(
        allowed_capabilities=["provider_connector", "provider_remote_mcp"],
    )
    service, _, _, _usage, _audit = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(
            _input(
                key,
                request_id="req-1",
                capabilities=("provider_connector", "provider_remote_mcp"),
                destination_ids=("connector:abc123", "connector:zzz999"),
            )
        )

    assert excinfo.value.error_code == "external_tool_fence_destination_not_permitted"


@pytest.mark.asyncio
async def test_acquire_rejects_decision_call_cap_over_stored_policy_ceiling() -> None:
    key = FakeKey(id=uuid.uuid4())
    service, _, _, _usage, _audit = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(
            _input(
                key,
                request_id="req-1",
                decision=_decision(effective_tool_call_cap=3),
            )
        )

    assert excinfo.value.error_code == "external_tool_fence_decision_call_cap_over_ceiling"
    assert key.external_tool_fence_state == "none"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_overrides", "code"),
    [
        ({"requested_model": ""}, "external_tool_fence_model_invalid"),
        ({"requested_model": "x" * 256}, "external_tool_fence_model_invalid"),
        ({"requested_model": "bad\nmodel"}, "external_tool_fence_model_invalid"),
        ({"provider": ""}, "external_tool_fence_provider_invalid"),
        ({"provider": "x" * 256}, "external_tool_fence_provider_invalid"),
        ({"provider": "bad\nprovider"}, "external_tool_fence_provider_invalid"),
        ({"route_id": "11111111-1111-1111-1111-111111111111"}, "external_tool_fence_route_id_invalid"),
        ({"endpoint": ""}, "external_tool_fence_endpoint_invalid"),
    ],
)
async def test_acquire_rejects_unsafe_route_facts_before_locking(route_overrides, code) -> None:
    key = FakeKey(id=uuid.uuid4())
    service, keys_repo, quota_repo, _usage, audit_repo = _service(key)

    with pytest.raises(InvalidExternalToolFenceInputError) as excinfo:
        await service.acquire(_input(key, request_id="req-1", route=_route(**route_overrides)))

    assert excinfo.value.error_code == code
    assert keys_repo.lock_calls == []
    assert key.external_tool_fence_state == "none"
    assert len(quota_repo.reservations) == 0
    assert audit_repo.records == []


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
        external_tool_provider="test-provider",
        external_tool_route_id=ROUTE_ID,
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
@pytest.mark.parametrize("status", ["held", "finalized", "released", "expired"])
async def test_same_request_retry_rejects_non_pending_pointed_reservation(status: str) -> None:
    key = FakeKey(id=uuid.uuid4())
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="req-retry",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test-mini",
        reserved_cost_eur=Decimal("1"),
        reserved_tokens=100,
        reserved_requests=1,
        status=status,
        expires_at=NOW + TTL,
        quota_mode="external_tool_fenced",
        external_tool_capabilities=["provider_web_search"],
        external_tool_destination_ids=[],
        external_tool_provider="test-provider",
        external_tool_route_id=ROUTE_ID,
    )
    key.external_tool_fence_state = "active"
    key.external_tool_fence_request_id = reservation.request_id
    key.external_tool_fence_reservation_id = reservation.id
    service, _, quota_repo, _usage, _audit = _service(
        key, quota_repo=FakeQuotaRepo([reservation])
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.acquire(_input(key, request_id=reservation.request_id))

    assert excinfo.value.error_code == "external_tool_fence_reservation_not_pending"
    assert len(quota_repo.reservations) == 1


@pytest.mark.asyncio
async def test_same_request_retry_rejects_pointed_reservation_bound_to_another_key() -> None:
    key = FakeKey(id=uuid.uuid4())
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=uuid.uuid4(),
        request_id="req-cross-key",
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
        external_tool_provider="test-provider",
        external_tool_route_id=ROUTE_ID,
    )
    key.external_tool_fence_state = "active"
    key.external_tool_fence_request_id = reservation.request_id
    key.external_tool_fence_reservation_id = reservation.id
    service, _, _, _usage, _audit = _service(
        key, quota_repo=FakeQuotaRepo([reservation])
    )

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.acquire(_input(key, request_id=reservation.request_id))

    assert excinfo.value.error_code == "external_tool_fence_reservation_key_mismatch"


# -- resolution ------------------------------------------------------------


def _bound_key_and_reservation(
    *,
    status: str,
    reserved: tuple[Decimal, int, int] = (Decimal("0"), 0, 0),
) -> tuple[FakeKey, FakeReservation, FakeLedger]:
    key = FakeKey(id=uuid.uuid4())
    key.cost_reserved_eur = reserved[0]
    key.tokens_reserved_total = reserved[1]
    key.requests_reserved_total = reserved[2]
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
        external_tool_provider="test-provider",
        external_tool_route_id=ROUTE_ID,
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
        gateway_key_id=key.id,
        endpoint=reservation.endpoint,
        provider=reservation.external_tool_provider,
        requested_model=reservation.requested_model,
    )
    return key, reservation, ledger


def _resolve_service(key, reservation, ledger):
    return _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger]),
    )


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


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["finalized", "released"])
async def test_resolve_terminal_reservation_clears_fence_and_audits(status: str) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status=status)
    service, _, _, _usage, audit_repo = _resolve_service(key, reservation, ledger)

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
    assert len(audit_repo.records) == 1


@pytest.mark.asyncio
async def test_resolve_locks_reservation_before_gateway_key() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    events: list[str] = []
    service, _, _, _, _audit = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation], events=events),
        usage_repo=FakeUsageRepo([ledger]),
        events=events,
    )

    await service.resolve(
        ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
    )

    assert events == ["reservation", "key"]


@pytest.mark.asyncio
async def test_resolve_rejects_non_terminal_reservation() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="pending")
    service, _, _, _usage, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_not_terminal"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger_count", [0, 2])
async def test_resolve_requires_exactly_one_linked_ledger(ledger_count: int) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    service, _, _, _, _audit = _service(
        key,
        quota_repo=FakeQuotaRepo([reservation]),
        usage_repo=FakeUsageRepo([ledger] * ledger_count),
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
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_released_reservation_with_success_ledger() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="released")
    ledger.accounting_status = "finalized"
    ledger.success = True
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_request_id_mismatch() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceConflictError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-other")
        )

    assert excinfo.value.error_code == "external_tool_fence_resolution_request_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_reservation_bound_to_other_key() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    other = uuid.uuid4()
    reservation.gateway_key_id = other
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_key_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_reservation_request_id_mismatch() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    reservation.request_id = "req-other"
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_request_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_non_fenced_reservation_mode() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    reservation.quota_mode = "strict_bounded"
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_not_fenced"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "break_fact",
    [
        lambda reservation: setattr(reservation, "external_tool_provider", None),
        lambda reservation: setattr(reservation, "external_tool_provider", "  "),
        lambda reservation: setattr(reservation, "external_tool_route_id", None),
        lambda reservation: setattr(reservation, "requested_model", None),
    ],
)
async def test_resolve_rejects_invalid_bound_route_facts(break_fact) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    break_fact(reservation)
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_reservation_route_facts_invalid"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_ledger_bound_to_other_key() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    ledger.gateway_key_id = uuid.uuid4()
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_key_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "break_fact",
    [
        lambda ledger: setattr(ledger, "endpoint", "/v1/other"),
        lambda ledger: setattr(ledger, "provider", "other-provider"),
        lambda ledger: setattr(ledger, "requested_model", "other-model"),
        lambda ledger: setattr(ledger, "request_id", "req-other"),
    ],
)
async def test_resolve_rejects_ledger_fact_mismatch(break_fact) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    break_fact(ledger)
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_ledger_facts_mismatch"
    assert key.external_tool_fence_state == "active"
    assert audit_repo.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bump",
    [
        _set_resolve_cost_reserved,
        _set_resolve_tokens_reserved,
        _set_resolve_requests_reserved,
    ],
)
async def test_resolve_rejects_positive_unreconciled_counters_without_mutating(bump) -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    bump(key)
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)
    counters_before = (key.cost_reserved_eur, key.tokens_reserved_total, key.requests_reserved_total)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_counters_inconsistent"
    assert key.external_tool_fence_state == "active"
    assert key.external_tool_fence_reservation_id == reservation.id
    assert (key.cost_reserved_eur, key.tokens_reserved_total, key.requests_reserved_total) == counters_before
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_resolve_rejects_negative_reserved_counters_without_mutating() -> None:
    key, reservation, ledger = _bound_key_and_reservation(status="finalized")
    key.cost_reserved_eur = Decimal("-0.01")
    service, _, _, _, audit_repo = _resolve_service(key, reservation, ledger)

    with pytest.raises(ExternalToolFenceInvariantError) as excinfo:
        await service.resolve(
            ExternalToolFenceResolveInput(gateway_key_id=key.id, request_id="req-1")
        )

    assert excinfo.value.error_code == "external_tool_fence_counters_inconsistent"
    assert key.external_tool_fence_state == "active"
    assert key.cost_reserved_eur == Decimal("-0.01")
    assert audit_repo.records == []


# -- read-only inspection ---------------------------------------------------


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
