from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import quota as quota_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.external_tool_fence import ExternalToolFenceProjection
from slaif_gateway.schemas.external_tool_hold import (
    ExternalToolAccountingHoldProjection,
    ExternalToolHoldAction,
    ExternalToolHoldReconciliationResult,
)
from slaif_gateway.schemas.reconciliation import (
    ReservationReconciliationResult,
    ReservationReconciliationSummary,
    StaleReservationCandidate,
)
from slaif_gateway.services.reconciliation_errors import ReservationNotExpiredError

runner = CliRunner()


def _candidate() -> StaleReservationCandidate:
    return StaleReservationCandidate(
        reservation_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        request_id="req-safe",
        status="pending",
        reserved_cost_eur=Decimal("0.300000000"),
        reserved_tokens=200,
        reserved_requests=1,
        expires_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _result(*, dry_run: bool) -> ReservationReconciliationResult:
    return ReservationReconciliationResult(
        reservation_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
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


def test_quota_help_includes_reconciliation_commands() -> None:
    result = runner.invoke(app, ["quota", "--help"])

    assert result.exit_code == 0
    assert "list-external-tool-fences" in result.stdout
    assert "list-expired-reservations" in result.stdout
    assert "reconcile-expired-reservations" in result.stdout
    assert "reconcile-reservation" in result.stdout
    assert "list-external-tool-holds" in result.stdout
    assert "reconcile-external-tool-hold" in result.stdout


def _hold_projection() -> ExternalToolAccountingHoldProjection:
    return ExternalToolAccountingHoldProjection(
        gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        reservation_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        usage_ledger_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        request_id="req-held",
        fence_state="held",
        accounting_status="interrupted",
        reason_code="missing_final_cost",
        evidence_quality="missing",
        held_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
        provider="openai",
        endpoint="/v1/chat/completions",
        requested_model="gpt-test",
        reserved_cost_eur=Decimal("1.2"),
        reserved_tokens=100,
        reserved_requests=1,
        partial_total_tokens=None,
        estimated_cost_eur=None,
    )


def test_list_external_tool_holds_prints_safe_text_and_json(monkeypatch) -> None:
    async def fake_list(*, limit):
        return [_hold_projection()]

    monkeypatch.setattr(quota_cli, "_list_external_tool_holds", fake_list)
    text_result = runner.invoke(app, ["quota", "list-external-tool-holds"])
    json_result = runner.invoke(app, ["quota", "list-external-tool-holds", "--json"])

    assert text_result.exit_code == 0
    assert "req-held" in text_result.stdout
    assert "token_hash" not in text_result.stdout
    assert json.loads(json_result.stdout)["external_tool_holds"][0]["fence_state"] == "held"


def test_list_external_tool_holds_empty_state(monkeypatch) -> None:
    async def fake_list(*, limit):
        return []

    monkeypatch.setattr(quota_cli, "_list_external_tool_holds", fake_list)
    result = runner.invoke(app, ["quota", "list-external-tool-holds"])

    assert result.exit_code == 0
    assert "No external-tool accounting holds found." in result.stdout


def test_external_tool_hold_dry_run_needs_no_actor_or_reason(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_reconcile(request):
        seen["request"] = request
        return ExternalToolHoldReconciliationResult(
            reservation_id=request.reservation_id,
            usage_ledger_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            action=request.action.value,
            executed=False,
            fence_state="held",
            reservation_status="pending",
            accounting_status="interrupted",
            actual_cost_eur=None,
            actual_total_tokens=0,
            success=None,
        )

    monkeypatch.setattr(quota_cli, "_reconcile_external_tool_hold", fake_reconcile)
    result = runner.invoke(
        app,
        [
            "quota",
            "reconcile-external-tool-hold",
            "--reservation-id",
            str(_hold_projection().reservation_id),
            "--action",
            ExternalToolHoldAction.FINALIZE_ACTUAL.value,
            "--actual-cost-eur",
            "0.1",
            "--actual-total-tokens",
            "10",
            "--success",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert seen["request"].execute is False
    assert seen["request"].actor_admin_id is None


def test_external_tool_hold_execute_and_release_flag_errors_are_safe() -> None:
    base = [
        "quota",
        "reconcile-external-tool-hold",
        "--reservation-id",
        str(_hold_projection().reservation_id),
        "--action",
        "release-no-charge",
        "--execute",
        "--confirm-no-charge",
        "--json",
    ]
    missing_actor = runner.invoke(app, base)
    incompatible = runner.invoke(
        app,
        base
        + [
            "--actor-admin-id",
            str(uuid.uuid4()),
            "--reason",
            "confirmed",
            "--actual-cost-eur",
            "0",
        ],
    )

    assert missing_actor.exit_code == 1
    assert json.loads(missing_actor.stdout)["error"]["code"] == "invalid_external_tool_accounting_hold"
    assert incompatible.exit_code == 1
    assert json.loads(incompatible.stdout)["error"]["code"] == "invalid_external_tool_accounting_hold"


def test_external_tool_hold_cli_rejects_invalid_action_uuid_and_decimal_without_secret_output() -> None:
    invalid_action = runner.invoke(
        app,
        [
            "quota",
            "reconcile-external-tool-hold",
            "--reservation-id",
            str(_hold_projection().reservation_id),
            "--action",
            "unknown-action",
            "--json",
        ],
    )
    invalid_uuid = runner.invoke(
        app,
        [
            "quota",
            "reconcile-external-tool-hold",
            "--reservation-id",
            "not-a-uuid",
            "--action",
            ExternalToolHoldAction.FINALIZE_ACTUAL.value,
            "--json",
        ],
    )
    invalid_decimal = runner.invoke(
        app,
        [
            "quota",
            "reconcile-external-tool-hold",
            "--reservation-id",
            str(_hold_projection().reservation_id),
            "--action",
            ExternalToolHoldAction.FINALIZE_ACTUAL.value,
            "--actual-cost-eur",
            "nan",
            "--json",
        ],
    )

    for result in (invalid_action, invalid_uuid, invalid_decimal):
        assert result.exit_code == 1
        output = result.stdout + result.stderr
        assert "token_hash" not in output
        assert "provider_api_key" not in output
        assert "prompt" not in output.lower()
        assert "response" not in output.lower()
    assert json.loads(invalid_action.stdout)["error"]["code"] == "invalid_value"
    assert "valid UUID" in json.loads(invalid_uuid.stdout)["error"]["message"]
    assert "finite" in json.loads(invalid_decimal.stdout)["error"]["message"]


def test_external_tool_hold_cli_finalize_flag_matrix_is_strict(monkeypatch) -> None:
    monkeypatch.setattr(
        quota_cli,
        "_reconcile_external_tool_hold",
        lambda request: None,
    )
    base = [
        "quota",
        "reconcile-external-tool-hold",
        "--reservation-id",
        str(_hold_projection().reservation_id),
        "--action",
        ExternalToolHoldAction.FINALIZE_ACTUAL.value,
        "--execute",
        "--actor-admin-id",
        str(uuid.uuid4()),
        "--reason",
        "bounded reason",
        "--json",
    ]
    missing_cost = runner.invoke(app, base + ["--actual-total-tokens", "1", "--success"])
    missing_tokens = runner.invoke(app, base + ["--actual-cost-eur", "0.1", "--success"])
    missing_success = runner.invoke(app, base + ["--actual-cost-eur", "0.1", "--actual-total-tokens", "1"])
    incompatible = runner.invoke(
        app,
        base
        + [
            "--actual-cost-eur",
            "0.1",
            "--actual-total-tokens",
            "1",
            "--success",
            "--confirm-no-charge",
        ],
    )
    for result in (missing_cost, missing_tokens, missing_success, incompatible):
        assert result.exit_code == 1
        assert json.loads(result.stdout)["error"]["code"] == "invalid_external_tool_accounting_hold"


def test_external_tool_hold_cli_execute_requires_reason_and_release_confirmation() -> None:
    common = [
        "quota",
        "reconcile-external-tool-hold",
        "--reservation-id",
        str(_hold_projection().reservation_id),
        "--execute",
        "--actor-admin-id",
        str(uuid.uuid4()),
        "--json",
    ]
    missing_reason = runner.invoke(
        app,
        common
        + [
            "--action",
            ExternalToolHoldAction.FINALIZE_ACTUAL.value,
            "--actual-cost-eur",
            "0.1",
            "--actual-total-tokens",
            "1",
            "--success",
        ],
    )
    missing_confirmation = runner.invoke(
        app,
        common
        + [
            "--action",
            ExternalToolHoldAction.RELEASE_NO_CHARGE.value,
            "--reason",
            "release",
        ],
    )
    assert missing_reason.exit_code == 1
    assert missing_confirmation.exit_code == 1
    assert json.loads(missing_reason.stdout)["error"]["code"] == "invalid_external_tool_accounting_hold"
    assert json.loads(missing_confirmation.stdout)["error"]["code"] == "invalid_external_tool_accounting_hold"


def test_list_expired_reservations_prints_safe_text(monkeypatch) -> None:
    async def fake_list(*, limit):
        assert limit == 10
        return [_candidate()]

    monkeypatch.setattr(quota_cli, "_list_expired_reservations", fake_list)

    result = runner.invoke(app, ["quota", "list-expired-reservations", "--limit", "10"])

    assert result.exit_code == 0
    assert "req-safe" in result.stdout
    assert "0.300000000" in result.stdout
    assert "token_hash" not in result.stdout


def test_list_expired_reservations_json_is_valid(monkeypatch) -> None:
    async def fake_list(*, limit):
        return [_candidate()]

    monkeypatch.setattr(quota_cli, "_list_expired_reservations", fake_list)

    result = runner.invoke(app, ["quota", "list-expired-reservations", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["expired_reservations"][0]["reserved_cost_eur"] == "0.300000000"


def test_reconcile_expired_reservations_defaults_to_dry_run(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_reconcile(*, limit, dry_run, actor_admin_id, reason):
        seen["dry_run"] = dry_run
        return ReservationReconciliationSummary(
            checked_count=1,
            candidate_count=1,
            reconciled_count=0,
            skipped_count=0,
            dry_run=dry_run,
            results=[_result(dry_run=dry_run)],
        )

    monkeypatch.setattr(quota_cli, "_reconcile_expired_reservations", fake_reconcile)

    result = runner.invoke(app, ["quota", "reconcile-expired-reservations"])

    assert result.exit_code == 0
    assert seen["dry_run"] is True
    assert "dry_run: True" in result.stdout
    assert "reconciled_count: 0" in result.stdout


def test_reconcile_expired_reservations_execute_mutates_through_service(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_reconcile(*, limit, dry_run, actor_admin_id, reason):
        seen["dry_run"] = dry_run
        seen["reason"] = reason
        return ReservationReconciliationSummary(
            checked_count=1,
            candidate_count=1,
            reconciled_count=1,
            skipped_count=0,
            dry_run=dry_run,
            results=[_result(dry_run=dry_run)],
        )

    monkeypatch.setattr(quota_cli, "_reconcile_expired_reservations", fake_reconcile)

    result = runner.invoke(
        app,
        ["quota", "reconcile-expired-reservations", "--execute", "--reason", "repair"],
    )

    assert result.exit_code == 0
    assert seen == {"dry_run": False, "reason": "repair"}
    assert "new_status: expired" in result.stdout


def test_reconcile_expired_reservations_fails_when_none_found(monkeypatch) -> None:
    async def fake_reconcile(*, limit, dry_run, actor_admin_id, reason):
        return ReservationReconciliationSummary(
            checked_count=0,
            candidate_count=0,
            reconciled_count=0,
            skipped_count=0,
            dry_run=dry_run,
            results=[],
        )

    monkeypatch.setattr(quota_cli, "_reconcile_expired_reservations", fake_reconcile)

    result = runner.invoke(app, ["quota", "reconcile-expired-reservations", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["message"] == "No expired pending reservations found."


def test_reconcile_reservation_invalid_uuid_fails_cleanly() -> None:
    result = runner.invoke(app, ["quota", "reconcile-reservation", "not-a-uuid"])

    assert result.exit_code == 1
    assert "must be a valid UUID" in result.stderr


def test_reconcile_reservation_domain_error_is_safe(monkeypatch) -> None:
    async def fake_reconcile(*, reservation_id, dry_run, actor_admin_id, reason):
        raise ReservationNotExpiredError()

    monkeypatch.setattr(quota_cli, "_reconcile_reservation", fake_reconcile)

    result = runner.invoke(
        app,
        ["quota", "reconcile-reservation", str(uuid.uuid4()), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "reservation_not_expired"
    assert "secret" not in result.stdout.lower()


def _fence() -> ExternalToolFenceProjection:
    return ExternalToolFenceProjection(
        gateway_key_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        fence_state="active",
        reservation_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        request_id="req-fenced",
        acquired_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        expires_at=datetime(2026, 1, 1, 0, 16, tzinfo=UTC),
    )


def test_list_external_tool_fences_prints_safe_text(monkeypatch) -> None:
    async def fake_list(*, limit):
        assert limit == 10
        return [_fence()]

    monkeypatch.setattr(quota_cli, "_list_external_tool_fences", fake_list)

    result = runner.invoke(app, ["quota", "list-external-tool-fences", "--limit", "10"])

    assert result.exit_code == 0
    assert "req-fenced" in result.stdout
    assert "active" in result.stdout
    assert "33333333-3333-3333-3333-333333333333" in result.stdout
    for forbidden in ("token_hash", "plaintext_key", "provider_api_key", "encrypted_payload", "nonce"):
        assert forbidden not in result.stdout


def test_list_external_tool_fences_json_is_valid(monkeypatch) -> None:
    async def fake_list(*, limit):
        return [_fence()]

    monkeypatch.setattr(quota_cli, "_list_external_tool_fences", fake_list)

    result = runner.invoke(app, ["quota", "list-external-tool-fences", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    row = payload["external_tool_fences"][0]
    assert row["fence_state"] == "active"
    assert row["reservation_id"] == "33333333-3333-3333-3333-333333333333"
    assert row["expires_at"] == "2026-01-01T00:16:00+00:00"


def test_list_external_tool_fences_empty_state(monkeypatch) -> None:
    async def fake_list(*, limit):
        return []

    monkeypatch.setattr(quota_cli, "_list_external_tool_fences", fake_list)

    result = runner.invoke(app, ["quota", "list-external-tool-fences"])

    assert result.exit_code == 0
    assert "No active or held external-tool fences found." in result.stdout
