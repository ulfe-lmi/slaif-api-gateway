from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.reconciliation import (
    ProviderCompletedReconciliationCandidate,
    ProviderCompletedReconciliationResult,
    ProviderCompletedReconciliationSummary,
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.workers import tasks_reconciliation


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction()


class _FakeSessionFactory:
    def __call__(self) -> _FakeSession:
        return _FakeSession()


class _FakeReconciliationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.expired_candidate = StaleReservationCandidate(
            reservation_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            request_id="req-safe",
            status="pending",
            reserved_cost_eur=Decimal("0.300000000"),
            reserved_tokens=200,
            reserved_requests=1,
            expires_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.provider_candidate = ProviderCompletedReconciliationCandidate(
            usage_ledger_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            reservation_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            request_id="req-provider",
            provider="openai",
            requested_model="gpt-test-mini",
            resolved_model="gpt-test-mini",
            endpoint="chat.completions",
            prompt_tokens=5,
            completion_tokens=6,
            total_tokens=11,
            estimated_cost_eur=Decimal("0.300000000"),
            actual_cost_eur=Decimal("0.000011000"),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            recovery_state="provider_completed_finalization_failed",
        )

    async def list_expired_pending_reservations(self, **kwargs):
        self.calls.append(("list_expired", kwargs))
        return [self.expired_candidate]

    async def list_provider_completed_recovery_rows(self, **kwargs):
        self.calls.append(("list_provider_completed", kwargs))
        return [self.provider_candidate]

    async def reconcile_expired_pending_reservations(self, **kwargs):
        self.calls.append(("reconcile_expired", kwargs))
        dry_run = bool(kwargs["dry_run"])
        return ReservationReconciliationSummary(
            checked_count=1,
            candidate_count=1,
            reconciled_count=0 if dry_run else 1,
            skipped_count=0,
            dry_run=dry_run,
            results=[
                ReservationReconciliationResult(
                    reservation_id=self.expired_candidate.reservation_id,
                    gateway_key_id=self.expired_candidate.gateway_key_id,
                    request_id="req-safe",
                    previous_status="pending",
                    new_status="pending" if dry_run else "expired",
                    released_cost_eur=Decimal("0.300000000"),
                    released_tokens=200,
                    released_requests=1,
                    ledger_created=not dry_run,
                    audit_created=not dry_run,
                    dry_run=dry_run,
                )
            ],
        )

    async def reconcile_provider_completed_recovery_rows(self, **kwargs):
        self.calls.append(("reconcile_provider_completed", kwargs))
        dry_run = bool(kwargs["dry_run"])
        return ProviderCompletedReconciliationSummary(
            checked_count=1,
            candidate_count=1,
            reconciled_count=0 if dry_run else 1,
            skipped_count=0,
            dry_run=dry_run,
            results=[
                ProviderCompletedReconciliationResult(
                    usage_ledger_id=self.provider_candidate.usage_ledger_id,
                    reservation_id=self.provider_candidate.reservation_id,
                    gateway_key_id=self.provider_candidate.gateway_key_id,
                    request_id="req-provider",
                    previous_accounting_status="failed",
                    new_accounting_status="failed" if dry_run else "finalized",
                    reservation_status="pending" if dry_run else "finalized",
                    used_cost_eur=Decimal("0.000011000"),
                    used_tokens=11,
                    reconciled=not dry_run,
                    dry_run=dry_run,
                )
            ],
        )


@pytest.fixture
def fake_task_dependencies(monkeypatch):
    engine = _FakeEngine()
    service = _FakeReconciliationService()
    monkeypatch.setattr(tasks_reconciliation, "create_engine_from_settings", lambda settings: engine)
    monkeypatch.setattr(
        tasks_reconciliation,
        "create_sessionmaker_from_engine",
        lambda engine: _FakeSessionFactory(),
    )
    monkeypatch.setattr(tasks_reconciliation, "_service", lambda session: service)
    return engine, service


@pytest.mark.asyncio
async def test_inspect_reconciliation_backlog_lists_without_mutating(fake_task_dependencies) -> None:
    engine, service = fake_task_dependencies

    result = await tasks_reconciliation._inspect_reconciliation_backlog(
        settings=Settings(DATABASE_URL="postgresql+asyncpg://test/test"),
    )

    assert result["status"] == "success"
    assert result["dry_run"] is True
    assert result["expired_reservations"]["candidate_count"] == 1
    assert result["provider_completed"]["candidate_count"] == 1
    assert [name for name, _ in service.calls] == ["list_expired", "list_provider_completed"]
    assert engine.disposed is True
    serialized = str(result)
    assert "token_hash" not in serialized
    assert "encrypted_payload" not in serialized
    assert "nonce" not in serialized
    assert "sk-slaif-" not in serialized
    assert "sensitive prompt" not in serialized


@pytest.mark.asyncio
async def test_expired_reservation_task_forces_dry_run_without_auto_execute(
    fake_task_dependencies,
) -> None:
    _, service = fake_task_dependencies

    result = await tasks_reconciliation._reconcile_expired_reservations(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test/test",
            RECONCILIATION_DRY_RUN=False,
            RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=False,
        ),
        dry_run=False,
    )

    assert result["dry_run"] is True
    assert result["reconciled_count"] == 0
    assert service.calls[-1][0] == "reconcile_expired"
    assert service.calls[-1][1]["dry_run"] is True


@pytest.mark.asyncio
async def test_expired_reservation_task_executes_only_with_auto_execute(
    fake_task_dependencies,
) -> None:
    _, service = fake_task_dependencies

    result = await tasks_reconciliation._reconcile_expired_reservations(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test/test",
            RECONCILIATION_DRY_RUN=False,
            RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=True,
        ),
        dry_run=False,
        reason="scheduled repair",
    )

    assert result["dry_run"] is False
    assert result["reconciled_count"] == 1
    assert service.calls[-1][1]["dry_run"] is False
    assert service.calls[-1][1]["reason"] == "scheduled repair"


@pytest.mark.asyncio
async def test_provider_completed_task_forces_dry_run_without_auto_execute(
    fake_task_dependencies,
) -> None:
    _, service = fake_task_dependencies

    result = await tasks_reconciliation._reconcile_provider_completed(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test/test",
            RECONCILIATION_DRY_RUN=False,
            RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=False,
        ),
        dry_run=False,
    )

    assert result["dry_run"] is True
    assert result["reconciled_count"] == 0
    assert service.calls[-1][0] == "reconcile_provider_completed"
    assert service.calls[-1][1]["dry_run"] is True


@pytest.mark.asyncio
async def test_provider_completed_task_executes_only_with_auto_execute(
    fake_task_dependencies,
) -> None:
    _, service = fake_task_dependencies

    result = await tasks_reconciliation._reconcile_provider_completed(
        settings=Settings(
            DATABASE_URL="postgresql+asyncpg://test/test",
            RECONCILIATION_DRY_RUN=False,
            RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=True,
        ),
        dry_run=False,
    )

    assert result["dry_run"] is False
    assert result["reconciled_count"] == 1
    assert service.calls[-1][1]["dry_run"] is False
    serialized = str(result)
    assert "provider-key" not in serialized
    assert "prompt" not in serialized
    assert "completion" not in serialized
