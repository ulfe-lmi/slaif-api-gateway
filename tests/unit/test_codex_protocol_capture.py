from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import capture_codex_protocol as capture


FIXTURE = (
    capture.REPO_ROOT
    / "tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json"
)
FIXTURE_0149 = (
    capture.REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural-v2.json"
)
HISTORICAL_0149 = (
    capture.REPO_ROOT / "tests/fixtures/codex/0.149.0/responses-structural.json"
)
APPROVED_FIXTURE_SHA256 = (
    "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
)
SAFE_HEADERS = (
    ("authorization", f"Bearer {capture.TOKEN_CANARY}"),
    ("content-length", "2"),
    ("content-type", "application/json"),
    ("user-agent", "client-id-canary"),
)


def _request(
    body: object,
    *,
    method: str = "POST",
    target: str = "/v1/responses",
    headers: tuple[tuple[str, str], ...] = SAFE_HEADERS,
) -> capture.ParsedHttpRequest:
    return capture.ParsedHttpRequest(
        method=method,
        target=target,
        version="HTTP/1.1",
        headers=headers,
        body=json.dumps(body).encode(),
    )


def _checked_in_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_bytes())


def test_exact_version_parser_and_mismatch_precedes_server_or_write(monkeypatch) -> None:
    assert capture.parse_codex_version("codex-cli 0.147.0\n") == "0.147.0"
    with pytest.raises(capture.CaptureError, match="unrecognized version"):
        capture.parse_codex_version("codex 0.147.0\n")

    monkeypatch.setattr(
        capture.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout="codex-cli 0.147.0\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        capture.LoopbackCaptureServer,
        "start",
        lambda self: pytest.fail("server must not bind after a version mismatch"),
    )
    monkeypatch.setattr(
        capture,
        "_atomic_write",
        lambda *args, **kwargs: pytest.fail("version mismatch must not write"),
    )
    with pytest.raises(capture.CaptureError, match="does not match"):
        capture.capture_live(
            codex_binary=Path("/synthetic/codex"),
            expected_version="0.146.0",
            model=capture.PINNED_MODEL,
            profile=capture.PINNED_PROFILE,
        )


def test_model_catalog_sanitizer_is_allowlisted_and_excludes_free_text() -> None:
    catalog = {
        "models": [
            {
                "slug": capture.PINNED_MODEL,
                "description": "catalog-description-canary",
                "base_instructions": "AGENTS-content-canary",
                "model_messages": {"instructions_template": "instruction-canary"},
                "availability_nux": {"message": "nux-canary"},
                "display_name": "display-canary",
                "use_responses_lite": True,
                "shell_type": "shell_command",
                "apply_patch_tool_type": "freeform",
                "supports_parallel_tool_calls": True,
                "input_modalities": ["text", "image"],
                "supported_reasoning_levels": [
                    {"effort": "low", "description": "reasoning-description-canary"}
                ],
            }
        ]
    }
    safe = capture.sanitize_model_catalog(catalog, model=capture.PINNED_MODEL)
    encoded = capture.canonical_json_bytes(safe)

    assert set(safe) <= capture._SAFE_CATALOG_FIELDS
    assert safe["supported_reasoning_levels"] == ["low"]
    for forbidden in capture._FREE_TEXT_CATALOG_FIELDS:
        assert forbidden not in safe
    assert b"canary" not in encoded


def test_header_sanitizer_keeps_names_and_never_values() -> None:
    safe = capture.sanitize_headers(SAFE_HEADERS)
    serialized = capture.canonical_json_bytes(safe)

    assert safe["authorization"] == {"present": True, "redacted": True}
    assert safe["content_encoding"] == {"present": False}
    assert safe["content_type"] == "application/json"
    assert "authorization" in safe["names"]
    assert capture.TOKEN_CANARY.encode() not in serialized
    assert b"client-id-canary" not in serialized


def test_request_sanitizer_preserves_structure_without_content_or_tool_schema_values() -> None:
    body = {
        "model": capture.PINNED_MODEL,
        "instructions": "instruction-canary",
        "metadata": {"person": "personal-canary"},
        "input": [
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "functions",
                        "description": "namespace-description-canary",
                        "tools": [
                            {
                                "type": "function",
                                "name": "safe_tool_name",
                                "description": "tool-description-canary",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "secret_property_name": {
                                            "type": "string",
                                            "description": "schema-description-canary",
                                            "default": "schema-default-canary",
                                        }
                                    },
                                    "required": ["secret_property_name"],
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": capture.PROMPT_CANARY}],
            },
        ],
    }
    safe = capture.sanitize_request(_request(body))
    serialized = capture.canonical_json_bytes(safe)

    assert b"safe_tool_name" in serialized
    assert b"namespace" in serialized
    for forbidden in (
        b"instruction-canary",
        b"personal-canary",
        capture.PROMPT_CANARY.encode(),
        b"tool-description-canary",
        b"schema-description-canary",
        b"schema-default-canary",
        b"secret_property_name",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("captured_request", "message"),
    (
        (_request({}, method="GET"), "unexpected HTTP method"),
        (_request({}, target="/v1/chat/completions"), "unexpected HTTP path"),
        (
            _request({}, headers=SAFE_HEADERS + (("content-encoding", "zstd"),)),
            "unsupported Content-Encoding",
        ),
        (
            capture.ParsedHttpRequest(
                method="POST",
                target="/v1/responses",
                version="HTTP/1.1",
                headers=SAFE_HEADERS,
                body=b"not-json secret-echo-canary",
            ),
            "malformed JSON",
        ),
    ),
)
def test_request_rejections_are_safe(captured_request, message: str) -> None:
    with pytest.raises(capture.CaptureError, match=message) as error:
        capture.sanitize_request(captured_request)
    assert "secret-echo-canary" not in str(error.value)


def test_http_parser_rejects_oversized_headers_and_body_without_echo() -> None:
    oversized_headers = b"POST /v1/responses HTTP/1.1\r\nX-Canary: " + (
        b"secret-echo-canary" * capture.MAX_HEADER_BYTES
    )
    with pytest.raises(capture.CaptureError, match="headers exceeded") as error:
        capture._parse_http_request(oversized_headers)
    assert "secret-echo-canary" not in str(error.value)

    oversized_body = (
        b"POST /v1/responses HTTP/1.1\r\nContent-Length: "
        + str(capture.MAX_BODY_BYTES + 1).encode()
        + b"\r\n\r\n"
    )
    with pytest.raises(capture.CaptureError, match="body exceeded"):
        capture._parse_http_request(oversized_body)


def test_extra_request_timeout_nonzero_and_malformed_sse_fail_safely() -> None:
    with pytest.raises(capture.CaptureError, match="exactly one"):
        capture.validate_request_count(2)
    with pytest.raises(capture.CaptureError, match="timed out"):
        capture.ensure_subprocess_success(timed_out=True)
    with pytest.raises(capture.CaptureError, match="unclassified"):
        capture.ensure_subprocess_success(returncode=7)
    with pytest.raises(capture.CaptureError, match="malformed") as error:
        capture.validate_mock_sse(b"event: response.created\ndata: secret-echo-canary\n\n")
    assert "secret-echo-canary" not in str(error.value)


def test_fixture_identity_canonical_encoding_and_required_capture_invariants() -> None:
    fixture = _checked_in_fixture()
    capture.validate_fixture(fixture)

    assert capture.APPROVED_CANONICAL_FIXTURE_SHA256 == APPROVED_FIXTURE_SHA256
    assert hashlib.sha256(capture.canonical_json_bytes(fixture)).hexdigest() == (
        APPROVED_FIXTURE_SHA256
    )
    assert FIXTURE.read_bytes() == capture.canonical_json_bytes(fixture)
    assert fixture["schema_version"] == capture.SCHEMA_VERSION
    assert fixture["identity"] == {
        "cli_family": "codex-cli",
        "cli_version": "0.147.0",
        "model": "gpt-5.6-sol",
        "profile": "api-key-responses-baseline",
        "source_tag": "rust-v0.147.0",
    }
    request = fixture["capture"]["request"]
    assert request["path"] == "/v1/responses"
    assert request["headers"]["authorization"] == {"present": True, "redacted": True}
    assert request["headers"]["content_encoding"] == {"present": False}
    assert fixture["capture"]["subprocess"] == {
        "accepted_mock": True,
        "exit_success": True,
    }


def test_fixture_contains_no_prompt_token_secret_client_or_description_canaries() -> None:
    payload = FIXTURE.read_bytes()
    forbidden = (
        capture.PROMPT_CANARY.encode(),
        capture.TOKEN_CANARY.encode(),
        b"client-id-canary",
        b"AGENTS-content-canary",
        b"schema-description-canary",
        b"base_instructions",
        b"model_messages",
    )
    assert all(value not in payload for value in forbidden)


def test_0149_fixture_is_separate_and_exactly_capture_derived() -> None:
    raw = FIXTURE_0149.read_bytes()
    fixture = json.loads(raw)
    capture.validate_0149_fixture(fixture)
    assert raw == capture.canonical_json_bytes(fixture)
    assert hashlib.sha256(raw).hexdigest() == capture.APPROVED_0149_CANONICAL_FIXTURE_SHA256
    assert hashlib.sha256(HISTORICAL_0149.read_bytes()).hexdigest() == (
        "0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d"
    )
    shapes = fixture["capture"]["variants"][0]["request"]["tool_declarations"]["shapes"]
    assert {shape["type"] for shape in shapes} == {
        "function",
        "custom",
        "tool_search",
        "web_search",
    }
    assert fixture["findings"]["adapter_managed_candidate_types"] == [
        "tool_search",
        "web_search",
    ]


def test_0149_production_path_returns_only_candidate_types_without_raw_values() -> None:
    body = {
        "model": capture.PINNED_0149_MODEL,
        "input": [{"type": "message", "role": "user", "content": "raw-canary"}],
        "tools": [
            {
                "type": "tool_search",
                "description": "candidate-description-canary",
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
    candidates = capture.validate_0149_production_path(_request(body))
    assert candidates == ("tool_search", "web_search")
    safe = capture.canonical_json_bytes({"candidate_types": candidates})
    assert b"raw-canary" not in safe
    assert b"candidate-description-canary" not in safe
    source = Path(capture.__file__).read_text(encoding="utf-8")
    assert "from slaif_gateway.modules.clients.registry import CODEX_0149_CLIENT_MODULE" in source
    assert "from slaif_gateway.services import responses_request_policy" in source
    assert "responses_request_policy.ResponsesRequestPolicy" in source


def test_0149_request_sanitizer_retains_only_observed_structural_facts() -> None:
    request = _request(
        {
            "model": "qwen3.8-27b",
            "input": [{"type": "message", "content": "synthetic"}],
            "instructions": "private prompt",
            "tools": [
                {
                    "type": "tool_search",
                    "description": "private description",
                    "execution": "client",
                    "parameters": {"type": "object"},
                },
                {
                    "type": "web_search",
                    "external_web_access": False,
                    "search_content_types": ["text", "image"],
                },
            ],
            "tool_choice": "auto",
        }
    )
    safe = capture.sanitize_0149_request(request)
    encoded = capture.canonical_json_bytes(safe)
    assert safe["tool_declarations"]["count"] == 2
    assert b"private prompt" not in encoded
    assert b"private description" not in encoded
    assert b"qwen3.8-27b" not in encoded


def test_0149_request_sanitizer_rejects_authority_fields_without_echo() -> None:
    request = _request(
        {
            "model": "qwen3.8-27b",
            "tools": [
                {
                    "type": "tool_search",
                    "description": "safe",
                    "execution": "client",
                    "parameters": {"authorization": "secret-canary"},
                }
            ],
            "tool_choice": "auto",
        }
    )
    with pytest.raises(capture.CaptureError) as error:
        capture.sanitize_0149_request(request)
    assert "secret-canary" not in str(error.value)


def test_compatibility_diff_is_reproducible_and_not_compatible() -> None:
    fixture = _checked_in_fixture()
    request = fixture["capture"]["request"]
    compatibility = fixture["gateway_compatibility"]

    assert capture.build_gateway_compatibility(request) == compatibility
    assert compatibility["status"] == "not_compatible"
    rejected_fields = {
        item["name"] for item in compatibility["top_level_fields"]["rejected"]
    }
    assert {"client_metadata", "include", "reasoning", "prompt_cache_key"} <= rejected_fields
    assert compatibility["input_item_types"]["rejected"]
    assert any(item["status"] == "rejected" for item in compatibility["tools"])


def test_altered_version_and_structure_fail_fixture_validation() -> None:
    fixture = _checked_in_fixture()
    altered_version = copy.deepcopy(fixture)
    altered_version["identity"]["cli_version"] = "0.148.0"
    with pytest.raises(capture.CaptureError, match="identity"):
        capture.validate_fixture(altered_version)

    altered_path = copy.deepcopy(fixture)
    altered_path["capture"]["request"]["path"] = "/v1/chat/completions"
    with pytest.raises(capture.CaptureError, match="path"):
        capture.validate_fixture(altered_path)


def _assert_fixture_integrity_failure(
    fixture: dict[str, object],
    *,
    injected_content: str | None = None,
) -> None:
    computed_digest = hashlib.sha256(capture.canonical_json_bytes(fixture)).hexdigest()
    with pytest.raises(capture.CaptureError) as error:
        capture.validate_fixture(fixture)

    assert str(error.value) == capture.FIXTURE_INTEGRITY_ERROR
    assert computed_digest not in str(error.value)
    if injected_content is not None:
        assert injected_content not in str(error.value)


def test_fixture_integrity_rejects_unknown_nested_content_without_echo() -> None:
    fixture = copy.deepcopy(_checked_in_fixture())
    injected_content = "synthetic-free-text-secret-canary"
    fixture["capture"]["unexpected_raw"] = {"value": injected_content}

    _assert_fixture_integrity_failure(fixture, injected_content=injected_content)


def test_fixture_integrity_rejects_removed_harmless_structural_member() -> None:
    fixture = copy.deepcopy(_checked_in_fixture())
    del fixture["model_catalog"]["supports_search_tool"]

    _assert_fixture_integrity_failure(fixture)


def test_fixture_integrity_rejects_subtle_schema_shape_mutation() -> None:
    fixture = copy.deepcopy(_checked_in_fixture())
    first_tool = fixture["capture"]["request"]["field_shapes"]["input"]["items"][0][
        "tools"
    ][0]["tools"][1]
    first_tool["parameter_schema"]["properties"][0]["type"] = "integer"

    _assert_fixture_integrity_failure(fixture)


def test_module_import_has_no_subprocess_network_or_filesystem_action(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("subprocess"))
    monkeypatch.setattr(capture.socket, "socket", lambda *args, **kwargs: pytest.fail("socket"))
    monkeypatch.setattr(Path, "write_bytes", lambda *args, **kwargs: pytest.fail("write"))

    assert importlib.reload(capture).PINNED_CLI_VERSION == "0.147.0"


def test_output_path_is_version_restricted_and_write_flag_is_explicit(tmp_path, monkeypatch) -> None:
    root = tmp_path / "codex"
    expected = root / "0.147.0/gpt-5.6-sol-api-key-responses.json"
    assert capture.validate_fixture_path(expected, allowed_root=root) == expected.resolve()
    with pytest.raises(capture.CaptureError, match="outside"):
        capture.validate_fixture_path(root / "latest.json", allowed_root=root)

    monkeypatch.setattr(
        capture,
        "capture_live",
        lambda **kwargs: pytest.fail("capture requires explicit write flag"),
    )
    result = capture.main(
        [
            "capture",
            "--codex-binary",
            "/synthetic/codex",
            "--expected-cli-version",
            capture.PINNED_CLI_VERSION,
            "--model",
            capture.PINNED_MODEL,
            "--profile",
            capture.PINNED_PROFILE,
            "--output",
            str(FIXTURE),
        ]
    )
    assert result == 1


def test_safe_failure_classifier_never_returns_captured_text() -> None:
    category = capture.classify_codex_failure(
        b"request failed with secret-echo-canary",
        b'{"type":"error","message":"prompt-content-canary"}\n',
    )
    assert category == "loopback_request_failed"
    assert "canary" not in category


def test_catalog_and_request_helpers_do_not_call_runtime_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(capture.subprocess, "run", lambda *args, **kwargs: pytest.fail("subprocess"))
    monkeypatch.setattr(capture.socket, "socket", lambda *args, **kwargs: pytest.fail("socket"))
    safe = capture.sanitize_headers(SAFE_HEADERS)
    assert safe["authorization"]["redacted"] is True
    assert capture.canonical_json_bytes({"b": 1, "a": 2}) == b'{\n  "a": 2,\n  "b": 1\n}\n'
