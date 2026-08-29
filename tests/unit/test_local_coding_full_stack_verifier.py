from __future__ import annotations

import hashlib
import http.server
import queue
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


def test_scrubbed_launcher_does_not_forward_source_script_exports() -> None:
    source = verifier._start_process.__code__.co_consts
    script = " ".join(value for value in source if isinstance(value, str))
    assert "/usr/bin/env -i" in script
    assert "QWEN3090_API_KEY" in script
    assert "OPENROUTER_API_KEY" not in script


def test_verifier_output_is_fixed_status_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verifier, "run", _complete_evidence)
    monkeypatch.setattr(sys, "argv", ["verify_local_coding_full_stack.py"])
    assert verifier.main() == 0
    output = capsys.readouterr().out
    assert output == "RESULT=OK status=real_composed_acceptance\n"
    assert "private" not in output
