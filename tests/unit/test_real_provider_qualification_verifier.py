from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "verify_real_provider_qualification.py"
SPEC = importlib.util.spec_from_file_location("real_provider_qualification", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFIER
SPEC.loader.exec_module(VERIFIER)


def _error_code(callable_, *args, **kwargs) -> str:
    with pytest.raises(VERIFIER.VerificationError) as raised:
        callable_(*args, **kwargs)
    return raised.value.code


def _protected_file(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return path


def _authorization(path: Path, **overrides: object) -> Path:
    document: dict[str, object] = {
        "candidate_commit": VERIFIER._safe_current_commit(),
        "max_requests": 8,
        "providers": ["openai", "openrouter"],
        "max_total_cost_eur": "0.05",
        "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat(),
    }
    document.update(overrides)
    return _protected_file(path, json.dumps(document))


def _response(body: str, *, content_type: str = "text/event-stream") -> httpx.Response:
    return httpx.Response(
        200,
        headers={
            "Content-Type": content_type,
            "X-SLAIF-Diagnostic-ID": "gw-12345678-1234-4123-8123-123456789abc",
        },
        content=body.encode(),
        request=httpx.Request("POST", "https://gateway.example/v1"),
    )


def _base_rows(flow: object | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    selected_flow = flow or VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a")
    reservation = {
        "id": "reservation-id",
        "gateway_key_id": "key-id",
        "endpoint": selected_flow.endpoint,
        "requested_model": selected_flow.model,
        "provider": selected_flow.provider,
        "resolved_model": "resolved-model",
        "streaming": selected_flow.streaming,
        "status": "finalized",
        "reserved_cost_eur": Decimal("0.01"),
        "reserved_tokens": 32,
        "reserved_requests": 1,
        "finalized_at": dt.datetime.now(dt.UTC),
        "released_at": None,
    }
    ledger = {
        "request_id": "gw-12345678-1234-4123-8123-123456789abc",
        "quota_reservation_id": "reservation-id",
        "gateway_key_id": "key-id",
        "endpoint": selected_flow.endpoint,
        "provider": selected_flow.provider,
        "requested_model": selected_flow.model,
        "resolved_model": "resolved-model",
        "streaming": selected_flow.streaming,
        "success": True,
        "accounting_status": "finalized",
        "http_status": 200,
        "input_tokens": 2,
        "output_tokens": 3,
        "total_tokens": 5,
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_eur": Decimal("0.01"),
        "actual_cost_eur": Decimal("0.01"),
        "actual_cost_native": Decimal("0.01"),
        "usage_raw": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        "response_metadata": {
            "cost_source": "slaif_calculated",
            "cost_confidence": "slaif_calculated",
        },
        "error_message": None,
        "finished_at": dt.datetime.now(dt.UTC),
    }
    key = {
        "id": "key-id",
        "public_key_id": "public-key-id",
        "key_prefix": "sk-slaif-",
        "key_hint": "hint",
        "token_hash": "digest-only",
        "status": "active",
        "valid_from": dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
        "valid_until": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        "cost_limit_eur": Decimal("1"),
        "token_limit_total": 1000,
        "request_limit_total": 8,
        "cost_used_eur": Decimal("0"),
        "tokens_used_total": 0,
        "requests_used_total": 0,
        "cost_reserved_eur": Decimal("0"),
        "tokens_reserved_total": 0,
        "requests_reserved_total": 0,
        "external_tool_fence_state": "none",
        "external_tool_fence_reservation_id": None,
        "external_tool_fence_request_id": None,
        "external_tool_fence_acquired_at": None,
        "external_tool_fence_expires_at": None,
        "allow_all_models": False,
        "allowed_models": [],
        "allow_all_endpoints": False,
        "allowed_endpoints": [],
        "key_purpose": "standard",
        "capability_policy_mode": "standard",
        "calibration_metadata": {},
        "metadata": {},
        "revoked_at": None,
    }
    return [reservation], [ledger], [key]


def test_guarded_dry_run_reports_no_http_or_sql(capsys: pytest.CaptureFixture[str]) -> None:
    assert VERIFIER.main(["--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "http_requests": 0,
        "reason": "guarded_dry_run",
        "real_provider_called": False,
        "result": "not_run",
        "sql_queries": 0,
    }


def test_main_rejects_secret_argv_before_argparse_can_echo_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert VERIFIER.main(["--unknown", "sk-secretvalue"]) == 1
    output = capsys.readouterr().out
    assert "sk-secretvalue" not in output
    assert "secret_argument_rejected" in output


def test_live_switch_is_required_before_any_configuration_or_traffic() -> None:
    arguments = VERIFIER._parser().parse_args([])
    assert _error_code(VERIFIER.load_live_configuration, arguments) == "live_execution_switch_required"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("http://gateway.example/v1", "gateway_base_url_invalid"),
        ("https://api.openai.com/v1", "gateway_provider_direct_url_rejected"),
        ("https://gateway.example/v1/", "gateway_base_url_invalid"),
        ("https://gateway.example/v1?x=1", "gateway_base_url_invalid"),
        ("https://user:pass@gateway.example/v1", "gateway_base_url_invalid"),
    ],
)
def test_gateway_target_is_exact_https_non_provider_url(value: str, code: str) -> None:
    assert _error_code(VERIFIER.validate_gateway_base_url, value) == code


def test_gateway_target_accepts_exact_v1_path() -> None:
    assert VERIFIER.validate_gateway_base_url("https://gateway.example/v1") == (
        "https://gateway.example/v1"
    )


@pytest.mark.parametrize(
    "value",
    [
        "postgresql://user:pass@localhost/slaif_gateway",
        "postgresql://user:pass@10.0.0.1/slaif_real_provider_qualification_x",
        "postgresql://user:pass@127.0.0.1/postgres",
        "postgresql://user:pass@127.0.0.1/slaif_real_provider_qualification_x?sslmode=require",
    ],
)
def test_database_target_refuses_shared_non_loopback_or_ambiguous_urls(value: str) -> None:
    assert _error_code(VERIFIER.validate_database_url, value) in {
        "database_name_invalid",
        "database_url_invalid",
    }


def test_database_target_requires_exact_disposable_name_and_loopback() -> None:
    target = VERIFIER.validate_database_url(
        "postgresql+asyncpg://user:pass@127.0.0.1/slaif_real_provider_qualification_a1"
    )
    assert target.database_name == "slaif_real_provider_qualification_a1"
    assert target.connect_url.startswith("postgresql://")


def test_protected_secret_files_reject_permissions_symlinks_and_repository_paths(tmp_path: Path) -> None:
    readable = tmp_path / "readable"
    readable.write_text("secret", encoding="utf-8")
    readable.chmod(0o644)
    assert _error_code(VERIFIER._protected_file_path, str(readable), name="gateway_key") == (
        "gateway_key_file_permissions_invalid"
    )

    target = _protected_file(tmp_path / "target", "secret")
    link = tmp_path / "link"
    link.symlink_to(target)
    assert _error_code(VERIFIER._protected_file_path, str(link), name="gateway_key") == (
        "gateway_key_file_invalid"
    )

    repository_file = VERIFIER._repo_root() / "AGENTS.md"
    assert _error_code(
        VERIFIER._protected_file_path, str(repository_file), name="authorization"
    ) in {"authorization_file_permissions_invalid", "authorization_file_in_repository"}

    parent = tmp_path / "parent"
    parent.mkdir()
    parent_file = _protected_file(parent / "parent-secret", "secret")
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(parent, target_is_directory=True)
    assert _error_code(
        VERIFIER._protected_file_path,
        str(parent_link / parent_file.name),
        name="gateway_key",
    ) == "gateway_key_path_resolved"


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("11111111-1111-4111-8111-111111111111", True),
        ("11111111111141118111111111111111", False),
        ("11111111-1111-4111-8111-11111111111Z", False),
        ("not-a-uuid", False),
    ],
)
def test_gateway_key_id_requires_canonical_uuid(value: str, valid: bool) -> None:
    if valid:
        assert VERIFIER.validate_gateway_key_id(value) == value
    else:
        assert _error_code(VERIFIER.validate_gateway_key_id, value) == "gateway_key_id_invalid"


def test_authorization_requires_exact_eight_both_providers_cost_and_future_expiry(
    tmp_path: Path,
) -> None:
    valid = VERIFIER._read_authorization(
        str(_authorization(tmp_path / "valid.json"))
    )
    assert valid.max_requests == 8
    assert valid.providers == {"openai", "openrouter"}
    assert valid.max_total_cost_eur == Decimal("0.05")

    for field, value, code in (
        ("max_requests", 7, "authorization_request_bound_invalid"),
        ("providers", ["openai"], "authorization_providers_invalid"),
        ("max_total_cost_eur", "0.06", "authorization_cost_bound_invalid"),
        ("expires_at", "2000-01-01T00:00:00+00:00", "authorization_expired"),
    ):
        path = tmp_path / f"{field}.json"
        assert _error_code(
            VERIFIER._read_authorization,
            str(_authorization(path, **{field: value})),
        ) == code

    malformed = _protected_file(tmp_path / "malformed.json", "not-json")
    assert _error_code(VERIFIER._read_authorization, str(malformed)) == "authorization_malformed"


def test_inherited_secret_environment_and_secret_argv_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "gateway-secret")
    assert _error_code(VERIFIER._reject_inherited_secrets) == "inherited_secret_environment_present"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert _error_code(VERIFIER._reject_secret_argv, ["tool", "--gateway-key=sk-secretvalue"]) == (
        "secret_argument_rejected"
    )
    assert _error_code(
        VERIFIER._reject_secret_argv,
        ["tool", "postgresql://user:secret@127.0.0.1/db"],
    ) == "secret_argument_rejected"


def test_live_configuration_reads_only_protected_files_and_builds_exact_eight_flows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["verifier"])
    key_file = _protected_file(tmp_path / "gateway.key", "gateway-test-token")
    database_file = _protected_file(
        tmp_path / "database.url",
        "postgresql+asyncpg://user:pass@127.0.0.1/slaif_real_provider_qualification_a1",
    )
    auth_file = _authorization(tmp_path / "authorization.json")
    arguments = VERIFIER._parser().parse_args(
        [
            "--execute-live",
            "--gateway-base-url",
            "https://gateway.example/v1",
            "--gateway-key-file",
            str(key_file),
            "--gateway-key-id",
            "11111111-1111-4111-8111-111111111111",
            "--database-url-file",
            str(database_file),
            "--authorization-file",
            str(auth_file),
            "--openai-model",
            "operator/openai-model",
            "--openrouter-model",
            "operator/openrouter-model",
        ]
    )
    configuration = VERIFIER.load_live_configuration(arguments)
    assert configuration.gateway_key == "gateway-test-token"
    assert len(configuration.flows) == 8
    assert [flow.provider for flow in configuration.flows] == [
        "openai",
        "openai",
        "openai",
        "openai",
        "openrouter",
        "openrouter",
        "openrouter",
        "openrouter",
    ]
    assert [flow.streaming for flow in configuration.flows] == [
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
    ]


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"input_tokens": 1, "output_tokens": 2, "total_tokens": 4}, "usage_total_inconsistent"),
        ({"input_tokens": True, "output_tokens": 2, "total_tokens": 3}, "usage_fields_invalid"),
        ({"input_tokens": -1, "output_tokens": 2, "total_tokens": 1}, "usage_negative"),
        ({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, "usage_zero"),
        (None, "usage_object_invalid"),
    ],
)
def test_usage_parser_rejects_bool_negative_inconsistent_and_zero(
    payload: object, code: str
) -> None:
    assert _error_code(VERIFIER._validate_usage_mapping, payload) == code


def test_usage_parser_accepts_chat_and_responses_aliases() -> None:
    assert VERIFIER._validate_usage_mapping(
        {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    ) == VERIFIER.Usage(2, 3, 5)
    assert VERIFIER._validate_usage_mapping(
        {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    ) == VERIFIER.Usage(2, 3, 5)


def test_nonstreaming_openai_shapes_require_assistant_output_and_usage() -> None:
    usage = {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    chat = {
        "object": "chat.completion",
        "choices": [
            {
                "message": {"role": "assistant", "content": "SLAIF-152A-OK"},
            }
        ],
        "usage": usage,
    }
    assert VERIFIER.validate_chat_body(chat) == VERIFIER.Usage(2, 3, 5)
    response = {
        "object": "response",
        "status": "completed",
        "output": [{"type": "message", "text": "SLAIF-152A-OK"}],
        "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    }
    assert VERIFIER.validate_responses_body(response) == VERIFIER.Usage(2, 3, 5)
    bad = dict(chat)
    bad["choices"] = []
    assert _error_code(VERIFIER.validate_chat_body, bad) == "chat_response_choices_invalid"


def test_chat_stream_requires_sse_done_terminal_usage_and_response_marker() -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"SLAIF-152A-OK"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\n'
        "data: [DONE]\n\n"
    )
    evidence = asyncio.run(VERIFIER.validate_chat_stream(_response(body)))
    assert evidence.usage == VERIFIER.Usage(2, 3, 5)
    missing_done = body.replace("data: [DONE]\n\n", "")
    assert _error_code(
        lambda: asyncio.run(VERIFIER.validate_chat_stream(_response(missing_done)))
    ) == "chat_stream_done_missing"
    error_event = 'data: {"error":{"message":"no"}}\n\n'
    assert _error_code(
        lambda: asyncio.run(VERIFIER.validate_chat_stream(_response(error_event)))
    ) == "sse_error_event"


def test_responses_stream_requires_one_completed_terminal_and_rejects_failures() -> None:
    body = (
        'data: {"type":"response.output_text.delta","delta":"SLAIF-152A-OK"}\n\n'
        'data: {"type":"response.completed","response":{"object":"response",'
        '"status":"completed","output":[{"text":"SLAIF-152A-OK"}],'
        '"usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5}}}\n\n'
    )
    evidence = asyncio.run(VERIFIER.validate_responses_stream(_response(body)))
    assert evidence.usage == VERIFIER.Usage(2, 3, 5)
    failed = 'data: {"type":"response.failed","response":{}}\n\n'
    assert _error_code(
        lambda: asyncio.run(VERIFIER.validate_responses_stream(_response(failed)))
    ) == "responses_stream_failed_event"
    truncated = body.split('data: {"type":"response.completed"', 1)[0]
    assert _error_code(
        lambda: asyncio.run(VERIFIER.validate_responses_stream(_response(truncated)))
    ) == "responses_stream_completed_missing"


def test_diagnostic_id_is_gateway_id_not_caller_request_id() -> None:
    response = _response("")
    response.headers["X-Request-ID"] = "caller-controlled"
    assert VERIFIER._diagnostic_id(response).startswith("gw-")
    response.headers["X-SLAIF-Diagnostic-ID"] = "caller-controlled"
    assert _error_code(VERIFIER._diagnostic_id, response) == "diagnostic_id_invalid"


def test_exact_flow_order_and_bounded_request_payloads() -> None:
    flows = VERIFIER._build_flows("openai/model", "openrouter/model")
    assert len(flows) == VERIFIER.MAX_REQUESTS == 8
    assert [flow.endpoint for flow in flows] == [
        "/v1/chat/completions",
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/responses",
    ] * 2
    assert all(
        int(VERIFIER._request_body(flow)["max_completion_tokens"]) <= 32
        if flow.endpoint.endswith("chat/completions")
        else int(VERIFIER._request_body(flow)["max_output_tokens"]) <= 32
        for flow in flows
    )
    assert all("tools" not in VERIFIER._request_body(flow) for flow in flows)


def test_fresh_key_baseline_rejects_history_state_and_complete_row_canary() -> None:
    key = _base_rows()[2][0]
    VERIFIER.validate_fresh_key(
        key_rows=[key],
        gateway_key_id="key-id",
        gateway_key="gateway-test-token",
        reservation_count=0,
        ledger_count=0,
    )
    key["requests_used_total"] = 1
    assert _error_code(
        VERIFIER.validate_fresh_key,
        key_rows=[key],
        gateway_key_id="key-id",
        gateway_key="gateway-test-token",
        reservation_count=0,
        ledger_count=0,
    ) == "fresh_key_counters_nonzero"
    key["requests_used_total"] = 0
    key["metadata"] = {"gateway_key": "gateway-test-token"}
    assert _error_code(
        VERIFIER.validate_fresh_key,
        key_rows=[key],
        gateway_key_id="key-id",
        gateway_key="gateway-test-token",
        reservation_count=0,
        ledger_count=0,
    ) == "fresh_key_plaintext_canary_found"


def test_fresh_key_baseline_rejects_old_reservation_and_ledger_totals() -> None:
    key = _base_rows()[2][0]
    assert _error_code(
        VERIFIER.validate_fresh_key,
        key_rows=[key],
        gateway_key_id="key-id",
        gateway_key="gateway-test-token",
        reservation_count=1,
        ledger_count=0,
    ) == "fresh_key_has_history"
    assert _error_code(
        VERIFIER.validate_fresh_key,
        key_rows=[key],
        gateway_key_id="key-id",
        gateway_key="gateway-test-token",
        reservation_count=0,
        ledger_count=1,
    ) == "fresh_key_has_history"


def test_ordinal_isolation_rejects_old_or_concurrent_uncorrelated_rows() -> None:
    seen = ["gw-1", "gw-2"]
    VERIFIER.validate_ordinal_run_isolation(
        reservation_ids=seen,
        ledger_ids=seen,
        seen_request_ids=seen,
        ordinal=2,
    )
    assert _error_code(
        VERIFIER.validate_ordinal_run_isolation,
        reservation_ids=["gw-old", *seen],
        ledger_ids=seen,
        seen_request_ids=seen,
        ordinal=2,
    ) == "run_ordinal_cardinality_invalid"
    assert _error_code(
        VERIFIER.validate_ordinal_run_isolation,
        reservation_ids=seen,
        ledger_ids=["gw-foreign", "gw-2"],
        seen_request_ids=seen,
        ordinal=2,
    ) == "run_ordinal_uncorrelated_rows"


def test_final_key_state_requires_zero_reserved_and_pending_state() -> None:
    key = _base_rows()[2][0]
    VERIFIER.validate_final_key_state(
        key_rows=[key],
        gateway_key_id="key-id",
        pending_reservations=0,
    )
    key["requests_reserved_total"] = 1
    assert _error_code(
        VERIFIER.validate_final_key_state,
        key_rows=[key],
        gateway_key_id="key-id",
        pending_reservations=0,
    ) == "fresh_key_counters_nonzero"


def test_cost_confidence_output_is_allowlisted() -> None:
    for confidence in sorted(VERIFIER.COST_CONFIDENCES):
        assert VERIFIER._metadata_cost_labels(
            {"cost_source": "slaif_calculated", "cost_confidence": confidence}
        ) == ("slaif_calculated", confidence)
    assert _error_code(
        VERIFIER._metadata_cost_labels,
        {"cost_source": "slaif_calculated", "cost_confidence": "operator-claimed"},
    ) == "correlation_cost_confidence_invalid"


def test_failed_attempt_does_not_prove_provider_execution(capsys: pytest.CaptureFixture[str]) -> None:
    error = VERIFIER.VerificationError("gateway_transport_failure", attempted_requests=1)
    assert VERIFIER._emit_failure(error) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["gateway_requests_attempted"] == 1
    assert output["correlated_completed_count"] == 0
    assert output["real_provider_call_proven"] is False


def test_success_summary_is_bounded_and_includes_model_and_token_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDatabase:
        def __init__(self, target, *, timeout_seconds):
            self.correlated = 0

        async def connect_and_check(self):
            return None

        async def prepare_fresh_key(self, *, gateway_key_id, gateway_key):
            assert gateway_key_id == "11111111-1111-4111-8111-111111111111"

        async def correlate(self, **kwargs):
            self.correlated += 1
            return VERIFIER.CorrelationEvidence(
                gateway_key_id="11111111-1111-4111-8111-111111111111",
                cost_source="slaif_calculated",
                cost_confidence="slaif_calculated",
                actual_cost_eur=Decimal("0"),
                stored_usage=VERIFIER.Usage(2, 3, 5),
                pending_reservations=0,
                counters_zero=True,
            )

        async def check_ordinal_isolation(self, **kwargs):
            return None

        async def final_run_check(self, **kwargs):
            assert len(kwargs["request_ids"]) == 8

        async def close(self):
            return None

    call_count = 0

    async def fake_execute(client, *, base_url, gateway_key, flow):
        nonlocal call_count
        call_count += 1
        return (
            f"gw-{call_count:08d}-1234-4123-8123-123456789abc",
            VERIFIER.TerminalEvidence(200, True, VERIFIER.Usage(2, 3, 5)),
        )

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(VERIFIER, "PostgresProbe", FakeDatabase)
    monkeypatch.setattr(VERIFIER, "execute_flow", fake_execute)
    monkeypatch.setattr(VERIFIER.asyncio, "sleep", no_sleep)
    authorization = VERIFIER.Authorization(
        candidate_commit="0" * 40,
        max_requests=8,
        providers=frozenset({"openai", "openrouter"}),
        max_total_cost_eur=Decimal("0.05"),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    config = VERIFIER.LiveConfiguration(
        gateway_base_url="https://gateway.example/v1",
        gateway_key="gateway-test-token",
        gateway_key_id="11111111-1111-4111-8111-111111111111",
        database_target=VERIFIER.DatabaseTarget(
            connect_url="postgresql://loopback/slaif_real_provider_qualification_a1",
            database_name="slaif_real_provider_qualification_a1",
        ),
        authorization=authorization,
        ca_file=None,
        min_gap_seconds=15,
        poll_timeout_seconds=1,
        poll_interval_seconds=0.01,
        flows=VERIFIER._build_flows("openai/model", "openrouter/model"),
    )
    result = asyncio.run(VERIFIER.run_live(config))
    assert result["gateway_requests_attempted"] == 8
    assert result["correlated_completed_count"] == 8
    assert result["real_provider_call_proven"] is True
    assert all(
        flow["model"] in {"openai/model", "openrouter/model"}
        and flow["response_input_tokens"] == 2
        and flow["response_output_tokens"] == 3
        and flow["response_total_tokens"] == 5
        and flow["stored_input_tokens"] == 2
        and flow["stored_output_tokens"] == 3
        and flow["stored_total_tokens"] == 5
        for flow in result["flows"]
    )


def test_correlation_requires_exact_reservation_ledger_relationship_and_zero_pending() -> None:
    flow = VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a")
    reservation, ledger, key = _base_rows(flow)
    result = VERIFIER.validate_correlation(
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=0,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=flow,
        expected_usage=VERIFIER.Usage(2, 3, 5),
    )
    assert result.gateway_key_id == "key-id"
    assert result.counters_zero is True
    ledger[0]["quota_reservation_id"] = "other-reservation"
    assert _error_code(
        VERIFIER.validate_correlation,
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=0,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=flow,
        expected_usage=VERIFIER.Usage(2, 3, 5),
    ) == "correlation_reservation_relationship_invalid"


def test_correlation_rejects_wrong_selected_gateway_key() -> None:
    reservation, ledger, key = _base_rows()
    reservation[0]["gateway_key_id"] = "foreign-key-id"
    ledger[0]["gateway_key_id"] = "foreign-key-id"
    assert _error_code(
        VERIFIER.validate_correlation,
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=0,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a"),
        expected_usage=VERIFIER.Usage(2, 3, 5),
    ) == "correlation_selected_key_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda reservation, ledger, key: reservation.__setitem__("status", "pending"),
         "correlation_reservation_not_finalized"),
        (lambda reservation, ledger, key: ledger.__setitem__("accounting_status", "pending"),
         "correlation_ledger_not_finalized"),
        (lambda reservation, ledger, key: ledger.__setitem__("response_metadata", {}),
         "correlation_cost_metadata_missing"),
        (lambda reservation, ledger, key: ledger.__setitem__(
            "response_metadata",
            {
                "cost_source": "provider_reported",
                "cost_confidence": "provider_reported_with_slaif_comparison",
            },
        ), "correlation_provider_cost_unsubstantiated"),
        (lambda reservation, ledger, key: ledger.__setitem__(
            "response_metadata",
            {
                "cost_source": "slaif_calculated",
                "cost_confidence": "slaif_calculated",
                "canary": "SLAIF-152A-PROBE",
            },
        ), "correlation_privacy_canary_found"),
    ],
)
def test_correlation_rejects_nonterminal_cost_privacy_and_metadata_failures(mutation, code) -> None:
    reservation, ledger, key = _base_rows()
    mutation(reservation[0], ledger[0], key[0])
    assert _error_code(
        VERIFIER.validate_correlation,
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=0,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a"),
        expected_usage=VERIFIER.Usage(2, 3, 5),
    ) == code


def test_correlation_rejects_pending_reservations_and_reserved_counters() -> None:
    reservation, ledger, key = _base_rows()
    key[0]["requests_reserved_total"] = 1
    assert _error_code(
        VERIFIER.validate_correlation,
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=0,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a"),
        expected_usage=VERIFIER.Usage(2, 3, 5),
    ) == "correlation_pending_or_reserved_state"
    key[0]["requests_reserved_total"] = 0
    assert _error_code(
        VERIFIER.validate_correlation,
        reservation_rows=reservation,
        ledger_rows=ledger,
        key_rows=key,
        pending_reservations=1,
        expected_key="gateway-test-token",
        expected_gateway_key_id="key-id",
        flow=VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a"),
        expected_usage=VERIFIER.Usage(2, 3, 5),
    ) == "correlation_pending_or_reserved_state"


def test_execute_flow_does_not_retry_transport_failures() -> None:
    class FailingClient:
        def __init__(self) -> None:
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            raise httpx.ConnectError("transport", request=httpx.Request("POST", "https://gateway.example"))

    client = FailingClient()
    flow = VERIFIER.Flow("openai", "/v1/chat/completions", False, "model-a")
    assert _error_code(
        lambda: asyncio.run(
            VERIFIER.execute_flow(
                client,
                base_url="https://gateway.example/v1",
                gateway_key="gateway-test-token",
                flow=flow,
            )
        )
    ) == "gateway_transport_failure"
    assert client.calls == 1
