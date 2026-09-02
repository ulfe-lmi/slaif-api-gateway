from __future__ import annotations

import ast
import hashlib
import http.server
import json
import os
import queue
import socket
import struct
import subprocess
import sys
import types
import threading
from pathlib import Path

import pytest

from scripts import verify_local_coding_full_stack as verifier


def _fake_codex_provenance() -> dict[str, object]:
    return {
        "source_class": "task_local_exact_npm",
        "requested_package_class": "@openai/codex",
        "requested_version_class": "0.149.0",
        "package_version_class": "0.149.0",
        "raw_version_class": "0.149.0",
        "invoked_version_class": "0.149.0",
        "task_local_under_root": True,
        "verified_binary_is_invoked": True,
        "catalog_and_command_binary_same": True,
        "host_default_version_class": "0.149.1",
        "host_default_matches_pinned": False,
    }


def _signed_local_request(
    *,
    body: bytes = b'{"model":"qwen3.8-27b"}',
    service_token: str = "service-token",
    signing_secret: str = "signing-secret",
    session: str = "session-opaque",
    route: str = verifier.LOCAL_CODING_ROUTE_NAME,
    timestamp: str = "1700000000",
    nonce: str = "1234567890abcdef",
    path: str = "/v1/responses",
    method: str = "POST",
    header_name_counts: tuple[tuple[str, int], ...] | None = None,
) -> verifier.CapturedRequest:
    parts = verifier.urlsplit(path)
    query = parts.query.encode("ascii")
    values = {
        "x-slaif-identity-version": "v1",
        "x-slaif-principal": "principal-opaque",
        "x-slaif-session": session,
        "x-slaif-repository": "repository-opaque",
        "x-slaif-route": route,
        "x-slaif-timestamp": timestamp,
        "x-slaif-nonce": nonce,
    }
    canonical = "\n".join(
        (
            "slaif-local-coding-identity-v1",
            method,
            parts.path,
            hashlib.sha256(query).hexdigest(),
            hashlib.sha256(body).hexdigest(),
            values["x-slaif-principal"],
            values["x-slaif-session"],
            values["x-slaif-repository"],
            values["x-slaif-route"],
            timestamp,
            nonce,
        )
    ).encode()
    headers = {"authorization": f"Bearer {service_token}", **values}
    headers["x-slaif-signature"] = "v1=" + verifier.hmac.new(
        signing_secret.encode(), canonical, hashlib.sha256
    ).hexdigest()
    counts = header_name_counts or tuple(sorted((name, 1) for name in headers))
    return verifier.CapturedRequest(
        path=path,
        body=body,
        headers=headers,
        method=method,
        header_name_counts=counts,
    )


def test_safe_uuid_is_canonical_without_exposing_values() -> None:
    assert verifier._safe_uuid("123e4567-e89b-12d3-a456-426614174000")
    assert not verifier._safe_uuid("123E4567-e89b-12d3-a456-426614174000")
    assert not verifier._safe_uuid("not-a-uuid")


def test_fixture_gate_keeps_historical_and_structural_artifacts_immutable() -> None:
    verifier._verify_fixtures()
    assert hashlib.sha256(verifier.HISTORICAL_FIXTURE.read_bytes()).hexdigest() == verifier.HISTORICAL_FIXTURE_SHA256
    assert hashlib.sha256(verifier.V2_FIXTURE.read_bytes()).hexdigest() == verifier.V2_FIXTURE_SHA256


def test_metadata_keys_are_structural_only() -> None:
    value = {"safe": {"nested": True}, "array": [{"kind": "value"}]}
    assert set(verifier._metadata_keys(value)) == {"safe", "nested", "array", "kind"}


def test_runtime_reference_requires_only_the_two_fixed_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reference = tmp_path / "runtime.env"
    reference.write_text(
        "SLAIF_155F_QWEN_BASE_URL=http://private.example/v1\n"
        "SLAIF_155F_QWEN_CREDENTIAL_SOURCE=/tmp/credential\n",
        encoding="utf-8",
    )
    reference.chmod(0o600)
    monkeypatch.setattr(verifier, "RUNTIME_REFERENCE", reference)
    with pytest.raises(verifier.VerificationError, match="credential_source_unavailable"):
        verifier._read_runtime_reference()


def test_runtime_reference_repr_and_str_redact_both_private_values() -> None:
    reference = verifier.RuntimeReference(
        "https://endpoint-canary.invalid/v1", Path("/tmp/source-canary")
    )
    assert repr(reference) == "RuntimeReference(<redacted>)"
    assert str(reference) == "RuntimeReference(<redacted>)"
    assert "endpoint-canary" not in repr(reference)
    assert "source-canary" not in str(reference)


def test_codex_0149_production_normalizer_accepts_only_reviewed_candidate_shapes() -> None:
    from slaif_gateway.modules.clients.registry import CODEX_0149_CLIENT_MODULE

    payload = {
        "model": verifier.CODEX_MODEL,
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "synthetic"}]}],
        "tools": [
            {
                "type": "tool_search",
                "description": "synthetic candidate",
                "execution": "client",
                "parameters": {},
            },
            {
                "type": "web_search",
                "external_web_access": False,
                "search_content_types": ["text"],
            },
        ],
        "tool_choice": "auto",
    }
    normalized = CODEX_0149_CLIENT_MODULE.normalize_responses(payload)
    assert normalized.adapter_managed_declaration_candidates == (
        "tool_search",
        "web_search",
    )
    assert normalized.body["tools"] == payload["tools"]


def test_exact_codex_capture_tool_mix_exercises_disposable_custom_tool_route_gate() -> None:
    from slaif_gateway.services.responses_route_capabilities import (
        default_responses_capabilities,
        enforce_responses_route_capabilities,
    )

    fixture = verifier.json.loads(verifier.V2_FIXTURE.read_bytes())
    shapes = fixture["capture"]["variants"][0]["request"]["tool_declarations"]["shapes"]
    assert {shape["type"] for shape in shapes} == {
        "custom",
        "function",
        "tool_search",
        "web_search",
    }
    capabilities = default_responses_capabilities()
    capabilities.update(
        {
            "streaming": True,
            "tools": True,
            "function_tools": True,
            "custom_tools": True,
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
        }
    )
    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        streaming_requested=True,
        route_supports_streaming=True,
        function_tools_requested=True,
        custom_tools_requested=True,
        codex_request_envelope_requested=True,
        codex_client_tools_requested=True,
        codex_streaming_tool_events_requested=True,
    )


def test_docker_requires_direct_or_passwordless_sudo_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0 if argv[:3] == ["sudo", "-n", "docker"] else 1, b"", b"")

    monkeypatch.setattr(verifier, "_run", fake_run)
    assert verifier._docker_prefix() == ("sudo", "-n", "docker")
    assert calls == [
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        ["sudo", "-n", "docker", "info", "--format", "{{.ServerVersion}}"],
    ]


@pytest.mark.parametrize(
    ("bad_field", "expected"),
    [
        ("parent", "gateway_report_parent_mismatch"),
        ("path", "gateway_report_not_report_only"),
    ],
)
def test_155af_topology_enforces_exact_prior_report_parent_and_report_only_path(
    monkeypatch: pytest.MonkeyPatch, bad_field: str, expected: str
) -> None:
    current_head = "current-155af-head"
    local_head = verifier.LOCAL_REPORT_HEAD
    report_path = "oap/reports/155-ab-proven-empty-reasoning-canonicalization-and-acceptance.md"

    def fake_git(*args: str, cwd: Path = verifier.REPO_ROOT) -> str:
        if args == ("rev-parse", "HEAD"):
            return local_head if cwd == verifier.LOCAL_ROOT else current_head
        if args == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", f"{verifier.GATEWAY_ACTIVATION_HEAD}^1"):
            return verifier.GATEWAY_REPORT_HEAD
        if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", verifier.GATEWAY_ACTIVATION_HEAD):
            return "oap/active\noap/orders/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md"
        if args == ("rev-parse", f"{verifier.GATEWAY_REPORT_HEAD}^1"):
            return "wrong-parent" if bad_field == "parent" else verifier.GATEWAY_IMPLEMENTATION_HEAD
        if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", verifier.GATEWAY_REPORT_HEAD):
            return "wrong-path" if bad_field == "path" else report_path
        return ""

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if argv[:2] == ["git", "merge-base"]:
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[:3] == ["gh", "pr", "view"]:
            pr = argv[3]
            head = current_head if pr == "291" else local_head
            payload = {
                "state": "OPEN",
                "isDraft": False,
                "headRefOid": head,
                "mergeStateStatus": "CLEAN",
                "autoMergeRequest": None,
            }
            return subprocess.CompletedProcess(argv, 0, verifier.json.dumps(payload).encode(), b"")
        if argv[:3] == ["gh", "pr", "checks"]:
            output = "\n".join(f"check-{index}\tpass\t1s\thttps://example.invalid/{index}" for index in range(10))
            return subprocess.CompletedProcess(argv, 0, (output + "\n").encode(), b"")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(verifier, "_git", fake_git)
    monkeypatch.setattr(verifier, "_run", fake_run)
    with pytest.raises(verifier.VerificationError, match=expected):
        verifier._verify_commit_topology()


def test_155ag_topology_anchors_are_the_155af_report_and_activation() -> None:
    assert verifier.GATEWAY_REPORT_HEAD == "37e923304cf4b1cdb4fb9f8faefe4a7b2fb6db6e"
    assert verifier.GATEWAY_IMPLEMENTATION_HEAD == "34ab5afd09af026286779838db21cddad1717877"
    assert verifier.GATEWAY_ACTIVATION_HEAD == "a570d6087ca488bc7fb1ec9a9ed0e51266b52b15"
    assert verifier.GATEWAY_REPORT_PATH == "oap/reports/155-af-null-encrypted-replay-detector-and-final-acceptance.md"


def test_155af_topology_anchors_exact_local_report_parent_and_path() -> None:
    assert verifier.LOCAL_ROOT == Path("/home/ubuntu/codex-work/slaif-local-coding-005m")
    assert verifier.LOCAL_REPORT_HEAD == "4d3ab2fd97d249710f952dd3d2c28936138cc8fa"
    assert verifier.LOCAL_REPORT_PARENT == "258ae2ebad39651076937b9f027e60831b8d2786"
    assert verifier.LOCAL_SIGNED_CONTRACT_HEAD == "356be8345dd71d6fddf829278651d18e485731d4"
    assert verifier.LOCAL_REPORT_PATH == "oap/reports/005-m-gateway-155r-real-codex-matrix-and-cutover-closure.md"


def test_local_error_vocabulary_is_pinned_to_immutable_local_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for relative_path in verifier._LOCAL_SOURCE_FILES:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            repr(sorted(verifier._LOCAL_FIXED_ERROR_CODE_TO_STAGE))
            + "\n"
            + repr(sorted(verifier._LOCAL_CONSTITUTION_INJECTION_SUFFIXES)),
            encoding="utf-8",
        )
    monkeypatch.setattr(verifier, "LOCAL_ROOT", tmp_path)
    verifier._verify_local_error_source_contract()
    assert verifier._safe_local_error_code_class("responses_tool_policy_invalid") == (
        "responses_tool_policy_invalid"
    )
    assert verifier._safe_local_error_code_class("constitution_bounds_exceeded") == (
        "constitution_bounds_exceeded"
    )
    assert verifier._safe_local_error_code_class("responses_codex_tool_roundtrip_invalid") == "other"
    assert verifier._safe_local_error_code_class("private-local-code") == "other"
    assert verifier._safe_local_error_code_class(None) == "other"


@pytest.mark.parametrize(
    ("code", "stage"),
    [
        ("invalid_service_authorization", "service_auth"),
        ("signed_identity_signature_mismatch", "signed_identity"),
        ("signed_identity_route_mismatch", "signed_identity"),
        ("invalid_json", "json_route_image"),
        ("image_limit_exceeded", "json_route_image"),
        ("responses_disabled_tool_choice", "tool_policy"),
        ("constitution_duplicate_marker", "observation_constitution"),
        ("upstream_timeout", "upstream"),
        ("other", "other"),
    ],
)
def test_local_error_stage_mapping_is_closed_and_cross_class_safe(
    code: str, stage: str
) -> None:
    assert verifier._safe_local_rejection_stage(code) == stage
    assert verifier._safe_local_rejection_stage("responses_codex_tool_roundtrip_invalid") == "other"


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        (None, "absent"),
        ("auto", "automatic_none"),
        ("none", "automatic_none"),
        ("required", "required"),
        ("tool_search", "explicit_disabled_search"),
        ("web_search", "explicit_disabled_search"),
        ({"type": "auto"}, "automatic_none"),
        ({"type": "allowed_tools", "mode": "none"}, "automatic_none"),
        ({"type": "function", "name": "lookup"}, "explicit_retained_local"),
        ({"type": "custom", "name": "emit"}, "explicit_retained_local"),
        ({"type": "mcp"}, "malformed_other"),
        ({"type": "function", "name": "missing"}, "malformed_other"),
        ({"type": "tool_search", "mode": "required"}, "malformed_other"),
        (["required"], "malformed_other"),
    ],
)
def test_local_tool_choice_classifier_is_bounded(
    choice: object, expected: str
) -> None:
    payload: dict[str, object] = {
        "tools": [
            {"type": "function", "name": "lookup"},
            {"type": "custom", "name": "emit"},
        ]
    }
    if choice is not None:
        payload["tool_choice"] = choice
    assert verifier._classify_local_tool_choice(payload) == expected


def test_local_tool_choice_classifier_rejects_ambiguous_duplicate_declarations() -> None:
    payload = {
        "tools": [
            {"type": "function", "name": "lookup"},
            {"type": "function", "name": "lookup"},
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
    }
    assert verifier._classify_local_tool_choice(payload) == "malformed_other"


@pytest.mark.parametrize(
    ("codes", "statuses", "expected"),
    [
        (["responses_tool_policy_invalid"], [422], {"tool_policy": "rejected"}),
        (["constitution_duplicate_marker"], [422], {"constitution": "rejected", "observation": "entered"}),
        (["upstream_error"], [502], {"upstream": "rejected"}),
        (["none"], [200], {"upstream": "succeeded", "tool_policy": "succeeded"}),
        (["not-a-local-code"], [500], {"tool_policy": "unknown", "upstream": "unknown"}),
    ],
)
def test_local_boundary_state_projection_is_fail_closed(
    codes: list[str], statuses: list[int], expected: dict[str, str]
) -> None:
    states = verifier._safe_local_boundary_states_from_codes(codes, statuses)
    for name, state in expected.items():
        assert states[name] == state
    assert set(states) == {"tool_policy", "observation", "constitution", "upstream"}


def test_local_boundary_state_projection_uses_only_existing_metric_deltas() -> None:
    before = verifier.LocalMetrics(1, 2, 3, 4, 5, 6, 7, 8)
    after = verifier.LocalMetrics(1, 3, 3, 4, 5, 6, 8, 8)
    states = verifier._safe_local_boundary_states_from_codes(
        ["none"], [200], before, after
    )
    assert states == {
        "tool_policy": "transformed",
        "observation": "entered",
        "constitution": "entered",
        "upstream": "succeeded",
    }


def test_local_relay_retains_only_source_reviewed_code_and_stage() -> None:
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    relay.remember_error_body(
        b'{"error":{"code":"responses_disabled_tool_choice"}}',
        request_body=b'{}',
    )
    relay.remember_response(422, "/v1/responses")
    status = relay.status()
    assert status["local_error_code_classes"] == ["responses_disabled_tool_choice"]
    assert status["local_error_stage_classes"] == ["tool_policy"]
    assert status["local_boundary_states"]["tool_policy"] == "rejected"
    assert verifier._safe_local_error_code_class("responses_codex_tool_roundtrip_invalid") == "other"


def test_signed_local_request_projection_verifies_exact_body_and_headers() -> None:
    request = _signed_local_request(path="/v1/responses?bounded=1")
    facts = verifier._safe_signed_identity_projection(
        request,
        service_token="service-token",
        signing_secret="signing-secret",
    )
    assert facts == {
        "service_bearer_equal": True,
        "required_header_cardinality_class": "exact",
        "canonical_bytes_reconstructed": True,
        "raw_body_canonical_participates": True,
        "signature_verifies": True,
        "route_matches": True,
        "method_path_query_valid": True,
        "version_shape_valid": True,
        "timestamp_shape_valid": True,
        "nonce_shape_valid": True,
        "no_extra_internal_headers": True,
        "signed_identity_class": "verified",
    }
    rendered = json.dumps(facts, sort_keys=True)
    assert "service-token" not in rendered
    assert "signing-secret" not in rendered
    assert "session-opaque" not in rendered


@pytest.mark.parametrize(
    ("kwargs", "expected_cardinality"),
    [
        ({"header_name_counts": tuple()}, "exact"),
        ({"header_name_counts": (("x-slaif-session", 2),)}, "duplicate"),
        ({"header_name_counts": (("x-slaif-session", 1),)}, "missing"),
        ({"header_name_counts": (("x-slaif-extra", 1),)}, "extra"),
    ],
)
def test_signed_local_request_projection_does_not_collapse_header_cardinality(
    kwargs: dict[str, object], expected_cardinality: str
) -> None:
    if expected_cardinality == "extra":
        base = _signed_local_request()
        kwargs = {
            **kwargs,
            "header_name_counts": (*base.header_name_counts, ("x-slaif-extra", 1)),
        }
    request = _signed_local_request(**kwargs)
    facts = verifier._safe_signed_identity_projection(
        request,
        service_token="service-token",
        signing_secret="signing-secret",
    )
    assert facts["required_header_cardinality_class"] == expected_cardinality
    if expected_cardinality != "exact":
        assert facts["signed_identity_class"] == "invalid"


@pytest.mark.parametrize(
    ("mutation", "expected_false"),
    [
        ("service", "service_bearer_equal"),
        ("body", "signature_verifies"),
        ("route", "route_matches"),
        ("timestamp", "timestamp_shape_valid"),
        ("nonce", "nonce_shape_valid"),
        ("internal", "no_extra_internal_headers"),
    ],
)
def test_signed_local_request_projection_negative_facts_fail_closed(
    mutation: str, expected_false: str
) -> None:
    request = _signed_local_request()
    headers = dict(request.headers)
    body = request.body
    counts = request.header_name_counts
    if mutation == "service":
        headers["authorization"] = "Bearer wrong-service"
    elif mutation == "body":
        body += b" "
    elif mutation == "route":
        request = _signed_local_request(route="wrong-route")
        headers = request.headers
    elif mutation == "timestamp":
        request = _signed_local_request(timestamp="01")
        headers = request.headers
    elif mutation == "nonce":
        request = _signed_local_request(nonce="short")
        headers = request.headers
    elif mutation == "internal":
        headers["x-internal-canary"] = "present"
        counts = tuple(sorted((*counts, ("x-internal-canary", 1))))
    mutated = verifier.CapturedRequest(
        path=request.path,
        body=body,
        headers=headers,
        method=request.method,
        header_name_counts=counts,
    )
    facts = verifier._safe_signed_identity_projection(
        mutated,
        service_token="service-token",
        signing_secret="signing-secret",
    )
    assert facts[expected_false] is False
    assert facts["signed_identity_class"] == "invalid"


def test_qwen_relay_keeps_compiler_and_inference_statuses_separate() -> None:
    relay = verifier._QwenRelayServer(
        ("127.0.0.1", 0),
        endpoint="http://127.0.0.1:1/v1",
        relay_token="relay-token",
        qwen_token="qwen-token",
    )
    relay.record_upstream_status(200, compiler=True)
    relay.record_upstream_status(503, inference=True)
    relay.remember_content_type("application/json", compiler=True)
    relay.remember_content_type("text/event-stream", inference=True)
    status = relay.status()
    assert status["compiler_statuses"] == [200]
    assert status["inference_statuses"] == [503]
    assert status["compiler_content_type_classes"] == ["json"]
    assert status["inference_content_type_classes"] == ["sse"]


def test_summary_retains_compiler_status_alongside_inference_status() -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_qwen_projection",
        codex_failure_category="turn_failed",
        gateway_requests=1,
        gateway_status={"response_statuses": [200]},
        local_requests=1,
        local_status={"response_statuses": [200]},
        qwen_status={
            "compiler_calls": 1,
            "compiler_statuses": [200],
            "compiler_content_type_classes": ["json"],
            "inference_calls": 1,
            "inference_statuses": [503],
            "inference_content_type_classes": ["json"],
        },
        request_projections=[{}],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    assert summary["qwen"]["compiler_count"] == "1"
    assert summary["qwen"]["compiler_status_classes"] == ["2xx"]
    assert summary["qwen"]["inference_count"] == "1"
    assert summary["qwen"]["status_classes"] == ["5xx"]
    assert verifier._sanitize_preclassification_summary(summary) == summary


def test_codex_provenance_accepts_only_task_local_exact_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path
    install = root / "codex-install"
    package = install / "node_modules" / "@openai" / "codex"
    binary = install / "node_modules" / ".bin" / "codex"
    package.mkdir(parents=True)
    binary.parent.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@openai/codex", "version": "0.149.0"}),
        encoding="utf-8",
    )
    binary.write_text("task-local executable", encoding="utf-8")

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raw = b"codex-cli 0.149.1\n" if argv[0] == "/usr/bin/codex" else b"codex-cli 0.149.0\n"
        return subprocess.CompletedProcess(argv, 0, raw, b"")

    monkeypatch.setattr(verifier, "_run", fake_run)
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: "/usr/bin/codex")
    facts = verifier._verify_codex_task_local_provenance(root, binary)
    assert facts == {
        "source_class": "task_local_exact_npm",
        "requested_package_class": "@openai/codex",
        "requested_version_class": "0.149.0",
        "package_version_class": "0.149.0",
        "raw_version_class": "0.149.0",
        "invoked_version_class": "0.149.0",
        "task_local_under_root": True,
        "verified_binary_is_invoked": True,
        "catalog_and_command_binary_same": True,
        "host_default_version_class": "0.149.1",
        "host_default_matches_pinned": False,
    }
    assert verifier._safe_codex_provenance(facts) == facts


@pytest.mark.parametrize("mutation", ["version", "binary"])
def test_codex_provenance_rejects_package_mismatch_and_host_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str
) -> None:
    root = tmp_path
    install = root / "codex-install"
    package = install / "node_modules" / "@openai" / "codex"
    binary = install / "node_modules" / ".bin" / "codex"
    package.mkdir(parents=True)
    binary.parent.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "@openai/codex",
                "version": "0.149.1" if mutation == "version" else "0.149.0",
            }
        ),
        encoding="utf-8",
    )
    binary.write_text("task-local executable", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "_run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, b"codex-cli 0.149.0\n", b""
        ),
    )
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: None)
    target = binary if mutation == "version" else Path("/usr/bin/codex")
    expected = "codex_package_version_mismatch" if mutation == "version" else "codex_binary_not_task_local"
    with pytest.raises(verifier.VerificationError, match=expected):
        verifier._verify_codex_task_local_provenance(root, target)


def test_codex_catalog_and_command_use_the_same_binary_variable() -> None:
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    matching_calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"_write_0149_model_catalog", "_exec_command_0149"}:
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            matching_calls.append(node.args[0].id)
    assert matching_calls
    assert set(matching_calls) == {"codex_binary"}
    source = Path(verifier.__file__).read_text(encoding="utf-8")
    assert "CODEX_PACKAGE_SPEC" in source
    assert "@openai/codex@" not in source


def test_155r_parses_immutable_direct_baseline_with_independent_verdicts() -> None:
    baseline = verifier._read_pinned_direct_baseline()
    assert verifier._terminal_completion_valid(baseline) is True
    rebuilt = verifier._safe_stream_summary(
        baseline, boundary="direct_qwen", ran=True,
        decision="ambiguous_stream_evidence",
    )
    assert rebuilt["evidence_source"] == "pinned_155l"
    assert rebuilt["ran_current_invocation"] is False
    assert rebuilt["normalization_status"] == "complete"
    assert baseline["terminal_completion_valid"] is True
    assert baseline["event_vocabulary_reviewed"] is False
    assert baseline["unknown_events"] is True
    assert baseline["event_counts"]["other"] == 1259


@pytest.mark.parametrize("mutation", ["altered", "duplicate"])
def test_155r_rejects_altered_or_multiple_direct_baseline_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str
) -> None:
    source = verifier.DIRECT_BASELINE_REPORT.read_text(encoding="utf-8")
    direct = next(line for line in source.splitlines() if line.startswith("STREAM_BOUNDARY ") and '"boundary":"direct_qwen"' in line)
    if mutation == "altered":
        source = source.replace('"unknown_events":true', '"unknown_events":false', 1)
    else:
        source += direct + "\n"
    report = tmp_path / "155-l-report.md"
    report.write_text(source, encoding="utf-8")
    monkeypatch.setattr(verifier, "DIRECT_BASELINE_REPORT", report)
    with pytest.raises(verifier.VerificationError, match="pinned_direct_baseline"):
        verifier._read_pinned_direct_baseline()


def test_check_parser_handles_spaced_names_and_fails_mixed_statuses() -> None:
    rows = [
        f"Check {index} with spaces\tpass\t1s\thttps://example.invalid/{index}\t"
        for index in range(10)
    ]
    assert verifier._checks_are_green(("\n".join(rows) + "\n").encode())
    rows[-1] = rows[-1].replace("\tpass\t", "\tpending\t")
    assert not verifier._checks_are_green(("\n".join(rows) + "\n").encode())


def test_stage_tracker_accepts_only_declared_stages_and_localizes_unknowns() -> None:
    tracker = verifier.StageTracker()
    for stage in verifier.COMPOSITION_STAGES:
        tracker.set(stage)
        assert str(tracker.unexpected()) == f"unexpected_{stage}"
    with pytest.raises(verifier.VerificationError, match="unknown_composition_stage"):
        tracker.set("not-a-stage")
    unknown = verifier.StageTracker()
    assert str(unknown.unexpected()) == "unexpected_unknown_stage"


def test_stage_tracker_composed_codes_are_fixed_and_private_free() -> None:
    tracker = verifier.StageTracker()
    assert {
        "client_stream",
        "boundary_capture",
        "tool_roundtrip_privacy_aliases",
        "tool_roundtrip_signed_identity_headers",
        "tool_roundtrip_sse_validation",
        "tool_roundtrip_qwen_boundary",
    }.issubset(verifier.COMPOSITION_STAGES)
    for stage in verifier.COMPOSITION_STAGES:
        tracker.set(stage)
        assert str(tracker.unexpected_composed()) == f"unexpected_composed_{stage}"
    unknown = verifier.StageTracker()
    assert str(unknown.unexpected_composed()) == "unexpected_composed_unknown_stage"
    tracker.set("tool_roundtrip_privacy_aliases")
    assert (
        str(tracker.unexpected_composed(TypeError("not retained")))
        == "unexpected_composed_tool_roundtrip_privacy_aliases_TypeError"
    )
    assert (
        str(tracker.unexpected_composed(RuntimeError("not retained")))
        == "unexpected_composed_tool_roundtrip_privacy_aliases_Other"
    )


def test_composed_wrapper_sanitizes_unexpected_exception_at_unknown_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("private body and endpoint")

    monkeypatch.setattr(verifier, "_run_composed_impl", fail)
    with pytest.raises(verifier.VerificationError, match="unexpected_unknown_stage") as error:
        verifier._run_composed(tmp_path, object(), Path("codex"))  # type: ignore[arg-type]
    assert "private" not in str(error.value)


def test_composed_wrapper_preserves_primary_stage_across_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*_args: object, tracker: verifier.StageTracker, **_kwargs: object) -> dict[str, object]:
        tracker.set("ordinary_response")
        raise RuntimeError("private provider response")

    monkeypatch.setattr(verifier, "_run_composed_impl", fail)
    with pytest.raises(verifier.VerificationError, match="unexpected_ordinary_response") as error:
        verifier._run_composed(tmp_path, object(), Path("codex"), fake_qwen=True)  # type: ignore[arg-type]
    assert "private" not in str(error.value)


def test_fake_qwen_rehearsal_double_has_bounded_wire_contract() -> None:
    fake, thread, token = verifier._start_fake_qwen()
    try:
        base = f"http://127.0.0.1:{fake.server_address[1]}"
        assert verifier.httpx.get(
            f"{base}/health", headers={"Authorization": f"Bearer {token}"}, timeout=5
        ).status_code == 200
        response = verifier.httpx.post(
            f"{base}/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": verifier.CODEX_MODEL, "stream": False},
            timeout=5,
        )
        assert response.status_code == 200
        stream = verifier.httpx.stream(
            "POST",
            f"{base}/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": verifier.CODEX_MODEL, "stream": True},
            timeout=5,
        )
        with stream as result:
            chunks = result.iter_raw()
            first = next(chunks)
            assert b"response.created" in first
            body = first + b"".join(chunks)
            assert b"response.output_text.delta" in body
            assert body.count(b"event: response.created") == 1
            assert body.count(b"event: response.completed") == 1
            assert body.count(b"event: response.output_item.added") == 1
            assert body.count(b"event: response.content_part.added") == 1
            assert body.count(b"event: response.output_text.done") == 1
            assert body.count(b"event: response.content_part.done") == 1
            assert body.count(b"event: response.output_item.done") == 1
            assert b"data: [DONE]" not in body
            assert b'"status":"in_progress"' in body
            assert b'"status":"completed"' in body
            assert b'"output":[{' in body
            assert b'"input_tokens_per_turn":[2]' in body
            assert b'"output_tokens_per_turn":[2]' in body
            assert fake.first_event_sent.wait(timeout=1)
        assert fake.inference_calls == 2
        assert fake.stream_calls == 1
    finally:
        fake.shutdown()
        fake.server_close()
        thread.join(timeout=2)


def test_fake_qwen_tool_roundtrip_mode_is_dedicated_and_allowlisted() -> None:
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "_FakeQwenHandler"
    )
    assert sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_stream_function"
        for node in handler.body
    ) == 1

    fake = verifier._FakeQwenServer(
        ("127.0.0.1", 0), "synthetic-token", tool_roundtrip_mode=True
    )
    try:
        calls: list[str] = []
        handler_instance = object.__new__(verifier._FakeQwenHandler)
        handler_instance.server = fake
        handler_instance._stream_function = lambda _payload: calls.append("function")
        handler_instance._stream_message = lambda: calls.append("message")
        handler_instance._stream({"stream": True, "input": []})
        handler_instance._stream(
            {
                "stream": True,
                "input": [{"type": "function_call_output", "call_id": "bounded", "output": "ok"}],
            }
        )
        assert calls == ["function", "message"]
        status = fake.status()
        assert status["tool_roundtrip_mode"] is True
        assert status["tool_roundtrip_turns"] == 2
        assert status["tool_result_observed"] == 1
        assert status["function_lifecycle_count"] == 1
        assert status["message_lifecycle_count"] == 1
    finally:
        fake.server_close()


def test_exec_command_0149_pins_zero_request_and_stream_retries() -> None:
    import scripts.capture_codex_protocol as capture

    command = capture._exec_command_0149(
        Path("/task/codex"),
        workdir=Path("/task/work"),
        port=12345,
        model=capture.PINNED_MODEL,
        model_catalog=Path("/task/catalog.json"),
        output_path=Path("/task/output.json"),
    )
    assert "model_providers.slaif-capture.request_max_retries=0" in command
    assert "model_providers.slaif-capture.stream_max_retries=0" in command


def test_forced_fake_rejection_emits_full_bounded_function_item() -> None:
    fake = verifier._FakeQwenServer(
        ("127.0.0.1", 0),
        "synthetic-token",
        qualification_rejection_mode=True,
    )
    try:
        events: list[tuple[str, dict[str, object]]] = []
        handler = object.__new__(verifier._FakeQwenHandler)
        handler.server = fake
        handler._write_stream_events = lambda value: events.extend(value)
        handler._json = lambda *_args: pytest.fail("known reviewed tool missing")
        handler._stream_qualification_rejection(
            {
                "tools": [
                    {
                        "type": "function",
                        "name": "shell_command",
                        "parameters": {"type": "object"},
                    }
                ]
            }
        )
        assert len(events) == 2
        item = events[1][1]["item"]
        assert item == {
            "type": "function_call",
            "id": "qualification_function",
            "status": "in_progress",
            "name": "shell_command",
            "arguments": "",
            "call_id": "qualification_call",
            "caller": None,
            "namespace": "functions",
        }
    finally:
        fake.server_close()


def test_qualification_hook_is_exact_profile_scoped_write_once_and_no_follow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from slaif_gateway.providers.streaming import ResponsesStreamValidationProfile
    from slaif_gateway.services import responses_gateway

    exact_root = tmp_path / "exact"
    ordinary_root = tmp_path / "ordinary"
    hosted_root = tmp_path / "hosted"
    symlink_root = tmp_path / "symlink"
    for root in (exact_root, ordinary_root, hosted_root, symlink_root):
        root.mkdir()
        root.chmod(0o700)
    artifact = exact_root / verifier.QUALIFICATION_ARTIFACT_NAME
    monkeypatch.setenv(verifier.QUALIFICATION_HOOK_ENV, "1")
    monkeypatch.setenv(verifier.QUALIFICATION_ROOT_ENV, str(exact_root))
    monkeypatch.setenv(verifier.QUALIFICATION_ARTIFACT_ENV, str(artifact))
    exact = ResponsesStreamValidationProfile(
        codex_reasoning_events=True,
        codex_0149_function_tool_events=True,
        codex_streaming_tool_events=True,
        declared_client_tools=frozenset({("functions", "shell_command", "function")}),
        web_search=False,
    )
    event = {
        "type": "response.output_item.added",
        "sequence_number": 1,
        "output_index": 0,
        "item": {
            "type": "function_call",
            "id": "qualification_function",
            "status": "in_progress",
            "name": "shell_command",
            "arguments": "synthetic-argument-canary",
            "call_id": "qualification_call",
            "caller": None,
            "namespace": "functions",
        },
    }
    responses_gateway._record_qualification_rejection(
        event, profile=exact, rejection_code="responses_stream_event_not_supported"
    )
    assert artifact.stat().st_mode & 0o777 == 0o600
    first = artifact.read_bytes()
    assert b"shell_command" not in first
    assert b"qualification_function" not in first
    assert b"qualification_call" not in first
    assert b"synthetic-argument-canary" not in first
    assert b"printf" not in first
    responses_gateway._record_qualification_rejection(
        {**event, "type": "response.other"},
        profile=exact,
        rejection_code="responses_stream_provider_failure",
    )
    assert artifact.read_bytes() == first

    ordinary = ResponsesStreamValidationProfile()
    ordinary_artifact = ordinary_root / verifier.QUALIFICATION_ARTIFACT_NAME
    monkeypatch.setenv(verifier.QUALIFICATION_ROOT_ENV, str(ordinary_root))
    monkeypatch.setenv(verifier.QUALIFICATION_ARTIFACT_ENV, str(ordinary_artifact))
    responses_gateway._record_qualification_rejection(
        event, profile=ordinary, rejection_code="responses_stream_event_not_supported"
    )
    assert not ordinary_artifact.exists()

    hosted = ResponsesStreamValidationProfile(
        codex_reasoning_events=True,
        codex_0149_function_tool_events=True,
        codex_streaming_tool_events=True,
        declared_client_tools=exact.declared_client_tools,
        web_search=True,
    )
    hosted_artifact = hosted_root / verifier.QUALIFICATION_ARTIFACT_NAME
    monkeypatch.setenv(verifier.QUALIFICATION_ROOT_ENV, str(hosted_root))
    monkeypatch.setenv(verifier.QUALIFICATION_ARTIFACT_ENV, str(hosted_artifact))
    responses_gateway._record_qualification_rejection(
        event, profile=hosted, rejection_code="responses_stream_event_not_supported"
    )
    assert not hosted_artifact.exists()

    symlink_target = symlink_root / "target.json"
    symlink_target.write_bytes(b"unchanged")
    symlink = symlink_root / verifier.QUALIFICATION_ARTIFACT_NAME
    symlink.symlink_to(symlink_target)
    monkeypatch.setenv(verifier.QUALIFICATION_ROOT_ENV, str(symlink_root))
    monkeypatch.setenv(verifier.QUALIFICATION_ARTIFACT_ENV, str(symlink))
    responses_gateway._record_qualification_rejection(
        event, profile=exact, rejection_code="responses_stream_event_not_supported"
    )
    assert symlink_target.read_bytes() == b"unchanged"


def test_qualification_reader_rejects_foreign_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    root.chmod(0o700)
    artifact = root / verifier.QUALIFICATION_ARTIFACT_NAME
    artifact.write_bytes(b"{}")
    artifact.chmod(0o600)
    real_lstat = Path.lstat

    def foreign_lstat(path: Path) -> object:
        result = real_lstat(path)
        if path == artifact:
            return types.SimpleNamespace(
                st_mode=result.st_mode,
                st_uid=os.getuid() + 1,
            )
        return result

    monkeypatch.setattr(Path, "lstat", foreign_lstat)
    with pytest.raises(verifier.VerificationError, match="qualification_artifact_invalid"):
        verifier._read_qualification_rejection(root)


def test_sanitized_rejection_survives_composed_cleanup_and_absent_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection = {
        "schema": "responses_stream_rejection_v1",
        "event_type": "response.output_item.added",
        "top_level_fields": [
            {"name": "item", "type": "object"},
            {"name": "type", "type": "string"},
        ],
        "nested_object_fields": [
            {"name": "item", "fields": [{"name": "type", "type": "string"}]}
        ],
        "validator_profile": {
            "codex_reasoning_events": True,
            "codex_0149_function_tool_events": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": False,
            "web_search": False,
            "declared_client_tools_class": "bounded",
            "web_search_max_tool_calls_class": "none",
        },
        "rejection": {
            "outcome": "validator_rejected",
            "code": "responses_stream_event_not_supported",
        },
    }
    monkeypatch.setattr(verifier, "_verify_commit_topology", lambda: None)
    monkeypatch.setattr(verifier, "_verify_fixtures", lambda: None)
    monkeypatch.setattr(verifier, "_validate_local_config", lambda *_args: Path("config"))
    monkeypatch.setattr(verifier, "_install_codex", lambda _root: Path("codex"))
    monkeypatch.setattr(verifier, "_verify_codex_task_local_provenance", lambda *_args: _fake_codex_provenance())
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="unclassified",
        gateway_requests=0,
        gateway_status={},
        local_requests=0,
        local_status={},
        qwen_status={},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=rejection,
        artifact_equal=True,
    )
    monkeypatch.setattr(
        verifier,
        "_run_composed_stream_diagnostic",
        lambda *_args, **_kwargs: {
            "codex_exit_success": False,
            "qualification_rejection": rejection,
            "qualification_summary": summary,
        },
    )
    monkeypatch.setattr(verifier, "_read_qualification_rejection", lambda _root: None)
    monkeypatch.setattr(verifier, "_read_preclassification_summary", lambda _root: summary)
    result = verifier._run_dedicated_codex_tool_roundtrip(
        fake_qwen=True,
        qualification_hook=True,
        qualification_rejection_mode=True,
    )
    assert result["qualification_rejection"] == rejection


def test_qualification_rejection_dual_evidence_must_match() -> None:
    result = {"qualification_rejection": {"unexpected": True}}
    with pytest.raises(verifier.VerificationError, match="qualification_artifact_invalid"):
        verifier._retain_sanitized_qualification_rejection(result, None)


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ((1, 1, 2), "qualification_turn_counts_g1_l1_q2"),
        ((0, 2, 1), "qualification_turn_counts_g0_l2_q1"),
        ((3, 1, 1), "qualification_turn_counts_gother_l1_q1"),
        (("bad", 1, 1), "qualification_turn_counts_gother_l1_q1"),
    ],
)
def test_qualification_turn_count_error_is_bounded(
    counts: tuple[object, object, object], expected: str
) -> None:
    error = verifier._qualification_turn_count_error(counts)
    assert str(error) == expected
    assert "bad" not in str(error)


def test_dedicated_tool_roundtrip_modes_select_hook_and_hook_free_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, bool]] = []

    def run_mode(*, fake_qwen: bool, qualification_hook: bool) -> dict[str, object]:
        calls.append((fake_qwen, qualification_hook))
        return {"codex_exit_success": True}

    monkeypatch.setattr(verifier, "_run_dedicated_codex_tool_roundtrip", run_mode)
    assert verifier.run_codex_tool_roundtrip_qualification(fake_qwen=True)[
        "codex_exit_success"
    ] is True
    assert verifier.run_codex_tool_roundtrip_protected(fake_qwen=True)[
        "codex_exit_success"
    ] is True
    assert calls == [(True, True), (True, False)]


def test_qualification_cli_returns_failure_for_safe_rejection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rejection = {
        "schema": "responses_stream_rejection_v1",
        "event_type": "response.other",
        "top_level_fields": [],
        "nested_object_fields": [],
        "validator_profile": {
            "codex_reasoning_events": True,
            "codex_0149_function_tool_events": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": False,
            "web_search": False,
            "declared_client_tools_class": "bounded",
            "web_search_max_tool_calls_class": "none",
        },
        "rejection": {"outcome": "validator_rejected", "code": "other"},
    }
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="unclassified",
        gateway_requests=1,
        gateway_status={"response_statuses": [400]},
        local_requests=0,
        local_status={},
        qwen_status={},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=rejection,
        artifact_equal=True,
    )
    monkeypatch.setattr(
        verifier,
        "run_codex_tool_roundtrip_qualification",
        lambda **_kwargs: {"qualification_rejection": rejection, "qualification_summary": summary},
    )
    monkeypatch.setattr(sys, "argv", ["verify", "--tool-roundtrip-qualification"])
    assert verifier.main() == 1
    assert capsys.readouterr().out.startswith("QUALIFICATION=REJECTED ")


def test_preclassification_summary_write_read_handles_short_writes_and_qwen_stream_facts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tmp_path.chmod(0o700)
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="mock_http_status_rejected",
        gateway_requests=2,
        gateway_status={"response_statuses": [200, 503], "response_content_type_classes": ["sse", "json"]},
        local_requests=2,
        local_status={"response_statuses": [200, 503], "response_content_type_classes": ["sse", "json"]},
        qwen_status={
            "inference_calls": 2,
            "inference_statuses": [200, 503],
            "inference_content_type_classes": ["sse", "json"],
            "path_rejections": 0,
            "stream_normal_close": True,
        },
        request_projections=[],
        accounting_statuses={
            "query_ok": True,
            "reservation_finalized": 1,
            "reservation_released": 1,
            "reservation_pending": 0,
            "ledger_finalized": 1,
            "ledger_failed": 1,
            "ledger_estimated": 0,
            "ledger_pending": 0,
        },
        qualification_rejection=None,
        artifact_equal=False,
    )
    original_write = verifier.os.write

    def short_write(fd: int, payload: bytes) -> int:
        return original_write(fd, payload[:1])

    monkeypatch.setattr(verifier.os, "write", short_write)
    assert verifier._write_preclassification_summary(tmp_path, summary) == summary
    assert verifier._read_preclassification_summary(tmp_path) == summary
    assert summary["qwen"]["normal_close"] is True
    assert summary["qwen"]["content_type_classes"] == ["sse", "json"]


@pytest.mark.parametrize(
    "facts",
    [
        {},
        {"gateway_statuses": ["bad"]},
        {"qwen_status": {"inference_statuses": [None]}},
        {"accounting_statuses": {"reservation_finalized": {"raw": "value"}}},
        {"request_projections": [{"unexpected": "private"}]},
    ],
)
def test_failure_localizer_totalizes_partial_safe_facts_without_keyerror(
    facts: dict[str, object],
) -> None:
    base: dict[str, object] = {
        "codex_failure_category": "unclassified",
        "gateway_requests": 1,
        "gateway_statuses": [200],
        "gateway_structures": [],
        "local_requests": 0,
        "local_statuses": [],
        "request_projections": [],
        "gateway_error_code_classes": [],
        "gateway_error_param_classes": [],
        "qwen_status": {},
        "fake_status": {},
        "accounting_statuses": {},
    }
    base.update(facts)
    assert isinstance(verifier._localize_composed_codex_failure(**base), str)


def test_fake_provider_failure_mode_is_opt_in_and_counts_inference_only() -> None:
    fake, thread, token = verifier._start_fake_qwen(
        tool_roundtrip_mode=True, provider_failure_mode=True
    )
    try:
        response = verifier.httpx.post(
            f"http://127.0.0.1:{fake.server_address[1]}/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": verifier.CODEX_MODEL, "stream": True},
            timeout=5,
        )
        assert response.status_code == 503
        status = fake.status()
        assert status["provider_failure_mode"] is True
        assert status["inference_calls"] == 1
        assert status["tool_roundtrip_turns"] == 0
    finally:
        fake.shutdown()
        fake.server_close()
        thread.join(timeout=5)


def test_summary_only_cli_evidence_is_nonzero_and_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="loopback_request_failed",
        gateway_requests=1,
        gateway_status={"response_statuses": [502]},
        local_requests=1,
        local_status={"response_statuses": [502]},
        qwen_status={"inference_calls": 1, "inference_statuses": [503]},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    monkeypatch.setattr(
        verifier,
        "run_codex_tool_roundtrip_qualification",
        lambda **_kwargs: {
            "codex_exit_success": False,
            "qualification_rejection": None,
            "qualification_summary": summary,
            "failure_code": "composed_tool_roundtrip_first_qwen_rejection",
        },
    )
    monkeypatch.setattr(sys, "argv", ["verify", "--tool-roundtrip-qualification"])
    assert verifier.main() == 1
    output = capsys.readouterr().out
    assert output.startswith("QUALIFICATION=FAILED ")
    assert "qualification_summary" not in output
    assert "private" not in output
    assert '"summary"' in output


def test_qualification_cli_direct_stdout_is_one_bounded_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        verifier,
        "run_codex_tool_roundtrip_qualification",
        lambda **_kwargs: {"codex_exit_success": True, "qualification_rejection": None, "qualification_summary": None},
    )
    monkeypatch.setattr(sys, "argv", ["verify", "--tool-roundtrip-qualification-fake"])
    assert verifier.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "QUALIFICATION=PASSED turns=2 function=1 message=1 accounting_rows=2\n"
    assert captured.out.count("\n") == 1


def test_outer_dedicated_runner_retains_summary_after_localizer_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="unclassified",
        gateway_requests=1,
        gateway_status={"response_statuses": [502]},
        local_requests=1,
        local_status={"response_statuses": [502]},
        qwen_status={"inference_calls": 1, "inference_statuses": [503]},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )

    monkeypatch.setattr(verifier, "_verify_commit_topology", lambda: None)
    monkeypatch.setattr(verifier, "_verify_fixtures", lambda: None)
    monkeypatch.setattr(verifier, "_validate_local_config", lambda *_args: Path("config"))
    monkeypatch.setattr(verifier, "_install_codex", lambda _root: Path("codex"))
    monkeypatch.setattr(verifier, "_verify_codex_task_local_provenance", lambda *_args: _fake_codex_provenance())

    def fail_after_summary(root: Path, *_args: object, **_kwargs: object) -> dict[str, object]:
        verifier._write_preclassification_summary(root, summary)
        raise KeyError("private diagnostic value")

    monkeypatch.setattr(verifier, "_run_composed_stream_diagnostic", fail_after_summary)
    result = verifier._run_dedicated_codex_tool_roundtrip(
        fake_qwen=True, qualification_hook=True
    )
    assert result["codex_exit_success"] is False
    assert result["failure_code"] == "qualification_failure_localization"
    assert result["qualification_rejection"] is None
    assert result["qualification_summary"] == summary

    monkeypatch.setattr(
        verifier, "run_codex_tool_roundtrip_qualification", lambda **_kwargs: result
    )
    monkeypatch.setattr(sys, "argv", ["verify", "--tool-roundtrip-qualification"])
    assert verifier.main() == 1
    output = capsys.readouterr().out
    assert output.startswith("QUALIFICATION=FAILED ")
    assert "private diagnostic value" not in output


def test_outer_dedicated_runner_adopts_summary_from_normal_failure_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="mock_response_failed",
        gateway_requests=1,
        gateway_status={"response_statuses": [502]},
        local_requests=1,
        local_status={"response_statuses": [502]},
        qwen_status={"inference_calls": 1, "inference_statuses": [503]},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    monkeypatch.setattr(verifier, "_verify_commit_topology", lambda: None)
    monkeypatch.setattr(verifier, "_verify_fixtures", lambda: None)
    monkeypatch.setattr(verifier, "_validate_local_config", lambda *_args: Path("config"))
    monkeypatch.setattr(verifier, "_install_codex", lambda _root: Path("codex"))
    monkeypatch.setattr(verifier, "_verify_codex_task_local_provenance", lambda *_args: _fake_codex_provenance())
    monkeypatch.setattr(
        verifier,
        "_run_composed_stream_diagnostic",
        lambda *_args, **_kwargs: {"codex_exit_success": False, "failure_code": "safe_failure"},
    )
    monkeypatch.setattr(verifier, "_read_preclassification_summary", lambda _root: summary)
    result = verifier._run_dedicated_codex_tool_roundtrip(
        fake_qwen=True, qualification_hook=True
    )
    assert result["codex_exit_success"] is False
    assert result["qualification_summary"] == summary


@pytest.mark.parametrize(
    ("marker", "category"),
    [
        (b"unknown variant `disabled`", "web_search_config_rejected"),
        (b"error loading config", "configuration_rejected"),
        (b"usage: codex exec", "argument_rejected"),
        (b"missing environment variable", "dummy_auth_environment_rejected"),
        (b"internal app-server channel closed", "app_server_channel_closed"),
        (b"error sending request for url", "loopback_request_failed"),
    ],
)
def test_summary_preserves_every_known_codex_failure_category(
    marker: bytes, category: str
) -> None:
    import scripts.capture_codex_protocol as capture

    assert capture.classify_codex_failure(marker) == category
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_codex_failure_projection",
        codex_failure_category=category,
        gateway_requests=0,
        gateway_status={},
        local_requests=0,
        local_status={},
        qwen_status={},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    assert summary["codex_failure_category"] == category


@pytest.mark.parametrize(
    ("reservations", "ledgers", "turn_count", "expected"),
    [
        ([], [], 0, True),
        (["finalized"], ["finalized"], 1, True),
        (["finalized", "finalized"], ["finalized", "finalized"], 2, True),
        (["released"], ["failed"], 1, True),
        (["finalized", "released"], ["finalized", "failed"], 2, True),
        (["finalized"], ["estimated"], 1, True),
        (["finalized", "finalized"], ["finalized", "estimated"], 2, True),
        (["released"], ["estimated"], 1, False),
        (["finalized"], ["failed"], 1, False),
        (["finalized", "released"], ["failed", "failed"], 2, False),
        (["pending"], ["pending"], 1, False),
        (["finalized"], ["finalized"], 2, False),
        (["released", "finalized"], ["failed", "finalized"], 2, False),
    ],
)
def test_qualification_accounting_accepts_only_coherent_terminal_pairs(
    reservations: list[str],
    ledgers: list[str],
    turn_count: int,
    expected: bool,
) -> None:
    assert verifier._qualification_terminal_sequence_valid(
        reservations, ledgers, turn_count
    ) is expected


def test_composed_roundtrip_does_not_shadow_seeded_key_in_metadata_loop() -> None:
    tree = ast.parse(Path(verifier.__file__).read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_run_composed_codex_tool_roundtrip"
    )
    assert all(
        not (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "key"
        )
        for node in ast.walk(function)
    )


def test_fake_qwen_tool_roundtrip_function_requires_known_local_tool() -> None:
    responses: list[tuple[int, str]] = []
    handler_instance = object.__new__(verifier._FakeQwenHandler)
    handler_instance._json = lambda status, payload: responses.append(
        (status, payload["error"]["code"])
    )
    handler_instance._stream_function(
        {"tools": [{"type": "function", "name": "unreviewed_tool"}]}
    )
    assert responses == [(400, "known_local_tool_missing")]


def test_composed_tool_roundtrip_requires_function_then_message_gateway_lifecycle() -> None:
    def structure(*events: str) -> dict[str, object]:
        return {"event_counts": {event: events.count(event) for event in set(events)}}

    valid = [
        structure(
            "response.output_item.added",
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
            "response.output_item.done",
        ),
        structure(
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.done",
            "response.content_part.done",
            "response.output_item.done",
        ),
    ]
    verifier._assert_function_then_message_structure(valid)

    invalid_first = valid[0]["event_counts"].copy()
    invalid_first["response.output_text.delta"] = 1
    with pytest.raises(verifier.VerificationError, match="composed_tool_roundtrip_lifecycle_invalid"):
        verifier._assert_function_then_message_structure(
            [{"event_counts": invalid_first}, valid[1]]
        )

    invalid_second = valid[1]["event_counts"].copy()
    invalid_second["response.function_call_arguments.done"] = 1
    with pytest.raises(verifier.VerificationError, match="composed_tool_roundtrip_lifecycle_invalid"):
        verifier._assert_function_then_message_structure(
            [valid[0], {"event_counts": invalid_second}]
        )

    with pytest.raises(verifier.VerificationError, match="composed_tool_roundtrip_lifecycle_invalid"):
        verifier._assert_function_then_message_structure(
            [{"event_counts": {"response.output_item.added": "1"}}, valid[1]]
        )


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"gateway_requests": 0}, "composed_tool_roundtrip_launch_config"),
        (
            {"gateway_requests": 1, "gateway_statuses": [400]},
            "composed_tool_roundtrip_first_gateway_pre_local_other_other_other",
        ),
        (
            {
                "gateway_requests": 1,
                "gateway_statuses": [400],
                "local_requests": 1,
                "local_statuses": [400],
            },
            "composed_tool_roundtrip_first_local_rejection",
        ),
        (
            {
                "gateway_requests": 1,
                "gateway_statuses": [400],
                "local_requests": 1,
                "local_statuses": [200],
            },
            "composed_tool_roundtrip_first_gateway_post_local_other_other_other",
        ),
        (
            {
                "gateway_requests": 1,
                "gateway_statuses": [502],
                "qwen_status": {
                    "upstream_statuses": [200, 500],
                    "inference_statuses": [500],
                },
            },
            "composed_tool_roundtrip_first_qwen_rejection",
        ),
        (
            {
                "gateway_requests": 1,
                "gateway_statuses": [200],
                "gateway_structures": [{"invalid": True}],
                "codex_failure_category": "mock_stream_rejected",
            },
            "composed_tool_roundtrip_codex_stream_parse",
        ),
        (
            {
                "gateway_requests": 2,
                "gateway_statuses": [200, 400],
                "local_requests": 2,
                "local_statuses": [200, 400],
            },
            "composed_tool_roundtrip_second_turn_local_rejection",
        ),
        (
            {
                "gateway_requests": 2,
                "gateway_statuses": [200, 400],
                "local_requests": 1,
                "local_statuses": [200],
                "qwen_status": {"inference_statuses": [200]},
                "gateway_error_code_classes": ["none", "codex_tool_roundtrip_invalid"],
                "gateway_error_param_classes": ["none", "input"],
                "request_projections": [
                    {},
                    {
                        "top_level_tool_type_counts": {"custom": 1, "function": 1},
                        "input_item_type_sequence": [
                            "function_call",
                            "function_call_output",
                        ],
                        "stream_class": "true",
                    },
                ],
            },
            "composed_tool_roundtrip_second_turn_gateway_codex_tool_roundtrip_invalid_input_top_level_function_pair_without_additional_tools",
        ),
        (
            {
                "gateway_requests": 2,
                "gateway_statuses": [200, 400],
                "local_requests": 2,
                "local_statuses": [200, 200],
                "gateway_error_code_classes": ["none", "codex_tool_roundtrip_invalid"],
                "gateway_error_param_classes": ["none", "input"],
            },
            "composed_tool_roundtrip_second_turn_gateway_codex_tool_roundtrip_invalid_input_other",
        ),
        (
            {
                "gateway_requests": 2,
                "gateway_statuses": [200, 400],
                "local_requests": 2,
                "local_statuses": [200, 200],
                "gateway_error_code_classes": ["none", "replay_reference_not_found"],
                "gateway_error_param_classes": ["none", "input"],
                "request_projections": [
                    {},
                    {
                        "top_level_tool_type_counts": {"custom": 1, "function": 1},
                        "input_item_type_sequence": [
                            "function_call",
                            "function_call_output",
                        ],
                        "stream_class": "true",
                    },
                ],
            },
            "composed_tool_roundtrip_second_turn_gateway_replay_reference_not_found_input_top_level_function_pair_without_additional_tools",
        ),
        (
            {
                "gateway_requests": 2,
                "gateway_statuses": [200, 200],
                "local_requests": 2,
                "local_statuses": [200, 200],
            },
            "composed_tool_roundtrip_final_message_failure",
        ),
    ],
)
def test_composed_tool_roundtrip_failure_localizer_is_bounded(
    overrides: dict[str, object], expected: str
) -> None:
    facts: dict[str, object] = {
        "codex_failure_category": "unclassified",
        "gateway_requests": 0,
        "gateway_statuses": [],
        "gateway_structures": [],
        "local_requests": 0,
        "local_statuses": [],
        "request_projections": [],
        "gateway_error_code_classes": [],
        "gateway_error_param_classes": [],
        "qwen_status": {},
        "fake_status": {},
        "accounting_statuses": {"query_ok": False},
    }
    facts.update(overrides)
    assert verifier._localize_composed_codex_failure(**facts) == expected


def test_composed_roundtrip_request_projection_retains_only_safe_shape() -> None:
    projection = verifier._safe_roundtrip_request_projection(
        json.dumps(
            {
                "tools": [
                    {"type": "function", "name": "private-name", "description": "private"},
                    {"type": "custom", "name": "private-custom"},
                ],
                "input": [
                    {"type": "function_call", "id": "private-id"},
                    {"type": "function_call_output", "call_id": "private-call", "output": "private"},
                ],
                "stream": True,
            }
        ).encode()
    )
    assert projection == {
        "top_level_tool_type_counts": {"custom": 1, "function": 1},
        "input_item_type_sequence": ["function_call", "function_call_output"],
        "function_call_fields": [
            {"name": "id", "type": "string"},
            {"name": "type", "type": "string"},
        ],
        "function_call_output_fields": [
            {"name": "call_id", "type": "string"},
            {"name": "output", "type": "string"},
            {"name": "type", "type": "string"},
        ],
        "function_item_id_state": "present",
        "function_item_id_prefix_class": "other",
        "function_call_id_state": "absent_or_invalid",
        "adjacent_matching_output": False,
        "stream_class": "true",
        "tool_choice_class": "absent",
    }
    assert (
        verifier._safe_roundtrip_projection_class(projection)
        == "top_level_function_pair_without_additional_tools"
    )
    assert verifier._safe_roundtrip_projection_class({}) == "other"


def test_preclassification_summary_records_bounded_request_ordinals() -> None:
    initial = {
        "top_level_tool_type_counts": {"custom": 1, "function": 1},
        "input_item_type_sequence": ["message"],
        "stream_class": "true",
    }
    continuation = {
        "top_level_tool_type_counts": {"custom": 1, "function": 1},
        "input_item_type_sequence": ["function_call", "function_call_output"],
        "function_call_fields": [
            {"name": "id", "type": "string"},
            {"name": "type", "type": "string"},
        ],
        "function_call_output_fields": [
            {"name": "call_id", "type": "string"},
            {"name": "output", "type": "string"},
            {"name": "type", "type": "string"},
        ],
        "stream_class": "true",
    }
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_codex_failure_projection",
        codex_failure_category="turn_failed",
        gateway_requests=2,
        gateway_status={
            "response_statuses": [200, 400],
            "error_code_classes": ["none", "codex_tool_roundtrip_invalid"],
            "error_param_classes": ["none", "input"],
            "error_param_field_classes": ["none", "type"],
        },
        local_requests=1,
        local_status={"response_statuses": [200]},
        qwen_status={"inference_calls": 1, "inference_statuses": [200]},
        request_projections=[initial, continuation],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    assert summary["request_profile_classes"] == [
        "other",
        "top_level_function_pair_without_additional_tools",
    ]
    assert summary["gateway_error_code_classes"] == [
        "none",
        "codex_tool_roundtrip_invalid",
    ]
    assert summary["gateway_error_param_classes"] == ["none", "input"]
    assert summary["gateway_error_param_field_classes"] == ["none", "type"]
    assert summary["second_request_input_item_type_sequence"] == [
        "function_call",
        "function_call_output",
    ]
    assert summary["second_request_top_level_tool_type_counts"] == {
        "custom": 1,
        "function": 1,
    }
    assert summary["second_function_call_fields"] == [
        {"name": "id", "type": "string"},
        {"name": "type", "type": "string"},
    ]
    assert summary["second_function_call_output_fields"] == [
        {"name": "call_id", "type": "string"},
        {"name": "output", "type": "string"},
        {"name": "type", "type": "string"},
    ]
    assert verifier._sanitize_preclassification_summary(summary) == summary


def test_gateway_error_parameter_projection_is_bounded_to_root_and_leaf() -> None:
    assert verifier._safe_gateway_error_param_class("input[1].type") == "input"
    assert verifier._safe_gateway_error_param_field_class("input[1].type") == "type"
    assert verifier._safe_gateway_error_param_field_class("input") == "none"
    assert verifier._safe_gateway_error_param_class("private-value") == "other"
    assert verifier._safe_gateway_error_param_field_class("private-value") == "other"


def test_input_item_error_projection_distinguishes_item_and_field_without_values() -> None:
    body = json.dumps(
        {
            "input": [
                {
                    "type": "message",
                    "content": [],
                    "private_field_canary": "private-value-canary",
                },
                "not-an-object",
            ]
        }
    ).encode()
    item = verifier._safe_input_item_error_projection("input[0]", body)
    assert item["input_item_error_shape_class"] == "item"
    assert item["item_json_type_class"] == "object"
    assert item["item_type_class"] == "message"
    assert item["index_syntactically_bounded"] is True
    assert item["index_in_range"] is True
    assert item["selected_item_object"] is True
    assert item["rejected_field_name_class"] == "none"
    assert {
        (field["name"], field["type"])
        for field in item["rejected_item_fields"]
    } >= {
        ("content", "array"),
        ("other", "string"),
        ("type", "string"),
    }
    field = verifier._safe_input_item_error_projection("input[0].content", body)
    assert field["input_item_error_shape_class"] == "field"
    assert field["rejected_field_name_class"] == "content"
    assert field["rejected_field_present"] is True
    unknown = verifier._safe_input_item_error_projection("input[0].private_field_canary", body)
    assert unknown["rejected_field_name_class"] == "other"
    assert unknown["rejected_field_present"] is True
    for projection in (item, field, unknown):
        rendered = json.dumps(projection, sort_keys=True)
        assert "private-value-canary" not in rendered
        assert "private_field_canary" not in rendered
        assert "input[0]" not in rendered


@pytest.mark.parametrize(
    ("param", "shape", "in_range"),
    [
        ("input[0]", "item", True),
        ("input[1]", "item", True),
        ("input[2]", "item", False),
        ("input[999]", "item", False),
        ("input[0].content", "field", True),
        ("input[0].content.text", "other", False),
        ("input[0].content-text", "other", False),
        ("input[0].content\u0000", "other", False),
        ("input[x]", "other", False),
        ("input[-1]", "other", False),
        ("input[0000]", "item", False),
    ],
)
def test_input_item_error_projection_is_closed_over_parameter_shapes(
    param: str, shape: str, in_range: bool
) -> None:
    body = b'{"input":[null,{"type":"reasoning"}]}'
    projection = verifier._safe_input_item_error_projection(param, body)
    assert projection["input_item_error_shape_class"] == shape
    assert projection["index_in_range"] is in_range
    assert set(projection) == {
        "input_item_error_shape_class",
        "item_json_type_class",
        "item_type_class",
        "rejected_item_fields",
        "rejected_field_name_class",
        "index_syntactically_bounded",
        "index_in_range",
        "selected_item_object",
        "rejected_field_present",
        "reasoning_item_type_is_reasoning",
        "reasoning_id_state",
        "reasoning_content_state",
        "reasoning_summary_state",
        "reasoning_encrypted_content_state",
        "reasoning_unexpected_semantic_fields_present",
        "reasoning_exact_allowed_key_set_match",
        "reasoning_exactly_one_candidate_placeholder",
        "reasoning_placeholder_precedes_function_pair",
        "exact_empty_reasoning_placeholder",
    }


def test_reasoning_placeholder_positive_is_value_free_and_pair_bound() -> None:
    pair = [{"type": "function_call"}, {"type": "function_call_output"}]
    for identifier in ("absent", "null"):
        placeholder: dict[str, object] = {
            "type": "reasoning",
            "content": [],
            "summary": [],
            "encrypted_content": None,
        }
        if identifier == "null":
            placeholder["id"] = None
        body = json.dumps({"input": [placeholder, *pair]}).encode()
        projection = verifier._safe_input_item_error_projection("input[0]", body)
        assert projection["reasoning_item_type_is_reasoning"] is True
        assert projection["reasoning_id_state"] == identifier
        assert projection["reasoning_content_state"] == "empty_array"
        assert projection["reasoning_summary_state"] == "empty_array"
        assert projection["reasoning_encrypted_content_state"] == "null"
        assert projection["reasoning_unexpected_semantic_fields_present"] is False
        assert projection["reasoning_exact_allowed_key_set_match"] is True
        assert projection["reasoning_exactly_one_candidate_placeholder"] is True
        assert projection["reasoning_placeholder_precedes_function_pair"] is True
        assert projection["exact_empty_reasoning_placeholder"] is True
        assert "reasoning-id-canary" not in json.dumps(projection)


@pytest.mark.parametrize(
    ("field", "value", "state"),
    [
        ("content", ["nonempty-canary"], "nonempty_array"),
        ("content", {"unexpected": "private-state-canary"}, "malformed"),
        ("content", None, "malformed"),
        ("summary", ["nonempty-canary"], "nonempty_array"),
        ("summary", {"unexpected": "private-state-canary"}, "malformed"),
        ("summary", None, "malformed"),
        ("encrypted_content", "opaque-canary", "non_null"),
        ("encrypted_content", {"unexpected": "private-state-canary"}, "malformed"),
    ],
)
def test_reasoning_placeholder_states_fail_closed_without_values(
    field: str, value: object, state: str
) -> None:
    placeholder: dict[str, object] = {
        "type": "reasoning",
        "content": [],
        "summary": [],
        "encrypted_content": None,
    }
    placeholder[field] = value
    body = json.dumps(
        {"input": [placeholder, {"type": "function_call"}, {"type": "function_call_output"}]}
    ).encode()
    projection = verifier._safe_input_item_error_projection("input[0]", body)
    assert projection[f"reasoning_{field}_state"] == state
    assert projection["exact_empty_reasoning_placeholder"] is False
    rendered = json.dumps(projection, sort_keys=True)
    assert "private-state-canary" not in rendered
    assert "nonempty-canary" not in rendered
    assert "opaque-canary" not in rendered


def test_reasoning_placeholder_records_absent_and_invalid_state_classes() -> None:
    base = {"type": "reasoning", "content": [], "summary": []}
    cases = [
        (base, "absent", "empty_array", "empty_array", "absent", False),
        ({"type": "reasoning", "encrypted_content": None}, "absent", "absent", "absent", "null", False),
        ({**base, "encrypted_content": None, "id": "id-canary"}, "other", "empty_array", "empty_array", "null", True),
        ({"type": "message", "content": [], "summary": [], "encrypted_content": None}, "absent", "empty_array", "empty_array", "null", True),
        ({"type": "reasoning", "content": [], "summary": [], "encrypted_content": None, "extra": "private-canary"}, "absent", "empty_array", "empty_array", "null", False),
    ]
    for item, id_state, content_state, summary_state, encrypted_state, exact_keys in cases:
        body = json.dumps(
            {"input": [item, {"type": "function_call"}, {"type": "function_call_output"}]}
        ).encode()
        projection = verifier._safe_input_item_error_projection("input[0]", body)
        assert projection["reasoning_id_state"] == id_state
        assert projection["reasoning_content_state"] == content_state
        assert projection["reasoning_summary_state"] == summary_state
        assert projection["reasoning_encrypted_content_state"] == encrypted_state
        assert projection["reasoning_exact_allowed_key_set_match"] is exact_keys
        assert projection["exact_empty_reasoning_placeholder"] is False
        assert "id-canary" not in json.dumps(projection)
        assert "private-canary" not in json.dumps(projection)


@pytest.mark.parametrize(
    "items",
    [
        [
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None, "status": "in_progress"},
            {"type": "function_call"},
            {"type": "function_call_output"},
        ],
        [
            {"type": "message", "content": [], "summary": [], "encrypted_content": None},
            {"type": "function_call"},
            {"type": "function_call_output"},
        ],
        [
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None},
            {"type": "function_call_output"},
            {"type": "function_call"},
        ],
        [
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None},
            {"type": "function_call"},
            {"type": "function_call_output"},
            {"type": "function_call"},
            {"type": "function_call_output"},
        ],
        [
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None},
            {"type": "custom_tool_call"},
            {"type": "custom_tool_call_output"},
        ],
        [
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None},
            {"type": "reasoning", "content": [], "summary": [], "encrypted_content": None},
            {"type": "function_call"},
            {"type": "function_call_output"},
        ],
    ],
)
def test_reasoning_placeholder_requires_one_exact_candidate_and_function_pair(
    items: list[dict[str, object]],
) -> None:
    projection = verifier._safe_input_item_error_projection(
        "input[0]", json.dumps({"input": items}).encode()
    )
    assert projection["exact_empty_reasoning_placeholder"] is False


def test_reasoning_placeholder_rejects_missing_and_malformed_input_selection() -> None:
    for param, body in (
        ("input[0]", b'{"input":[null]}'),
        ("input[999]", b'{"input":[{"type":"reasoning"}]}'),
        ("input[x]", b'{"input":[{"type":"reasoning"}]}'),
        ("input[0].content.text", b'{"input":[{"type":"reasoning"}]}'),
    ):
        projection = verifier._safe_input_item_error_projection(param, body)
        assert projection["exact_empty_reasoning_placeholder"] is False


def test_input_item_error_summary_is_ordinal_and_rejects_duplicate_fields() -> None:
    safe = verifier._safe_input_item_error_projection(
        "input[1].type", b'{"input":[{"type":"message"},{"type":"reasoning"}]}'
    )
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="turn_failed",
        gateway_requests=2,
        gateway_status={
            "response_statuses": [200, 400],
            "input_item_error_projections": [
                verifier._empty_input_item_error_projection(),
                safe,
            ],
        },
        local_requests=1,
        local_status={"response_statuses": [200]},
        qwen_status={"inference_calls": 1, "inference_statuses": [200]},
        request_projections=[],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    assert len(summary["gateway_input_item_error_projections"]) == 2
    assert verifier._sanitize_preclassification_summary(summary) == summary
    duplicate = json.loads(json.dumps(summary))
    duplicate["gateway_input_item_error_projections"][1]["rejected_item_fields"].append(
        duplicate["gateway_input_item_error_projections"][1]["rejected_item_fields"][0]
    )
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(duplicate)
    unaligned = json.loads(json.dumps(summary))
    unaligned["gateway_input_item_error_projections"] = [
        verifier._empty_input_item_error_projection()
    ]
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(unaligned)
    invalid_state = json.loads(json.dumps(summary))
    invalid_state["gateway_input_item_error_projections"][1]["reasoning_id_state"] = "private"
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(invalid_state)


@pytest.mark.parametrize(
    ("raw_code", "safe_code"),
    [
        ("responses_codex_tool_roundtrip_invalid", "codex_tool_roundtrip_invalid"),
        ("responses_codex_replay_reference_not_found", "replay_reference_not_found"),
        ("responses_codex_replay_route_mismatch", "replay_route_mismatch"),
        ("responses_route_capability_not_supported", "route_capability_not_supported"),
        ("responses_route_capability_missing", "route_capability_not_supported"),
        ("responses_function_tool_capability_not_supported", "route_capability_not_supported"),
        ("responses_custom_tool_capability_not_supported", "route_capability_not_supported"),
        ("responses_codex_streaming_tool_events_not_allowed", "route_capability_not_supported"),
        ("unrecognized_gateway_error", "other"),
    ],
)
def test_gateway_error_code_allowlist_maps_only_bounded_classes(
    raw_code: str, safe_code: str
) -> None:
    assert verifier._safe_gateway_error_code_class(raw_code) == safe_code


@pytest.mark.parametrize(
    "safe_code",
    [
        "codex_tool_roundtrip_invalid",
        "replay_reference_not_found",
        "replay_route_mismatch",
        "route_capability_not_supported",
        "other",
    ],
)
def test_second_gateway_error_matrix_is_bounded_for_g2_l1_q1(
    safe_code: str,
) -> None:
    expected = (
        "composed_tool_roundtrip_second_turn_gateway_"
        f"{safe_code}_input_top_level_function_pair_without_additional_tools"
    )
    assert verifier._localize_composed_codex_failure(
        codex_failure_category="unclassified",
        gateway_requests=2,
        gateway_statuses=[200, 400],
        gateway_structures=[],
        local_requests=1,
        local_statuses=[200],
        request_projections=[
            {},
            {
                "top_level_tool_type_counts": {"function": 1},
                "input_item_type_sequence": [
                    "function_call",
                    "function_call_output",
                ],
                "stream_class": "true",
            },
        ],
        gateway_error_code_classes=["none", safe_code],
        gateway_error_param_classes=["none", "input"],
        qwen_status={"inference_statuses": [200]},
        fake_status={},
        accounting_statuses={},
    ) == expected


def test_summary_sanitizer_rejects_duplicate_fields_and_unaligned_error_ordinals() -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="turn_failed",
        gateway_requests=2,
        gateway_status={
            "response_statuses": [200, 400],
            "error_code_classes": ["none", "codex_tool_roundtrip_invalid"],
            "error_param_classes": ["none", "input"],
            "error_param_field_classes": ["none", "type"],
        },
        local_requests=1,
        local_status={"response_statuses": [200]},
        qwen_status={"inference_calls": 1, "inference_statuses": [200]},
        request_projections=[
            {},
            {
                "top_level_tool_type_counts": {"function": 1},
                "input_item_type_sequence": [
                    "function_call",
                    "function_call_output",
                ],
                "function_call_fields": [
                    {"name": "id", "type": "string"},
                    {"name": "type", "type": "string"},
                ],
                "function_call_output_fields": [
                    {"name": "call_id", "type": "string"},
                    {"name": "output", "type": "string"},
                    {"name": "type", "type": "string"},
                ],
                "stream_class": "true",
            },
        ],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    duplicate = json.loads(json.dumps(summary))
    duplicate["second_function_call_fields"].append(
        duplicate["second_function_call_fields"][0]
    )
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(duplicate)
    unaligned = json.loads(json.dumps(summary))
    unaligned["gateway_error_code_classes"] = ["none"]
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(unaligned)


def test_summary_keeps_local_vocabulary_separate_from_gateway_vocabulary() -> None:
    summary = verifier._safe_preclassification_summary(
        stage="tool_roundtrip_failure_decision",
        codex_failure_category="turn_failed",
        gateway_requests=1,
        gateway_status={"response_statuses": [422], "error_code_classes": ["request_policy_invalid"]},
        local_requests=1,
        local_status={
            "response_statuses": [422],
            "local_error_code_classes": ["responses_disabled_tool_choice"],
            "local_error_stage_classes": ["tool_policy"],
            "local_boundary_states": {
                "tool_policy": "rejected",
                "observation": "not_reached",
                "constitution": "not_reached",
                "upstream": "not_reached",
            },
        },
        qwen_status={"inference_calls": 0, "inference_statuses": []},
        request_projections=[{"tool_choice_class": "explicit_disabled_search"}],
        accounting_statuses={"query_ok": False},
        qualification_rejection=None,
        artifact_equal=False,
    )
    assert summary["local_error_code_classes"] == ["responses_disabled_tool_choice"]
    assert summary["local_error_stage_classes"] == ["tool_policy"]
    assert summary["first_request_tool_choice_class"] == "explicit_disabled_search"
    assert verifier._sanitize_preclassification_summary(summary) == summary
    tampered = json.loads(json.dumps(summary))
    tampered["local_error_code_classes"] = ["responses_codex_tool_roundtrip_invalid"]
    with pytest.raises(verifier.VerificationError, match="qualification_summary_invalid"):
        verifier._sanitize_preclassification_summary(tampered)


def test_composed_evidence_rejects_placeholder_counts() -> None:
    evidence = {name: True for name in (
        "session_a1_a2_equal", "session_b_different", "session_second_key_different",
        "cache_reuse_observed", "rehydration_observed", "exact_replay_rejected",
        "failure_rollback_observed", "provider_counts_observed", "postgres_rows_observed",
        "hosted_tools_stripped", "privacy_observed", "post_cleanup_model_ok",
    )}
    evidence.update(provider_calls=0, relay_calls=0)
    with pytest.raises(verifier.VerificationError, match="provider_call_count_missing"):
        verifier._assert_required_evidence(evidence)


def test_composed_evidence_requires_real_equal_provider_and_relay_counts() -> None:
    evidence = _complete_evidence()
    evidence.update(provider_calls=3, qwen_calls=2, relay_calls=2, local_forwarded_calls=2)
    with pytest.raises(verifier.VerificationError, match="provider_call_count_mismatch"):
        verifier._assert_required_evidence(evidence)
    evidence["qwen_calls"] = 3
    evidence["local_forwarded_calls"] = 1
    with pytest.raises(verifier.VerificationError, match="local_forward_count_mismatch"):
        verifier._assert_required_evidence(evidence)
    evidence["relay_calls"] = 3
    evidence["local_forwarded_calls"] = 3
    verifier._assert_required_evidence(evidence)


def _complete_evidence() -> dict[str, object]:
    return {
        name: True
        for name in (
            "session_a1_a2_equal",
            "session_b_different",
            "session_second_key_different",
            "cache_reuse_observed",
            "rehydration_observed",
            "exact_replay_rejected",
            "failure_rollback_observed",
            "provider_counts_observed",
            "postgres_rows_observed",
            "hosted_tools_stripped",
            "privacy_observed",
            "post_cleanup_model_ok",
        )
    } | {
        "provider_calls": 3,
        "qwen_calls": 3,
        "relay_calls": 3,
        "local_forwarded_calls": 3,
    }


@pytest.mark.parametrize(
    "missing",
    [
        "session_a1_a2_equal",
        "session_b_different",
        "session_second_key_different",
        "cache_reuse_observed",
        "rehydration_observed",
        "exact_replay_rejected",
        "failure_rollback_observed",
        "provider_counts_observed",
        "postgres_rows_observed",
        "hosted_tools_stripped",
        "privacy_observed",
        "post_cleanup_model_ok",
    ],
)
def test_composed_evidence_rejects_each_missing_or_false_fact(missing: str) -> None:
    evidence = _complete_evidence()
    evidence.pop(missing)
    with pytest.raises(verifier.VerificationError, match="required_composed_evidence_missing"):
        verifier._assert_required_evidence(evidence)
    evidence[missing] = False
    with pytest.raises(verifier.VerificationError, match="required_composed_evidence_missing"):
        verifier._assert_required_evidence(evidence)


def test_successful_relay_count_excludes_replay_and_tamper_statuses() -> None:
    assert verifier._successful_relay_count((200, 409, 403, 403, 500, 200)) == 2


def test_local_bound_privacy_allows_only_service_and_signed_headers() -> None:
    request = verifier.CapturedRequest(
        path="/v1/responses",
        body=b"safe-body",
        headers={
            "authorization": "Bearer service-token",
            "x-slaif-session": "opaque-session",
        },
    )
    verifier._assert_local_bound_privacy(
        (request,), raw_aliases={"opaque-session"}, service_token="service-token"
    )
    leaked = verifier.CapturedRequest(
        path="/v1/responses", body=b"opaque-session", headers={"authorization": "Bearer service-token"}
    )
    with pytest.raises(verifier.VerificationError, match="raw_client_alias_forwarded"):
        verifier._assert_local_bound_privacy(
            (leaked,), raw_aliases={"opaque-session"}, service_token="service-token"
        )


def test_local_bound_privacy_classifier_preserves_source_target_and_locations() -> None:
    requests = (
        verifier.CapturedRequest(
            path="/v1/responses",
            body=b'{"client_metadata":{"session_id":"alias-a"}}',
            headers={"authorization": "Bearer service-token", "x-slaif-session": "opaque"},
        ),
        verifier.CapturedRequest(
            path="/v1/responses",
            body=b'{"input":[{"internal_chat_message_metadata_passthrough":{"thread_id":"alias-b"}}]}',
            headers={"authorization": "Bearer service-token", "x-slaif-signature": "v1=opaque"},
        ),
    )
    findings = verifier._safe_local_bound_privacy_findings(
        requests,
        (
            {"session": {"alias-a"}},
            {"thread": {"alias-b"}},
        ),
        service_token="service-token",
    )
    assert findings == [
        {
            "source_turn": 0,
            "target_turn": 0,
            "location_class": "top_level_client_metadata",
            "alias_key_class": "session",
        },
        {
            "source_turn": 1,
            "target_turn": 1,
            "location_class": "input_internal_chat_message_metadata_passthrough",
            "alias_key_class": "thread",
        },
    ]
    cross_turn = verifier._safe_local_bound_privacy_findings(
        (
            requests[0],
            verifier.CapturedRequest(
                path="/v1/responses",
                body=b'{"prompt_cache_key":"prefix-alias-a"}',
                headers={"authorization": "Bearer service-token"},
            ),
        ),
        ({"session": {"alias-a"}},),
        service_token="service-token",
    )
    assert cross_turn == [
        {
            "source_turn": 0,
            "target_turn": 0,
            "location_class": "top_level_client_metadata",
            "alias_key_class": "session",
        },
        {
            "source_turn": 0,
            "target_turn": 1,
            "location_class": "other_json_body_path",
            "body_path_class": "prompt_cache_key",
            "alias_key_class": "session",
        },
    ]


def test_local_config_is_validated_before_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credential = tmp_path / "credential"
    credential.write_text("QWEN3090_API_KEY=private\n", encoding="utf-8")
    settings = types.SimpleNamespace(
        server=types.SimpleNamespace(listen_host="127.0.0.1", listen_port=18031),
        upstream=types.SimpleNamespace(
            model=verifier.CODEX_MODEL,
            api_key_env=verifier.QWEN_RELAY_TOKEN_ENV,
            base_url="http://127.0.0.1:39149/v1",
        ),
        compiler=types.SimpleNamespace(api_key_env=verifier.QWEN_RELAY_TOKEN_ENV),
        gateway_ingress=types.SimpleNamespace(mode="service_bearer_signed_identity_v1"),
        routes=[types.SimpleNamespace(responses_tool_policy="drop_disabled_codex_search")],
    )
    config_module = types.ModuleType("slaif_local_coding.config")
    config_module.load_settings = lambda _path: settings
    package_module = types.ModuleType("slaif_local_coding")
    monkeypatch.setitem(sys.modules, "slaif_local_coding", package_module)
    monkeypatch.setitem(sys.modules, "slaif_local_coding.config", config_module)
    config = verifier._validate_local_config(
        tmp_path, verifier.RuntimeReference("http://private.example/v1", credential)
    )
    assert config.is_file()
    config_text = config.read_text(encoding="utf-8")
    assert "private.example" not in config_text
    assert "http://127.0.0.1:39149/v1" in config_text
    assert verifier.QWEN_RELAY_TOKEN_ENV in config_text


def test_forwarding_relay_passes_sse_chunk_before_upstream_finishes() -> None:
    first_sent = threading.Event()
    release = threading.Event()

    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: first\\n\\n")
            self.wfile.flush()
            first_sent.set()
            release.wait(timeout=2)
            self.wfile.write(b"data: done\\n\\n")
            self.wfile.flush()

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), upstream.server_address[1])
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    chunks: queue.Queue[bytes] = queue.Queue()

    def read_response() -> None:
        with verifier.httpx.Client(timeout=5) as client:
            with client.stream(
                "POST",
                f"http://127.0.0.1:{relay.server_address[1]}/v1/responses",
                content=b"{}",
            ) as response:
                for chunk in response.iter_raw():
                    chunks.put(chunk)

    reader = threading.Thread(target=read_response, daemon=True)
    reader.start()
    assert first_sent.wait(timeout=2)
    first_chunk = chunks.get(timeout=2)
    assert b"data: first" in first_chunk
    assert reader.is_alive()
    release.set()
    reader.join(timeout=2)
    assert not reader.is_alive()
    upstream.shutdown()
    upstream.server_close()
    relay.shutdown()
    relay.server_close()
    upstream_thread.join(timeout=2)
    relay_thread.join(timeout=2)


def test_gateway_facing_relay_records_pinned_capture_sse_structure() -> None:
    fake, fake_thread, token = verifier._start_fake_qwen()
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), fake.server_address[1])
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    try:
        with verifier.httpx.stream(
            "POST",
            f"http://127.0.0.1:{relay.server_address[1]}/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": verifier.CODEX_MODEL, "stream": True},
            timeout=5,
        ) as response:
            assert response.status_code == 200
            chunks = response.iter_raw()
            first = next(chunks)
            assert b"response.created" in first
            assert b"response.completed" in first + b"".join(chunks)
        structures = relay.status()["sse_structures"]
        assert isinstance(structures, list) and len(structures) == 1
        assert structures[0] == verifier._FAKE_STANDARD_SSE_STRUCTURE
    finally:
        relay.shutdown()
        relay.server_close()
        fake.shutdown()
        fake.server_close()
        relay_thread.join(timeout=2)
        fake_thread.join(timeout=2)


def _record_sse_structure(
    events: list[tuple[str, dict[str, object]]], *, done: bool = False
) -> dict[str, object]:
    recorder = verifier._SSEStructuralRecorder()
    recorder.mark_first_event_before_upstream_completion()
    for event, payload in events:
        recorder.feed(
            (
                f"event: {event}\ndata: "
                f"{verifier.json.dumps(payload, separators=(',', ':'))}\n\n"
            ).encode()
        )
    if done:
        recorder.feed(b"data: [DONE]\n\n")
    recorder.mark_normal_close()
    return recorder.snapshot()


def test_sse_structure_accepts_exact_pinned_capture_pair() -> None:
    events = [
        (
            "response.created",
            {
                "type": "response.created",
                "response": {
                    "id": "resp_capture",
                    "object": "response",
                    "status": "in_progress",
                    "model": verifier.CODEX_MODEL,
                },
            },
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_capture",
                    "object": "response",
                    "status": "completed",
                    "model": verifier.CODEX_MODEL,
                    "output": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                },
            },
        ),
    ]
    verifier._assert_pinned_capture_sse_structure(_record_sse_structure(events))


def test_error_event_projection_keeps_only_finite_safe_facts() -> None:
    structure = _record_sse_structure([
        (
            "error",
            {
                "type": "error",
                "code": "provider_error",
                "message": "private provider detail",
                "param": None,
                "sequence_number": 4,
                "private_extra": "must not survive",
            },
        )
    ])
    assert structure["error_event"] is True
    assert structure["error_code_class"] == "provider_error"
    assert structure["error_type_class"] == "unknown"
    assert structure["error_field_names"] == [
        "code", "message", "param", "sequence_number", "type"
    ]
    rendered = verifier.json.dumps(structure)
    assert "private provider detail" not in rendered
    assert "must not survive" not in rendered

    hostile = _record_sse_structure([
        ("error", {"type": "error", "code": "unbounded-private-code" * 100})
    ])
    assert hostile["error_code_class"] == "unknown"
    assert "unbounded-private-code" not in verifier.json.dumps(hostile)


def _valid_composed_path() -> dict[str, object]:
    return {
        "gateway_to_local_request_count_class": "one",
        "gateway_to_local_response_count_class": "one",
        "local_response_status_class": "2xx",
        "local_response_content_type_class": "sse",
        "local_rejected": False,
        "local_handler_error": False,
        "local_upstream_truncated": False,
        "local_downstream_closed_early": False,
        "local_terminal_completion_valid": True,
        "local_to_qwen_inference_call_count_class": "one",
        "qwen_upstream_response_count_class": "one",
        "qwen_upstream_status_class": "2xx",
        "qwen_upstream_content_type_class": "sse",
        "qwen_terminal_completion_valid": True,
        "qwen_handler_error": False,
        "qwen_upstream_truncated": False,
        "qwen_path_rejection": False,
        "gateway_error_event": False,
        "gateway_error_field_names": [],
        "gateway_error_code_class": "unknown",
        "gateway_error_type_class": "unknown",
        "gateway_accounting_terminal": True,
    }


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("zero_gateway_request", "gateway_owned"),
        ("local_before_qwen", "local_owned"),
        ("qwen_failure", "local_qwen_owned"),
        ("qwen_valid_local_failure", "local_owned"),
        ("gateway_failure", "gateway_owned"),
        ("complete", "terminal_boundaries_completed"),
        ("many_calls", "ambiguous_stream_evidence"),
    ],
)
def test_composed_path_classifier_proves_each_owner_branch(
    mutation: str, expected: str
) -> None:
    local = verifier._stream_observation(
        boundary="local_output", status=200, content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE, client_completed=True,
    )
    gateway = verifier._stream_observation(
        boundary="gateway_output", status=200, content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE, client_completed=True,
    )
    path = _valid_composed_path()
    if mutation == "zero_gateway_request":
        path["gateway_to_local_request_count_class"] = "zero"
    elif mutation == "local_before_qwen":
        path.update(
            local_to_qwen_inference_call_count_class="zero",
            local_response_status_class="unknown",
            local_terminal_completion_valid=False,
        )
    elif mutation == "qwen_failure":
        path.update(
            qwen_upstream_status_class="5xx",
            qwen_terminal_completion_valid=False,
            local_response_status_class="unknown",
            local_terminal_completion_valid=False,
        )
    elif mutation == "qwen_valid_local_failure":
        path.update(local_response_status_class="unknown", local_terminal_completion_valid=False)
    elif mutation == "gateway_failure":
        path["gateway_error_event"] = True
    elif mutation == "many_calls":
        path["local_to_qwen_inference_call_count_class"] = "many"
    assert verifier._classify_composed_path(path, local, gateway) == expected


def test_composed_path_projection_totalizes_hostile_values() -> None:
    safe = verifier._safe_composed_path(
        {"gateway_to_local_request_count_class": [], "gateway_error_code_class": ["secret"]},
        decision="ambiguous_stream_evidence",
    )
    assert safe["gateway_to_local_request_count_class"] == "unknown"
    assert safe["gateway_error_code_class"] == "unknown"
    assert all(isinstance(value, (bool, str, list)) for value in safe.values())


def test_sse_structure_rejects_unknown_event_type() -> None:
    event = {
        "type": "response.unreviewed",
        "response": {"id": "resp_capture", "status": "in_progress"},
    }
    structure = _record_sse_structure([("response.unreviewed", event)])
    assert structure["unknown_events"] is True
    assert structure["event_trace"] == [{"event": "other", "count": 1}]


@pytest.mark.parametrize(
    "variant",
    ["reordered", "duplicated", "done", "wrong_status"],
)
def test_sse_structure_rejects_order_duplicates_done_and_wrong_status(variant: str) -> None:
    created = {
        "type": "response.created",
        "response": {
            "id": "resp_capture",
            "object": "response",
            "status": "in_progress",
            "model": verifier.CODEX_MODEL,
        },
    }
    completed = {
        "type": "response.completed",
        "response": {
            "id": "resp_capture",
            "object": "response",
            "status": "completed",
            "model": verifier.CODEX_MODEL,
            "output": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        },
    }
    events = [("response.created", created), ("response.completed", completed)]
    if variant == "reordered":
        events.reverse()
    elif variant == "duplicated":
        events.insert(1, events[0])
    elif variant == "wrong_status":
        created["response"]["status"] = "completed"
    structure = _record_sse_structure(events, done=variant == "done")
    with pytest.raises(verifier.VerificationError, match="gateway_sse_schema_mismatch"):
        verifier._assert_pinned_capture_sse_structure(structure)


@pytest.mark.parametrize(
    "field",
    [
        "response_id_relation",
        "completed_status_completed",
        "model_matches",
        "completed_usage_valid",
        "first_event_before_upstream_completion",
        "normal_close",
    ],
)
def test_stream_completion_gate_rejects_missing_or_false_safe_facts(field: str) -> None:
    structure = verifier.json.loads(
        verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE)
    )
    structure[field] = False
    assert verifier._stream_has_valid_completion(structure) is False


def test_stream_completion_gate_rejects_missing_terminal_event_and_invalid_bounds() -> None:
    structure = verifier.json.loads(
        verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE)
    )
    structure["event_trace"] = [{"event": "response.created", "count": 1}]
    structure["event_counts"] = {"response.created": 1}
    structure["response_completed"] = False
    assert verifier._stream_has_valid_completion(structure) is False
    structure["event_trace"] = [
        {"event": "response.created", "count": 1},
        {"event": "response.completed", "count": 1},
    ]
    structure["event_counts"] = {"response.created": 1, "response.completed": 1}
    structure["response_completed"] = True
    structure["terminal_output_shape"] = "other"
    assert verifier._stream_has_valid_completion(structure) is False
    recorder = verifier._SSEStructuralRecorder()
    recorder.feed(b"data: {" + b"x" * verifier._SSE_CAPTURE_LIMIT + b"}\n\n")
    assert recorder.snapshot()["invalid"] is True


def test_stream_differential_classification_fails_closed_for_non_sse() -> None:
    valid = {
        "structure": verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        "http_status_class": "2xx",
        "content_type_class": "sse",
        "failure_code": None,
        "valid_completion": True,
        "client_completed": True,
    }
    local = dict(valid)
    gateway = dict(valid)
    direct = dict(valid)
    gateway["content_type_class"] = "json"
    assert verifier._classify_stream_differential(direct, local, gateway) == (
        "ambiguous_stream_evidence"
    )


def test_stream_ownership_does_not_misclassify_invalid_completed_shape() -> None:
    structure = verifier.json.loads(
        verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE)
    )
    structure["completed_usage_valid"] = False
    direct = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=structure,
        client_completed=False,
    )
    valid = {
        "boundary": "local_output",
        "http_status_class": "2xx",
        "content_type_class": "sse",
        "structure": verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        "client_completed": True,
        "failure_code": None,
        "valid_completion": True,
        "response_completed": True,
    }
    assert direct["response_completed"] is True
    assert verifier._classify_stream_differential(direct, valid, valid) == (
        "ambiguous_stream_evidence"
    )


@pytest.mark.parametrize(
    ("target", "client_completed", "expected"),
    [
        ("direct_qwen", True, "qwen_owned"),
        ("local_output", True, "local_owned"),
        ("gateway_output", True, "gateway_owned"),
        ("gateway_output", False, "official_client_observation"),
        (None, True, "all_boundaries_completed"),
    ],
)
def test_stream_differential_decision_table_covers_each_nonambiguous_branch(
    target: str | None, client_completed: bool, expected: str
) -> None:
    valid = {
        "boundary": "direct_qwen",
        "http_status_class": "2xx",
        "content_type_class": "sse",
        "structure": verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        "client_completed": True,
        "failure_code": None,
        "response_completed": True,
        "valid_completion": True,
    }
    direct = dict(valid, boundary="direct_qwen")
    local = dict(valid, boundary="local_output")
    gateway = dict(valid, boundary="gateway_output", client_completed=client_completed)
    if target is not None and not (target == "gateway_output" and not client_completed):
        target_observation = {
            "direct_qwen": direct,
            "local_output": local,
            "gateway_output": gateway,
        }[target]
        target_structure = verifier.json.loads(
            verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE)
        )
        target_structure["event_trace"] = [{"event": "response.created", "count": 1}]
        target_structure["event_counts"] = {"response.created": 1}
        target_structure["response_completed"] = False
        target_observation["structure"] = target_structure
        target_observation["response_completed"] = False
        target_observation["valid_completion"] = False
    assert verifier._classify_stream_differential(direct, local, gateway) == expected


def test_qwen_relay_passes_sse_chunk_before_upstream_finishes() -> None:
    first_sent = threading.Event()
    release = threading.Event()

    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: first\\n\\n")
            self.wfile.flush()
            first_sent.set()
            release.wait(timeout=2)
            self.wfile.write(b"data: done\\n\\n")
            self.wfile.flush()

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    relay = verifier._QwenRelayServer(
        ("127.0.0.1", 0),
        endpoint=f"http://127.0.0.1:{upstream.server_address[1]}/v1",
        relay_token="local-relay-token",
        qwen_token="qwen-token",
    )
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    chunks: queue.Queue[bytes] = queue.Queue()

    def read_response() -> None:
        with verifier.httpx.Client(timeout=5) as client:
            with client.stream(
                "POST",
                f"http://127.0.0.1:{relay.server_address[1]}/v1/responses",
                headers={"Authorization": "Bearer local-relay-token"},
                content=b'{"model":"qwen3.8-27b"}',
            ) as response:
                for chunk in response.iter_raw():
                    chunks.put(chunk)

    reader = threading.Thread(target=read_response, daemon=True)
    reader.start()
    assert first_sent.wait(timeout=2)
    assert b"data: first" in chunks.get(timeout=2)
    assert reader.is_alive()
    release.set()
    reader.join(timeout=2)
    assert not reader.is_alive()
    upstream.shutdown()
    upstream.server_close()
    relay.shutdown()
    relay.server_close()
    upstream_thread.join(timeout=2)
    relay_thread.join(timeout=2)


def test_qwen_relay_maps_authenticated_readiness_health_without_counting_inference() -> None:
    class Protected(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path != "/health" or self.headers.get("authorization") != "Bearer qwen-token":
                self.send_response(401)
                self.end_headers()
                return
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    protected = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Protected)
    protected_thread = threading.Thread(target=protected.serve_forever, daemon=True)
    protected_thread.start()
    relay = verifier._QwenRelayServer(
        ("127.0.0.1", 0),
        endpoint=f"http://127.0.0.1:{protected.server_address[1]}/v1",
        relay_token="local-relay-token",
        qwen_token="qwen-token",
    )
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    try:
        response = verifier.httpx.get(
            f"http://127.0.0.1:{relay.server_address[1]}/health",
            headers={"Authorization": "Bearer local-relay-token"},
            timeout=5,
        )
        assert response.status_code == 200
        assert relay.status()["health_calls"] == 1
        assert relay.status()["calls"] == 0
        unauthorized = verifier.httpx.get(
            f"http://127.0.0.1:{relay.server_address[1]}/health",
            headers={"Authorization": "Bearer wrong"},
            timeout=5,
        )
        assert unauthorized.status_code == 401
        assert relay.status()["calls"] == 0
    finally:
        relay.shutdown()
        relay.server_close()
        protected.shutdown()
        protected.server_close()
        relay_thread.join(timeout=2)
        protected_thread.join(timeout=2)


def test_qwen_relay_path_mapping_uses_protected_origin_and_v1_base() -> None:
    assert verifier._qwen_target("https://private.example/v1", "/health") == "https://private.example/health"
    assert verifier._qwen_target("https://private.example/v1", "/v1/models") == "https://private.example/v1/models"
    assert verifier._qwen_target("https://private.example/v1", "/v1/responses") == "https://private.example/v1/responses"
    assert verifier._qwen_target("https://private.example/v1", "/v1/chat/completions") == "https://private.example/v1/chat/completions"
    assert verifier._qwen_target("https://private.example/v1", "https://gateway.example/v1/responses") == "https://private.example/v1/responses"
    assert verifier._qwen_target("https://private.example/v1", "/v1/responses?bounded=1") == "https://private.example/v1/responses?bounded=1"
    assert verifier._safe_path_class("/v1/responses?bounded=1") == "v1_responses"
    assert verifier._safe_path_class("/v1/v1/responses") == "double_v1_responses"
    assert verifier._safe_path_class("/responses") == "bare_responses"
    assert verifier._safe_path_class("/v1/other") == "other"
    with pytest.raises(verifier.VerificationError, match="qwen_relay_path_invalid"):
        verifier._qwen_target("https://private.example/v1", "/responses")
    with pytest.raises(verifier.VerificationError, match="qwen_relay_path_invalid"):
        verifier._qwen_target("https://private.example/v1", "/v1/v1/responses")
    with pytest.raises(verifier.VerificationError, match="qwen_relay_path_invalid"):
        verifier._qwen_target("https://private.example/v1", "/v1/responses?" + "x" * 257)


def test_ordinary_response_localizer_uses_bounded_qwen_status_for_nonlocal_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    relay.remember_response(404, "/v1/responses")
    monkeypatch.setattr(
        verifier,
        "_qwen_relay_status",
        lambda _port: {"path_rejections": 0, "upstream_statuses": [404]},
    )
    error = verifier._localize_ordinary_response_failure(relay, 39149)
    assert str(error) == "ordinary_response_fake_qwen_404"


@pytest.mark.parametrize(
    ("exception_type", "expected"),
    [
        (
            "APIResponseValidationError",
            "ordinary_response_gateway_response_schema",
        ),
        ("BadRequestError", "ordinary_response_gateway_response_bad_request"),
    ],
)
def test_ordinary_response_localizer_maps_allowlisted_downstream_200_errors(
    monkeypatch: pytest.MonkeyPatch, exception_type: str, expected: str
) -> None:
    import httpx
    from openai import APIResponseValidationError, BadRequestError

    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    relay.remember_response(200, "/v1/responses")
    monkeypatch.setattr(
        verifier,
        "_qwen_relay_status",
        lambda _port: {"path_rejections": 0, "upstream_statuses": []},
    )
    response = httpx.Response(
        200 if exception_type == "APIResponseValidationError" else 400,
        request=httpx.Request("POST", "http://127.0.0.1/v1/responses"),
    )
    if exception_type == "APIResponseValidationError":
        exception = APIResponseValidationError(response=response, body={})
    else:
        exception = BadRequestError("bad request", response=response, body={})
    error = verifier._localize_ordinary_response_failure(relay, 39149, exception)
    assert str(error) == expected


def test_ordinary_response_localizer_keeps_unknown_downstream_200_errors_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    relay.remember_response(200, "/v1/responses")
    monkeypatch.setattr(
        verifier,
        "_qwen_relay_status",
        lambda _port: {"path_rejections": 0, "upstream_statuses": []},
    )
    error = verifier._localize_ordinary_response_failure(
        relay, 39149, RuntimeError("private response detail")
    )
    assert str(error) == "ordinary_response_failed"


def test_constitution_failure_localizer_reports_only_bounded_stage_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    monkeypatch.setattr(
        verifier,
        "_qwen_relay_status",
        lambda _port: {
            "path_rejections": 0,
            "calls": 1,
            "compiler_calls": 1,
            "inference_calls": 1,
            "upstream_statuses": [200],
        },
    )
    assert str(verifier._localize_constitution_failure(relay, 39149)) == (
        "constitution_local_compiler_rejected"
    )


def test_constitution_failure_localizer_distinguishes_successful_local_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    relay.remember_response(200, "/v1/responses")
    verifier_status = {
        "path_rejections": 0,
        "calls": 1,
        "compiler_calls": 0,
        "inference_calls": 1,
        "upstream_statuses": [200],
    }
    monkeypatch.setattr(verifier, "_qwen_relay_status", lambda _port: verifier_status)
    assert str(verifier._localize_constitution_failure(relay, 39149)) == (
        "constitution_gateway_response_rejected"
    )


def test_unexpected_preflight_failure_is_localized_without_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise RuntimeError("private-derived detail")

    monkeypatch.setattr(verifier, "_verify_commit_topology", fail)
    with pytest.raises(verifier.VerificationError, match="unexpected_topology") as error:
        verifier.run()
    assert "private-derived" not in str(error.value)


def test_scrubbed_launcher_does_not_forward_source_script_exports() -> None:
    source = verifier._start_process.__code__.co_consts
    script = " ".join(value for value in source if isinstance(value, str))
    assert "/usr/bin/env -i" in script
    assert "QWEN3090_API_KEY" in script
    assert "OPENROUTER_API_KEY" not in script


def test_verifier_output_is_fixed_status_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verifier, "run", lambda **_kwargs: _complete_evidence())
    monkeypatch.setattr(sys, "argv", ["verify_local_coding_full_stack.py"])
    assert verifier.main() == 0
    output = capsys.readouterr().out
    assert output == "RESULT=OK status=real_composed_acceptance\n"
    assert "private" not in output


def _stream_result_for_summary(decision: str = "all_boundaries_completed") -> dict[str, object]:
    observations = {}
    for boundary in ("direct_qwen", "local_output", "gateway_output"):
        observations[boundary] = verifier._stream_observation(
            boundary=boundary,
            status=200,
            content_type_class="sse",
            structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
            client_completed=True,
        )
    return {
        **observations,
        "decision": decision,
        "ran_boundaries": ["direct_qwen", "local_output", "gateway_output"],
    }


def test_stream_differential_cli_emits_exact_bounded_summary_for_each_boundary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _stream_result_for_summary()
    monkeypatch.setattr(verifier, "run_stream_differential", lambda: result)
    monkeypatch.setattr(sys, "argv", ["verify_local_coding_full_stack.py", "--stream-differential"])
    assert verifier.main() == 0
    captured = capsys.readouterr()
    expected_boundary = (
        '{"boundary":"{boundary}","completed_output_empty":true,'
        '"completed_status_completed":true,"completed_usage_valid":true,'
        '"content_type_class":"sse","created_status_in_progress":true,'
        '"decision":"all_boundaries_completed","done_sentinel":false,'
        '"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown",'
        '"error_event":false,"error_field_names":[],"error_type_class":"unknown",'
        '"event_counts":{"response.completed":1,"response.created":1},'
        '"event_trace":[{"count":1,"event":"response.created"},'
        '{"count":1,"event":"response.completed"}],"event_trace_overflow":false,'
        '"event_vocabulary_reviewed":true,"evidence_source":"current_155r",'
        '"failure_code":"none","first_event_before_upstream_completion":true,'
        '"handler_error":false,"http_status_class":"2xx","invalid":false,'
        '"model_matches":true,"normal_close":true,"normalization_reason":"none",'
        '"normalization_status":"complete","official_client_completion":true,'
        '"ran":true,"ran_current_invocation":true,"response_completed":true,"response_id_relation":true,'
        '"terminal_completion_valid":true,"terminal_output_shape":"empty_array","unknown_events":false,'
        '"upstream_truncated":false,"valid_completion":true}'
    )
    expected = "\n".join(
        [
            "STREAM_BOUNDARY "
            + expected_boundary.replace(
                '"boundary":"{boundary}"', f'"boundary":"{boundary}"', 1
            )
            for boundary in verifier._STREAM_BOUNDARIES
        ]
        + ['STREAM_DECISION "all_boundaries_completed"']
    ) + "\n"
    assert captured.out == expected
    assert captured.err == ""
    assert len(captured.out) < 4096
    assert "resp_capture" not in captured.out
    assert "response_field_names" not in captured.out
    assert "all_boundaries_completed" in captured.out


@pytest.mark.parametrize(
    "decision",
    [
        "qwen_owned",
        "local_owned",
        "local_qwen_owned",
        "gateway_owned",
        "official_client_observation",
        "ambiguous_stream_evidence",
    ],
)
def test_stream_differential_cli_emits_all_allowlisted_decisions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    decision: str,
) -> None:
    monkeypatch.setattr(
        verifier, "run_stream_differential", lambda: _stream_result_for_summary(decision)
    )
    monkeypatch.setattr(sys, "argv", ["verify_local_coding_full_stack.py", "--stream-differential"])
    assert verifier.main() == 0
    assert capsys.readouterr().out.endswith(f'STREAM_DECISION "{decision}"\n')


def test_stream_differential_qwen_owned_emits_only_direct_boundary() -> None:
    direct = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        client_completed=True,
    )
    direct_structure = verifier.json.loads(verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE))
    direct_structure["event_sequence"] = ["response.created"]
    direct_structure["event_counts"] = {"response.created": 1}
    direct_structure["event_trace"] = [{"event": "response.created", "count": 1}]
    direct["structure"] = direct_structure
    direct["response_completed"] = False
    direct["valid_completion"] = False
    result = {
        "decision": "qwen_owned",
        "ran_boundaries": ["direct_qwen"],
        "direct_qwen": direct,
    }
    lines = verifier._stream_summary_lines(result)
    assert len(lines) == 4
    assert lines[0].startswith("STREAM_BOUNDARY ")
    assert '"ran":true' in lines[0]
    assert '"ran":false' in lines[1]
    assert '"normalization_reason":"not_run"' in lines[1]
    assert '"ran":false' in lines[2]
    assert lines[3] == 'STREAM_DECISION "qwen_owned"'


def test_stream_differential_cli_qwen_owned_is_exact_and_does_not_claim_unrun_boundaries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    direct = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=verifier.json.loads(verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE)),
        client_completed=True,
    )
    direct["structure"]["event_sequence"] = ["response.created"]
    direct["structure"]["event_counts"] = {"response.created": 1}
    direct["structure"]["event_trace"] = [{"event": "response.created", "count": 1}]
    direct["response_completed"] = False
    direct["valid_completion"] = False
    result = {
        "decision": "qwen_owned",
        "ran_boundaries": ["direct_qwen"],
        "direct_qwen": direct,
    }
    monkeypatch.setattr(verifier, "run_stream_differential", lambda: result)
    monkeypatch.setattr(sys, "argv", ["verify_local_coding_full_stack.py", "--stream-differential"])
    assert verifier.main() == 0
    captured = capsys.readouterr()
    expected = "\n".join(verifier._stream_summary_lines(result)) + "\n"
    assert captured.out == expected
    assert captured.err == ""
    assert captured.out.count("STREAM_BOUNDARY ") == 3
    assert '"ran":false' in captured.out
    assert '"normalization_reason":"not_run"' in captured.out


def test_stream_differential_stops_before_composed_on_qwen_owned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    direct = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        client_completed=True,
    )
    direct_structure = verifier.json.loads(verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE))
    direct_structure["event_sequence"] = ["response.created"]
    direct_structure["event_counts"] = {"response.created": 1}
    direct_structure["event_trace"] = [{"event": "response.created", "count": 1}]
    direct["structure"] = direct_structure
    direct["response_completed"] = False
    direct["valid_completion"] = False
    monkeypatch.setattr(verifier, "_run_direct_stream_diagnostic", lambda *_args: direct)
    monkeypatch.setattr(
        verifier,
        "_run_composed_stream_diagnostic",
        lambda *_args: pytest.fail("composed diagnostic must not run"),
    )
    monkeypatch.setattr(verifier, "_verify_commit_topology", lambda: None)
    monkeypatch.setattr(verifier, "_read_runtime_reference", lambda: object())
    monkeypatch.setattr(verifier, "_verify_fixtures", lambda: None)
    monkeypatch.setattr(verifier, "_validate_local_config", lambda *_args: tmp_path / "config")
    result = verifier.run_stream_differential()
    assert result["decision"] == "qwen_owned"
    assert result["ran_boundaries"] == ["direct_qwen"]


def test_composed_only_mode_never_calls_direct_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = verifier._read_pinned_direct_baseline()
    raw = verifier._stream_observation(
        boundary="local_output",
        status=200,
        content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        client_completed=True,
    )
    gateway = dict(raw, boundary="gateway_output")
    monkeypatch.setattr(verifier, "_verify_commit_topology", lambda: None)
    monkeypatch.setattr(
        verifier,
        "_read_runtime_reference",
        lambda: pytest.fail("fake composed mode must not read protected runtime"),
    )
    monkeypatch.setattr(verifier, "_verify_fixtures", lambda: None)
    monkeypatch.setattr(verifier, "_read_pinned_direct_baseline", lambda: baseline)
    monkeypatch.setattr(verifier, "_validate_local_config", lambda *_args: None)
    monkeypatch.setattr(
        verifier,
        "_run_direct_stream_diagnostic",
        lambda *_args: pytest.fail("composed-only mode must not call direct"),
    )
    monkeypatch.setattr(
        verifier,
        "_run_composed_stream_diagnostic",
        lambda *_args, **_kwargs: {
            "local_output": raw,
            "gateway_output": gateway,
            "accounting_verified": True,
            "local_status": {
                "forwarded_count": 1,
                "rejected_count": 0,
                "response_statuses": [200],
                "response_content_type_classes": ["sse"],
            },
            "gateway_status": {
                "sse_structures": [verifier._PINNED_CAPTURE_SSE_STRUCTURE],
            },
            "qwen_status": {
                "inference_calls": 1,
                "upstream_statuses": [200],
                "sse_content_type_classes": ["sse"],
                "sse_structures": [verifier._PINNED_CAPTURE_SSE_STRUCTURE],
                "path_rejections": 0,
            },
        },
    )
    result = verifier.run_composed_only(fake_qwen=True)
    assert result["decision"] == "terminal_boundaries_completed"
    assert result["ran_boundaries"] == ["direct_qwen", "local_output", "gateway_output"]
    assert result["direct_qwen"]["evidence_source"] == "pinned_155l"
    assert result["direct_qwen"]["ran_current_invocation"] is False
    for boundary in ("local_output", "gateway_output"):
        assert result[boundary]["evidence_source"] == "current_155r"
        assert result[boundary]["ran_current_invocation"] is True


def test_relay_handle_error_is_safe_and_fail_closed() -> None:
    forwarding = verifier._ForwardingRelay(("127.0.0.1", 0), 1)
    forwarding.handle_error(None, None)
    assert forwarding.status()["handler_error"] is True
    qwen = verifier._QwenRelayServer(
        ("127.0.0.1", 0), endpoint="http://127.0.0.1/v1", relay_token="r", qwen_token="q"
    )
    qwen.handle_error(None, None)
    assert qwen.status()["handler_error"] is True


@pytest.mark.parametrize(
    "missing",
    [
        "direct_qwen",
        "local_output",
        "gateway_output",
        "decision",
    ],
)
def test_stream_summary_totalizes_missing_boundary_or_decision(missing: str) -> None:
    result = _stream_result_for_summary()
    result.pop(missing)
    lines = verifier._stream_summary_lines(result)
    assert len(lines) == 4
    expected_decision = (
        "ambiguous_stream_evidence" if missing == "decision" else "all_boundaries_completed"
    )
    assert lines[-1] == f'STREAM_DECISION "{expected_decision}"'


def test_stream_summary_emits_fixed_invalid_schema_for_missing_structure() -> None:
    result = _stream_result_for_summary("ambiguous_stream_evidence")
    result["direct_qwen"] = dict(
        result["direct_qwen"], structure=None, response_completed=False, valid_completion=False
    )
    lines = verifier._stream_summary_lines(result)
    assert '"boundary":"direct_qwen"' in lines[0]
    assert '"event_trace":[]' in lines[0]
    assert '"failure_code":"unknown_failure"' in lines[0]
    assert '"invalid":true' in lines[0]


def test_stream_summary_totalizes_inconsistent_event_counts() -> None:
    result = _stream_result_for_summary()
    structure = dict(result["direct_qwen"]["structure"])  # type: ignore[index]
    structure["event_counts"] = {"response.created": 2}
    result["direct_qwen"] = dict(result["direct_qwen"], structure=structure)  # type: ignore[arg-type]
    lines = verifier._stream_summary_lines(result)
    assert '"duplicates":true' in lines[0]
    assert '"terminal_completion_valid":false' in lines[0]


@pytest.mark.parametrize("response_completed", [True, False])
def test_stream_summary_rejects_response_completed_sequence_mismatch(
    response_completed: bool,
) -> None:
    result = _stream_result_for_summary()
    observation = dict(result["direct_qwen"])
    structure = verifier.json.loads(verifier.json.dumps(observation["structure"]))
    if response_completed:
        structure["event_sequence"] = ["response.created"]
        structure["event_counts"] = {"response.created": 1}
        structure["event_trace"] = [{"event": "response.created", "count": 1}]
    else:
        structure["event_trace"] = [
            {"event": "response.created", "count": 1},
            {"event": "response.completed", "count": 1},
        ]
    observation["structure"] = structure
    observation["response_completed"] = response_completed
    result["direct_qwen"] = observation
    lines = verifier._stream_summary_lines(result)
    assert '"normalization_status":"invalid"' in lines[0]
    assert '"normalization_reason":"inconsistent_completion"' in lines[0]


def test_forwarding_relay_drains_upstream_after_downstream_reset() -> None:
    first_sent = threading.Event()
    release = threading.Event()

    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))
            created = (
                b'event: response.created\n'
                b'data: {"type":"response.created","response":{"id":"resp_capture",'
                b'"object":"response","status":"in_progress","model":"qwen3.8-27b"}}\n\n'
            )
            completed = (
                b'event: response.completed\n'
                b'data: {"type":"response.completed","response":{"id":"resp_capture",'
                b'"object":"response","status":"completed","model":"qwen3.8-27b",'
                b'"output":[],"usage":{"input_tokens":0,"output_tokens":0,"total_tokens":0}}}\n\n'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(created)
            self.wfile.flush()
            first_sent.set()
            release.wait(timeout=2)
            self.wfile.write(completed)
            self.wfile.flush()

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), upstream.server_address[1])
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    client = socket.create_connection(("127.0.0.1", relay.server_address[1]), timeout=2)
    try:
        client.sendall(
            b"POST /v1/responses HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Length: 2\r\nConnection: close\r\n\r\n{}"
        )
        received = b""
        while b"response.created" not in received:
            chunk = client.recv(4096)
            assert chunk
            received += chunk
        assert b"response.created" in received
        assert first_sent.wait(timeout=2)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        client.close()
        release.set()
        deadline = verifier.time.monotonic() + 3
        structure = None
        while verifier.time.monotonic() < deadline:
            structures = relay.status()["sse_structures"]
            if structures:
                structure = structures[-1]
                break
            verifier.time.sleep(0.02)
        assert structure is not None
        assert structure["event_trace"] == [
            {"event": "response.created", "count": 1},
            {"event": "response.completed", "count": 1},
        ]
        assert structure["normal_close"] is True
        assert structure["response_id_relation"] is True
        assert relay.status()["upstream_truncated"] is False
    finally:
        try:
            client.close()
        except OSError:
            pass
        release.set()
        relay.shutdown()
        relay.server_close()
        upstream.shutdown()
        upstream.server_close()
        relay_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_forwarding_relay_records_upstream_truncation_without_normal_close() -> None:
    class Truncated(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", "256")
            self.end_headers()
            self.wfile.write(b"event: response.created\ndata: {}\n\n")
            self.wfile.flush()
            self.connection.close()

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Truncated)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    relay = verifier._ForwardingRelay(("127.0.0.1", 0), upstream.server_address[1])
    relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
    relay_thread.start()
    try:
        response = verifier.httpx.post(
            f"http://127.0.0.1:{relay.server_address[1]}/v1/responses",
            content=b"{}",
            timeout=5,
        )
        assert response.status_code == 200
        deadline = verifier.time.monotonic() + 2
        while verifier.time.monotonic() < deadline and not relay.status()["upstream_truncated"]:
            verifier.time.sleep(0.02)
        assert relay.status()["upstream_truncated"] is True
        assert relay.status()["sse_structures"][-1]["normal_close"] is False
    finally:
        relay.shutdown()
        relay.server_close()
        upstream.shutdown()
        upstream.server_close()
        relay_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_sse_recorder_compresses_repeated_deltas_beyond_64_events() -> None:
    recorder = verifier._SSEStructuralRecorder()
    for _ in range(100):
        recorder.feed(
            b'event: response.output_text.delta\n'
            b'data: {"type":"response.output_text.delta"}\n\n'
        )
    recorder.mark_normal_close()
    structure = recorder.snapshot()
    assert structure["event_trace"] == [{"event": "response.output_text.delta", "count": 100}]
    assert structure["event_counts"] == {"response.output_text.delta": 100}
    summary = verifier._safe_stream_summary(
        verifier._stream_observation(
            boundary="direct_qwen",
            status=200,
            content_type_class="sse",
            structure=structure,
            client_completed=True,
        ),
        boundary="direct_qwen",
        decision="ambiguous_stream_evidence",
    )
    assert summary["normalization_status"] == "complete"
    assert summary["event_trace"] == [{"event": "response.output_text.delta", "count": 100}]


def test_repeated_deltas_do_not_invalidate_a_complete_stream() -> None:
    created = {
        "type": "response.created",
        "response": {
            "id": "resp_capture",
            "object": "response",
            "status": "in_progress",
            "model": verifier.CODEX_MODEL,
        },
    }
    completed = {
        "type": "response.completed",
        "response": {
            "id": "resp_capture",
            "object": "response",
            "status": "completed",
            "model": verifier.CODEX_MODEL,
            "output": [{"type": "message"}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        },
    }
    events = [("response.created", created)]
    events.extend(
        ("response.output_text.delta", {"type": "response.output_text.delta"})
        for _ in range(100)
    )
    events.append(("response.completed", completed))
    structure = _record_sse_structure(events)
    assert structure["duplicates"] is False
    assert structure["event_counts"]["response.output_text.delta"] == 100
    assert verifier._stream_has_valid_completion(structure) is True


def test_trace_overflow_preserves_producer_completion_fact() -> None:
    structure = verifier.json.loads(verifier.json.dumps(verifier._PINNED_CAPTURE_SSE_STRUCTURE))
    structure["event_trace"] = [{"event": "response.created", "count": 1}]
    structure["event_sequence"] = ["response.created"]
    structure["event_counts"] = {"response.created": 1, "response.completed": 1}
    structure["event_trace_overflow"] = True
    observation = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=structure,
        client_completed=True,
    )
    observation["response_completed"] = True
    summary = verifier._safe_stream_summary(
        observation, boundary="direct_qwen", decision="ambiguous_stream_evidence"
    )
    assert summary["response_completed"] is True
    assert summary["normalization_reason"] == "trace_overflow"
    assert summary["valid_completion"] is False


def test_sse_recorder_marks_event_run_overflow_without_opaque_failure() -> None:
    recorder = verifier._SSEStructuralRecorder()
    for index in range(verifier._SSE_EVENT_RUN_LIMIT + 1):
        event = "response.created" if index % 2 else "response.in_progress"
        recorder.feed(
            f'event: {event}\ndata: {{"type":"{event}"}}\n\n'.encode("ascii")
        )
    recorder.mark_normal_close()
    structure = recorder.snapshot()
    summary = verifier._safe_stream_summary(
        verifier._stream_observation(
            boundary="direct_qwen",
            status=200,
            content_type_class="sse",
            structure=structure,
            client_completed=True,
        ),
        boundary="direct_qwen",
        decision="ambiguous_stream_evidence",
    )
    assert structure["event_trace_overflow"] is True
    assert summary["normalization_status"] == "degraded"
    assert summary["normalization_reason"] == "trace_overflow"
    assert summary["valid_completion"] is False


@pytest.mark.parametrize(
    ("status", "content_type", "structure"),
    [
        (100, "unknown", None),
        (302, "other", None),
        (404, "json", None),
        (500, "other", None),
        (None, None, None),
        (200, "sse", []),
        (200, "sse", {"event_sequence": ["response.created"]}),
    ],
)
def test_safe_stream_summary_totalizes_all_bounded_producer_shapes(
    status: int | None, content_type: str | None, structure: object
) -> None:
    observation = verifier._stream_observation(
        boundary="direct_qwen",
        status=status,
        content_type_class=content_type,
        structure=structure,
        client_completed=False,
        failure_code=None,
    )
    summary = verifier._safe_stream_summary(
        observation, boundary="direct_qwen", decision="ambiguous_stream_evidence"
    )
    assert summary["boundary"] == "direct_qwen"
    assert summary["ran"] is True
    assert summary["decision"] == "ambiguous_stream_evidence"
    assert summary["normalization_status"] in {"complete", "degraded", "invalid"}
    assert summary["normalization_reason"] in verifier._STREAM_NORMALIZATION_REASONS
    assert len(summary["event_trace"]) <= verifier._SSE_EVENT_RUN_LIMIT


def test_safe_stream_summary_records_handler_and_truncation_without_private_text() -> None:
    observation = verifier._stream_observation(
        boundary="gateway_output",
        status=200,
        content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        client_completed=False,
        failure_code="handler_error",
    )
    observation.update(handler_error=True, upstream_truncated=True)
    summary = verifier._safe_stream_summary(
        observation, boundary="gateway_output", decision="ambiguous_stream_evidence"
    )
    assert summary["handler_error"] is True
    assert summary["upstream_truncated"] is True
    assert summary["normalization_reason"] == "handler_error"
    assert "private" not in verifier.json.dumps(summary)


def test_normalized_summary_rebuild_discards_unexpected_extra_keys() -> None:
    observation = verifier._stream_observation(
        boundary="direct_qwen",
        status=200,
        content_type_class="sse",
        structure=verifier._PINNED_CAPTURE_SSE_STRUCTURE,
        client_completed=True,
    )
    normalized = verifier._safe_stream_summary(
        observation, boundary="direct_qwen", decision="ambiguous_stream_evidence"
    )
    normalized["raw_private_extra"] = "opaque"
    rebuilt = verifier._safe_stream_summary(
        normalized, boundary="direct_qwen", decision="ambiguous_stream_evidence"
    )
    assert "raw_private_extra" not in rebuilt
    assert "opaque" not in verifier.json.dumps(rebuilt)
