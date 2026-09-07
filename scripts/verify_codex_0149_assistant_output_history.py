"""Prove the Codex 0.149 assistant-output history rejection before correction.

The verifier uses a task-local Codex CLI, the unchanged Gateway application,
an in-process signed fake Local service, and a fake downstream stream.  It
retains only fixed structural facts.  Request bodies, text, images, IDs,
headers, credentials, paths, and arbitrary subprocess output are discarded.
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
from collections.abc import Iterator, Mapping
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_PACKAGE = "@openai/codex@0.149.0"
CODEX_MODEL = "codex-0149-assistant-history-model"
LOCAL_SERVICE_TOKEN = "synthetic-local-history-service-token-161-a"
LOCAL_SIGNING_SECRET = "synthetic-local-history-signing-secret-161-a"
LOCAL_DERIVATION_SECRET = "synthetic-local-history-derivation-secret-161-a"
GATEWAY_HMAC_SECRET = "synthetic-local-history-gateway-hmac-secret-161-a"
ADMIN_SECRET = "synthetic-local-history-admin-secret-161-a"
ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
MAX_CAPTURE_BODY_BYTES = 1_048_576
MAX_CAPTURE_ERROR_BYTES = 16_384
MAX_HISTORY_TEXT_BYTES = 65_536

_ALLOWED_ERROR_CODE = "responses_input_content_part_not_supported"
_SAFE_ERROR_CODES = frozenset({_ALLOWED_ERROR_CODE})
_SAFE_DIAGNOSTIC_GATEWAY_CODES = frozenset(
    {
        "responses_input_content_part_not_supported",
        "responses_input_multimodal_not_supported",
        "responses_input_image_part_invalid",
        "responses_input_image_url_invalid",
        "responses_input_image_mime_not_supported",
        "responses_input_item_invalid",
        "responses_input_invalid",
        "responses_codex_envelope_not_allowed",
        "responses_codex_client_tools_not_allowed",
        "responses_codex_streaming_tool_events_not_allowed",
        "responses_stream_event_not_supported",
        "responses_streaming_usage_missing_estimated",
        "responses_route_capability_not_supported",
        "responses_route_capability_missing",
        "responses_codex_tool_roundtrip_invalid",
        "incompatible_client_server_pair",
        "provider_response_invalid",
        "route_resolution_error",
    }
)
_SAFE_CODEX_FAILURES = frozenset(
    {
        "argument_separator_rejected",
        "configuration_rejected",
        "mock_http_status_rejected",
        "loopback_request_failed",
        "loopback_connection_failed",
        "mock_stream_rejected",
        "mock_response_failed",
        "turn_failed",
        "error_event",
        "nonzero_after_turn_completed",
        "incomplete_event_sequence",
        "unclassified",
    }
)


class VerificationError(RuntimeError):
    """A fixed verifier failure; its argument never contains request data."""


def _type_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _size_class(value: object) -> str:
    if not isinstance(value, str):
        return "not_string"
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return "invalid_unicode"
    return "empty" if size == 0 else "bounded" if size <= MAX_HISTORY_TEXT_BYTES else "oversized"


def _fixed_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_ERROR_CODES else "other"


def _safe_diagnostic_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_DIAGNOSTIC_GATEWAY_CODES else "other"


def _fixed_param_class(value: object) -> str:
    if not isinstance(value, str):
        return "other"
    if value == "input[5].content[0].type":
        return "input_5_content_0_type"
    match = re.fullmatch(r"input\[([0-9]{1,4})\]\.content\[([0-9]{1,4})\]\.type", value)
    if match is not None:
        input_index = int(match.group(1))
        content_index = int(match.group(2))
        if input_index <= 32 and content_index <= 32:
            return f"input_index_{input_index}_content_index_{content_index}_type"
        return "input_index_or_content_index_other"
    return "other"


def _codex_failure_category(stderr: bytes, stdout: bytes) -> str:
    from scripts.capture_codex_protocol import classify_codex_failure

    value = classify_codex_failure(stderr, stdout)
    return value if value in _SAFE_CODEX_FAILURES else "other"


def _safe_progress_class(value: int) -> str:
    return "zero" if value == 0 else "one" if value == 1 else "two" if value == 2 else "other"


def _safe_status_class(value: int | None) -> str:
    if value is None:
        return "none"
    return "2xx" if 200 <= value < 300 else "4xx" if 400 <= value < 500 else "5xx" if 500 <= value < 600 else "other"


def _safe_failure_progress(observation: GatewayObservation, local: _LocalServer) -> str:
    status = observation.response_statuses[-1] if observation.response_statuses else None
    error_code = _safe_diagnostic_error_code(observation.error_codes[-1] if observation.error_codes else None)
    param_class = observation.param_classes[-1] if observation.param_classes else "other"
    return (
        f"gateway_{_safe_progress_class(observation.request_count)}"
        f"_status_{_safe_status_class(status)}"
        f"_error_{error_code}"
        f"_param_{param_class}"
        f"_local_{_safe_progress_class(local.state.request_count)}"
    )


def _safe_status_sequence(observation: GatewayObservation) -> str:
    statuses = observation.response_statuses[:4]
    return "_".join(_safe_status_class(status) for status in statuses) or "none"


def _safe_history_projection(body: object) -> dict[str, object]:
    """Project one request into fixed facts without retaining text or IDs."""

    projection: dict[str, object] = {
        "body_object": isinstance(body, Mapping),
        "assistant_history_count": 0,
        "assistant_history_present": False,
        "assistant_role_exact": False,
        "assistant_output_text_count": 0,
        "assistant_output_text_type_exact": False,
        "assistant_output_text_nonempty_unicode": False,
        "assistant_output_text_size_class": "not_string",
        "image_part_count_class": "zero",
        "raw_value_retained": False,
    }
    if not isinstance(body, Mapping):
        return projection
    input_items = body.get("input")
    if not isinstance(input_items, list):
        return projection
    image_count = 0
    for item in input_items:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "input_image":
            image_count += 1
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "input_image":
                image_count += 1
        if item.get("role") != "assistant":
            continue
        projection["assistant_history_count"] = int(projection["assistant_history_count"]) + 1
        projection["assistant_history_present"] = True
        projection["assistant_role_exact"] = True
        for part in content:
            if not isinstance(part, Mapping) or part.get("type") != "output_text":
                continue
            projection["assistant_output_text_count"] = int(
                projection["assistant_output_text_count"]
            ) + 1
            projection["assistant_output_text_type_exact"] = part.get("type") == "output_text"
            text = part.get("text")
            if not isinstance(text, str):
                continue
            projection["assistant_output_text_size_class"] = _size_class(text)
            try:
                encoded_size = len(text.encode("utf-8"))
            except UnicodeEncodeError:
                continue
            projection["assistant_output_text_nonempty_unicode"] = (
                encoded_size > 0 and encoded_size <= MAX_HISTORY_TEXT_BYTES
            )
    projection["image_part_count_class"] = (
        "zero" if image_count == 0 else "one" if image_count == 1 else "many"
    )
    return projection


def _safe_error_projection(body: bytes) -> dict[str, str | bool]:
    """Parse only the closed error code/parameter classes."""

    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return {"json_object": False, "error_code": "other", "param_class": "other"}
    error = decoded.get("error") if isinstance(decoded, Mapping) else None
    if not isinstance(error, Mapping):
        return {"json_object": isinstance(decoded, Mapping), "error_code": "other", "param_class": "other"}
    return {
        "json_object": True,
        "error_code": _fixed_error_code(error.get("code")),
        "param_class": _fixed_param_class(error.get("param")),
    }


class GatewayObservation:
    """ASGI observer retaining only bounded request/response predicates."""

    def __init__(self, app) -> None:
        self.app = app
        self.request_count = 0
        self.response_statuses: list[int] = []
        self.error_codes: list[str] = []
        self.param_classes: list[str] = []
        self.image_count_classes: list[str] = []
        self.second_projection: dict[str, object] | None = None
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send) -> None:
        is_responses = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v1/responses"
        )
        ordinal = 0
        if is_responses:
            with self._lock:
                self.request_count += 1
                ordinal = self.request_count
        request_body = bytearray()
        request_overflow = False

        async def observed_receive():
            nonlocal request_overflow
            message = await receive()
            if is_responses and message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes) and len(request_body) + len(chunk) <= MAX_CAPTURE_BODY_BYTES:
                    request_body.extend(chunk)
                else:
                    request_overflow = True
                if not message.get("more_body", False):
                    if not request_overflow:
                        try:
                            decoded = json.loads(bytes(request_body))
                        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                            decoded = None
                        candidate_projection = _safe_history_projection(decoded)
                        self.image_count_classes.append(str(candidate_projection["image_part_count_class"]))
                        if ordinal > 1 and candidate_projection["assistant_history_present"] is True:
                            self.second_projection = candidate_projection
                    request_body.clear()
            return message

        status: int | None = None
        response_body = bytearray()
        response_overflow = False

        async def observed_send(message) -> None:
            nonlocal status, response_overflow
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 0))
            elif is_responses and status is not None and status >= 400:
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes) and len(response_body) + len(chunk) <= MAX_CAPTURE_ERROR_BYTES:
                    response_body.extend(chunk)
                else:
                    response_overflow = True
            await send(message)

        await self.app(scope, observed_receive, observed_send)
        if is_responses and status is not None:
            parsed = (
                _safe_error_projection(bytes(response_body))
                if status >= 400 and not response_overflow
                else {"error_code": "other", "param_class": "other"}
            )
            with self._lock:
                self.response_statuses.append(status)
                self.error_codes.append(str(parsed["error_code"]))
                self.param_classes.append(str(parsed["param_class"]))
            response_body.clear()


def _sse(event: Mapping[str, object]) -> bytes:
    return ("data: " + json.dumps(event, separators=(",", ":")) + "\n\n").encode()


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 2,
        "input_tokens_details": {
            "cached_tokens": 0,
            "input_tokens_per_turn": [2],
            "cached_tokens_per_turn": [0],
        },
        "output_tokens": 2,
        "output_tokens_details": {
            "reasoning_tokens": 0,
            "tool_output_tokens": 0,
            "output_tokens_per_turn": [2],
            "tool_output_tokens_per_turn": [0],
        },
        "total_tokens": 4,
    }


def _tool_name(payload: Mapping[str, object]) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if (
            isinstance(tool, Mapping)
            and tool.get("type") == "function"
            and tool.get("name") in {"shell_command", "exec_command"}
        ):
            return str(tool["name"])
    raise VerificationError("known_local_tool_missing")


def _tool_arguments(payload: Mapping[str, object], name: str) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if not isinstance(tool, Mapping) or tool.get("type") != "function" or tool.get("name") != name:
            continue
        parameters = tool.get("parameters")
        if not isinstance(parameters, Mapping):
            return "{}"
        properties = parameters.get("properties")
        required = parameters.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            return "{}"
        values: dict[str, object] = {}
        for field in required[:8]:
            schema = properties.get(field)
            schema_type = schema.get("type") if isinstance(schema, Mapping) else None
            values[str(field)] = (
                "cat SYNTHETIC_TASK.md"
                if schema_type == "string"
                else 1
                if schema_type == "integer"
                else False
                if schema_type == "boolean"
                else []
                if schema_type == "array"
                else {}
            )
        return json.dumps(values, separators=(",", ":"))
    raise VerificationError("known_local_tool_missing")


def _function_stream(arguments: str, tool_name: str) -> tuple[dict[str, object], ...]:
    response_id = "response_history_function"
    item_id = "function_history_first"
    call_id = "call_history_first"
    return (
        {"type": "response.created", "sequence_number": 0, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.in_progress", "sequence_number": 1, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.output_item.added", "output_index": 0, "sequence_number": 2, "item": {"type": "function_call", "id": item_id, "status": "in_progress", "namespace": None, "name": tool_name, "arguments": "", "call_id": call_id, "caller": None}},
        {"type": "response.function_call_arguments.delta", "item_id": item_id, "output_index": 0, "sequence_number": 3, "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": item_id, "output_index": 0, "sequence_number": 4, "name": tool_name, "arguments": arguments},
        {"type": "response.output_item.done", "output_index": 0, "sequence_number": 5, "item": {"type": "function_call", "id": item_id, "status": "completed", "namespace": None, "name": tool_name, "arguments": arguments, "call_id": call_id, "caller": None}},
        {"type": "response.completed", "sequence_number": 6, "response": {"id": response_id, "status": "completed", "model": CODEX_MODEL, "output": [{"type": "function_call", "id": "parser_function", "status": "completed", "namespace": None, "name": tool_name, "arguments": arguments, "call_id": "parser_call"}], "usage": _usage()}},
    )


def _message_stream() -> tuple[dict[str, object], ...]:
    response_id = "response_history_first"
    item_id = "message_history_first"
    return (
        {"type": "response.created", "sequence_number": 0, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.in_progress", "sequence_number": 1, "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL}},
        {"type": "response.output_item.added", "output_index": 0, "sequence_number": 2, "item": {"type": "message", "id": item_id, "status": "in_progress", "role": "assistant", "content": [], "phase": None}},
        {"type": "response.content_part.added", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 3, "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []}},
        {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 4, "delta": "synthetic", "logprobs": []},
        {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 5, "text": "synthetic", "logprobs": []},
        {"type": "response.content_part.done", "item_id": item_id, "output_index": 0, "content_index": 0, "sequence_number": 6, "part": {"type": "output_text", "text": "synthetic", "annotations": [], "logprobs": None}},
        {"type": "response.output_item.done", "output_index": 0, "sequence_number": 7, "item": {"type": "message", "id": item_id, "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": "synthetic", "annotations": [], "logprobs": None}], "phase": None, "summary": []}},
        {"type": "response.completed", "sequence_number": 8, "response": {"id": response_id, "status": "completed", "model": CODEX_MODEL, "output": [{"type": "message", "id": "parser_message", "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": "synthetic", "annotations": [], "logprobs": None}], "phase": None}], "usage": _usage()}},
    )


class HistoryLocalState:
    def __init__(self) -> None:
        self.request_count = 0
        self.signed_request_count = 0
        self.function_count = 0
        self.message_count = 0
        self._lock = threading.Lock()

    def observe(self, body: bytes, headers: http.client.HTTPMessage, path: str) -> tuple[dict[str, object], ...]:
        if path != "/v1/responses":
            raise VerificationError("local_path_invalid")
        if headers.get("authorization") != "Bearer " + LOCAL_SERVICE_TOKEN:
            raise VerificationError("local_service_auth_invalid")
        required = {
            "x-slaif-identity-version",
            "x-slaif-principal",
            "x-slaif-session",
            "x-slaif-repository",
            "x-slaif-route",
            "x-slaif-timestamp",
            "x-slaif-nonce",
            "x-slaif-signature",
        }
        if not required.issubset({name.lower() for name in headers}):
            raise VerificationError("local_signed_headers_missing")
        from slaif_gateway.modules.servers.local_coding.identity import (
            LocalCodingRequestIdentity,
            canonical_identity_bytes,
            expected_signature,
        )

        identity = LocalCodingRequestIdentity(
            principal=headers["x-slaif-principal"],
            session=headers["x-slaif-session"],
            repository=headers["x-slaif-repository"],
            route=headers["x-slaif-route"],
            identity_mode="signed_identity_v1",
        )
        canonical = canonical_identity_bytes(
            method="POST",
            path=path,
            raw_query=b"",
            body=body,
            identity=identity,
            timestamp=headers["x-slaif-timestamp"],
            nonce=headers["x-slaif-nonce"],
        )
        expected = expected_signature(secret=LOCAL_SIGNING_SECRET.encode(), canonical=canonical)
        if not hmac.compare_digest(headers["x-slaif-signature"], expected):
            raise VerificationError("local_signature_invalid")
        with self._lock:
            self.request_count += 1
            self.signed_request_count += 1
            ordinal = self.request_count
        payload = json.loads(body)
        if not isinstance(payload, Mapping):
            raise VerificationError("local_body_invalid")
        if ordinal == 1:
            tool_name = _tool_name(payload)
            arguments = _tool_arguments(payload, tool_name)
            self.function_count += 1
            return _function_stream(arguments, tool_name)
        if ordinal == 2:
            items = payload.get("input")
            if not isinstance(items, list):
                raise VerificationError("local_tool_result_input_missing")
            calls = [item for item in items if isinstance(item, Mapping) and item.get("type") == "function_call"]
            outputs = [item for item in items if isinstance(item, Mapping) and item.get("type") == "function_call_output"]
            if len(calls) != 1 or len(outputs) != 1:
                raise VerificationError("local_tool_result_pair_invalid")
            if items.index(calls[0]) + 1 != items.index(outputs[0]) or calls[0].get("call_id") != outputs[0].get("call_id"):
                raise VerificationError("local_tool_result_adjacency_invalid")
            self.message_count += 1
            return _message_stream()
        raise VerificationError("local_request_count_exceeded")


class _LocalHandler(http.server.BaseHTTPRequestHandler):
    server: "_LocalServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > MAX_CAPTURE_BODY_BYTES:
                raise VerificationError("local_body_bound_invalid")
            body = self.rfile.read(length)
            events = self.server.state.observe(body, self.headers, self.path)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.end_headers()
            for event in events:
                self.wfile.write(_sse(event))
                self.wfile.flush()
        except VerificationError:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"history_fake_local_failed"}}')


class _LocalServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state: HistoryLocalState) -> None:
        super().__init__(("127.0.0.1", 0), _LocalHandler)
        self.state = state


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("process_launch_failed") from exc


def _install_codex(root: Path) -> Path:
    install = root / "codex-install"
    install.mkdir(mode=0o700)
    if _run(["npm", "init", "-y"], cwd=install, env=os.environ.copy(), timeout=30).returncode != 0:
        raise VerificationError("codex_install_failed")
    if _run(
        ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", CODEX_PACKAGE],
        cwd=install,
        env=os.environ.copy(),
        timeout=180,
    ).returncode != 0:
        raise VerificationError("codex_install_failed")
    binary = install / "node_modules/.bin/codex"
    version = _run([str(binary), "--version"], cwd=install, env=os.environ.copy(), timeout=10)
    if version.returncode != 0 or version.stdout != b"codex-cli 0.149.0\n":
        raise VerificationError("codex_version_mismatch")
    return binary


def _resume_command(binary: Path, *, workdir: Path, port: int, model_catalog: Path, output: Path, thread_id: str, image: Path) -> list[str]:
    from scripts.capture_codex_protocol import _exec_resume_command_0149

    command = _exec_resume_command_0149(
        binary,
        workdir=workdir,
        port=port,
        model=CODEX_MODEL,
        model_catalog=model_catalog,
        output_path=output,
        thread_id=thread_id,
    )
    output_index = command.index("-o")
    command[output_index:output_index] = [
        "-c",
        "model_providers.slaif-capture.request_max_retries=0",
        "-c",
        "model_providers.slaif-capture.stream_max_retries=0",
    ]
    resume_index = command.index("resume")
    command[resume_index + 1 : resume_index + 1] = ["--image", str(image)]
    command[-1] = "Inspect the attached synthetic crop and return one short answer."
    return command


def _command_shape(command: list[str]) -> dict[str, object]:
    return {
        "zero_request_retries": "model_providers.slaif-capture.request_max_retries=0" in command,
        "zero_stream_retries": "model_providers.slaif-capture.stream_max_retries=0" in command,
        "resume": "resume" in command,
        "image": "--image" in command,
    }


def _database() -> tuple[str, bool, str | None]:
    provided = os.environ.get("TEST_DATABASE_URL")
    if provided:
        return provided, False, None
    name = f"slaif_gateway_161_assistant_history_test_{os.getpid()}"
    from scripts.verify_codex_0149_local_roundtrip import _run as run_command

    result = run_command(
        ["bash", "scripts/create-test-db.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "TEST_DB_NAME": name},
        timeout=30,
    )
    if result.returncode != 0:
        raise VerificationError("postgres_setup_failed")
    return f"postgresql+asyncpg://slaif:slaif@localhost:5432/{name}", True, name


@contextlib.contextmanager
def _environment(values: dict[str, str]) -> Iterator[None]:
    previous = os.environ.copy()
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


async def _accounting_count(database_url: str, key_id: object) -> int:
    from slaif_gateway.db.models import QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            reservations = await session.scalar(
                select(func.count()).select_from(QuotaReservation).where(QuotaReservation.gateway_key_id == key_id)
            )
            ledgers = await session.scalar(
                select(func.count()).select_from(UsageLedger).where(UsageLedger.gateway_key_id == key_id)
            )
            return int(reservations or 0) + int(ledgers or 0)
    finally:
        await engine.dispose()


def run_prefixed_reproduction() -> str:
    from scripts import capture_codex_protocol as capture
    from tests.e2e.test_openai_python_client_responses import _create_responses_test_data
    from tests.e2e.test_openai_python_client_chat import _run_uvicorn_server
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_CLIENT_MODULE_VERSION, CODEX_0149_FIXTURE_SHA256

    database_url, own_db, db_name = _database()
    local = _LocalServer(HistoryLocalState())
    local_thread = threading.Thread(target=local.serve_forever, daemon=True)
    local_thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="slaif-161-history-") as temporary:
            root = Path(temporary)
            home = root / "codex-home"
            work = root / "workspace"
            home.mkdir(mode=0o700)
            work.mkdir(mode=0o700)
            image = root / "synthetic.png"
            image.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360606000000004000100f6173855d00000000049454e44ae426082"))
            state = local.state
            values = {
                "DATABASE_URL": database_url,
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
            with _environment(values):
                get_settings.cache_clear()
                migration = _run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT, env=values, timeout=120)
                if migration.returncode != 0:
                    raise VerificationError("migration_failed")
                from slaif_gateway.config import get_settings as configured_settings

                created = asyncio.run(
                    _create_responses_test_data(
                        database_url,
                        provider="local-coding",
                        model=CODEX_MODEL,
                        upstream_model=CODEX_MODEL,
                        base_url=f"http://127.0.0.1:{local.server_address[1]}/v1",
                        api_key_env_var="LOCAL_CODING_SERVICE_TOKEN",
                        streaming=True,
                        function_tools=True,
                        custom_tools=True,
                        image_input=True,
                        local_coding_contract={
                            "contract_version": "local-coding-v1",
                            "route_name": "vision",
                            "tool_policy_version": "responses-tool-policy-v1",
                            "identity_mode": "signed_identity_v1",
                            "replay_mode": "process_local_ttl_lru",
                            "deployment_mode": "single_worker",
                        },
                        responses_policy={
                            "version": 1,
                            "local_coding_repository_scope": "assistant-history-repository",
                            "allowed_capabilities": ["codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events"],
                            "client_module": {"id": "codex-0.149-responses-v1", "version": CODEX_0149_CLIENT_MODULE_VERSION, "fixture_sha256": CODEX_0149_FIXTURE_SHA256},
                        },
                        codex_request_envelope=True,
                        codex_client_tools=True,
                        codex_streaming_tool_events=True,
                    )
                )
                binary = _install_codex(root)
                catalog = root / "model-catalog.json"
                environment = capture._isolated_environment(home)
                environment.update(values)
                environment[capture.CAPTURE_API_KEY_ENV] = created.plaintext_key
                capture._write_0149_model_catalog(binary, catalog, environment=environment, model=CODEX_MODEL)
                catalog_value = json.loads(catalog.read_text(encoding="utf-8"))
                catalog_models = catalog_value.get("models") if isinstance(catalog_value, Mapping) else None
                if not isinstance(catalog_models, list) or len(catalog_models) != 1 or not isinstance(catalog_models[0], dict):
                    raise VerificationError("model_catalog_shape_invalid")
                catalog_models[0]["supports_image_detail_original"] = True
                catalog.write_text(json.dumps(catalog_value, separators=(",", ":")), encoding="utf-8")
                gateway_port = _free_port()
                observation = GatewayObservation(create_app(configured_settings()))
                first = capture._exec_command_0149(
                    binary,
                    workdir=work,
                    port=gateway_port,
                    model=CODEX_MODEL,
                    model_catalog=catalog,
                    output_path=root / "first-output.json",
                    ephemeral=False,
                    instruction="Describe the attached synthetic image briefly without tools.",
                )
                first_output_index = first.index("-o")
                first[first_output_index:first_output_index] = ["--image", str(image)]
                if not _command_shape(first)["zero_request_retries"] or not _command_shape(first)["zero_stream_retries"]:
                    raise VerificationError("zero_retry_command_invalid")
                first_result = None
                previous_logging_disable = logging.root.manager.disable
                logging.disable(logging.CRITICAL)
                try:
                    with _run_uvicorn_server(observation, gateway_port):
                        first_result = _run(first, cwd=work, env=environment, timeout=180)
                        if first_result.returncode != 0:
                            category = _codex_failure_category(first_result.stderr, first_result.stdout)
                            raise VerificationError(
                                f"codex_first_turn_{category}_{_safe_failure_progress(observation, local)}"
                            )
                        try:
                            thread_id = capture._session_capture_thread_id(first_result.stdout)
                        except Exception as exc:
                            raise VerificationError("codex_thread_id_invalid") from exc
                        del first_result
                        second = _resume_command(
                            binary,
                            workdir=work,
                            port=gateway_port,
                            model_catalog=catalog,
                            output=root / "second-output.json",
                            thread_id=thread_id,
                            image=image,
                        )
                        second_shape = _command_shape(second)
                        if not all(second_shape.values()):
                            raise VerificationError("resume_command_invalid")
                        second_result = _run(second, cwd=work, env=environment, timeout=180)
                        if second_result.returncode == 0:
                            raise VerificationError("history_rejection_not_reproduced")
                        del second_result, thread_id
                finally:
                    logging.disable(previous_logging_disable)
                if observation.request_count != 3 or observation.response_statuses != [200, 200, 400]:
                    raise VerificationError(
                        f"gateway_request_progression_{_safe_progress_class(observation.request_count)}"
                        f"_statuses_{_safe_status_sequence(observation)}"
                        f"_local_{_safe_progress_class(state.request_count)}"
                    )
                if observation.error_codes[-1] != _ALLOWED_ERROR_CODE:
                    raise VerificationError("history_error_code_invalid")
                if observation.param_classes[-1] != "input_5_content_0_type":
                    raise VerificationError(
                        f"history_error_param_{observation.param_classes[-1]}"
                    )
                projection = observation.second_projection or {}
                required = (
                    projection.get("assistant_history_present") is True,
                    projection.get("assistant_role_exact") is True,
                    projection.get("assistant_output_text_count") == 1,
                    projection.get("assistant_output_text_type_exact") is True,
                    projection.get("assistant_output_text_nonempty_unicode") is True,
                    projection.get("image_part_count_class") == "one",
                    projection.get("raw_value_retained") is False,
                )
                if not all(required):
                    if projection.get("image_part_count_class") != "one":
                        raise VerificationError(
                            f"history_projection_image_count_{projection.get('image_part_count_class', 'other')}"
                            f"_sequence_{'_'.join(observation.image_count_classes[:4]) or 'none'}"
                        )
                    names = (
                        "history_present",
                        "role",
                        "output_text_count",
                        "output_text_type",
                        "output_text_unicode",
                        "image_count",
                        "raw_absent",
                    )
                    failed = "_".join(name for name, passed in zip(names, required) if not passed)
                    raise VerificationError(f"history_projection_invalid_{failed or 'other'}")
                if state.request_count != 2 or state.signed_request_count != 2:
                    raise VerificationError("fake_local_advanced_on_rejection")
                if state.function_count != 1 or state.message_count != 1:
                    raise VerificationError("fake_local_lifecycle_invalid")
                return "VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_OK request_count=3 local_count=2 clean_rejection=true"
    finally:
        local.shutdown()
        local.server_close()
        local_thread.join(timeout=5)
        if own_db and db_name:
            try:
                subprocess.run(
                    ["sudo", "-n", "-u", "postgres", "dropdb", "--if-exists", db_name],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(run_prefixed_reproduction())
        return 0
    except VerificationError as exc:
        print(f"VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code={exc.args[0]}")
        return 1
    except Exception as exc:
        name = type(exc).__name__
        safe_name = name if name in {"AttributeError", "KeyError", "TypeError", "ValueError", "IndexError"} else "other"
        print(f"VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code=unexpected_{safe_name}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
