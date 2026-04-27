from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services import accounting
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.accounting_errors import (
    ActualCostExceededReservationError,
    ReservationAlreadyFinalizedError,
)
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError


@dataclass
class FakeKeyRow:
    id: uuid.UUID
    cost_reserved_eur: Decimal = Decimal("0.300000000")
    tokens_reserved_total: int = 200
    requests_reserved_total: int = 1
    cost_used_eur: Decimal = Decimal("0")
    tokens_used_total: int = 0
    requests_used_total: int = 0
    last_used_at: datetime | None = None


@dataclass
class FakeReservationRow:
    id: uuid.UUID
    gateway_key_id: uuid.UUID
    request_id: str = "req_1"
    endpoint: str = "/v1/chat/completions"
    requested_model: str = "classroom-cheap"
    reserved_cost_eur: Decimal = Decimal("0.300000000")
    reserved_tokens: int = 200
    reserved_requests: int = 1
    status: str = "pending"
    created_at: datetime = datetime(2026, 4, 25, tzinfo=UTC)
    finalized_at: datetime | None = None
    released_at: datetime | None = None


class FakeGatewayKeysRepository:
    def __init__(self, row: FakeKeyRow) -> None:
        self.row = row
        self.lock_calls: list[uuid.UUID] = []
        self.commits = 0

    async def get_gateway_key_by_id_for_quota_update(self, gateway_key_id):
        self.lock_calls.append(gateway_key_id)
        return self.row

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
        if gateway_key.tokens_reserved_total < reserved_tokens_total:
            raise QuotaCounterInvariantError(param="tokens_reserved_total")
        if gateway_key.requests_reserved_total < reserved_requests_total:
            raise QuotaCounterInvariantError(param="requests_reserved_total")
        gateway_key.cost_reserved_eur -= reserved_cost_eur
        gateway_key.tokens_reserved_total -= reserved_tokens_total
        gateway_key.requests_reserved_total -= reserved_requests_total
        gateway_key.cost_used_eur += actual_cost_eur
        gateway_key.tokens_used_total += actual_tokens_total
        gateway_key.requests_used_total += actual_requests_total
        gateway_key.last_used_at = last_used_at
        return gateway_key


class FakeQuotaReservationsRepository:
    def __init__(self, row: FakeReservationRow) -> None:
        self.row = row
        self.commits = 0

    async def get_reservation_by_id_for_update(self, reservation_id):
        return self.row if reservation_id == self.row.id else None

    async def get_reservation_by_id(self, reservation_id):
        return self.row if reservation_id == self.row.id else None

    async def mark_pending_reservation_finalized(self, reservation, *, finalized_at):
        reservation.status = "finalized"
        reservation.finalized_at = finalized_at
        return reservation


class FakeUsageLedgerRepository:
    def __init__(self) -> None:
        self.success_calls: list[dict[str, object]] = []
        self.provider_completed_calls: list[dict[str, object]] = []
        self.rows: dict[uuid.UUID, SimpleNamespace] = {}
        self.commits = 0

    async def create_success_record(self, **kwargs):
        self.success_calls.append(kwargs)
        row = SimpleNamespace(id=uuid.uuid4(), accounting_status="finalized", **kwargs)
        self.rows[row.id] = row
        return row

    async def get_usage_record_by_request_id(self, request_id):
        return next(
            (row for row in self.rows.values() if row.request_id == request_id),
            None,
        )

    async def get_usage_record_by_id(self, usage_id):
        return self.rows.get(usage_id)

    async def create_provider_completed_record(self, **kwargs):
        self.provider_completed_calls.append(kwargs)
        row = SimpleNamespace(id=uuid.uuid4(), accounting_status="pending", success=None, **kwargs)
        self.rows[row.id] = row
        return row

    async def mark_provider_completed_record_finalized(
        self,
        usage_ledger_id,
        *,
        http_status,
        response_metadata,
        finished_at,
        latency_ms,
    ):
        row = self.rows[usage_ledger_id]
        row.success = True
        row.accounting_status = "finalized"
        row.http_status = http_status
        row.error_type = None
        row.error_message = None
        row.response_metadata = response_metadata
        row.finished_at = finished_at
        row.latency_ms = latency_ms
        return row

    async def mark_provider_completed_record_finalization_failed(
        self,
        usage_ledger_id,
        *,
        error_type,
        error_message,
        response_metadata,
        finished_at,
        latency_ms,
    ):
        row = self.rows[usage_ledger_id]
        row.success = None
        row.accounting_status = "failed"
        row.error_type = error_type
        row.error_message = error_message
        row.response_metadata = response_metadata
        row.finished_at = finished_at
        row.latency_ms = latency_ms
        return row


def _auth(gateway_key_id: uuid.UUID) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key_id,
        owner_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        public_key_id="public",
        status="active",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "classroom-cheap", "messages": [], "max_completion_tokens": 100},
        requested_output_tokens=100,
        effective_output_tokens=100,
        estimated_input_tokens=100,
        injected_default_output_tokens=False,
    )


def _estimate() -> ChatCostEstimate:
    return ChatCostEstimate(
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        native_currency="EUR",
        estimated_input_tokens=100,
        estimated_output_tokens=100,
        estimated_input_cost_native=Decimal("0.100000000"),
        estimated_output_cost_native=Decimal("0.200000000"),
        estimated_total_cost_native=Decimal("0.300000000"),
        estimated_total_cost_eur=Decimal("0.300000000"),
        pricing_rule_id=None,
        fx_rate_id=None,
    )


def _response() -> ProviderResponse:
    return ProviderResponse(
        provider="openai",
        upstream_model="gpt-4.1-mini",
        status_code=200,
        json_body={"id": "chatcmpl_1"},
        upstream_request_id="upstream_req_1",
        usage=ProviderUsage(
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            other_usage={"prompt_tokens": 50, "prompt": "secret", "completion": "secret"},
        ),
    )


def _service():
    key = FakeKeyRow(id=uuid.uuid4())
    reservation = FakeReservationRow(id=uuid.uuid4(), gateway_key_id=key.id)
    key_repo = FakeGatewayKeysRepository(key)
    quota_repo = FakeQuotaReservationsRepository(reservation)
    usage_repo = FakeUsageLedgerRepository()
    return (
        AccountingService(
            gateway_keys_repository=key_repo,
            quota_reservations_repository=quota_repo,
            usage_ledger_repository=usage_repo,
        ),
        key,
        reservation,
        key_repo,
        quota_repo,
        usage_repo,
    )


@pytest.mark.asyncio
async def test_finalize_successful_response_moves_counters_and_writes_ledger() -> None:
    service, key, reservation, key_repo, quota_repo, usage_repo = _service()

    result = await service.finalize_successful_response(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        _response(),
        request_id="req_1",
        started_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 25, 12, 0, 1, tzinfo=UTC),
    )

    assert result.accounting_status == "finalized"
    assert result.actual_cost_eur == Decimal("0.1000000000")
    assert result.prompt_tokens == 50
    assert result.completion_tokens == 25
    assert result.total_tokens == 75
    assert reservation.status == "finalized"
    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("0.1000000000")
    assert key.tokens_used_total == 75
    assert key.requests_used_total == 1
    assert usage_repo.success_calls[0]["upstream_request_id"] == "upstream_req_1"
    assert usage_repo.success_calls[0]["actual_cost_eur"] == Decimal("0.1000000000")
    assert usage_repo.success_calls[0]["usage_raw"] == {"prompt_tokens": 50}
    assert "provider_api_key" not in usage_repo.success_calls[0]
    assert key_repo.commits == 0
    assert quota_repo.commits == 0
    assert usage_repo.commits == 0


@pytest.mark.asyncio
async def test_provider_completed_record_can_be_finalized_without_duplicate_ledger() -> None:
    service, key, reservation, _, _, usage_repo = _service()

    record = await service.record_provider_completed_before_finalization(
        reservation.id,
        _auth(key.id),
        _route(),
        _estimate(),
        _response(),
        request_id="req_1",
        streaming=True,
        started_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )
    result = await service.finalize_successful_response(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        _response(),
        request_id="req_1",
        streaming=True,
        provider_completed_usage_ledger_id=record.usage_ledger_id,
        finished_at=datetime(2026, 4, 25, 12, 0, 1, tzinfo=UTC),
    )

    row = usage_repo.rows[record.usage_ledger_id]
    assert result.usage_ledger_id == record.usage_ledger_id
    assert result.accounting_status == "finalized"
    assert row.accounting_status == "finalized"
    assert row.success is True
    assert row.response_metadata["needs_reconciliation"] is False
    assert row.response_metadata["recovery_state"] == "finalized"
    assert usage_repo.success_calls == []
    assert len(usage_repo.provider_completed_calls) == 1
    assert key.tokens_used_total == 75
    assert reservation.status == "finalized"


@pytest.mark.asyncio
async def test_provider_completed_finalization_failure_marks_recovery_record() -> None:
    service, key, reservation, _, _, usage_repo = _service()
    key.cost_reserved_eur = Decimal("0")

    record = await service.record_provider_completed_before_finalization(
        reservation.id,
        _auth(key.id),
        _route(),
        _estimate(),
        _response(),
        request_id="req_1",
        streaming=True,
    )

    with pytest.raises(QuotaCounterInvariantError):
        await service.finalize_successful_response(
            reservation.id,
            _auth(key.id),
            _route(),
            _policy(),
            _estimate(),
            _response(),
            request_id="req_1",
            streaming=True,
            provider_completed_usage_ledger_id=record.usage_ledger_id,
        )
    recovery = await service.mark_provider_completed_finalization_failed(
        record.usage_ledger_id,
        reservation.id,
        QuotaCounterInvariantError(param="cost_reserved_eur"),
    )

    row = usage_repo.rows[record.usage_ledger_id]
    assert recovery.needs_reconciliation is True
    assert row.accounting_status == "failed"
    assert row.success is None
    assert row.error_type == "accounting_finalization_failed"
    assert row.response_metadata["needs_reconciliation"] is True
    assert row.response_metadata["recovery_state"] == "provider_completed_finalization_failed"
    assert row.actual_cost_eur == Decimal("0.1000000000")
    assert reservation.status == "pending"


@pytest.mark.asyncio
async def test_finalize_rejects_actual_usage_beyond_reservation() -> None:
    service, key, reservation, *_ = _service()
    reservation.reserved_tokens = 10

    with pytest.raises(ActualCostExceededReservationError):
        await service.finalize_successful_response(
            reservation.id,
            _auth(key.id),
            _route(),
            _policy(),
            _estimate(),
            _response(),
            request_id="req_1",
        )


@pytest.mark.asyncio
async def test_double_finalization_fails_before_counter_mutation() -> None:
    service, key, reservation, *_ = _service()

    await service.finalize_successful_response(
        reservation.id,
        _auth(key.id),
        _route(),
        _policy(),
        _estimate(),
        _response(),
        request_id="req_1",
    )

    with pytest.raises(ReservationAlreadyFinalizedError):
        await service.finalize_successful_response(
            reservation.id,
            _auth(key.id),
            _route(),
            _policy(),
            _estimate(),
            _response(),
            request_id="req_2",
        )

    assert key.cost_reserved_eur == Decimal("0")
    assert key.tokens_reserved_total == 0
    assert key.requests_reserved_total == 0
    assert key.cost_used_eur == Decimal("0.1000000000")
    assert key.tokens_used_total == 75
    assert key.requests_used_total == 1


@pytest.mark.asyncio
async def test_finalize_raises_if_reserved_counters_would_underflow() -> None:
    service, key, reservation, *_ = _service()
    key.cost_reserved_eur = Decimal("0")

    with pytest.raises(QuotaCounterInvariantError) as excinfo:
        await service.finalize_successful_response(
            reservation.id,
            _auth(key.id),
            _route(),
            _policy(),
            _estimate(),
            _response(),
            request_id="req_1",
        )

    assert excinfo.value.param == "cost_reserved_eur"
    assert reservation.status == "pending"
    assert key.cost_used_eur == Decimal("0")
    assert key.tokens_used_total == 0
    assert key.requests_used_total == 0


def test_accounting_service_has_no_provider_or_runtime_side_effect_imports() -> None:
    source = inspect.getsource(accounting)

    forbidden = (
        "httpx",
        "OpenAIProviderAdapter",
        "OpenRouterProviderAdapter",
        "aiosmtplib",
        "celery",
        "redis",
        "fastapi",
        "create_async_engine",
        ".commit(",
    )
    for text in forbidden:
        assert text not in source
