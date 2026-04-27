from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import quota as quota_cli
from slaif_gateway.cli.main import app
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
    assert "list-expired-reservations" in result.stdout
    assert "reconcile-expired-reservations" in result.stdout
    assert "reconcile-reservation" in result.stdout


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
