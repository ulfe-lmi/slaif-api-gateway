from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import os
import subprocess

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


def test_codex_provenance_attests_exact_launcher_and_native_topology(tmp_path) -> None:
    install, launcher, native, launcher_digest, native_digest = _synthetic_codex_installation(
        tmp_path
    )
    provenance = verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture=architecture,
            launcher_digest=launcher_digest,
            native_digest=native_digest,
        )
    with pytest.raises(verifier.VerificationError, match="codex_runtime_unsupported"):
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
        native.write_bytes(b"x" * (verifier.MAX_CODEX_NATIVE_BYTES + 1))
        os.chmod(native, 0o755)
    else:
        native_digest = "0" * 64
    with pytest.raises(verifier.VerificationError, match="codex_native_"):
        verifier._attest_codex_installation(
            install,
            runner=_synthetic_version_runner,
            platform_name="linux",
            architecture="x86_64",
            launcher_digest=launcher_digest,
            native_digest=native_digest,
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
        verifier._attest_codex_installation(
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
        verifier._attest_codex_installation(
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
