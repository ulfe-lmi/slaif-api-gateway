from __future__ import annotations

import hashlib
import http.server
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
def test_155r_topology_enforces_exact_prior_report_parent_and_report_only_path(
    monkeypatch: pytest.MonkeyPatch, bad_field: str, expected: str
) -> None:
    current_head = "current-155r-head"
    local_head = verifier.LOCAL_REPORT_HEAD
    report_path = "oap/reports/155-r-retained-event-qualification-and-final-stream.md"

    def fake_git(*args: str, cwd: Path = verifier.REPO_ROOT) -> str:
        if args == ("rev-parse", "HEAD"):
            return local_head if cwd == verifier.LOCAL_ROOT else current_head
        if args == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", f"{verifier.GATEWAY_ACTIVATION_HEAD}^1"):
            return verifier.GATEWAY_REPORT_HEAD
        if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", verifier.GATEWAY_ACTIVATION_HEAD):
            return "oap/active\noap/orders/155-t-codex-envelope-activation-and-function-roundtrip.md"
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


def test_155t_topology_anchors_are_the_155s_report_and_activation() -> None:
    assert verifier.GATEWAY_REPORT_HEAD == "e7fedae6562cdfd7df6a605128e5bc93fc224119"
    assert verifier.GATEWAY_IMPLEMENTATION_HEAD == "ce725def4b931c2bf86770d8c6bd75c7e37247ef"
    assert verifier.GATEWAY_ACTIVATION_HEAD == "ad3ab547052d8a7600db9802e25da45bbf4b07da"
    assert verifier.GATEWAY_REPORT_PATH == "oap/reports/155-s-real-codex-tool-stream-lifecycle-and-acceptance.md"


def test_155s_topology_anchors_exact_local_report_parent_and_path() -> None:
    assert verifier.LOCAL_ROOT == Path("/home/ubuntu/codex-work/slaif-local-coding-005m")
    assert verifier.LOCAL_REPORT_HEAD == "4d3ab2fd97d249710f952dd3d2c28936138cc8fa"
    assert verifier.LOCAL_REPORT_PARENT == "258ae2ebad39651076937b9f027e60831b8d2786"
    assert verifier.LOCAL_SIGNED_CONTRACT_HEAD == "356be8345dd71d6fddf829278651d18e485731d4"
    assert verifier.LOCAL_REPORT_PATH == "oap/reports/005-m-gateway-155r-real-codex-matrix-and-cutover-closure.md"


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
    assert {"client_stream", "boundary_capture"}.issubset(verifier.COMPOSITION_STAGES)
    for stage in verifier.COMPOSITION_STAGES:
        tracker.set(stage)
        assert str(tracker.unexpected_composed()) == f"unexpected_composed_{stage}"
    unknown = verifier.StageTracker()
    assert str(unknown.unexpected_composed()) == "unexpected_composed_unknown_stage"


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
