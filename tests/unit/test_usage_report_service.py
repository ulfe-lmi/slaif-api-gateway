from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.schemas.usage import UsageReportFilters
from slaif_gateway.services.usage_report_service import UsageReportService


KEY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OWNER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
COHORT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class FakeUsageRow:
    request_id: str
    provider: str
    requested_model: str
    resolved_model: str
    success: bool | None
    created_at: datetime
    gateway_key_id: uuid.UUID = KEY_ID
    owner_id: uuid.UUID | None = OWNER_ID
    cohort_id: uuid.UUID | None = COHORT_ID
    owner_email_snapshot: str | None = "student@example.org"
    owner_name_snapshot: str | None = "Demo"
    owner_surname_snapshot: str | None = "Student"
    cohort_name_snapshot: str | None = "demo-cohort"
    endpoint: str = "/v1/chat/completions"
    streaming: bool = False
    accounting_status: str = "finalized"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_eur: Decimal | None = None
    actual_cost_eur: Decimal | None = None
    native_currency: str | None = "EUR"
    upstream_request_id: str | None = None
    response_metadata: dict[str, object] = field(default_factory=dict)


class FakeUsageRepository:
    def __init__(self, rows: list[FakeUsageRow]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def list_usage_records(self, **kwargs: object) -> list[FakeUsageRow]:
        self.calls.append(kwargs)
        rows = list(self.rows)
        if kwargs.get("start_at") is not None:
            rows = [row for row in rows if row.created_at >= kwargs["start_at"]]
        if kwargs.get("end_at") is not None:
            rows = [row for row in rows if row.created_at <= kwargs["end_at"]]
        if kwargs.get("provider") is not None:
            rows = [row for row in rows if row.provider == kwargs["provider"]]
        if kwargs.get("model") is not None:
            rows = [
                row
                for row in rows
                if row.requested_model == kwargs["model"] or row.resolved_model == kwargs["model"]
            ]
        if kwargs.get("owner_id") is not None:
            rows = [row for row in rows if row.owner_id == kwargs["owner_id"]]
        if kwargs.get("cohort_id") is not None:
            rows = [row for row in rows if row.cohort_id == kwargs["cohort_id"]]
        if kwargs.get("gateway_key_id") is not None:
            rows = [row for row in rows if row.gateway_key_id == kwargs["gateway_key_id"]]
        rows.sort(key=lambda row: row.created_at, reverse=not kwargs.get("ascending", False))
        if kwargs.get("limit") is not None:
            rows = rows[: int(kwargs["limit"])]
        return rows


def _rows() -> list[FakeUsageRow]:
    return [
        FakeUsageRow(
            request_id="req-1",
            provider="openai",
            requested_model="gpt-test-mini",
            resolved_model="gpt-test-mini",
            success=True,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cached_tokens=2,
            reasoning_tokens=1,
            estimated_cost_eur=Decimal("0.010000000"),
            actual_cost_eur=Decimal("0.008000000"),
            response_metadata={"provider_reported_cost": "0.007"},
            created_at=BASE_TIME,
        ),
        FakeUsageRow(
            request_id="req-2",
            provider="openai",
            requested_model="gpt-test-mini",
            resolved_model="gpt-test-mini",
            success=False,
            prompt_tokens=3,
            completion_tokens=0,
            total_tokens=3,
            estimated_cost_eur=Decimal("0.002000000"),
            actual_cost_eur=None,
            accounting_status="failed",
            created_at=BASE_TIME + timedelta(hours=1),
        ),
        FakeUsageRow(
            request_id="req-3",
            provider="local-test",
            requested_model="demo-model",
            resolved_model="demo-model",
            success=True,
            prompt_tokens=7,
            completion_tokens=4,
            total_tokens=11,
            estimated_cost_eur=Decimal("0.004000000"),
            actual_cost_eur=Decimal("0.003000000"),
            owner_id=None,
            cohort_id=None,
            created_at=BASE_TIME + timedelta(days=1),
        ),
    ]


def _service(rows: list[FakeUsageRow]) -> tuple[UsageReportService, FakeUsageRepository]:
    repo = FakeUsageRepository(rows)
    return UsageReportService(usage_ledger_repository=repo), repo


def test_summarizes_by_provider_model_and_aggregates_counts_tokens_and_costs() -> None:
    service, _ = _service(_rows())

    rows = service_run(service.summarize_usage(group_by="provider_model"))
    openai = next(row for row in rows if row.grouping_key == "openai:gpt-test-mini")

    assert openai.request_count == 2
    assert openai.success_count == 1
    assert openai.failure_count == 1
    assert openai.prompt_tokens == 13
    assert openai.completion_tokens == 5
    assert openai.total_tokens == 18
    assert openai.cached_tokens == 2
    assert openai.reasoning_tokens == 1
    assert openai.estimated_cost_eur == Decimal("0.012000000")
    assert openai.actual_cost_eur == Decimal("0.008000000")
    assert openai.provider_reported_cost == Decimal("0.007")
    assert openai.first_seen_at == BASE_TIME
    assert openai.last_seen_at == BASE_TIME + timedelta(hours=1)


def test_summarizes_supported_groupings() -> None:
    service, _ = _service(_rows())

    expected_keys = {
        "provider": "openai",
        "model": "gpt-test-mini",
        "provider_model": "openai:gpt-test-mini",
        "owner": str(OWNER_ID),
        "cohort": str(COHORT_ID),
        "key": str(KEY_ID),
        "day": BASE_TIME.date().isoformat(),
    }
    for group_by, expected_key in expected_keys.items():
        rows = service_run(service.summarize_usage(group_by=group_by))
        assert any(row.grouping_key == expected_key for row in rows)


def test_summarize_applies_filters_and_limit() -> None:
    service, repo = _service(_rows())
    filters = UsageReportFilters(
        start_at=BASE_TIME + timedelta(minutes=30),
        end_at=BASE_TIME + timedelta(days=2),
        provider="openai",
        model="gpt-test-mini",
        owner_id=OWNER_ID,
        cohort_id=COHORT_ID,
        gateway_key_id=KEY_ID,
    )

    rows = service_run(service.summarize_usage(filters=filters, group_by="provider", limit=1))

    assert len(rows) == 1
    assert rows[0].request_count == 1
    assert repo.calls[0]["limit"] is None
    assert repo.calls[0]["ascending"] is True
    assert repo.calls[0]["provider"] == "openai"
    assert repo.calls[0]["model"] == "gpt-test-mini"


def test_export_returns_safe_rows_sorted_ascending_and_respects_limit() -> None:
    service, repo = _service(_rows())

    exported = service_run(service.export_usage(limit=2))

    assert [row.request_id for row in exported] == ["req-1", "req-2"]
    assert exported[0].gateway_key_id == KEY_ID
    assert exported[0].actual_cost_eur == Decimal("0.008000000")
    assert not hasattr(exported[0], "prompt")
    assert not hasattr(exported[0], "completion")
    assert not hasattr(exported[0], "token_hash")
    assert repo.calls[0]["limit"] == 2
    assert repo.calls[0]["ascending"] is True


def service_run(coro):
    import asyncio

    return asyncio.run(coro)
