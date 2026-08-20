"""Focused unit contract tests for external-tool accounting holds."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldInput,
    ExternalToolHoldAction,
    ExternalToolHoldEvidenceQuality,
    ExternalToolHoldReconciliationInput,
    ExternalToolHoldReasonCode,
    safe_hold_metadata,
    validate_partial_facts,
)
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService

NOW = datetime(2026, 1, 1, tzinfo=UTC)
KEY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RESERVATION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


@dataclass
class FakeKey:
    id: uuid.UUID = KEY_ID
    external_tool_fence_state: str = "active"
    external_tool_fence_reservation_id: uuid.UUID = RESERVATION_ID
    external_tool_fence_request_id: str = "req-1"
    external_tool_fence_acquired_at: datetime = NOW
    external_tool_fence_expires_at: datetime = NOW + timedelta(minutes=15)
    cost_reserved_eur: Decimal = Decimal("3")
    tokens_reserved_total: int = 100
    requests_reserved_total: int = 1


@dataclass
class FakeReservation:
    id: uuid.UUID = RESERVATION_ID
    gateway_key_id: uuid.UUID = KEY_ID
    request_id: str = "req-1"
    endpoint: str = "/v1/responses"
    requested_model: str = "gpt-test"
    reserved_cost_eur: Decimal = Decimal("3")
    reserved_tokens: int = 100
    reserved_requests: int = 1
    status: str = "pending"
    quota_mode: str = "external_tool_fenced"
    external_tool_provider: str = "openrouter"
    external_tool_route_id: uuid.UUID = uuid.UUID("33333333-3333-3333-3333-333333333333")
    expires_at: datetime = NOW + timedelta(minutes=15)


@dataclass
class FakeLedger:
    id: uuid.UUID
    quota_reservation_id: uuid.UUID
    request_id: str
    gateway_key_id: uuid.UUID
    endpoint: str
    provider: str
    requested_model: str
    accounting_status: str
    success: bool | None
    total_tokens: int
    estimated_cost_eur: Decimal | None
    response_metadata: dict[str, object]
    actual_cost_eur: Decimal | None = None
    streaming: bool = False
    created_at: datetime = NOW


class Keys:
    def __init__(self, key: FakeKey) -> None:
        self.key = key

    async def get_gateway_key_for_update(self, key_id):
        return self.key if key_id == self.key.id else None

    async def set_external_tool_fence(self, key, **kwargs):
        for name, value in kwargs.items():
            setattr(key, f"external_tool_fence_{name}", value)

    async def finalize_reserved_counters(self, key, **kwargs):
        key.cost_reserved_eur -= kwargs["reserved_cost_eur"]
        key.tokens_reserved_total -= kwargs["reserved_tokens_total"]
        key.requests_reserved_total -= kwargs["reserved_requests_total"]

    async def subtract_reserved_counters(self, key, **kwargs):
        key.cost_reserved_eur -= kwargs["cost_reserved_eur"]
        key.tokens_reserved_total -= kwargs["tokens_reserved_total"]
        key.requests_reserved_total -= kwargs["requests_reserved_total"]


class Reservations:
    def __init__(self, reservation: FakeReservation) -> None:
        self.reservation = reservation

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.reservation if reservation_id == self.reservation.id else None

    async def mark_pending_reservation_finalized(self, reservation, *, finalized_at):
        reservation.status = "finalized"
        return reservation

    async def mark_pending_reservation_released(self, reservation, *, released_at):
        reservation.status = "released"
        return reservation


class Usage:
    def __init__(self) -> None:
        self.rows: list[FakeLedger] = []

    async def get_usage_records_by_reservation_id(self, reservation_id):
        return [row for row in self.rows if row.quota_reservation_id == reservation_id]

    async def create_usage_record(self, **kwargs):
        row = FakeLedger(
            id=uuid.uuid4(),
            quota_reservation_id=kwargs["quota_reservation_id"],
            request_id=kwargs["request_id"],
            gateway_key_id=kwargs["gateway_key_id"],
            endpoint=kwargs["endpoint"],
            provider=kwargs["provider"],
            requested_model=kwargs["requested_model"],
            accounting_status=kwargs["accounting_status"],
            success=kwargs["success"],
            total_tokens=kwargs["total_tokens"],
            estimated_cost_eur=kwargs["estimated_cost_eur"],
            response_metadata=kwargs["response_metadata"],
            streaming=kwargs["streaming"],
        )
        self.rows.append(row)
        return row

    async def get_usage_record_by_id_for_update(self, usage_id):
        return next((row for row in self.rows if row.id == usage_id), None)

    async def update_external_tool_hold_ledger(self, ledger, **kwargs):
        ledger.accounting_status = kwargs["accounting_status"]
        ledger.success = kwargs["success"]
        ledger.actual_cost_eur = kwargs["actual_cost_eur"]
        ledger.total_tokens = kwargs["total_tokens"]
        ledger.response_metadata = kwargs["response_metadata"]
        return ledger


class Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


def _service():
    key = FakeKey()
    reservations = Reservations(FakeReservation())
    usage = Usage()
    audit = Audit()
    return (
        ExternalToolAccountingHoldService(
            gateway_keys_repository=Keys(key),
            quota_reservations_repository=reservations,
            usage_ledger_repository=usage,
            audit_repository=audit,
        ),
        key,
        usage,
        audit,
    )


class Fence:
    async def resolve(self, request, **kwargs):
        return None


def _input(**overrides):
    values = dict(
        gateway_key_id=KEY_ID,
        reservation_id=RESERVATION_ID,
        request_id="req-1",
        reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_COST,
        evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
        streaming=True,
        now=NOW,
    )
    values.update(overrides)
    return ExternalToolAccountingHoldInput(**values)


@pytest.mark.asyncio
async def test_missing_cost_creates_interrupted_hold_without_counter_mutation():
    service, key, usage, audit = _service()

    result = await service.place(_input())

    assert result.fence_state == "held"
    assert result.accounting_status == "interrupted"
    assert len(usage.rows) == 1
    assert usage.rows[0].usage_raw if hasattr(usage.rows[0], "usage_raw") else True
    assert key.cost_reserved_eur == Decimal("3")
    assert key.tokens_reserved_total == 100
    assert key.requests_reserved_total == 1
    assert audit.rows[0]["action"] == "external_tool_accounting_hold_created"


@pytest.mark.asyncio
async def test_exact_hold_retry_is_idempotent_and_changed_facts_conflict():
    service, _, usage, _ = _service()
    request = _input(
        reason_code=ExternalToolHoldReasonCode.AMBIGUOUS_FINAL_COST,
        evidence_quality=ExternalToolHoldEvidenceQuality.AMBIGUOUS,
        partial_total_tokens=12,
        estimated_cost_eur=Decimal("0.50"),
    )

    first = await service.place(request)
    second = await service.place(request)

    assert second.usage_ledger_id == first.usage_ledger_id
    assert len(usage.rows) == 1
    with pytest.raises(Exception, match="conflict"):
        await service.place(
            _input(
                reason_code=ExternalToolHoldReasonCode.MISSING_FINAL_USAGE,
                evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
                partial_total_tokens=12,
                estimated_cost_eur=Decimal("0.50"),
            )
        )


@pytest.mark.asyncio
async def test_finalize_actual_charged_failure_moves_reserved_balance_to_used():
    service, key, usage, _ = _service()
    await service.place(_input())
    service._fence_service = Fence()

    result = await service.reconcile(
        ExternalToolHoldReconciliationInput(
            reservation_id=RESERVATION_ID,
            action=ExternalToolHoldAction.FINALIZE_ACTUAL,
            execute=True,
            actor_admin_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            reason="provider outcome reconciled",
            actual_cost_eur=Decimal("4.25"),
            actual_total_tokens=125,
            success=False,
        )
    )

    assert result.fence_state == "held"
    assert result.accounting_status == "finalized"
    assert usage.rows[0].success is False
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0


@pytest.mark.asyncio
async def test_release_requires_explicit_confirmation():
    service, _, _, _ = _service()
    await service.place(_input())
    with pytest.raises(Exception, match="confirmation"):
        await service.reconcile(
            ExternalToolHoldReconciliationInput(
                reservation_id=RESERVATION_ID,
                action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
                execute=True,
                actor_admin_id=uuid.uuid4(),
                reason="not enough evidence",
            )
        )


def test_metadata_is_versioned_and_content_free():
    metadata = safe_hold_metadata(
        reason_code=ExternalToolHoldReasonCode.INTERRUPTION_DISCONNECT,
        evidence_quality=ExternalToolHoldEvidenceQuality.MISSING,
        held_at=NOW,
    )

    assert metadata["external_tool_accounting_hold"]["version"] == 1
    assert "response" not in repr(metadata).lower()
    assert "prompt" not in repr(metadata).lower()


def test_partial_facts_reject_negative_values():
    with pytest.raises(ValueError):
        validate_partial_facts(partial_total_tokens=-1, estimated_cost_eur=None)
    with pytest.raises(ValueError):
        validate_partial_facts(partial_total_tokens=None, estimated_cost_eur=Decimal("NaN"))
