from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import quota as quota_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.reconciliation import (
    ProviderCompletedReconciliationCandidate,
    ProviderCompletedReconciliationResult,
    ProviderCompletedReconciliationSummary,
)
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryMetadataMissingError,
)

runner = CliRunner()


def _candidate() -> ProviderCompletedReconciliationCandidate:
    return ProviderCompletedReconciliationCandidate(
        usage_ledger_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        reservation_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        gateway_key_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        request_id="req-provider-completed",
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


def _result(*, dry_run: bool) -> ProviderCompletedReconciliationResult:
    return ProviderCompletedReconciliationResult(
        usage_ledger_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        reservation_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        gateway_key_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        request_id="req-provider-completed",
        previous_accounting_status="failed",
        new_accounting_status="failed" if dry_run else "finalized",
        reservation_status="pending" if dry_run else "finalized",
        used_cost_eur=Decimal("0.000011000"),
        used_tokens=11,
        reconciled=not dry_run,
        dry_run=dry_run,
    )


def test_quota_help_includes_provider_completed_recovery_commands() -> None:
    result = runner.invoke(app, ["quota", "--help"])

    assert result.exit_code == 0
    assert "list-provider-completed-recovery" in result.stdout
    assert "reconcile-provider-completed" in result.stdout


def test_list_provider_completed_recovery_prints_safe_text(monkeypatch) -> None:
    async def fake_list(*, limit, provider, model, gateway_key_id):
        assert limit == 10
        assert provider == "openai"
        assert model == "gpt-test-mini"
        assert gateway_key_id is None
        return [_candidate()]

    monkeypatch.setattr(quota_cli, "_list_provider_completed_recovery", fake_list)

    result = runner.invoke(
        app,
        [
            "quota",
            "list-provider-completed-recovery",
            "--limit",
            "10",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
        ],
    )

    assert result.exit_code == 0
    assert "req-provider-completed" in result.stdout
    assert "provider_completed_finalization_failed" in result.stdout
    assert "token_hash" not in result.stdout
    assert "sk-" not in result.stdout


def test_list_provider_completed_recovery_json_is_valid(monkeypatch) -> None:
    async def fake_list(*, limit, provider, model, gateway_key_id):
        return [_candidate()]

    monkeypatch.setattr(quota_cli, "_list_provider_completed_recovery", fake_list)

    result = runner.invoke(app, ["quota", "list-provider-completed-recovery", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    row = payload["provider_completed_recovery"][0]
    assert row["actual_cost_eur"] == "0.000011000"
    assert row["total_tokens"] == 11


def test_reconcile_provider_completed_defaults_to_dry_run(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_reconcile(**kwargs):
        seen.update(kwargs)
        return ProviderCompletedReconciliationSummary(
            checked_count=1,
            candidate_count=1,
            reconciled_count=0,
            skipped_count=0,
            dry_run=kwargs["dry_run"],
            results=[_result(dry_run=kwargs["dry_run"])],
        )

    monkeypatch.setattr(quota_cli, "_reconcile_provider_completed", fake_reconcile)

    result = runner.invoke(app, ["quota", "reconcile-provider-completed"])

    assert result.exit_code == 0
    assert seen["dry_run"] is True
    assert "dry_run: True" in result.stdout
    assert "reconciled_count: 0" in result.stdout


def test_reconcile_provider_completed_execute_mutates_through_service(monkeypatch) -> None:
    seen: dict[str, object] = {}
    usage_id = uuid.uuid4()

    async def fake_reconcile(**kwargs):
        seen.update(kwargs)
        return _result(dry_run=kwargs["dry_run"])

    monkeypatch.setattr(quota_cli, "_reconcile_provider_completed", fake_reconcile)

    result = runner.invoke(
        app,
        [
            "quota",
            "reconcile-provider-completed",
            "--usage-ledger-id",
            str(usage_id),
            "--execute",
            "--reason",
            "repair",
        ],
    )

    assert result.exit_code == 0
    assert seen["usage_ledger_id"] == usage_id
    assert seen["dry_run"] is False
    assert seen["reason"] == "repair"
    assert "new_accounting_status: finalized" in result.stdout
    assert "Executing provider-completed recovery" in result.stderr


def test_reconcile_provider_completed_rejects_two_ids() -> None:
    result = runner.invoke(
        app,
        [
            "quota",
            "reconcile-provider-completed",
            "--usage-ledger-id",
            str(uuid.uuid4()),
            "--reservation-id",
            str(uuid.uuid4()),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["message"] == "Provide only one of --usage-ledger-id or --reservation-id"


def test_reconcile_provider_completed_domain_error_is_safe(monkeypatch) -> None:
    async def fake_reconcile(**kwargs):
        _ = kwargs
        raise ProviderCompletedRecoveryMetadataMissingError()

    monkeypatch.setattr(quota_cli, "_reconcile_provider_completed", fake_reconcile)

    result = runner.invoke(app, ["quota", "reconcile-provider-completed", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "provider_completed_recovery_metadata_missing"
    assert "secret" not in result.stdout.lower()
