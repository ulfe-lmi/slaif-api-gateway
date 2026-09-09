from __future__ import annotations

import asyncio
import base64
import hashlib
import http.client
import inspect
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import verify_codex_0149_assistant_output_history as verifier


def _history_body(text: str = "history-only-text") -> dict[str, object]:
    return {
        "model": verifier.CODEX_MODEL,
        "stream": True,
        "input": [
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
                    {"type": "input_text", "text": "crop"},
                ],
            },
        ],
    }


def _synthetic_codex_installation(tmp_path):
    install = tmp_path / "codex-install"
    root_package = install / "node_modules/@openai/codex"
    platform_package = install / "node_modules/@openai/codex-linux-x64"
    launcher = root_package / "bin/codex.js"
    native = platform_package / "vendor/x86_64-unknown-linux-musl/bin/codex"
    (install / "node_modules/.bin").mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    native.parent.mkdir(parents=True)
    launcher_bytes = b"synthetic-launcher"
    native_bytes = b"synthetic-native"
    launcher.write_bytes(launcher_bytes)
    native.write_bytes(native_bytes)
    os.chmod(launcher, 0o755)
    os.chmod(native, 0o755)
    (install / "node_modules/.bin/codex").symlink_to(verifier.CODEX_LAUNCHER_RELATIVE_PATH)
    (root_package / "package.json").write_text(
        json.dumps(
            {
                "name": verifier.CODEX_ROOT_PACKAGE_NAME,
                "version": verifier.CODEX_ROOT_PACKAGE_VERSION,
                "bin": {"codex": "bin/codex.js"},
                "optionalDependencies": {
                    verifier.CODEX_PLATFORM_PACKAGE_NAME: verifier.CODEX_PLATFORM_OPTIONAL_ALIAS
                },
            }
        ),
        encoding="utf-8",
    )
    (platform_package / "package.json").write_text(
        json.dumps(
            {
                "name": verifier.CODEX_PLATFORM_DISTRIBUTION_NAME,
                "version": verifier.CODEX_PLATFORM_PACKAGE_VERSION,
                "os": ["linux"],
                "cpu": ["x64"],
            }
        ),
        encoding="utf-8",
    )
    (install / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "synthetic-codex-install",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "node_modules/@openai/codex": {
                        "version": verifier.CODEX_ROOT_PACKAGE_VERSION,
                        "integrity": verifier.CODEX_ROOT_PACKAGE_INTEGRITY,
                    },
                    "node_modules/@openai/codex-linux-x64": {
                        "version": verifier.CODEX_PLATFORM_PACKAGE_VERSION,
                        "integrity": verifier.CODEX_PLATFORM_PACKAGE_INTEGRITY,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return (
        install,
        launcher,
        native,
        hashlib.sha256(launcher_bytes).hexdigest(),
        hashlib.sha256(native_bytes).hexdigest(),
    )


def _synthetic_version_runner(command, *, cwd, env, timeout):
    return subprocess.CompletedProcess(command, 0, verifier.CODEX_VERSION_OUTPUT, b"")


def _attest_synthetic_codex(install, **kwargs):
    kwargs.setdefault("native_size", len(b"synthetic-native"))
    return verifier._attest_codex_installation(install, **kwargs)


def test_diagnostic_stage_vocabulary_transitions_and_serialization() -> None:
    diagnostic = verifier.DiagnosticState()
    for stage in verifier.DIAGNOSTIC_STAGES:
        diagnostic.advance(stage)
    assert diagnostic.stage == "complete"
    serialized = diagnostic.serialize()
    assert serialized == diagnostic.serialize()
    assert '"stage":"complete"' in serialized
    with pytest.raises(verifier.VerificationError, match="diagnostic_stage_invalid"):
        diagnostic.advance("not-a-stage")


@pytest.mark.parametrize(
    ("exc", "category"),
    [
        (ModuleNotFoundError("private"), "import"),
        (OSError("private"), "filesystem"),
        (subprocess.TimeoutExpired("private", 1), "subprocess_timeout"),
        (ConnectionError("private"), "server_runtime"),
        (AssertionError("private"), "assertion"),
        (RuntimeError("private"), "runtime"),
    ],
)
def test_diagnostic_exception_categories_are_closed(exc, category) -> None:
    assert verifier._diagnostic_exception_category(exc) == category
    with pytest.raises(TypeError, match="diagnostic_exception_not_exception"):
        verifier._diagnostic_exception_category(KeyboardInterrupt())


@pytest.mark.parametrize(
    "stage",
    [
        "imports",
        "local_start",
        "first_client",
        "resume_client",
        "postconditions",
        "accounting_validate",
    ],
)
def test_diagnostic_unexpected_failure_is_stage_closed_and_private(stage) -> None:
    diagnostic = verifier.DiagnosticState()
    diagnostic.advance(stage)
    raw = "PRIVATE_DIAGNOSTIC_CANARY_161F"
    line = verifier._diagnostic_unexpected_line(diagnostic, RuntimeError(raw))
    assert f"unexpected_{stage}_runtime" in line
    assert raw not in line
    assert raw not in repr(diagnostic.snapshot())
    assert all(
        key in diagnostic.snapshot() for key in ("stage", "primary_stage", "cleanup_succeeded")
    )


def test_diagnostic_snapshot_bounds_gateway_and_local_progress() -> None:
    diagnostic = verifier.DiagnosticState()
    observation = SimpleNamespace(
        request_count=99,
        response_statuses=[200, 400, 500, 700, 201],
        error_codes=["PRIVATE_ERROR_CODE"],
        param_classes=["input[999].content[999].private"],
    )
    local = SimpleNamespace(
        state=SimpleNamespace(
            request_count=99,
            signed_request_count=3,
            function_count=1,
            message_count=2,
        )
    )
    diagnostic.refresh(observation=observation, local=local)
    snapshot = diagnostic.snapshot()
    assert snapshot["gateway_request_count"] == "other"
    assert snapshot["gateway_statuses"] == ["2xx", "4xx", "5xx", "other"]
    assert snapshot["gateway_error_code"] == "other"
    assert snapshot["gateway_param_class"] == "other"
    assert snapshot["local_request_count"] == "other"
    assert snapshot["local_signed_request_count"] == "other"
    assert snapshot["local_function_count"] == "one"
    assert snapshot["local_message_count"] == "two"
    assert "PRIVATE_ERROR_CODE" not in repr(snapshot)
    assert "private" not in repr(snapshot)


def test_diagnostic_primary_failure_survives_cleanup_failure() -> None:
    diagnostic = verifier.DiagnosticState()
    diagnostic.advance("resume_client")
    diagnostic.mark_unexpected(RuntimeError("PRIVATE_PRIMARY"))
    diagnostic.advance("cleanup")
    diagnostic.cleanup_attempted = True
    diagnostic.cleanup_succeeded = False
    snapshot = diagnostic.snapshot()
    assert snapshot["primary_stage"] == "resume_client"
    assert snapshot["primary_category"] == "runtime"
    assert snapshot["cleanup_succeeded"] is False
    assert "PRIVATE_PRIMARY" not in repr(snapshot)


def test_diagnostic_main_does_not_emit_arbitrary_exception_details() -> None:
    source = inspect.getsource(verifier.main)
    assert "type(exc).__name__" not in source
    assert "repr(exc)" not in source
    assert "traceback" not in source


def test_main_rejects_direct_and_legacy_diagnostic_mode_conflict(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_codex_0149_assistant_output_history.py",
            "--direct-bounded-fake",
            "--diagnostic-no-image-first-turn",
            "--local-checkout",
            "/private/local",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        verifier.main()
    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def _turn_failed_jsonl(message: object = "invalid image") -> bytes:
    return (json.dumps({"type": "turn.failed", "error": {"message": message}}) + "\n").encode()


def test_turn_failure_projection_positive_is_closed_and_source_pinned() -> None:
    projection = verifier._turn_failure_projection(
        b"",
        b'{"type":"thread.started"}\n' + _turn_failed_jsonl("invalid image"),
    )
    assert projection["turn_failed_shape_class"] == "exact"
    assert projection["message_domain"] == "invalid_image"
    assert projection["turn_failed_count_class"] == "one"
    assert projection["event_classes"] == ["thread.started", "turn.failed"]
    assert projection["combined_failure_class"] == "message_specific"
    assert verifier.CODEX_TURN_FAILURE_SOURCE_TAG == "rust-v0.149.0"
    assert verifier.CODEX_TURN_FAILURE_SOURCE_COMMIT == "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0"
    assert verifier.CODEX_TURN_FAILURE_EVENT_SOURCE_PATH == "codex-rs/exec/src/exec_events.rs"
    assert verifier.CODEX_TURN_FAILURE_PROCESSOR_SOURCE_PATH == (
        "codex-rs/exec/src/event_processor_with_jsonl_output.rs"
    )


@pytest.mark.parametrize(
    ("message", "domain"),
    [
        ("invalid image", "invalid_image"),
        ("image processing failed", "image_processing_or_capability"),
        ("unknown model catalog entry", "model_catalog_or_model"),
        ("configuration rejected", "configuration"),
        ("authentication failed", "authentication"),
        ("sandbox workspace denied", "workspace_or_sandbox"),
        ("request timeout", "request_or_transport"),
        ("stream response failed", "stream_or_response"),
        ("internal runtime failure", "internal_runtime"),
        ("turn failed", "generic_turn_failed"),
        ("unclassified condition", "other"),
    ],
)
def test_turn_failure_message_domains_are_closed(message, domain) -> None:
    projection = verifier._turn_failure_projection(b"", _turn_failed_jsonl(message))
    assert projection["message_domain"] == domain
    assert projection["message_size_class"] == "bounded"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json\n",
        b"[]\n",
        b'{"type":"turn.failed"}\n',
        b'{"type":"turn.failed","error":{}}\n',
        b'{"type":"turn.failed","error":{"message":3}}\n',
        b'{"type":"turn.failed","error":{"message":"x"},"extra":true}\n',
        _turn_failed_jsonl("one") + _turn_failed_jsonl("two"),
    ],
)
def test_turn_failure_projection_rejects_malformed_shapes(payload) -> None:
    projection = verifier._turn_failure_projection(b"", payload)
    assert projection["turn_failed_shape_class"] in {
        "missing",
        "duplicate",
        "top_level_fields_other",
        "error_object_other",
        "message_field_other",
        "message_type_other",
    }


def test_turn_failure_projection_bounds_records_lines_messages_and_event_classes() -> None:
    many_records = b"".join(b'{"type":"unknown"}\n' for _ in range(65))
    long_line = b"{" + b"x" * verifier.MAX_TURN_FAILURE_LINE_BYTES + b"}\n"
    long_token = "PRIVATE_LONG_TURN_FAILURE_CANARY_161I"
    long_message = _turn_failed_jsonl(
        long_token * (verifier.MAX_TURN_FAILURE_MESSAGE_BYTES // len(long_token) + 1)
    )
    projection = verifier._turn_failure_projection(
        b"x" * (verifier.MAX_TURN_FAILURE_STDERR_BYTES + 1),
        many_records + long_line + long_message,
    )
    assert projection["stderr_size_class"] == "oversized"
    assert projection["record_count_class"] == "truncated"
    assert projection["records_truncated"] is True
    assert len(projection["event_classes"]) <= verifier.MAX_TURN_FAILURE_EVENT_CLASSES
    assert long_token not in repr(projection)


def test_turn_failure_projection_combines_stderr_and_message_without_raw_text() -> None:
    agreeing = verifier._turn_failure_projection(
        b"error loading config", _turn_failed_jsonl("configuration rejected")
    )
    conflicting = verifier._turn_failure_projection(
        b"error loading config", _turn_failed_jsonl("request timeout")
    )
    generic = verifier._turn_failure_projection(b"", _turn_failed_jsonl("turn failed"))
    assert agreeing["combined_failure_class"] == "agreeing"
    assert conflicting["combined_failure_class"] == "conflicting"
    assert generic["combined_failure_class"] == "generic"
    raw = "PRIVATE_TURN_FAILED_MESSAGE_CANARY_161I"
    private = verifier._turn_failure_projection(b"", _turn_failed_jsonl(raw))
    assert raw not in repr(private)
    assert raw not in json.dumps(private, sort_keys=True)
    assert verifier._turn_failure_code(private).startswith("turn_failed_exact_")


def test_codex_provenance_attests_exact_launcher_and_native_topology(tmp_path) -> None:
    install, launcher, native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    provenance = _attest_synthetic_codex(
        install,
        runner=_synthetic_version_runner,
        platform_name="linux",
        architecture="x86_64",
        launcher_digest=launcher_digest,
        native_digest=native_digest,
    )
    assert provenance.launcher == install / "node_modules/.bin/codex"
    assert provenance.native == native
    assert provenance.launcher.resolve() == launcher


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "wrong"),
        ("version", "0.149.1"),
        ("bin", {"codex": "wrong.js"}),
        ("optionalDependencies", {}),
    ],
)
def test_codex_provenance_rejects_root_manifest_drift(tmp_path, field, value) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    path = install / "node_modules/@openai/codex/package.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="codex_root_manifest_invalid"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("version", "0.149.0"), ("os", ["darwin"]), ("cpu", ["arm64"])],
)
def test_codex_provenance_rejects_platform_manifest_drift(tmp_path, field, value) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    path = install / "node_modules/@openai/codex-linux-x64/package.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="codex_platform_manifest_invalid"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize("kind", ["missing", "malformed", "root", "platform", "ambiguous"])
def test_codex_provenance_rejects_lock_integrity_drift(tmp_path, kind) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    path = install / "package-lock.json"
    if kind == "missing":
        path.unlink()
    elif kind == "malformed":
        path.write_text("[]", encoding="utf-8")
    else:
        lock = json.loads(path.read_text(encoding="utf-8"))
        packages = lock["packages"]
        package_path = (
            "node_modules/@openai/codex"
            if kind in {"root", "ambiguous"}
            else "node_modules/@openai/codex-linux-x64"
        )
        packages[package_path]["integrity"] = (
            [verifier.CODEX_ROOT_PACKAGE_INTEGRITY] if kind == "ambiguous" else "wrong-integrity"
        )
        path.write_text(json.dumps(lock), encoding="utf-8")
    error = (
        "codex_lock_invalid" if kind in {"missing", "malformed"} else "codex_lock_integrity_invalid"
    )
    with pytest.raises(verifier.VerificationError, match=error):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize("architecture", ["arm64", "amd64", "i686"])
def test_codex_provenance_rejects_unsupported_runtime(tmp_path, architecture) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    with pytest.raises(verifier.VerificationError, match="codex_runtime_unsupported"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture=architecture,
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )
    with pytest.raises(verifier.VerificationError, match="codex_runtime_unsupported"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="darwin",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize("kind", ["missing", "regular", "absolute", "wrong", "escape"])
def test_codex_provenance_rejects_launcher_link_drift(tmp_path, kind) -> None:
    install, launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    link = install / "node_modules/.bin/codex"
    link.unlink()
    if kind == "regular":
        link.write_bytes(b"not-a-link")
    elif kind == "absolute":
        link.symlink_to(launcher)
    elif kind == "wrong":
        link.symlink_to("../@openai/codex/bin/other.js")
    elif kind == "escape":
        outside = tmp_path / "outside"
        outside.write_bytes(b"outside")
        link.symlink_to(outside)
    with pytest.raises(verifier.VerificationError, match="codex_launcher_link_invalid"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize("kind", ["missing", "symlink", "oversized", "digest"])
def test_codex_provenance_rejects_launcher_file_drift(tmp_path, kind) -> None:
    install, launcher, native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    if kind == "missing":
        launcher.unlink()
    elif kind == "symlink":
        launcher.unlink()
        launcher.symlink_to(native)
    elif kind == "oversized":
        launcher.write_bytes(b"x" * (verifier.MAX_CODEX_LAUNCHER_BYTES + 1))
        os.chmod(launcher, 0o755)
    else:
        launcher_digest = "0" * 64
    with pytest.raises(verifier.VerificationError, match="codex_launcher_"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


@pytest.mark.parametrize(
    "kind", ["missing", "directory", "symlink", "non_executable", "oversized", "digest"]
)
def test_codex_provenance_rejects_native_file_drift(tmp_path, kind) -> None:
    install, _launcher, native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    expected_native_size = len(b"synthetic-native")
    if kind == "missing":
        native.unlink()
    elif kind == "directory":
        native.unlink()
        native.mkdir()
    elif kind == "symlink":
        native.unlink()
        outside = tmp_path / "native-outside"
        outside.write_bytes(b"outside")
        native.symlink_to(outside)
    elif kind == "non_executable":
        os.chmod(native, 0o600)
    elif kind == "oversized":
        expected_native_size += 1
    else:
        native_digest = "0" * 64
    with pytest.raises(verifier.VerificationError, match="codex_native_"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
            native_size=expected_native_size,
        )


@pytest.mark.parametrize("delta", [-1, 1])
def test_codex_provenance_rejects_one_byte_native_size_drift(tmp_path, delta) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    with pytest.raises(verifier.VerificationError, match="codex_native_size_invalid"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
            native_size=len(b"synthetic-native") + delta,
        )


@pytest.mark.parametrize("native_size", [True, False, "16", 16.0, 0])
def test_codex_provenance_rejects_invalid_native_size_injection(tmp_path, native_size) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    with pytest.raises(verifier.VerificationError, match="codex_native_size_invalid"):
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
            native_size=native_size,
        )


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, b"", b""),
        subprocess.CompletedProcess([], 0, b"wrong\n", b""),
        subprocess.CompletedProcess([], 0, verifier.CODEX_VERSION_OUTPUT, b"diagnostic"),
    ],
)
def test_codex_provenance_rejects_version_probe_drift(tmp_path, result) -> None:
    install, _launcher, _native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )

    def runner(command, *, cwd, env, timeout):
        return result

    with pytest.raises(verifier.VerificationError, match="codex_version_mismatch"):
        _attest_synthetic_codex(
            install,
            runner=runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )


def test_codex_provenance_has_no_broad_search_or_raw_error_values(tmp_path) -> None:
    install, _launcher, native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    native.unlink()
    with pytest.raises(verifier.VerificationError) as exc_info:
        _attest_synthetic_codex(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )
    assert str(native) not in str(exc_info.value)
    source = inspect.getsource(verifier._attest_codex_installation)
    assert "rglob" not in source
    assert "which(" not in source
    assert "glob(" not in source


def test_history_projection_is_structural_and_discards_text() -> None:
    raw_text = "UNRETAINED_ASSISTANT_TEXT_161A"
    projection = verifier._safe_history_projection(_history_body(raw_text))

    assert projection == {
        "body_object": True,
        "assistant_history_count": 1,
        "assistant_history_present": True,
        "assistant_role_exact": True,
        "assistant_output_text_count": 1,
        "assistant_output_text_type_exact": True,
        "assistant_output_text_nonempty_unicode": True,
        "assistant_output_text_size_class": "bounded",
        "image_part_count_class": "one",
        "image_wire_class": "other",
        "raw_value_retained": False,
    }
    assert raw_text not in repr(projection)


def test_history_projection_rejects_empty_invalid_and_oversized_text_classes() -> None:
    empty = verifier._safe_history_projection(_history_body(""))
    oversized = verifier._safe_history_projection(
        _history_body("x" * (verifier.MAX_HISTORY_TEXT_BYTES + 1))
    )
    invalid = verifier._safe_history_projection(_history_body("\udcff"))

    assert empty["assistant_output_text_nonempty_unicode"] is False
    assert empty["assistant_output_text_size_class"] == "empty"
    assert oversized["assistant_output_text_nonempty_unicode"] is False
    assert oversized["assistant_output_text_size_class"] == "oversized"
    assert invalid["assistant_output_text_nonempty_unicode"] is False
    assert invalid["assistant_output_text_size_class"] == "invalid_unicode"


def _direct_observer_body(
    image_bytes: bytes, *, history: bool = False, extra: bool = False
) -> bytes:
    image_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    items: list[dict[str, object]] = []
    if history:
        part: dict[str, object] = {"type": "output_text", "text": "history-only-text"}
        if extra:
            part["annotations"] = []
        items.append({"role": "assistant", "content": [part]})
    items.append(
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": image_url},
                {"type": "input_text", "text": "bounded"},
            ],
        }
    )
    return json.dumps({"stream": True, "input": items}).encode()


def _direct_headers(authorization: str = "Bearer synthetic-direct-upstream-token-161-p"):
    headers = http.client.HTTPMessage()
    headers["authorization"] = authorization
    return headers


def test_direct_upstream_observer_accepts_full_then_crop_history() -> None:
    full = b"full"
    crop = b"crop"
    expectations = {
        "full_sha256": hashlib.sha256(full).hexdigest(),
        "full_length": len(full),
        "crop_sha256": hashlib.sha256(crop).hexdigest(),
        "crop_length": len(crop),
    }
    state = verifier._DirectUpstreamState(expectations)
    state.observe(_direct_observer_body(full), _direct_headers())
    state.observe(_direct_observer_body(crop, history=True), _direct_headers())
    assert state.request_count == 2
    assert state.authorization_count == 2
    assert state.first_image_class == "full"
    assert state.second_image_class == "crop"
    assert state.history_semantics_valid is True
    assert state.semantic_text_equal is True


@pytest.mark.parametrize("kind", ["auth", "text", "extra"])
def test_direct_upstream_observer_rejects_history_mutations(kind: str) -> None:
    full = b"full"
    crop = b"crop"
    expectations = {
        "full_sha256": hashlib.sha256(full).hexdigest(),
        "full_length": len(full),
        "crop_sha256": hashlib.sha256(crop).hexdigest(),
        "crop_length": len(crop),
    }
    state = verifier._DirectUpstreamState(expectations)
    state.observe(_direct_observer_body(full), _direct_headers())
    body = _direct_observer_body(crop, history=True)
    headers = _direct_headers()
    if kind == "auth":
        headers = _direct_headers("Bearer wrong")
        error = "direct_upstream_authorization_invalid"
    elif kind == "text":
        body = body.replace(b"history-only-text", b"changed-text")
        error = "direct_upstream_output_text_invalid"
    else:
        body = body.replace(b'"type": "output_text"', b'"type": "output_text", "phase": "x"')
        error = "direct_upstream_output_text_invalid"
    with pytest.raises(verifier.VerificationError, match=error):
        state.observe(body, headers)


def test_direct_upstream_observer_rejects_extra_request() -> None:
    full = b"full"
    crop = b"crop"
    expectations = {
        "full_sha256": hashlib.sha256(full).hexdigest(),
        "full_length": len(full),
        "crop_sha256": hashlib.sha256(crop).hexdigest(),
        "crop_length": len(crop),
    }
    state = verifier._DirectUpstreamState(expectations)
    state.observe(_direct_observer_body(full), _direct_headers())
    state.observe(_direct_observer_body(crop, history=True), _direct_headers())
    with pytest.raises(verifier.VerificationError, match="direct_upstream_retry_invalid"):
        state.observe(_direct_observer_body(crop, history=True), _direct_headers())


def test_direct_terminal_sse_requires_order_and_usage() -> None:
    body = b"".join(verifier._sse(event) for event in verifier._message_stream("history-only-text"))
    assert verifier._validate_direct_terminal_sse(body) == "history-only-text"
    with pytest.raises(verifier.VerificationError, match="direct_terminal_event_sequence_invalid"):
        verifier._validate_direct_terminal_sse(
            body.replace(b"response.completed", b"response.unknown")
        )
    events = list(verifier._message_stream("history-only-text"))
    events[-1]["response"].pop("usage")
    without_usage = b"".join(verifier._sse(event) for event in events)
    with pytest.raises(verifier.VerificationError, match="direct_terminal_usage_missing"):
        verifier._validate_direct_terminal_sse(without_usage)


@pytest.mark.parametrize("mutation", ["changed", "missing", "wrong_role"])
def test_direct_terminal_rejects_returned_text_mutations(mutation: str) -> None:
    events = list(verifier._message_stream("returned-text"))
    if mutation == "changed":
        events[5]["text"] = "different-text"
    elif mutation == "missing":
        events[7]["item"]["content"] = []
    else:
        events[7]["item"]["role"] = "user"
    body = b"".join(verifier._sse(event) for event in events)
    with pytest.raises(verifier.VerificationError):
        verifier._validate_direct_terminal_sse(body)


def test_direct_local_source_attestation_rejects_loaded_source_mismatch(
    tmp_path, monkeypatch
) -> None:
    checkout = tmp_path / "local"
    expected = checkout / "src/slaif_local_coding/__init__.py"
    expected.parent.mkdir(parents=True)
    expected.write_text("", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, b"/unrelated/source.py\n", b"")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    assert (
        verifier._attest_direct_local_source(checkout, {"PYTHONPATH": str(expected.parent)})
        is False
    )


def test_error_projection_is_closed_and_does_not_retain_raw_values() -> None:
    private_code = "private-code-161a"
    private_param = "input[5].content[0].private"
    body = json.dumps(
        {"error": {"code": private_code, "param": private_param, "message": "private"}}
    ).encode()
    projection = verifier._safe_error_projection(body)

    assert projection == {"json_object": True, "error_code": "other", "param_class": "other"}
    assert private_code not in repr(projection)
    assert private_param not in repr(projection)


def test_exact_image_fixture_and_resume_command_shape_is_explicit(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    facts = verifier._validate_image_pair(written["full_path"], written["crop_path"])
    initial = verifier._initial_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "first.json",
        full_image=facts["full_path"],
    )
    command = verifier._resume_last_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "last.json",
        crop_image=facts["crop_path"],
    )
    verifier._validate_command_binding(initial, expected_image=facts["full_path"], resume=False)
    verifier._validate_command_binding(command, expected_image=facts["crop_path"], resume=True)

    initial_suffix = initial[initial.index("--cd") :]
    assert initial_suffix[:7] == [
        "--cd",
        str(tmp_path / "workspace"),
        "--image",
        str(facts["full_path"]),
        "--output-last-message",
        str(tmp_path / "first.json"),
        "Describe the attached synthetic full scene briefly without tools.",
    ]
    resume_index = command.index("resume")
    assert command[resume_index : resume_index + 5] == [
        "resume",
        "--last",
        "--json",
        "--strict-config",
        "--ignore-user-config",
    ]
    assert command[command.index("--image") : command.index("--image") + 2] == [
        "--image",
        str(facts["crop_path"]),
    ]
    assert "--output-last-message" in command
    assert "resume" in command and "--last" in command
    assert not any("123e4567" in item for item in command)


def test_image_fixture_negatives_are_bounded_and_fail_closed(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    with pytest.raises(verifier.VerificationError, match="image_fixture_missing"):
        written["full_path"].unlink()
        verifier._validate_image_pair(written["full_path"], written["crop_path"])

    written = verifier._write_image_fixtures(tmp_path)
    written["crop_path"].write_bytes(b"not-a-png")
    with pytest.raises(verifier.VerificationError, match="image_fixture_crop_invalid"):
        verifier._validate_image_pair(written["full_path"], written["crop_path"])

    written = verifier._write_image_fixtures(tmp_path)
    written["crop_path"].write_bytes(written["full_path"].read_bytes())
    with pytest.raises(verifier.VerificationError, match="image_fixture_pair_not_distinct"):
        verifier._validate_image_pair(written["full_path"], written["crop_path"])


def test_image_command_negatives_cover_binding_placement_and_cardinality(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    command = verifier._resume_last_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "last.json",
        crop_image=written["crop_path"],
    )
    missing = [item for item in command if item not in {"--image", str(written["crop_path"])}]
    with pytest.raises(verifier.VerificationError, match="image_command_missing"):
        verifier._validate_command_binding(
            missing, expected_image=written["crop_path"], resume=True
        )

    stale = list(command)
    stale[stale.index(str(written["crop_path"]))] = str(written["full_path"])
    with pytest.raises(verifier.VerificationError, match="image_command_binding_invalid"):
        verifier._validate_command_binding(stale, expected_image=written["crop_path"], resume=True)

    multiple = list(command)
    image_index = multiple.index("--image")
    multiple[image_index:image_index] = ["--image", str(written["full_path"])]
    with pytest.raises(verifier.VerificationError, match="image_command_multiple"):
        verifier._validate_command_binding(
            multiple, expected_image=written["crop_path"], resume=True
        )

    misplaced = list(command)
    image_index = misplaced.index("--image")
    output_index = misplaced.index("--output-last-message")
    output_flag = misplaced.pop(output_index)
    misplaced.insert(image_index, output_flag)
    with pytest.raises(verifier.VerificationError, match="image_command_suffix_invalid"):
        verifier._validate_command_binding(
            misplaced, expected_image=written["crop_path"], resume=True
        )


def test_no_image_control_removes_exactly_one_full_image_pair(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    baseline = verifier._initial_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "first.json",
        full_image=written["full_path"],
    )
    control = verifier._no_image_first_turn_command(baseline, expected_image=written["full_path"])
    verifier._validate_no_image_command(
        control,
        baseline=baseline,
        expected_image=written["full_path"],
        crop_image=written["crop_path"],
    )
    image_index = baseline.index("--image")
    assert control == baseline[:image_index] + baseline[image_index + 2 :]
    assert "--image" not in control
    assert str(written["full_path"]) not in control
    assert "resume" not in control and "--last" not in control


@pytest.mark.parametrize("mutation", ["missing", "wrong", "duplicate", "resume"])
def test_no_image_control_rejects_differential_mutations(tmp_path, mutation) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    baseline = verifier._initial_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "first.json",
        full_image=written["full_path"],
    )
    if mutation == "missing":
        mutated = [item for item in baseline if item not in {"--image", str(written["full_path"])}]
        with pytest.raises(verifier.VerificationError, match="no_image_command_image_pair_invalid"):
            verifier._no_image_first_turn_command(mutated, expected_image=written["full_path"])
        return
    else:
        mutated = verifier._no_image_first_turn_command(
            baseline, expected_image=written["full_path"]
        )
        if mutation == "wrong":
            mutated.insert(mutated.index("--output-last-message"), str(written["full_path"]))
        elif mutation == "duplicate":
            index = mutated.index("--output-last-message")
            mutated[index:index] = ["--image", str(written["full_path"])]
        elif mutation == "resume":
            mutated.insert(2, "resume")
    with pytest.raises(verifier.VerificationError, match="no_image_"):
        verifier._validate_no_image_command(
            mutated,
            baseline=baseline,
            expected_image=written["full_path"],
            crop_image=written["crop_path"],
        )


def test_image_wire_projection_discards_data_url_and_classifies_fixture(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    facts = verifier._validate_image_pair(written["full_path"], written["crop_path"])
    expectations = verifier._image_expectations(facts)
    encoded = base64.b64encode(written["crop_path"].read_bytes()).decode()
    raw_url = "data:image/png;base64," + encoded
    projection = verifier._safe_history_projection(
        {
            "input": [
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "safe"}],
                },
                {"role": "user", "content": [{"type": "input_image", "image_url": raw_url}]},
            ]
        },
        image_expectations=expectations,
    )
    assert projection["image_wire_class"] == "crop"
    assert raw_url not in repr(projection)


def test_gateway_observer_marks_bounded_body_overflow(monkeypatch) -> None:
    monkeypatch.setattr(verifier, "MAX_CAPTURE_BODY_BYTES", 4)
    body = b"12345"

    async def app(scope, receive, send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    messages = iter(({"type": "http.request", "body": body, "more_body": False},))

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(_message: dict[str, object]) -> None:
        return None

    observer = verifier.GatewayObservation(app)
    asyncio.run(
        observer(
            {"type": "http", "method": "POST", "path": "/v1/responses"},
            receive,
            send,
        )
    )
    assert observer.request_overflow_classes == ["request_body_overflow"]
    assert observer.request_projections == []


def test_gateway_observer_projects_second_body_without_raw_values() -> None:
    sent: list[dict[str, object]] = []
    body = json.dumps(_history_body("not-retained-observer-text")).encode()

    async def app(scope, receive, send) -> None:
        assert scope["path"] == "/v1/responses"
        message = await receive()
        assert message["body"] == body
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "error": {
                            "code": verifier._ALLOWED_ERROR_CODE,
                            "param": "input[5].content[0].type",
                        }
                    }
                ).encode(),
                "more_body": False,
            }
        )

    messages = iter(({"type": "http.request", "body": body, "more_body": False},))

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    observer = verifier.GatewayObservation(app)
    observer.request_count = 1
    asyncio.run(
        observer(
            {"type": "http", "method": "POST", "path": "/v1/responses"},
            receive,
            send,
        )
    )

    assert observer.request_count == 2
    assert observer.response_statuses == [400]
    assert observer.error_codes == [verifier._ALLOWED_ERROR_CODE]
    assert observer.param_classes == ["input_5_content_0_type"]
    assert observer.second_projection is not None
    assert observer.second_projection["assistant_output_text_nonempty_unicode"] is True
    assert "not-retained-observer-text" not in repr(observer.second_projection)
    assert "not-retained-observer-text" not in repr(sent)


def test_error_projection_unknown_and_malformed_inputs_are_fixed() -> None:
    assert verifier._safe_error_projection(b"not-json") == {
        "json_object": False,
        "error_code": "other",
        "param_class": "other",
    }
    assert (
        verifier._fixed_param_class("input[1].content[0].type")
        == "input_index_1_content_index_0_type"
    )
    assert verifier._fixed_param_class("input[5].content[0].type.extra") == "other"


def _catalog_document() -> dict[str, object]:
    return {
        "schema": "synthetic-catalog-v1",
        "models": [
            {"slug": "other-model", "unrelated": {"stable": True}},
            {
                "slug": verifier.CODEX_MODEL,
                "display_name": "synthetic",
                "unrelated": {"stable": True},
            },
        ],
    }


def test_vision_catalog_positive_facts_are_exact_and_preserve_unrelated_fields(tmp_path) -> None:
    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    facts = verifier._validate_vision_catalog_document(
        prepared, model=verifier.CODEX_MODEL, baseline=baseline
    )
    assert facts["modalities_exact"] is True
    assert facts["image_detail_false"] is True
    assert facts["context_exact"] is True
    assert facts["max_context_exact"] is True
    assert facts["parallel_tools_false"] is True
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    assert selected["input_modalities"] == ["text", "image"]
    assert selected["supports_image_detail_original"] is False
    assert selected["context_window"] == 100_000
    assert selected["max_context_window"] == 100_000
    assert selected["supports_parallel_tool_calls"] is False
    assert selected["unrelated"] == {"stable": True}
    assert verifier.LOCAL_005Q_SOURCE_COMMIT == "64e50172ee02563e2b021554f6b0d345cc7dfdec"
    assert verifier.LOCAL_005Q_VISION_SOURCE_PATH == "tests/helpers/vision_e2e_support.py"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("input_modalities", ["image", "text"], "vision_catalog_modalities_invalid"),
        ("input_modalities", ["text", "image", "audio"], "vision_catalog_modalities_invalid"),
        ("supports_image_detail_original", True, "vision_catalog_image_detail_invalid"),
        ("supports_image_detail_original", None, "vision_catalog_image_detail_invalid"),
        ("context_window", 99_999, "vision_catalog_context_invalid"),
        ("context_window", True, "vision_catalog_context_invalid"),
        ("max_context_window", 100_001, "vision_catalog_context_invalid"),
        ("max_context_window", None, "vision_catalog_context_invalid"),
        ("supports_parallel_tool_calls", True, "vision_catalog_parallel_tools_invalid"),
        ("supports_parallel_tool_calls", None, "vision_catalog_parallel_tools_invalid"),
    ],
)
def test_vision_catalog_rejects_malformed_or_unapproved_facts(field, value, error) -> None:
    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    selected[field] = value
    with pytest.raises(verifier.VerificationError, match=error):
        verifier._validate_vision_catalog_document(prepared, model=verifier.CODEX_MODEL)


def test_vision_catalog_rejects_missing_duplicate_and_unknown_mutation_without_raw_value() -> None:
    missing = {"models": [{"slug": "different"}]}
    with pytest.raises(verifier.VerificationError, match="vision_catalog_model_missing"):
        verifier._prepare_vision_catalog_document(missing, model=verifier.CODEX_MODEL)

    duplicate = {"models": [{"slug": verifier.CODEX_MODEL}, {"slug": verifier.CODEX_MODEL}]}
    with pytest.raises(verifier.VerificationError, match="vision_catalog_model_duplicate"):
        verifier._prepare_vision_catalog_document(duplicate, model=verifier.CODEX_MODEL)

    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    raw_canary = "UNRETAINED_CATALOG_CANARY_161C"
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    selected["unreviewed_mutation"] = raw_canary
    with pytest.raises(verifier.VerificationError) as exc_info:
        verifier._validate_vision_catalog_document(
            prepared, model=verifier.CODEX_MODEL, baseline=baseline
        )
    assert exc_info.value.args[0] == "vision_catalog_unrelated_mutation"
    assert raw_canary not in str(exc_info.value)


def test_vision_catalog_write_is_canonical_bounded_and_mode_0600(tmp_path) -> None:
    baseline = _catalog_document()
    path = tmp_path / "catalog.json"
    facts = verifier._write_and_validate_vision_catalog(path, baseline, model=verifier.CODEX_MODEL)
    assert facts["model_present"] is True
    assert path.stat().st_mode & 0o777 == 0o600
    raw = path.read_bytes()
    assert (
        raw
        == (
            json.dumps(json.loads(raw), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        ).encode()
    )

    oversized = _catalog_document()
    oversized["models"][1]["description"] = "x" * (verifier.MAX_CAPTURE_BODY_BYTES + 1)
    with pytest.raises(verifier.VerificationError, match="vision_catalog_oversized"):
        verifier._write_and_validate_vision_catalog(
            tmp_path / "oversized.json", oversized, model=verifier.CODEX_MODEL
        )

    with pytest.raises(verifier.VerificationError, match="vision_catalog_noncanonical"):
        verifier._prepare_vision_catalog_document(
            {"models": [{"slug": verifier.CODEX_MODEL, "bad": object()}]},
            model=verifier.CODEX_MODEL,
        )


def test_canonical_capture_environment_is_pinned_and_stale_alias_is_rejected(tmp_path) -> None:
    args = verifier._codex_profile_args(port=43123, model_catalog=tmp_path / "catalog.json")
    provider_blocks = [item for item in args if item.startswith("model_providers.slaif-capture=")]
    assert len(provider_blocks) == 1
    assert f'env_key="{verifier.CODEX_CAPTURE_API_KEY_ENV}"' in provider_blocks[0]
    assert verifier.STALE_CAPTURE_API_KEY_ENV not in provider_blocks[0]


def test_accounting_snapshot_terminal_shape_and_equality_are_closed() -> None:
    snapshot = {
        "reservations_total": "two",
        "reservations_finalized": "two",
        "reservations_pending": "zero",
        "reservations_released": "zero",
        "ledgers_total": "two",
        "ledgers_finalized": "two",
        "ledgers_pending": "zero",
        "ledgers_failed": "zero",
        "ledgers_successful": "two",
        "replay_references": "zero",
        "query_success": True,
    }
    assert verifier._accounting_snapshot_is_two_terminal_successes(snapshot)
    assert verifier._accounting_snapshot_equal(snapshot, dict(snapshot))
    changed = dict(snapshot)
    changed["ledgers_total"] = "other"
    assert verifier._accounting_snapshot_equal(snapshot, changed) is False
    assert "PRIVATE_DB_ID" not in repr(snapshot)


def test_accounting_control_line_is_closed_and_cleanup_bounded() -> None:
    diagnostic = verifier.DiagnosticState(
        accounting_control_snapshot={
            "reservations_total": "two",
            "reservations_finalized": "two",
            "reservations_pending": "zero",
            "reservations_released": "zero",
            "ledgers_total": "two",
            "ledgers_finalized": "two",
            "ledgers_pending": "zero",
            "ledgers_failed": "zero",
            "ledgers_successful": "two",
            "replay_references": "zero",
            "query_success": True,
        },
        accounting_control_gateway_count="two",
        accounting_control_statuses="2xx_2xx",
        accounting_control_images="full_none",
        accounting_control_local_count="two",
        cleanup_succeeded=True,
    )
    line = verifier._accounting_control_line(diagnostic)
    assert line.startswith("VERIFY_CODEX_0149_ACCOUNTING_BEFORE_REJECTION_OK ")
    assert "reservations_total=two" in line
    assert "images=full_none" in line
    assert "cleanup_succeeded=true" in line
    assert "PRIVATE" not in line


def test_accounting_dispatch_forwards_once_and_preserves_default(monkeypatch) -> None:
    calls: list[tuple[bool, bool]] = []

    def fake_body(diagnostic, *, no_image_first_turn=False, accounting_before_rejection=False):
        calls.append((no_image_first_turn, accounting_before_rejection))
        return "CONTROL_STUB"

    monkeypatch.setattr(verifier, "_run_prefixed_reproduction_body", fake_body)
    assert (
        verifier.run_prefixed_reproduction(
            verifier.DiagnosticState(), accounting_before_rejection=True
        )
        == "CONTROL_STUB"
    )
    assert verifier.run_prefixed_reproduction(verifier.DiagnosticState()) == "CONTROL_STUB"
    assert calls == [(False, True), (False, False)]
    with pytest.raises(verifier.VerificationError, match="diagnostic_control_args_conflict"):
        verifier.run_prefixed_reproduction(
            verifier.DiagnosticState(),
            no_image_first_turn=True,
            accounting_before_rejection=True,
        )


def test_diagnostic_import_stages_and_module_context_are_closed() -> None:
    diagnostic = verifier.DiagnosticState()
    import_stages = (
        "imports",
        "import_capture",
        "import_responses_helper",
        "import_chat_helper",
        "import_gateway_config",
        "import_gateway_app",
        "import_codex_module",
        "database_setup",
    )
    for stage in import_stages:
        diagnostic.advance(stage)
    with pytest.raises(verifier.VerificationError, match="diagnostic_stage_non_monotonic"):
        diagnostic.advance("import_capture")
    diagnostic.module_context = "module"
    diagnostic.scripts_package_present = True
    diagnostic.verifier_module_present = True
    diagnostic.duplicate_verifier_module = False
    snapshot = diagnostic.snapshot()
    assert snapshot["module_context"] == "module"
    assert snapshot["scripts_package_present"] is True
    assert snapshot["verifier_module_present"] is True
    assert snapshot["duplicate_verifier_module"] is False
