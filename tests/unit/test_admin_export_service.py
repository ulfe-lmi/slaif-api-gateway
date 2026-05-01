from __future__ import annotations

import csv
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from slaif_gateway.services.admin_export_service import (
    AdminCsvExportService,
    build_audit_csv,
    build_usage_csv,
    sanitize_csv_cell,
)


class _FakeUsageRepository:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.seen: dict[str, object] = {}

    async def list_usage_for_admin(self, **kwargs):
        self.seen = kwargs
        return self.rows[: kwargs["limit"]]


class _FakeAuditRepository:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = rows or []
        self.audit_calls: list[dict[str, object]] = []

    async def list_audit_logs_for_admin(self, **kwargs):
        self.seen = kwargs
        return self.rows[: kwargs["limit"]]

    async def add_audit_log(self, **kwargs):
        self.audit_calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())


def _usage_row(**overrides: object) -> object:
    values = {
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "finished_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "request_id": "=req_formula",
        "gateway_key_id": uuid.uuid4(),
        "gateway_key": SimpleNamespace(public_key_id="pub_safe"),
        "owner_id": uuid.uuid4(),
        "owner_email_snapshot": "owner@example.org",
        "institution_id": uuid.uuid4(),
        "cohort_id": uuid.uuid4(),
        "endpoint": "/v1/chat/completions",
        "provider": "openai",
        "requested_model": "gpt-safe",
        "resolved_model": "gpt-safe",
        "streaming": False,
        "accounting_status": "finalized",
        "success": True,
        "http_status": 200,
        "error_type": "none",
        "error_message": "prompt text must not export",
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_eur": Decimal("0.001000000"),
        "actual_cost_eur": Decimal("0.002000000"),
        "native_currency": "EUR",
        "latency_ms": 42,
        "usage_raw": {"prompt": "secret prompt"},
        "response_metadata": {"response_body": "secret completion"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _audit_row(**overrides: object) -> object:
    values = {
        "created_at": datetime(2026, 1, 2, tzinfo=UTC),
        "admin_user_id": uuid.uuid4(),
        "action": "+formula",
        "entity_type": "gateway_key",
        "entity_id": uuid.uuid4(),
        "request_id": "req_audit",
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
        "old_values": {
            "token_hash": "secret-token-hash",
            "encrypted_payload": "secret-payload",
            "prompt": "prompt text must not export",
            "safe": "=formula",
        },
        "new_values": {
            "provider_api_key": "sk-provider-secret-value",
            "session_token": "session-secret",
            "safe_new": "ok",
        },
        "note": "Authorization: Bearer secret-token and prompt text must not export",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _csv_rows(content: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(content)))


def test_sanitize_csv_cell_neutralizes_formula_prefixes() -> None:
    assert sanitize_csv_cell("=cmd") == "'=cmd"
    assert sanitize_csv_cell("+cmd") == "'+cmd"
    assert sanitize_csv_cell("-cmd") == "'-cmd"
    assert sanitize_csv_cell("@cmd") == "'@cmd"
    assert sanitize_csv_cell("\tcmd") == "'\tcmd"
    assert sanitize_csv_cell("\rcmd") == "'\rcmd"


def test_usage_csv_contains_safe_columns_and_excludes_content_and_secrets() -> None:
    content = build_usage_csv([_usage_row()])
    rows = _csv_rows(content)

    assert rows[0]["request_id"] == "'=req_formula"
    assert rows[0]["key_public_id"] == "pub_safe"
    assert rows[0]["actual_cost_eur"] == "0.002000000"
    assert "usage_raw" not in rows[0]
    assert "response_metadata" not in rows[0]
    for forbidden in ("prompt text", "secret prompt", "secret completion", "token_hash", "encrypted_payload"):
        assert forbidden not in content


def test_audit_csv_sanitizes_metadata_and_formula_cells() -> None:
    content = build_audit_csv([_audit_row()])
    rows = _csv_rows(content)

    assert rows[0]["action"] == "'+formula"
    assert "safe_new" in rows[0]["new_values_sanitized"]
    assert "token_hash" not in content
    assert "encrypted_payload" not in content
    assert "provider_api_key" not in content
    assert "session_token" not in content
    assert "sk-provider-secret-value" not in content
    assert "prompt text must not export" not in content
    assert "Authorization: Bearer" not in content


def test_export_service_respects_limits_and_audits_usage_export() -> None:
    usage_repo = _FakeUsageRepository([_usage_row(), _usage_row(request_id="req_two")])
    audit_repo = _FakeAuditRepository()
    service = AdminCsvExportService(usage_ledger_repository=usage_repo, audit_repository=audit_repo)
    actor_id = uuid.uuid4()

    result = _run(
        service.export_usage_csv(
            actor_admin_id=actor_id,
            reason="approved export",
            limit=1,
            provider="openai",
            model="gpt",
        )
    )

    assert result.row_count == 1
    assert usage_repo.seen["provider"] == "openai"
    assert usage_repo.seen["limit"] == 1
    assert audit_repo.audit_calls[0]["action"] == "admin_usage_export_csv"
    assert audit_repo.audit_calls[0]["admin_user_id"] == actor_id
    assert audit_repo.audit_calls[0]["note"] == "approved export"


def test_export_service_audits_audit_export_after_building_csv() -> None:
    audit_repo = _FakeAuditRepository([_audit_row()])
    service = AdminCsvExportService(
        usage_ledger_repository=_FakeUsageRepository([]),
        audit_repository=audit_repo,
    )

    result = _run(
        service.export_audit_csv(
            actor_admin_id=uuid.uuid4(),
            reason="audit review",
            limit=10,
            action="key",
        )
    )

    assert result.row_count == 1
    assert audit_repo.seen["action"] == "key"
    assert audit_repo.audit_calls[0]["action"] == "admin_audit_export_csv"
    assert audit_repo.audit_calls[0]["entity_type"] == "audit_log_export"


def _run(coro):
    import asyncio

    return asyncio.run(coro)
