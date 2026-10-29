"""Unit tests for the diagnostics CLI (typed service boundary, safe output)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from slaif_gateway.cli.diagnostics import app as diagnostics_app
from slaif_gateway.schemas.request_diagnostics import (
    DiagnosticLookupOutcome,
    DiagnosticLookupResult,
    DiagnosticsCleanupResult,
    DiagnosticsNamespace,
    DiagnosticsStatus,
    RequestDiagnosticRecord,
)

RUNNER = CliRunner()


def _record() -> RequestDiagnosticRecord:
    now = datetime.now(UTC)
    return RequestDiagnosticRecord(
        id=uuid.uuid4(),
        gateway_request_id="gw-00000000-0000-4000-8000-000000000001",
        client_request_id="req-legit",
        client_id_unavailable_reason=None,
        method="POST",
        endpoint_template="/v1/responses",
        occurred_at=now,
        http_status=400,
        stream_outcome="http_rejection",
        source="responses_route_limits",
        reason_code="responses_codex_context_window_exceeded",
        error_code="responses_codex_context_window_exceeded",
        error_param="input",
        positions=None,
        counts=None,
        limits=None,
        gateway_key_id=uuid.uuid4(),
        route_id=uuid.uuid4(),
        route_pattern="gpt-4o",
        deployment_revision=None,
        estimated_input_tokens=100,
        output_allowance_tokens=200,
        context_window_tokens=300,
        replay_error_code=None,
        recorded_at=now,
    )


def _status(**overrides: Any) -> DiagnosticsStatus:
    base: dict[str, Any] = dict(
        recording_enabled=True,
        retention_seconds=604800,
        max_records=10000,
        write_timeout_ms=100,
        store_available=True,
        retained_records=0,
    )
    base.update(overrides)
    return DiagnosticsStatus(**base)


def test_status_distinguishes_disabled_unavailable_empty_enabled() -> None:
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.status = _async_callable(_status(recording_enabled=False))
        result = RUNNER.invoke(diagnostics_app, ["status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["recording_enabled"] is False
        assert payload["store_available"] is True
        assert payload["retained_records"] == 0

        service.return_value.status = _async_callable(
            _status(recording_enabled=True, store_available=False)
        )
        result = RUNNER.invoke(diagnostics_app, ["status", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["store_available"] is False

        service.return_value.status = _async_callable(_status())
        result = RUNNER.invoke(diagnostics_app, ["status"])
        assert result.exit_code == 0
        assert "retained dataset is empty" in result.output

        service.return_value.status = _async_callable(_status(retained_records=7))
        result = RUNNER.invoke(diagnostics_app, ["status"])
        assert result.exit_code == 0
        assert "7 retained record(s)" in result.output


def test_status_disabled_and_store_unavailable_reports_both_states() -> None:
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.status = _async_callable(
            _status(recording_enabled=False, store_available=False)
        )
        # human output must distinguish BOTH states (not just "disabled")
        result = RUNNER.invoke(diagnostics_app, ["status"])
        assert result.exit_code == 0
        assert "disabled" in result.output
        assert "unavailable" in result.output
        assert "retained reads still available" not in result.output
        # JSON reports the same combination
        result = RUNNER.invoke(diagnostics_app, ["status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["recording_enabled"] is False
        assert payload["store_available"] is False
        # the opposite combination (disabled but store healthy) stays distinct
        service.return_value.status = _async_callable(
            _status(recording_enabled=False, store_available=True)
        )
        result = RUNNER.invoke(diagnostics_app, ["status"])
        assert result.exit_code == 0
        assert "disabled" in result.output
        assert "retained reads still available" in result.output
        assert "store unavailable" not in result.output


def test_request_show_found_payload_contains_only_safe_fields() -> None:
    record = _record()
    result_obj = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.FOUND,
        namespace=DiagnosticsNamespace.ANY,
        record=record,
        match_count=1,
    )
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.resolve = lambda lookup_id, namespace=None: _async_callable(
            result_obj
        )()
        result = RUNNER.invoke(
            diagnostics_app, ["request", "show", "--request-id", record.gateway_request_id]
        )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["error_code"] == "responses_codex_context_window_exceeded"
    assert payload["estimated_input_tokens"] == 100
    # No secret-bearing or free-form fields are ever emitted.
    for forbidden in ("error_message", "observed", "field", "authorization"):
        assert forbidden not in json.dumps(payload)


def test_request_show_ambiguous_reports_count_overflow_and_candidates() -> None:
    candidates = tuple()
    result_obj = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.AMBIGUOUS,
        namespace=DiagnosticsNamespace.CLIENT,
        match_count=101,
        candidates=candidates,
        overflow=True,
    )
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.resolve = lambda lookup_id, namespace=None: _async_callable(
            result_obj
        )()
        result = RUNNER.invoke(
            diagnostics_app,
            ["request", "show", "--request-id", "req-x", "--namespace", "client", "--json"],
        )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "ambiguous"
    assert payload["match_count"] == 101
    assert payload["overflow"] is True


def test_request_show_not_found_and_unavailable_exit_codes() -> None:
    not_found = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.NOT_FOUND, namespace=DiagnosticsNamespace.ANY
    )
    unavailable = DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.UNAVAILABLE,
        namespace=DiagnosticsNamespace.ANY,
        reason="store_unavailable",
    )
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.resolve = lambda lookup_id, namespace=None: _async_callable(
            not_found
        )()
        result = RUNNER.invoke(
            diagnostics_app, ["request", "show", "--request-id", "missing"]
        )
        assert result.exit_code == 0
        assert "not_found" in result.output

        service.return_value.resolve = lambda lookup_id, namespace=None: _async_callable(
            unavailable
        )()
        result = RUNNER.invoke(
            diagnostics_app, ["request", "show", "--request-id", "missing", "--json"]
        )
        assert result.exit_code == 1
        assert json.loads(result.output)["reason"] == "store_unavailable"


def test_request_show_rejects_unknown_namespace() -> None:
    result = RUNNER.invoke(
        diagnostics_app,
        ["request", "show", "--request-id", "x", "--namespace", "bogus"],
    )
    assert result.exit_code != 0
    assert "namespace" in result.output


def test_cleanup_reports_deleted_count_and_unavailable() -> None:
    with patch("slaif_gateway.cli.diagnostics._service") as service:
        service.return_value.cleanup = _async_callable(
            DiagnosticsCleanupResult(deleted_count=3, store_available=True)
        )
        result = RUNNER.invoke(diagnostics_app, ["cleanup", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["deleted_count"] == 3

        service.return_value.cleanup = _async_callable(
            DiagnosticsCleanupResult(
                deleted_count=0, store_available=False, reason="store_unavailable"
            )
        )
        result = RUNNER.invoke(diagnostics_app, ["cleanup", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["store_available"] is False


def test_missing_database_config_emits_json_error_in_json_mode() -> None:
    from slaif_gateway.config import Settings

    with patch(
        "slaif_gateway.cli.diagnostics.get_settings", return_value=Settings(_env_file=None)
    ):
        for args in (
            ["status", "--json"],
            ["cleanup", "--json"],
            ["request", "show", "--request-id", "x", "--json"],
        ):
            result = RUNNER.invoke(diagnostics_app, args)
            assert result.exit_code == 1, args
            payload = json.loads(result.output)
            assert payload["error"]["code"] == "database_not_configured", args


def _async_callable(value: Any):
    async def _op() -> Any:
        return value

    return _op
