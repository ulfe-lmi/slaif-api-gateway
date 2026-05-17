from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from typer.testing import CliRunner

from slaif_gateway.cli import calibration as calibration_cli
from slaif_gateway.cli.main import app
from slaif_gateway.services.calibration_summary_service import (
    CalibrationObservedSummary,
    CalibrationPolicyProposal,
    CalibrationPreviewResult,
    CalibrationSummaryError,
)

runner = CliRunner()
KEY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
SECRET_VALUE = "sk-live-secret-must-not-render"
PROMPT_TEXT = "prompt text must not render"
COMPLETION_TEXT = "completion text must not render"


def test_calibration_help_registers_summarize() -> None:
    result = runner.invoke(app, ["calibration", "--help"])

    assert result.exit_code == 0
    assert "summarize" in result.stdout


def test_calibration_summarize_outputs_safe_text(monkeypatch) -> None:
    async def fake_summarize(**kwargs):
        assert kwargs["gateway_key_id"] == str(KEY_ID)
        return _preview()

    monkeypatch.setattr(calibration_cli, "_summarize", fake_summarize)

    result = runner.invoke(app, ["calibration", "summarize", "--gateway-key-id", str(KEY_ID)])

    assert result.exit_code == 0
    assert "Trusted calibration usage summary" in result.stdout
    assert "Preview-only strict participant policy proposal" in result.stdout
    assert "gpt-4.1-mini" in result.stdout
    assert "No templates, keys, routes, or pricing rows were changed." in result.stdout
    assert SECRET_VALUE not in result.stdout
    assert PROMPT_TEXT not in result.stdout
    assert COMPLETION_TEXT not in result.stdout


def test_calibration_summarize_json_is_valid_and_safe(monkeypatch) -> None:
    async def fake_summarize(**kwargs):
        return _preview()

    monkeypatch.setattr(calibration_cli, "_summarize", fake_summarize)

    result = runner.invoke(app, ["calibration", "summarize", "--gateway-key-id", str(KEY_ID), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["gateway_key_id"] == str(KEY_ID)
    assert payload["proposal"]["proposed_request_limit_total"] == 6
    serialized = json.dumps(payload, sort_keys=True)
    assert SECRET_VALUE not in serialized
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized


def test_calibration_summarize_rejects_standard_key(monkeypatch) -> None:
    async def fake_summarize(**kwargs):
        raise CalibrationSummaryError("Calibration summaries are available only for trusted calibration keys.")

    monkeypatch.setattr(calibration_cli, "_summarize", fake_summarize)

    result = runner.invoke(app, ["calibration", "summarize", "--gateway-key-id", str(KEY_ID)])

    assert result.exit_code == 1
    assert "trusted calibration keys" in result.stderr


def test_calibration_summarize_output_file_uses_safe_json(tmp_path, monkeypatch) -> None:
    async def fake_summarize(**kwargs):
        return _preview()

    monkeypatch.setattr(calibration_cli, "_summarize", fake_summarize)
    output = tmp_path / "calibration.json"

    first = runner.invoke(
        app,
        ["calibration", "summarize", "--gateway-key-id", str(KEY_ID), "--output", str(output)],
    )
    second = runner.invoke(
        app,
        ["calibration", "summarize", "--gateway-key-id", str(KEY_ID), "--output", str(output)],
    )

    assert first.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["proposal"]["proposed_allowed_models"] == ["gpt-4.1-mini"]
    assert second.exit_code == 1
    assert "already exists" in second.stderr


def _preview() -> CalibrationPreviewResult:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    summary = CalibrationObservedSummary(
        gateway_key_id=KEY_ID,
        public_key_id="public-calibration",
        owner_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        owner_email="owner@example.org",
        owner_display_name="Owner Name",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        time_window_start=now,
        time_window_end=now,
        observed_request_count=2,
        observed_endpoints=("/v1/chat/completions",),
        observed_providers=("openai",),
        observed_requested_models=("gpt-4.1-mini",),
        observed_resolved_upstream_models=("gpt-4.1-mini",),
        observed_provider_hosts=("api.openai.com",),
        observed_provider_endpoint_paths=("/v1/chat/completions",),
        observed_hosted_capabilities=(),
        observed_unknown_hosted_capabilities=(),
        observed_denied_capabilities=(),
        total_input_tokens=10,
        total_output_tokens=20,
        total_tokens=30,
        total_reasoning_tokens=None,
        total_cached_tokens=None,
        max_input_tokens_per_request=6,
        max_output_tokens_per_request=11,
        max_total_tokens_per_request=17,
        max_reasoning_tokens_per_request=None,
        max_cached_tokens_per_request=None,
        total_slaif_calculated_cost=Decimal("0.010000000"),
        total_provider_reported_cost=None,
        max_slaif_calculated_cost_per_request=Decimal("0.006000000"),
        max_provider_reported_cost_per_request=None,
        cost_currencies=("EUR",),
        cost_confidence="slaif_calculated",
        warnings=(),
    )
    proposal = CalibrationPolicyProposal(
        proposed_allowed_endpoints=("/v1/chat/completions",),
        proposed_allowed_models=("gpt-4.1-mini",),
        proposed_allowed_providers=("openai",),
        proposed_allowed_hosted_capabilities=(),
        hosted_capabilities_requiring_review=(),
        proposed_request_limit_total=6,
        proposed_token_limit_total=90,
        proposed_input_token_limit_total=30,
        proposed_output_token_limit_total=60,
        proposed_reasoning_token_limit_total=None,
        proposed_cost_limit_eur=Decimal("0.030000000"),
        proposed_max_input_tokens_per_request=18,
        proposed_max_output_tokens_per_request=33,
        proposed_max_total_tokens_per_request=51,
        proposed_max_single_request_cost_eur=Decimal("0.018000000"),
        proposed_rate_limit_policy=None,
        warnings=(),
        assumptions=("safe metadata only",),
        source_gateway_key_id=KEY_ID,
        source_time_window_start=now,
        source_time_window_end=now,
        multiplier=Decimal("3"),
    )
    return CalibrationPreviewResult(summary=summary, proposal=proposal, is_empty=False)
