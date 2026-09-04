"""Bounded Codex 0.149 -> Gateway -> fake Local two-turn verifier.

This is a local regression tool, not an OAP/reporting harness.  It retains only
fixed counters and booleans; request/response bodies and opaque identifiers are
discarded after each bounded assertion.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import hmac
import http.client
import http.server
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_PACKAGE = "@openai/codex@0.149.0"
CODEX_VERSION = "0.149.0"
CODEX_MODEL = "codex-0149-roundtrip-model"
LOCAL_SERVICE_TOKEN = "local-roundtrip-service-token"
LOCAL_SIGNING_SECRET = "local-roundtrip-signing-secret-0123456789"
LOCAL_DERIVATION_SECRET = "local-roundtrip-derivation-secret-0123456789"
GATEWAY_HMAC_SECRET = "roundtrip-gateway-hmac-secret-0123456789"
ADMIN_SECRET = "roundtrip-admin-secret-0123456789"
ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"

OBLIGATION_MANIFEST = {
    "app/codex_replay_repository": "2e5ddd592c3a3f39ffef789c442dba884444919c",
    "app/codex_0149_client": "9f773ea74f9aeb7e6ed651f34fc85466fbbd7a4d",
    "app/contracts": "b24a19901445483d18c6799b55e89fb73d1fa73f",
    "app/codex_replay_service": "c0813d120c67474785bb1ddad971dd2cd4dcdec6",
    "app/responses_gateway": "c280af6354904ebcb831f75023373b1fecfdb700",
    "app/responses_request_policy": "e2197a3184ee028f95e0a72dbe8857954cad45bd",
    "fixture/reasoning": "5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c",
    "fixture/session": "a0073a638b82750b3752ac5b78f5df91f97d7d56",
    "fixture/structural": "c182dd195312368d58c80f25c915e83e8474a470",
    "fixture/local_filter": "cdd33cb5c52377f80282803f53005074df091fc8",
    "fixture/signed_identity": "e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9",
    "replay/no_downgrade_rotation": "permanent-tests",
    "identity/stream/accounting/privacy": "permanent-tests",
    "fake_codex_two_turn": "scripts-and-unit-test",
    "historical_155_machinery": "absent",
}

_PRODUCTION_BLOBS = {
    "app/slaif_gateway/db/repositories/codex_replay.py": "2e5ddd592c3a3f39ffef789c442dba884444919c",
    "app/slaif_gateway/modules/clients/codex_0149.py": "9f773ea74f9aeb7e6ed651f34fc85466fbbd7a4d",
    "app/slaif_gateway/modules/contracts.py": "b24a19901445483d18c6799b55e89fb73d1fa73f",
    "app/slaif_gateway/services/codex_replay_service.py": "c0813d120c67474785bb1ddad971dd2cd4dcdec6",
    "app/slaif_gateway/services/responses_gateway.py": "c280af6354904ebcb831f75023373b1fecfdb700",
    "app/slaif_gateway/services/responses_request_policy.py": "e2197a3184ee028f95e0a72dbe8857954cad45bd",
}
_PERMANENT_TEST_BLOBS = {
    "tests/integration/test_codex_replay_references_postgres.py": "7810a949e00b7c89c290ba79ac246fa145d5c651",
    "tests/unit/test_codex_client_modules.py": "ba14d1e8a9953cdc885918c1fa867cf23deba630",
    "tests/unit/test_codex_replay_service.py": "29a9b11195670f933d83ffef4f23673e92801893",
    "tests/unit/test_responses_codex_multiturn_replay.py": "f91038cf946aeb097b6de91886bcd21490115e47",
    "tests/unit/test_responses_codex_streaming_tools.py": "f872fa53820687a3a6612c8131d4fddb73521757",
}
_PERMANENT_FIXTURE_BLOBS = {
    "tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json": "5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c",
    "tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json": "a0073a638b82750b3752ac5b78f5df91f97d7d56",
    "tests/fixtures/codex/0.149.0/responses-structural-v2.json": "c182dd195312368d58c80f25c915e83e8474a470",
    "tests/fixtures/local_coding/responses_tool_filter_vectors.json": "cdd33cb5c52377f80282803f53005074df091fc8",
    "tests/fixtures/local_coding/signed_identity_v1_vectors.json": "e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9",
}
_UNCHANGED_BLOBS = {
    "tests/unit/test_oap_governance.py": "8ff65fc27e89c6d432a8128619b4e53a3bcedf21",
    "AGENTIC_CLIENT_INTEGRATION.md": "7c48c679d14aa127f0c31fc3260e4a3fb01ee25f",
}
_DOCTRINE_LINKS = (
    "AGENTIC_CLIENT_INTEGRATION.md",
    "docs/module-architecture.md",
    "docs/responses-compatibility.md",
    "docs/compatibility-matrix.md",
)
_SAFE_FAILURE_COMPONENT = re.compile(r"^[a-z0-9_+.-]{1,160}$")


def missing_doctrine_links(documents: dict[str, str]) -> list[str]:
    """Return fixed missing-link classes for the four authority locations."""
    missing: list[str] = []
    if "AGENTIC_CLIENT_INTEGRATION.md" not in documents.get("AGENTS.md", ""):
        missing.append("doctrine_link:AGENTS.md")
    for path_text in _DOCTRINE_LINKS[1:]:
        if "../AGENTIC_CLIENT_INTEGRATION.md" not in documents.get(path_text, ""):
            missing.append(f"doctrine_link:{path_text}")
    return missing


def _safe_gateway_failure_code(observation: object, exception_class: str = "none") -> str:
    """Project Gateway observations into one bounded, value-free class."""
    request_count = getattr(observation, "request_count", 0)
    request_class = "one" if request_count == 1 else "two" if request_count == 2 else "other"
    statuses = getattr(observation, "response_statuses", [])
    status = statuses[-1] if statuses else 0
    status_class = "2xx" if 200 <= status < 300 else "4xx" if 400 <= status < 500 else "5xx" if 500 <= status < 600 else "other"
    codes = getattr(observation, "error_codes", [])
    code = codes[-1] if codes and codes[-1] in _GATEWAY_ERROR_CODES else "other"
    shapes = getattr(observation, "error_shapes", [])
    shape = shapes[-1] if shapes and _SAFE_FAILURE_COMPONENT.fullmatch(shapes[-1]) else "other"
    profiles = getattr(observation, "request_shapes", [])
    raw_profile = profiles[-1] if profiles else ""
    if "stream_true" not in raw_profile:
        profile = "stream_other"
    else:
        tool_class = (
            "function_custom_web_search"
            if all(token in raw_profile for token in ("function[", "custom[", "web_search["))
            else "function_custom"
            if "function[" in raw_profile and "custom[" in raw_profile
            else "function"
            if "function[" in raw_profile
            else "other"
        )
        input_class = (
            "message"
            if "_input_message" in raw_profile
            else "function_continuation"
            if "function_call,function_call_output" in raw_profile
            else "other"
        )
        profile = f"stream_true_{tool_class}_input_{input_class}"
    safe_exception = exception_class if exception_class in {"none", "AttributeError", "ValueError", "TypeError", "KeyError", "IndexError", "other"} else "other"
    return f"gateway_requests_{request_class}_status_{status_class}_error_{code}_shape_{shape}_exception_{safe_exception}_profile_{profile}"


def _git_blob_hash(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _git_ref(ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii", errors="ignore").strip()


def evaluate_obligations() -> list[str]:
    """Return only fixed missing obligation names from local repository state."""
    missing: list[str] = []
    if _git_ref("HEAD:app") != "bd536a282362cc549cc0c5518db8e743af667b63":
        missing.append("app_tree")
    for group in (_PRODUCTION_BLOBS, _PERMANENT_TEST_BLOBS, _PERMANENT_FIXTURE_BLOBS):
        for path_text, expected in group.items():
            path = REPO_ROOT / path_text
            if not path.is_file() or _git_blob_hash(path) != expected:
                missing.append(path_text)
    required_paths = (
        "scripts/verify_codex_0149_local_roundtrip.py",
        "tests/unit/test_codex_0149_local_roundtrip.py",
        "tests/unit/test_responses_codex_multiturn_replay.py",
        "tests/unit/test_responses_codex_streaming_tools.py",
        "tests/integration/test_codex_replay_references_postgres.py",
    )
    for path_text in required_paths:
        if not (REPO_ROOT / path_text).is_file():
            missing.append(path_text)
    for path_text in (
        "scripts/verify_local_coding_full_stack.py",
        "tests/unit/test_local_coding_full_stack_verifier.py",
    ):
        if (REPO_ROOT / path_text).exists():
            missing.append(f"historical_absent:{path_text}")
    app_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "app").rglob("*.py")
    )
    if "SLAIF_155X_" in app_text:
        missing.append("historical_app_qualification_symbols_absent")
    for path_text, expected in _UNCHANGED_BLOBS.items():
        path = REPO_ROOT / path_text
        if not path.is_file() or _git_blob_hash(path) != expected:
            missing.append(f"unchanged:{path_text}")
    documents = {
        path_text: (REPO_ROOT / path_text).read_text(encoding="utf-8")
        for path_text in ("AGENTS.md", *_DOCTRINE_LINKS[1:])
        if (REPO_ROOT / path_text).is_file()
    }
    missing.extend(missing_doctrine_links(documents))
    return missing


class VerificationError(RuntimeError):
    """A fixed verifier failure that never contains request-derived text."""


_CODEX_FAILURE_CATEGORIES = frozenset(
    {
        "argument_separator_rejected",
        "web_search_config_rejected",
        "configuration_rejected",
        "argument_or_configuration_rejected",
        "argument_rejected",
        "dummy_auth_environment_rejected",
        "mock_stream_closed_early",
        "mock_stream_idle_timeout",
        "mock_completed_event_rejected",
        "mock_response_failed",
        "mock_http_status_rejected",
        "loopback_request_failed",
        "app_server_channel_closed",
        "workdir_rejected",
        "custom_provider_auth_rejected",
        "mock_stream_rejected",
        "loopback_connection_failed",
        "turn_failed",
        "error_event",
        "nonzero_after_turn_completed",
        "incomplete_event_sequence",
        "unclassified",
    }
)

_GATEWAY_ERROR_CODES = frozenset(
    {
        "responses_codex_request_envelope_invalid",
        "responses_codex_client_tools_not_enabled",
        "responses_codex_client_tools_not_allowed",
        "responses_codex_client_tools_invalid",
        "responses_codex_streaming_tools_not_enabled",
        "responses_codex_streaming_tool_events_not_allowed",
        "responses_codex_envelope_not_allowed",
        "responses_codex_envelope_invalid",
        "responses_codex_limits_invalid",
        "responses_codex_client_tools_provider_authority_not_supported",
        "responses_codex_tool_roundtrip_invalid",
        "responses_codex_tool_roundtrip_too_large",
        "responses_codex_replay_reference_not_found",
        "responses_codex_replay_route_mismatch",
        "responses_route_capability_not_supported",
        "responses_route_capability_invalid",
        "responses_route_capability_missing",
        "responses_input_item_tool_not_supported",
        "responses_input_tool_item_not_supported",
        "responses_input_item_type_not_supported",
        "responses_function_call_output_invalid",
        "responses_input_invalid",
        "responses_input_item_invalid",
        "responses_input_item_role_not_supported",
        "responses_tool_type_not_supported",
        "responses_tool_invalid_shape",
        "responses_tools_not_supported",
        "responses_function_tool_streaming_not_supported",
        "incompatible_client_server_pair",
        "local_coding_identity_unavailable",
        "local_coding_endpoint_not_supported",
        "provider_configuration_error",
        "provider_request_error",
        "provider_response_invalid",
        "model_not_found",
        "model_route_disabled",
        "model_not_allowed_for_key",
        "provider_disabled",
        "provider_not_allowed_for_key",
        "route_resolution_error",
        "client_module_invalid",
        "unsupported_client_module",
        "client_module_metadata_invalid",
        "client_module_fixture_mismatch",
        "client_request_invalid",
        "unsupported_client_endpoint",
        "codex_0149_request_invalid",
        "codex_0149_field_shape",
        "codex_0149_candidate_shape",
        "codex_0149_authority_shape",
        "codex_0149_tool_declaration",
        "responses_custom_tool_streaming_not_supported",
        "responses_function_tool_capability_not_supported",
        "responses_function_tool_streaming_not_supported",
        "responses_custom_tool_capability_not_supported",
        "responses_custom_tool_format_not_supported",
        "responses_adapter_managed_tool_invalid",
        "responses_tool_choice_invalid",
        "responses_tool_count_exceeded",
        "responses_tool_invalid_shape",
        "responses_tool_type_not_supported",
        "responses_tools_not_supported",
        "responses_field_invalid_type",
        "responses_field_not_supported",
        "responses_stream_event_not_supported",
        "responses_streaming_usage_missing_estimated",
        "responses_codex_client_tools_too_large",
        "responses_codex_client_tools_property_count_exceeded",
        "responses_codex_client_tools_schema_too_deep",
        "responses_codex_encrypted_reasoning_replay_not_allowed",
        "upstream_payload_not_approved",
        "validation_error",
        "400",
        "invalid_request_error",
    }
)


def _safe_type_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "other"


def _safe_size_class(value: object) -> str:
    if not isinstance(value, str):
        return "not_string"
    size = len(value.encode("utf-8"))
    return "empty" if size == 0 else "bounded" if size <= 4096 else "oversized"


def _safe_codex_failure_category(stderr: bytes, stdout: bytes) -> str:
    import scripts.capture_codex_protocol as capture

    category = capture.classify_codex_failure(stderr, stdout)
    if category != "unclassified":
        return category if category in _CODEX_FAILURE_CATEGORIES else "unclassified"
    lowered = stdout[:512_000].lower()
    safe_patterns = (
        (b"model not found", "model_unavailable"),
        (b"no such model", "model_unavailable"),
        (b"unknown model", "model_unavailable"),
        (b"api key", "api_key_rejected"),
        (b"authentication", "authentication_rejected"),
        (b"provider", "provider_configuration_rejected"),
        (b"sandbox", "sandbox_rejected"),
    )
    for marker, value in safe_patterns:
        if marker in lowered:
            return value
    return "unclassified"


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("process_launch_failed") from exc


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _install_codex(root: Path) -> Path:
    install = root / "codex-install"
    install.mkdir(mode=0o700)
    if _run(["npm", "init", "-y"], cwd=install, timeout=30).returncode != 0:
        raise VerificationError("codex_install_failed")
    if _run(
        ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", CODEX_PACKAGE],
        cwd=install,
        timeout=180,
    ).returncode != 0:
        raise VerificationError("codex_install_failed")
    binary = install / "node_modules/.bin/codex"
    version = _run([str(binary), "--version"], timeout=10)
    if version.returncode != 0 or version.stdout != b"codex-cli 0.149.0\n":
        raise VerificationError("codex_version_mismatch")
    return binary


def _codex_command(binary: Path, *, workdir: Path, port: int, catalog: Path, output: Path) -> list[str]:
    """Return the exact zero-retry command shape used by the pinned client."""
    base_url = f'"http://127.0.0.1:{port}/v1"'
    return [
        str(binary),
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "--json",
        "--strict-config",
        "--ephemeral",
        "--ignore-user-config",
        "-C",
        str(workdir),
        "-m",
        CODEX_MODEL,
        "-c",
        'model_provider="slaif-roundtrip"',
        "-c",
        (
            "model_providers.slaif-roundtrip={"
            f'name="Local roundtrip",base_url={base_url},'
            'env_key="SLAIF_CODEX_ROUNDTRIP_API_KEY",wire_api="responses"}'
        ),
        "-c",
        f"model_catalog_json={json.dumps(str(catalog))}",
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        "model_providers.slaif-roundtrip.request_max_retries=0",
        "-c",
        "model_providers.slaif-roundtrip.stream_max_retries=0",
        "-o",
        str(output),
        "Use one local shell command to read SYNTHETIC_TASK.md, then report completion.",
    ]


def _write_roundtrip_model_catalog(
    binary: Path,
    destination: Path,
    *,
    environment: dict[str, str],
) -> None:
    """Use the repository's already-qualified disposable catalog helper."""
    import scripts.capture_codex_protocol as capture

    capture._write_0149_model_catalog(
        binary,
        destination,
        environment=environment,
        model=CODEX_MODEL,
    )


def _sse(event: dict[str, object]) -> bytes:
    return ("data: " + json.dumps(event, separators=(",", ":")) + "\n\n").encode()


def _usage(input_tokens: int = 2, output_tokens: int = 2) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": 0,
            "input_tokens_per_turn": [input_tokens],
            "cached_tokens_per_turn": [0],
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {
            "reasoning_tokens": 0,
            "tool_output_tokens": 0,
            "output_tokens_per_turn": [output_tokens],
            "tool_output_tokens_per_turn": [0],
        },
        "total_tokens": input_tokens + output_tokens,
    }


def _function_stream(arguments: str, tool_name: str) -> tuple[dict[str, object], ...]:
    response_id = "response_roundtrip_function"
    item_id = "function1"
    return (
        {"type": "response.created", "sequence_number": 0, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.in_progress", "sequence_number": 1, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.output_item.added", "output_index": 0, "sequence_number": 2, "item": {"type": "function_call", "id": item_id, "status": "in_progress", "namespace": None, "name": tool_name, "arguments": "", "call_id": "call_roundtrip", "caller": None}},
        {"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": 0, "sequence_number": 3, "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": 0, "sequence_number": 4, "name": tool_name, "arguments": arguments},
        {"type": "response.output_item.done", "output_index": 0, "sequence_number": 5, "item": {"type": "function_call", "id": item_id, "status": "completed", "namespace": None, "name": tool_name, "arguments": arguments, "call_id": "call_roundtrip", "caller": None}},
        {"type": "response.completed", "sequence_number": 6, "response": {"id": response_id, "status": "completed", "model": CODEX_MODEL, "output": [{"type": "function_call", "id": "parser_function", "status": "completed", "namespace": None, "name": tool_name, "arguments": arguments, "call_id": "parser_call"}], "usage": _usage()}},
    )


def _message_stream() -> tuple[dict[str, object], ...]:
    response_id = "response_roundtrip_message"
    item_id = "message_roundtrip"
    return (
        {"type": "response.created", "sequence_number": 0, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.in_progress", "sequence_number": 1, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.output_item.added", "output_index": 0, "sequence_number": 2, "item": {"type": "message", "id": item_id, "status": "in_progress", "role": "assistant", "content": [], "phase": None}},
        {"type": "response.content_part.added", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 3, "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []}},
        {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 4, "delta": "done", "logprobs": []},
        {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 5, "text": "done", "logprobs": []},
        {"type": "response.content_part.done", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 6, "part": {"type": "output_text", "text": "done", "annotations": [], "logprobs": None}},
        {"type": "response.output_item.done", "output_index": 0, "sequence_number": 7, "item": {"type": "message", "id": item_id, "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": "done", "annotations": [], "logprobs": None}], "phase": None, "summary": []}},
        {"type": "response.completed", "sequence_number": 8, "response": {"id": response_id, "status": "completed", "model": CODEX_MODEL, "output": [{"type": "message", "id": "parser_message", "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": "done", "annotations": [], "logprobs": None}], "phase": None}], "usage": _usage()}},
    )


def _tool_name(payload: dict[str, object]) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if isinstance(tool, dict) and tool.get("type") == "function" and tool.get("name") in {"shell_command", "exec_command"}:
            return str(tool["name"])
    raise VerificationError("known_local_tool_missing")


def _tool_arguments(payload: dict[str, object], name: str) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function" or tool.get("name") != name:
            continue
        parameters = tool.get("parameters")
        if not isinstance(parameters, dict):
            return "{}"
        properties = parameters.get("properties")
        required = parameters.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            return "{}"
        values: dict[str, object] = {}
        for field in required[:8]:
            schema = properties.get(field)
            schema_type = schema.get("type") if isinstance(schema, dict) else None
            values[str(field)] = "cat SYNTHETIC_TASK.md" if schema_type == "string" else 1 if schema_type == "integer" else False if schema_type == "boolean" else [] if schema_type == "array" else {}
        return json.dumps(values, separators=(",", ":"))
    raise VerificationError("known_local_tool_missing")


class _FakeLocalState:
    def __init__(self, *, service_token: str, signing_secret: bytes) -> None:
        self.service_token = service_token
        self.signing_secret = signing_secret
        self.request_count = 0
        self.signed_request_count = 0
        self.second_id_absent = False
        self.second_adjacent_output = False
        self.second_call_id_present = False
        self.normal_close_count = 0
        self.terminal_count = 0
        self.function_count = 0
        self.message_count = 0
        self.hosted_authority_absent = False
        self._lock = threading.Lock()

    def observe(self, body: bytes, headers: http.client.HTTPMessage, path: str) -> tuple[dict[str, object], ...]:
        if headers.get("authorization") != f"Bearer {self.service_token}" or path != "/v1/responses":
            raise VerificationError("local_auth_or_path_failed")
        required = {"x-slaif-identity-version", "x-slaif-principal", "x-slaif-session", "x-slaif-repository", "x-slaif-route", "x-slaif-timestamp", "x-slaif-nonce", "x-slaif-signature"}
        names = {name.lower() for name in headers}
        if not required.issubset(names):
            raise VerificationError("signed_headers_missing")
        identity = {
            "principal": headers["x-slaif-principal"],
            "session": headers["x-slaif-session"],
            "repository": headers["x-slaif-repository"],
            "route": headers["x-slaif-route"],
        }
        from slaif_gateway.modules.servers.local_coding.identity import LocalCodingRequestIdentity, canonical_identity_bytes, expected_signature
        from slaif_gateway.modules.servers.local_coding.contract import parse_local_coding_route_contract
        route = parse_local_coding_route_contract({"local_coding": {"contract_version": "local-coding-v1", "route_name": "vision", "tool_policy_version": "responses-tool-policy-v1", "identity_mode": "signed_identity_v1", "replay_mode": "process_local_ttl_lru", "deployment_mode": "single_worker"}})
        if route is None:
            raise VerificationError("local_route_contract_invalid")
        local_identity = LocalCodingRequestIdentity(**identity, identity_mode="signed_identity_v1")
        canonical = canonical_identity_bytes(method="POST", path=path, raw_query=b"", body=body, identity=local_identity, timestamp=headers["x-slaif-timestamp"], nonce=headers["x-slaif-nonce"])
        if not hmac.compare_digest(headers["x-slaif-signature"], expected_signature(secret=self.signing_secret, canonical=canonical)):
            raise VerificationError("signed_body_mismatch")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise VerificationError("local_body_invalid")
        with self._lock:
            self.request_count += 1
            ordinal = self.request_count
            self.signed_request_count += 1
        if ordinal == 1:
            tools = payload.get("tools")
            self.hosted_authority_absent = isinstance(tools, list) and all(
                isinstance(tool, dict)
                and tool.get("type") in {"function", "custom"}
                for tool in tools
            )
            tool_name = _tool_name(payload)
            arguments = _tool_arguments(payload, tool_name)
            self.function_count += 1
            del payload
            return _function_stream(arguments, tool_name)
        if ordinal == 2:
            items = payload.get("input")
            if not isinstance(items, list):
                raise VerificationError("second_input_not_array")
            calls = [item for item in items if isinstance(item, dict) and item.get("type") == "function_call"]
            outputs = [item for item in items if isinstance(item, dict) and item.get("type") == "function_call_output"]
            self.second_id_absent = len(calls) == 1 and "id" not in calls[0]
            self.second_call_id_present = len(calls) == 1 and isinstance(calls[0].get("call_id"), str)
            self.second_adjacent_output = len(calls) == 1 and len(outputs) == 1 and items.index(calls[0]) + 1 == items.index(outputs[0]) and calls[0].get("call_id") == outputs[0].get("call_id")
            if not (self.second_id_absent and self.second_call_id_present and self.second_adjacent_output):
                raise VerificationError("idless_call_continuation_invalid")
            self.message_count += 1
            del payload
            return _message_stream()
        del payload
        raise VerificationError("unexpected_local_request_count")

    def mark_terminal(self) -> None:
        with self._lock:
            self.terminal_count += 1
            self.normal_close_count += 1


class _FakeLocalHandler(http.server.BaseHTTPRequestHandler):
    server: "_FakeLocalServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 4 * 1024 * 1024:
                raise VerificationError("local_body_size_invalid")
            body = self.rfile.read(length)
            events = self.server.state.observe(body, self.headers, self.path)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.end_headers()
            for event in events:
                self.wfile.write(_sse(event))
                self.wfile.flush()
            self.server.state.mark_terminal()
        except VerificationError:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"roundtrip_failed"}}')


class _FakeLocalServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state: _FakeLocalState) -> None:
        super().__init__(("127.0.0.1", 0), _FakeLocalHandler)
        self.state = state


class _GatewayObservation:
    """Record only bounded Responses status/error classes around the app."""

    def __init__(self, app) -> None:
        self.app = app
        self.request_count = 0
        self.response_statuses: list[int] = []
        self.error_codes: list[str] = []
        self.error_shapes: list[str] = []
        self.request_shapes: list[str] = []
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send) -> None:
        is_responses = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v1/responses"
        )
        if is_responses:
            with self._lock:
                self.request_count += 1
        request_body = bytearray()

        async def observed_receive():
            message = await receive()
            if (
                is_responses
                and message.get("type") == "http.request"
                and len(request_body) <= 65_536
            ):
                request_body.extend(message.get("body", b"")[:65_536])
                if not message.get("more_body", False):
                    self._record_request_shape(bytes(request_body))
            return message
        status: int | None = None
        body = bytearray()

        async def observed_send(message) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 0))
            elif (
                is_responses
                and status is not None
                and status >= 400
                and len(body) <= 16_384
            ):
                body.extend(message.get("body", b"")[:16_384])
            await send(message)

        await self.app(scope, observed_receive, observed_send)
        if is_responses and status is not None:
            code = "none"
            shape = "none"
            if status >= 400:
                try:
                    decoded = json.loads(bytes(body))
                    error = decoded.get("error")
                    raw_code = error.get("code") if isinstance(error, dict) else None
                    if raw_code in _GATEWAY_ERROR_CODES:
                        code = raw_code
                    elif isinstance(raw_code, str):
                        code = "other"
                    if isinstance(error, dict):
                        shape = "error"
                        raw_type = error.get("type")
                        if raw_type == "invalid_request_error":
                            shape = "error_invalid_request"
                        elif raw_type == "authentication_error":
                            shape = "error_authentication"
                        elif raw_type == "server_error":
                            shape = "error_server"
                        param = error.get("param")
                        if isinstance(param, str):
                            root = param.split(".", 1)[0].split("[", 1)[0]
                            if root in {"input", "tools", "stream", "model", "tool_choice"}:
                                shape = f"{shape}_{root}"
                                leaf = param.rsplit(".", 1)[-1]
                                if leaf in {
                                    "type",
                                    "name",
                                    "description",
                                    "parameters",
                                    "format",
                                    "external_web_access",
                                    "search_content_types",
                                }:
                                    shape = f"{shape}_{leaf}"
                                elif root == "tools":
                                    shape = f"{shape}_other_leaf"
                            else:
                                shape = f"{shape}_other_param"
                    elif "detail" in decoded:
                        shape = "detail"
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
                    code = "other"
                    shape = "malformed"
            with self._lock:
                self.response_statuses.append(status)
                self.error_codes.append(code)
                self.error_shapes.append(shape)

    def _record_request_shape(self, body: bytes) -> None:
        try:
            decoded = json.loads(body)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            shape = "malformed"
        else:
            if not isinstance(decoded, dict):
                shape = "non_object"
            else:
                tools = decoded.get("tools")
                tool_classes: list[str] = []
                if isinstance(tools, list):
                    for tool in tools:
                        if not isinstance(tool, dict):
                            tool_classes.append("other")
                        elif tool.get("type") in {"function", "custom", "web_search"}:
                            field_names = set(tool) & {
                                "type",
                                "name",
                                "description",
                                "parameters",
                                "strict",
                                "format",
                                "external_web_access",
                                "search_content_types",
                                "execution",
                            }
                            nested_class = "none"
                            if isinstance(tool.get("format"), dict):
                                nested_type = tool["format"].get("type")
                                nested_class = (
                                    nested_type
                                    if nested_type in {"text", "grammar"}
                                    else "other"
                                )
                            tool_classes.append(
                                f"{tool['type']}[{','.join(sorted(field_names))}]"
                                f"_format_{nested_class}"
                                f"_description_{_safe_type_class(tool.get('description'))}"
                                f"_{_safe_size_class(tool.get('description'))}"
                            )
                        else:
                            tool_classes.append("other")
                items = decoded.get("input")
                item_classes: list[str] = []
                if isinstance(items, list):
                    for item in items:
                        value = item.get("type") if isinstance(item, dict) else None
                        item_classes.append(
                            value
                            if value
                            in {"function_call", "function_call_output", "message", "reasoning"}
                            else "other"
                        )
                shape = (
                    f"stream_{'true' if decoded.get('stream') is True else 'other'}"
                    f"_tools_{','.join(tool_classes) or 'none'}"
                    f"_input_{','.join(item_classes) or 'none'}"
                )
        with self._lock:
            self.request_shapes.append(shape)


class _GatewayExceptionObservation(logging.Handler):
    """Retain only exception class names from the in-process server logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.exception_classes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info is None:
            return
        name = record.exc_info[0].__name__
        if name in {"TypeError", "KeyError", "ValueError", "IndexError", "AttributeError"}:
            self.exception_classes.append(name)
        else:
            self.exception_classes.append("other")

@contextlib.contextmanager
def _temporary_environment(values: dict[str, str]) -> Iterator[None]:
    old = os.environ.copy()
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


async def _accounting_counts(database_url: str, key_id: object) -> dict[str, int]:
    from slaif_gateway.db.models import QuotaReservation, UsageLedger
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            reservations = await session.execute(
                select(QuotaReservation.status, func.count()).where(QuotaReservation.gateway_key_id == key_id).group_by(QuotaReservation.status)
            )
            ledgers = await session.execute(
                select(UsageLedger.accounting_status, func.count()).where(UsageLedger.gateway_key_id == key_id).group_by(UsageLedger.accounting_status)
            )
            result = {"reservation_finalized": 0, "reservation_pending": 0, "ledger_finalized": 0, "ledger_pending": 0}
            for status, count in reservations:
                result[f"reservation_{status}"] = int(count)
            for status, count in ledgers:
                result[f"ledger_{status}"] = int(count)
            return result
    finally:
        await engine.dispose()


def _database() -> tuple[str, bool, str | None]:
    provided = os.environ.get("TEST_DATABASE_URL")
    if provided:
        return provided, False, None
    name = f"slaif_gateway_160_roundtrip_test_{os.getpid()}"
    result = _run(["bash", "scripts/create-test-db.sh"], cwd=REPO_ROOT, env={**os.environ, "TEST_DB_NAME": name}, timeout=30)
    if result.returncode != 0:
        raise VerificationError("postgres_setup_failed")
    return f"postgresql+asyncpg://slaif:slaif@localhost:5432/{name}", True, name


def run_roundtrip() -> str:
    from tests.e2e.test_openai_python_client_responses import _create_responses_test_data
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_CLIENT_MODULE_VERSION, CODEX_0149_FIXTURE_SHA256
    from tests.e2e.test_openai_python_client_chat import _run_uvicorn_server
    import scripts.capture_codex_protocol as capture

    db_url, own_db, db_name = _database()
    with tempfile.TemporaryDirectory(prefix="slaif-codex0149-roundtrip-") as temporary:
        root = Path(temporary)
        home = root / "codex-home"
        work = root / "workspace"
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        (work / "SYNTHETIC_TASK.md").write_text("bounded task\n", encoding="utf-8")
        state = _FakeLocalState(service_token=LOCAL_SERVICE_TOKEN, signing_secret=LOCAL_SIGNING_SECRET.encode())
        fake = _FakeLocalServer(state)
        thread = threading.Thread(target=fake.serve_forever, daemon=True)
        fake_port = fake.server_address[1]
        gateway_port = _free_port()
        values = {
            "DATABASE_URL": db_url,
            "APP_ENV": "test",
            "GATEWAY_KEY_PREFIX": "sk-slaif-",
            "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
            "ACTIVE_HMAC_KEY_VERSION": "1",
            "TOKEN_HMAC_SECRET_V1": GATEWAY_HMAC_SECRET,
            "ADMIN_SESSION_SECRET": ADMIN_SECRET,
            "ONE_TIME_SECRET_ENCRYPTION_KEY": ONE_TIME_SECRET_KEY,
            "LOCAL_CODING_SERVICE_TOKEN": LOCAL_SERVICE_TOKEN,
            "LOCAL_CODING_SIGNING_SECRET_V1": LOCAL_SIGNING_SECRET,
            "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1": LOCAL_DERIVATION_SECRET,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(REPO_ROOT / "app"),
        }
        try:
            with _temporary_environment(values):
                get_settings.cache_clear()
                migration = _run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=REPO_ROOT,
                    env=values,
                    timeout=120,
                )
                if migration.returncode != 0:
                    raise VerificationError("migration_failed")
                del migration
                thread.start()
                created = asyncio.run(
                    _create_responses_test_data(
                        db_url,
                        provider="local-coding",
                        model=CODEX_MODEL,
                        upstream_model=CODEX_MODEL,
                        base_url=f"http://127.0.0.1:{fake_port}/v1",
                        api_key_env_var="LOCAL_CODING_SERVICE_TOKEN",
                        streaming=True,
                        local_coding_contract={"contract_version": "local-coding-v1", "route_name": "vision", "tool_policy_version": "responses-tool-policy-v1", "identity_mode": "signed_identity_v1", "replay_mode": "process_local_ttl_lru", "deployment_mode": "single_worker"},
                        responses_policy={"version": 1, "local_coding_repository_scope": "roundtrip-repository", "allowed_capabilities": ["codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events"], "client_module": {"id": "codex-0.149-responses-v1", "version": CODEX_0149_CLIENT_MODULE_VERSION, "fixture_sha256": CODEX_0149_FIXTURE_SHA256}},
                        codex_request_envelope=True,
                        codex_client_tools=True,
                        codex_streaming_tool_events=True,
                        function_tools=True,
                        custom_tools=True,
                        image_input=True,
                    )
                )
                gateway_observation = _GatewayObservation(create_app(get_settings()))
                binary = _install_codex(root)
                catalog = root / "model-catalog.json"
                capture_environment = capture._isolated_environment(home)
                capture_environment[capture.CAPTURE_API_KEY_ENV] = created.plaintext_key
                capture_environment["SLAIF_CODEX_ROUNDTRIP_API_KEY"] = created.plaintext_key
                _write_roundtrip_model_catalog(
                    binary,
                    catalog,
                    environment=capture_environment,
                )
                command = capture._exec_command_0149(
                    binary,
                    workdir=work,
                    port=gateway_port,
                    model=CODEX_MODEL,
                    model_catalog=catalog,
                    output_path=root / "codex-output.json",
                    instruction="Use one local shell command to read SYNTHETIC_TASK.md, then report completion.",
                )
                capture_environment["DATABASE_URL"] = db_url
                capture_environment["APP_ENV"] = "test"
                gateway_errors = _GatewayExceptionObservation()
                logging.getLogger().addHandler(gateway_errors)
                try:
                    with _run_uvicorn_server(gateway_observation, gateway_port):
                        result = _run(command, cwd=work, env=capture_environment, timeout=180)
                finally:
                    logging.getLogger().removeHandler(gateway_errors)
                stdout, stderr = result.stdout, result.stderr
                if result.returncode != 0:
                    category = _safe_codex_failure_category(stderr, stdout)
                    del stdout, stderr
                    if gateway_observation.request_count and not state.request_count:
                        exception_class = (
                            gateway_errors.exception_classes[-1]
                            if gateway_errors.exception_classes
                            else "none"
                        )
                        raise VerificationError(
                            _safe_gateway_failure_code(
                                gateway_observation,
                                exception_class,
                            )
                        )
                    raise VerificationError(
                        f"codex_no_gateway_request_{category}"
                        if state.request_count == 0
                        else f"codex_first_turn_only_{category}"
                        if state.request_count == 1
                        else f"codex_second_turn_failed_{category}"
                    )
                del stdout, stderr
                counts = asyncio.run(_accounting_counts(db_url, created.gateway_key_id))
                if state.request_count != 2 or state.signed_request_count != 2:
                    raise VerificationError("two_gateway_local_turns_missing")
                if not (state.second_id_absent and state.second_call_id_present and state.second_adjacent_output):
                    raise VerificationError("idless_call_continuation_invalid")
                if state.function_count != 1 or state.message_count != 1 or state.terminal_count != 2:
                    raise VerificationError("stream_lifecycle_counts_invalid")
                if counts.get("reservation_finalized") != 2 or counts.get("ledger_finalized") != 2 or counts.get("reservation_pending", 0) or counts.get("ledger_pending", 0):
                    raise VerificationError("accounting_predicate_failed")
                return "VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2"
        finally:
            fake.shutdown()
            fake.server_close()
            thread.join(timeout=5)
            if own_db and db_name:
                _run(["sudo", "-n", "-u", "postgres", "dropdb", "--if-exists", db_name], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(run_roundtrip())
        return 0
    except VerificationError as exc:
        print(f"VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_FAILED code={exc.args[0]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
