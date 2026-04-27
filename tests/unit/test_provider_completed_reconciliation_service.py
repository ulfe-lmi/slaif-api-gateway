from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.services.quota_errors import QuotaCounterInvariantError
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryMetadataMissingError,
    ProviderCompletedRecoveryNotRepairableError,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService


@dataclass
class FakeGatewayKey:
    id: uuid.UUID
    cost_reserved_eur: Decimal = Decimal("0.300000000")
    tokens_reserved_total: int = 200
    requests_reserved_total: int = 1
    cost_used_eur: Decimal = Decimal("0")
    tokens_used_total: int = 0
    requests_used_total: int = 0
    last_used_at: datetime | None = None


@dataclass
class FakeReservation:
    id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str
    endpoint: str = "/v1/chat/completions"
    requested_model: str | None = "gpt-test-mini"
    reserved_cost_eur: Decimal = Decimal("0.300000000")
    reserved_tokens: int = 200
    reserved_requests: int = 1
    status: str = "pending"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    expires_at: datetime = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    finalized_at: datetime | None = None
    released_at: datetime | None = None


def _ledger(*, reservation: FakeReservation, **overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid.uuid4(),
        "quota_reservation_id": reservation.id,
        "gateway_key_id": reservation.gateway_key_id,
        "request_id": reservation.request_id,
        "provider": "openai",
        "requested_model": "gpt-test-mini",
        "resolved_model": "gpt-test-mini",
        "endpoint": "chat.completions",
        "prompt_tokens": 5,
        "completion_tokens": 6,
        "total_tokens": 11,
        "estimated_cost_eur": Decimal("0.300000000"),
        "actual_cost_eur": Decimal("0.000011000"),
        "actual_cost_native": Decimal("0.000011000"),
        "native_currency": "EUR",
        "accounting_status": "failed",
        "success": None,
        "error_type": "accounting_finalization_failed",
        "error_message": "accounting_finalization_failed",
        "response_metadata": {
            "needs_reconciliation": True,
            "recovery_state": "provider_completed_finalization_failed",
        },
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "finished_at": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeUsageRepo:
    def __init__(self, ledgers: list[SimpleNamespace]) -> None:
        self.ledgers = {row.id: row for row in ledgers}
        self.marked: list[dict[str, object]] = []

    async def list_provider_completed_recovery_records(self, **kwargs):
        _ = kwargs
        return list(self.ledgers.values())

    async def get_provider_completed_recovery_record_for_update(
        self,
        *,
        usage_ledger_id=None,
        reservation_id=None,
    ):
        for row in self.ledgers.values():
            if usage_ledger_id is not None and row.id == usage_ledger_id:
                return row
            if reservation_id is not None and row.quota_reservation_id == reservation_id:
                return row
        return None

    async def get_usage_record_by_id(self, usage_ledger_id):
        return self.ledgers.get(usage_ledger_id)

    async def mark_provider_completed_reconciled(self, usage_ledger_id, **kwargs):
        row = self.ledgers[usage_ledger_id]
        self.marked.append(kwargs)
        row.success = True
        row.accounting_status = "finalized"
        row.error_type = None
        row.error_message = None
        row.response_metadata = kwargs["response_metadata"]
        row.finished_at = kwargs["finished_at"]
        return row


class FakeQuotaRepo:
    def __init__(self, reservations: list[FakeReservation]) -> None:
        self.reservations = {row.id: row for row in reservations}

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.reservations.get(reservation_id)

    async def mark_pending_reservation_finalized(self, reservation, *, finalized_at):
        reservation.status = "finalized"
        reservation.finalized_at = finalized_at
        return reservation


class FakeKeysRepo:
    def __init__(self, gateway_key: FakeGatewayKey) -> None:
        self.gateway_key = gateway_key

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id):
        if gateway_key_id == self.gateway_key.id:
            return self.gateway_key
        return None

    async def finalize_reserved_counters(
        self,
        gateway_key,
        *,
        reserved_cost_eur,
        reserved_tokens_total,
        reserved_requests_total,
        actual_cost_eur,
        actual_tokens_total,
        actual_requests_total,
        last_used_at,
    ):
        if gateway_key.cost_reserved_eur < reserved_cost_eur:
            raise QuotaCounterInvariantError(param="cost_reserved_eur")
        gateway_key.cost_reserved_eur -= reserved_cost_eur
        gateway_key.tokens_reserved_total -= reserved_tokens_total
        gateway_key.requests_reserved_total -= reserved_requests_total
        gateway_key.cost_used_eur += actual_cost_eur
        gateway_key.tokens_used_total += actual_tokens_total
        gateway_key.requests_used_total += actual_requests_total
        gateway_key.last_used_at = last_used_at
        return gateway_key


class FakeAuditRepo:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.records.append(kwargs)
        return object()


def _service(
    *,
    reservation: FakeReservation | None = None,
    key: FakeGatewayKey | None = None,
    ledger: SimpleNamespace | None = None,
):
    key = key or FakeGatewayKey(id=uuid.uuid4())
    reservation = reservation or FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id=f"req-{uuid.uuid4()}",
    )
    ledger = ledger or _ledger(reservation=reservation)
    usage_repo = FakeUsageRepo([ledger])
    audit_repo = FakeAuditRepo()
    service = ReservationReconciliationService(
        gateway_keys_repository=FakeKeysRepo(key),
        quota_reservations_repository=FakeQuotaRepo([reservation]),
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    return service, reservation, key, ledger, usage_repo, audit_repo


@pytest.mark.asyncio
async def test_lists_only_repairable_provider_completed_rows() -> None:
    service, _, _, ledger, _, _ = _service()

    rows = await service.list_provider_completed_recovery_rows()

    assert len(rows) == 1
    assert rows[0].usage_ledger_id == ledger.id
    assert rows[0].actual_cost_eur == Decimal("0.000011000")


@pytest.mark.asyncio
async def test_dry_run_validates_without_mutating() -> None:
    service, reservation, key, ledger, usage_repo, audit_repo = _service()

    result = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=ledger.id,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.reconciled is False
    assert reservation.status == "pending"
    assert key.cost_reserved_eur == Decimal("0.300000000")
    assert key.cost_used_eur == Decimal("0")
    assert ledger.accounting_status == "failed"
    assert usage_repo.marked == []
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_execute_finalizes_reservation_counters_ledger_and_audit() -> None:
    service, reservation, key, ledger, usage_repo, audit_repo = _service()

    result = await service.reconcile_provider_completed_recovery(
        usage_ledger_id=ledger.id,
        dry_run=False,
        reason="repair after crash sk-slaif-secretvalue",
    )

    assert result.reconciled is True
    assert result.new_accounting_status == "finalized"
    assert reservation.status == "finalized"
    assert key.cost_reserved_eur == Decimal("0E-9")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("0.000011000")
    assert key.tokens_used_total == 11
    assert key.requests_used_total == 1
    assert ledger.accounting_status == "finalized"
    assert ledger.success is True
    assert ledger.response_metadata["needs_reconciliation"] is False
    assert ledger.response_metadata["recovery_state"] == "provider_completed_reconciled"
    assert "sk-slaif-secretvalue" not in str(ledger.response_metadata)
    assert len(usage_repo.marked) == 1
    assert audit_repo.records[0]["action"] == "provider_completed_reconciliation"
    assert audit_repo.records[0]["entity_id"] == ledger.id
    assert "sk-slaif-secretvalue" not in str(audit_repo.records[0]["note"])


@pytest.mark.asyncio
async def test_missing_cost_metadata_fails_closed_without_mutation() -> None:
    key = FakeGatewayKey(id=uuid.uuid4())
    reservation = FakeReservation(id=uuid.uuid4(), gateway_key_id=key.id, request_id="missing")
    service, _, _, ledger, usage_repo, audit_repo = _service(
        key=key,
        reservation=reservation,
        ledger=_ledger(reservation=reservation, actual_cost_eur=None),
    )

    with pytest.raises(ProviderCompletedRecoveryMetadataMissingError):
        await service.reconcile_provider_completed_recovery(
            usage_ledger_id=ledger.id,
            dry_run=False,
        )

    assert reservation.status == "pending"
    assert key.cost_reserved_eur == Decimal("0.300000000")
    assert usage_repo.marked == []
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_non_pending_reservation_fails_without_double_charge() -> None:
    key = FakeGatewayKey(id=uuid.uuid4())
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="done",
        status="finalized",
    )
    service, _, _, ledger, usage_repo, audit_repo = _service(
        key=key,
        reservation=reservation,
        ledger=_ledger(reservation=reservation),
    )

    with pytest.raises(ProviderCompletedRecoveryNotRepairableError):
        await service.reconcile_provider_completed_recovery(
            usage_ledger_id=ledger.id,
            dry_run=False,
        )

    assert key.cost_used_eur == Decimal("0")
    assert usage_repo.marked == []
    assert audit_repo.records == []
