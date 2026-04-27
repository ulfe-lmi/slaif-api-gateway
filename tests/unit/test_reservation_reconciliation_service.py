from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.services.quota_errors import QuotaCounterInvariantError
from slaif_gateway.services.reconciliation_errors import (
    ReconciliationInvariantError,
    ReservationNotExpiredError,
    ReservationNotPendingError,
)
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService


@dataclass
class FakeGatewayKey:
    id: uuid.UUID
    cost_reserved_eur: Decimal = Decimal("0.300000000")
    tokens_reserved_total: int = 200
    requests_reserved_total: int = 1
    cost_used_eur: Decimal = Decimal("0")


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


class FakeQuotaRepo:
    def __init__(self, reservations: list[FakeReservation]) -> None:
        self.reservations = {row.id: row for row in reservations}

    async def list_expired_pending_reservations(self, *, now, limit):
        rows = [
            row
            for row in self.reservations.values()
            if row.status == "pending" and row.expires_at <= now
        ]
        return sorted(rows, key=lambda row: row.expires_at)[:limit]

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.reservations.get(reservation_id)

    async def mark_pending_reservation_expired(self, reservation, *, released_at):
        reservation.status = "expired"
        reservation.released_at = released_at
        return reservation


class FakeKeysRepo:
    def __init__(self, gateway_key: FakeGatewayKey) -> None:
        self.gateway_key = gateway_key

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id):
        if gateway_key_id == self.gateway_key.id:
            return self.gateway_key
        return None

    async def subtract_reserved_counters(
        self,
        gateway_key,
        *,
        cost_reserved_eur,
        tokens_reserved_total,
        requests_reserved_total,
    ):
        if gateway_key.cost_reserved_eur < cost_reserved_eur:
            raise QuotaCounterInvariantError(param="cost_reserved_eur")
        gateway_key.cost_reserved_eur -= cost_reserved_eur
        gateway_key.tokens_reserved_total -= tokens_reserved_total
        gateway_key.requests_reserved_total -= requests_reserved_total
        return gateway_key


class FakeUsageRepo:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []
        self.existing_request_ids: set[str] = set()

    async def get_usage_record_by_request_id(self, request_id):
        if request_id in self.existing_request_ids:
            return object()
        return None

    async def create_failure_record(self, **kwargs):
        self.records.append(kwargs)
        self.existing_request_ids.add(str(kwargs["request_id"]))
        return object()


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
    usage_repo: FakeUsageRepo | None = None,
    audit_repo: FakeAuditRepo | None = None,
):
    gateway_key_id = uuid.uuid4()
    key = key or FakeGatewayKey(id=gateway_key_id)
    reservation = reservation or FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id=f"req-{uuid.uuid4()}",
    )
    usage_repo = usage_repo or FakeUsageRepo()
    audit_repo = audit_repo or FakeAuditRepo()
    service = ReservationReconciliationService(
        gateway_keys_repository=FakeKeysRepo(key),
        quota_reservations_repository=FakeQuotaRepo([reservation]),
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    return service, reservation, key, usage_repo, audit_repo


@pytest.mark.asyncio
async def test_list_returns_expired_pending_reservations_only() -> None:
    key = FakeGatewayKey(id=uuid.uuid4())
    expired = FakeReservation(id=uuid.uuid4(), gateway_key_id=key.id, request_id="expired")
    future = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="future",
        expires_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    released = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="released",
        status="released",
    )
    service = ReservationReconciliationService(
        gateway_keys_repository=FakeKeysRepo(key),
        quota_reservations_repository=FakeQuotaRepo([expired, future, released]),
        usage_ledger_repository=FakeUsageRepo(),
        audit_repository=FakeAuditRepo(),
    )

    rows = await service.list_expired_pending_reservations(now=datetime(2026, 1, 1, 1, tzinfo=UTC))

    assert [row.request_id for row in rows] == ["expired"]


@pytest.mark.asyncio
async def test_dry_run_does_not_mutate_counters_status_ledger_or_audit() -> None:
    service, reservation, key, usage_repo, audit_repo = _service()

    result = await service.reconcile_expired_pending_reservation(
        reservation.id,
        now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.new_status == "pending"
    assert reservation.status == "pending"
    assert key.cost_reserved_eur == Decimal("0.300000000")
    assert key.tokens_reserved_total == 200
    assert key.requests_reserved_total == 1
    assert usage_repo.records == []
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_execute_expires_reservation_decrements_counters_and_writes_ledger_and_audit() -> None:
    service, reservation, key, usage_repo, audit_repo = _service()

    result = await service.reconcile_expired_pending_reservation(
        reservation.id,
        now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        reason="process crash recovery sk-slaif-secretvalue",
    )

    assert result.previous_status == "pending"
    assert result.new_status == "expired"
    assert result.ledger_created is True
    assert result.audit_created is True
    assert reservation.status == "expired"
    assert key.cost_reserved_eur == Decimal("0E-9")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("0")
    assert usage_repo.records[0]["actual_cost_eur"] == Decimal("0")
    assert usage_repo.records[0]["error_type"] == "stale_quota_reservation"
    assert "sk-slaif-secretvalue" not in str(usage_repo.records[0]["error_message"])
    assert "messages" not in usage_repo.records[0]
    assert audit_repo.records[0]["action"] == "quota_reservation_expired"
    assert "sk-slaif-secretvalue" not in str(audit_repo.records[0]["note"])


@pytest.mark.asyncio
async def test_execute_does_not_create_duplicate_ledger_for_existing_request_id() -> None:
    usage_repo = FakeUsageRepo()
    service, reservation, _, _, _ = _service(usage_repo=usage_repo)
    usage_repo.existing_request_ids.add(reservation.request_id)

    result = await service.reconcile_expired_pending_reservation(
        reservation.id,
        now=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )

    assert result.ledger_created is False
    assert usage_repo.records == []


@pytest.mark.asyncio
async def test_non_expired_pending_reservation_is_not_reconciled() -> None:
    future = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=uuid.uuid4(),
        request_id="future",
        expires_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    service, reservation, _, _, _ = _service(reservation=future, key=FakeGatewayKey(id=future.gateway_key_id))

    with pytest.raises(ReservationNotExpiredError):
        await service.reconcile_expired_pending_reservation(
            reservation.id,
            now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_non_pending_reservation_is_not_reconciled() -> None:
    released = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=uuid.uuid4(),
        request_id="released",
        status="released",
    )
    service, reservation, _, _, _ = _service(reservation=released, key=FakeGatewayKey(id=released.gateway_key_id))

    with pytest.raises(ReservationNotPendingError):
        await service.reconcile_expired_pending_reservation(
            reservation.id,
            now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_invariant_failure_is_surfaced_and_does_not_write_ledger_or_audit() -> None:
    key = FakeGatewayKey(id=uuid.uuid4(), cost_reserved_eur=Decimal("0"))
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="underflow",
    )
    service, _, _, usage_repo, audit_repo = _service(reservation=reservation, key=key)

    with pytest.raises(ReconciliationInvariantError) as excinfo:
        await service.reconcile_expired_pending_reservation(
            reservation.id,
            now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        )

    assert excinfo.value.param == "cost_reserved_eur"
    assert reservation.status == "pending"
    assert usage_repo.records == []
    assert audit_repo.records == []


@pytest.mark.asyncio
async def test_batch_summary_counts_reconciled_rows() -> None:
    service, _, _, _, _ = _service()

    summary = await service.reconcile_expired_pending_reservations(
        now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        limit=100,
    )

    assert summary.checked_count == 1
    assert summary.candidate_count == 1
    assert summary.reconciled_count == 1
    assert summary.skipped_count == 0
    assert summary.results[0].new_status == "expired"


@pytest.mark.asyncio
async def test_batch_reconciliation_fails_on_invariant_error() -> None:
    key = FakeGatewayKey(id=uuid.uuid4(), cost_reserved_eur=Decimal("0"))
    reservation = FakeReservation(
        id=uuid.uuid4(),
        gateway_key_id=key.id,
        request_id="underflow",
    )
    service, _, _, _, _ = _service(reservation=reservation, key=key)

    with pytest.raises(ReconciliationInvariantError):
        await service.reconcile_expired_pending_reservations(
            now=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=100,
        )
