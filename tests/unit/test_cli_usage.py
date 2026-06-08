from __future__ import annotations

import csv
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import usage as usage_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.usage import UsageExportRow, UsageSummaryRow
from slaif_gateway.services.chat_live_burn_telemetry import ChatLiveBurnAggregate

runner = CliRunner()
KEY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OWNER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
COHORT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _summary_row() -> UsageSummaryRow:
    return UsageSummaryRow(
        grouping_key="openai:gpt-test-mini",
        grouping_label="openai / gpt-test-mini",
        request_count=2,
        success_count=1,
        failure_count=1,
        prompt_tokens=13,
        completion_tokens=5,
        total_tokens=18,
        cached_tokens=2,
        reasoning_tokens=1,
        estimated_cost_eur=Decimal("0.012000000"),
        actual_cost_eur=Decimal("0.008000000"),
        provider_reported_cost=Decimal("0.007000000"),
        first_seen_at=CREATED_AT,
        last_seen_at=CREATED_AT,
    )


def _export_row() -> UsageExportRow:
    return UsageExportRow(
        created_at=CREATED_AT,
        request_id="req-safe",
        gateway_key_id=KEY_ID,
        owner_id=OWNER_ID,
        cohort_id=COHORT_ID,
        provider="openai",
        requested_model="gpt-test-mini",
        resolved_model="gpt-test-mini",
        endpoint="/v1/chat/completions",
        streaming=False,
        success=True,
        accounting_status="finalized",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cached_tokens=2,
        reasoning_tokens=1,
        estimated_cost_eur=Decimal("0.010000000"),
        actual_cost_eur=Decimal("0.008000000"),
        native_currency="EUR",
        upstream_request_id="upstream-safe",
        chat_live_burn_triggered=True,
        chat_live_burn_stop_reason="tokens",
        chat_live_burn_estimated_tokens_at_stop=142,
        chat_live_burn_estimated_cost_eur_at_stop=Decimal("0.220000000"),
        chat_live_burn_cost_margin_eur=Decimal("0.010000000"),
        chat_live_burn_token_margin=50,
        chat_live_burn_final_provider_usage_available=False,
    )


def test_usage_help_registers_commands() -> None:
    result = runner.invoke(app, ["usage", "--help"])

    assert result.exit_code == 0
    assert "summarize" in result.stdout
    assert "export" in result.stdout
    assert "live-burn-summary" in result.stdout


def test_summarize_outputs_safe_text(monkeypatch) -> None:
    async def fake_summarize_usage(**kwargs: object) -> list[UsageSummaryRow]:
        assert kwargs["group_by"] == "provider_model"
        return [_summary_row()]

    monkeypatch.setattr(usage_cli, "_summarize_usage", fake_summarize_usage)

    result = runner.invoke(app, ["usage", "summarize"])

    assert result.exit_code == 0
    assert "openai:gpt-test-mini" in result.stdout
    assert "0.008000000" in result.stdout
    assert "token_hash" not in result.stdout
    assert "prompt secret" not in result.stdout


def test_summarize_json_outputs_valid_json_and_serializes_decimal(monkeypatch) -> None:
    async def fake_summarize_usage(**kwargs: object) -> list[UsageSummaryRow]:
        return [_summary_row()]

    monkeypatch.setattr(usage_cli, "_summarize_usage", fake_summarize_usage)

    result = runner.invoke(app, ["usage", "summarize", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    row = payload["usage_summary"][0]
    assert row["actual_cost_eur"] == "0.008000000"
    assert row["first_seen_at"] == CREATED_AT.isoformat()


def test_summarize_invalid_group_by_fails() -> None:
    result = runner.invoke(app, ["usage", "summarize", "--group-by", "provider_key_secret"])

    assert result.exit_code == 1
    assert "--group-by must be one of" in result.stderr


def test_summarize_parses_filters(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_summarize_usage(**kwargs: object) -> list[UsageSummaryRow]:
        seen.update(kwargs)
        return []

    monkeypatch.setattr(usage_cli, "_summarize_usage", fake_summarize_usage)

    result = runner.invoke(
        app,
        [
            "usage",
            "summarize",
            "--start-at",
            "2026-01-01T00:00:00Z",
            "--end-at",
            "2026-01-02T00:00:00Z",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--owner-id",
            str(OWNER_ID),
            "--cohort-id",
            str(COHORT_ID),
            "--key-id",
            str(KEY_ID),
            "--group-by",
            "key",
            "--limit",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert seen["group_by"] == "key"
    assert seen["limit"] == 7
    filters = seen["filters"]
    assert filters.provider == "openai"
    assert filters.model == "gpt-test-mini"
    assert filters.owner_id == OWNER_ID
    assert filters.cohort_id == COHORT_ID
    assert filters.gateway_key_id == KEY_ID


def test_export_csv_stdout_uses_stable_columns(monkeypatch) -> None:
    async def fake_export_usage(**kwargs: object) -> list[UsageExportRow]:
        assert kwargs["limit"] is None
        return [_export_row()]

    monkeypatch.setattr(usage_cli, "_export_usage", fake_export_usage)

    result = runner.invoke(app, ["usage", "export", "--format", "csv"])

    assert result.exit_code == 0
    rows = list(csv.DictReader(result.stdout.splitlines()))
    assert rows[0]["request_id"] == "req-safe"
    assert rows[0]["actual_cost_eur"] == "0.008000000"
    assert rows[0]["chat_live_burn_triggered"] == "true"
    assert rows[0]["chat_live_burn_stop_reason"] == "tokens"
    assert rows[0]["chat_live_burn_estimated_tokens_at_stop"] == "142"
    assert list(rows[0]) == usage_cli._EXPORT_COLUMNS


def test_export_json_stdout_outputs_valid_json(monkeypatch) -> None:
    async def fake_export_usage(**kwargs: object) -> list[UsageExportRow]:
        return [_export_row()]

    monkeypatch.setattr(usage_cli, "_export_usage", fake_export_usage)

    result = runner.invoke(app, ["usage", "export", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["gateway_key_id"] == str(KEY_ID)
    assert payload[0]["actual_cost_eur"] == "0.008000000"
    assert payload[0]["chat_live_burn_final_provider_usage_available"] is False


def test_live_burn_summary_outputs_safe_text(monkeypatch) -> None:
    async def fake_summarize_chat_live_burn(**kwargs: object) -> ChatLiveBurnAggregate:
        return ChatLiveBurnAggregate(
            triggered_total=12,
            stop_reason_tokens=8,
            stop_reason_cost=3,
            stop_reason_both=1,
            stop_reason_unknown=0,
            final_provider_usage_available=5,
            final_provider_usage_missing=7,
            estimated_tokens_at_stop_sum=1234,
            estimated_cost_eur_at_stop_sum=Decimal("0.340000000"),
        )

    monkeypatch.setattr(usage_cli, "_summarize_chat_live_burn", fake_summarize_chat_live_burn)

    result = runner.invoke(app, ["usage", "live-burn-summary"])

    assert result.exit_code == 0
    assert "Chat streaming live-burn summary" in result.stdout
    assert "triggered_total: 12" in result.stdout
    assert "stop_reason_tokens: 8" in result.stdout
    assert "raw_response_body" not in result.stdout


def test_live_burn_summary_json_outputs_safe_payload(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_summarize_chat_live_burn(**kwargs: object) -> ChatLiveBurnAggregate:
        seen.update(kwargs)
        return ChatLiveBurnAggregate(
            triggered_total=1,
            stop_reason_tokens=0,
            stop_reason_cost=1,
            stop_reason_both=0,
            stop_reason_unknown=0,
            final_provider_usage_available=1,
            final_provider_usage_missing=0,
            estimated_tokens_at_stop_sum=10,
            estimated_cost_eur_at_stop_sum=Decimal("0.100000000"),
        )

    monkeypatch.setattr(usage_cli, "_summarize_chat_live_burn", fake_summarize_chat_live_burn)

    result = runner.invoke(
        app,
        [
            "usage",
            "live-burn-summary",
            "--json",
            "--provider",
            "openai",
            "--key-id",
            str(KEY_ID),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)["chat_streaming_live_burn_summary"]
    assert payload["triggered_total"] == 1
    assert payload["estimated_cost_eur_at_stop_sum"] == "0.100000000"
    filters = seen["filters"]
    assert filters.provider == "openai"
    assert filters.gateway_key_id == KEY_ID


def test_export_output_file_and_existing_file_behavior(tmp_path, monkeypatch) -> None:
    async def fake_export_usage(**kwargs: object) -> list[UsageExportRow]:
        return [_export_row()]

    monkeypatch.setattr(usage_cli, "_export_usage", fake_export_usage)
    output_path = tmp_path / "usage.csv"

    first = runner.invoke(app, ["usage", "export", "--output", str(output_path)])
    second = runner.invoke(app, ["usage", "export", "--output", str(output_path)])
    third = runner.invoke(app, ["usage", "export", "--output", str(output_path), "--force"])

    assert first.exit_code == 0
    assert "req-safe" in output_path.read_text(encoding="utf-8")
    assert second.exit_code == 1
    assert "already exists" in second.stderr
    assert third.exit_code == 0


def test_export_invalid_format_fails() -> None:
    result = runner.invoke(app, ["usage", "export", "--format", "xlsx"])

    assert result.exit_code == 1
    assert "--format must be csv or json" in result.stderr


def test_invalid_datetime_uuid_and_limit_fail() -> None:
    bad_datetime = runner.invoke(app, ["usage", "summarize", "--start-at", "not-a-date"])
    bad_uuid = runner.invoke(app, ["usage", "summarize", "--owner-id", "not-a-uuid"])
    bad_limit = runner.invoke(app, ["usage", "summarize", "--limit", "0"])

    assert bad_datetime.exit_code == 1
    assert "ISO datetime" in bad_datetime.stderr
    assert bad_uuid.exit_code == 1
    assert "valid UUID" in bad_uuid.stderr
    assert bad_limit.exit_code == 1
    assert "--limit must be positive" in bad_limit.stderr


def test_missing_database_url_fails_cleanly(monkeypatch) -> None:
    from slaif_gateway.config import get_settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    try:
        result = runner.invoke(app, ["usage", "summarize"])
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 1
    assert "DATABASE_URL is not configured" in result.stderr
