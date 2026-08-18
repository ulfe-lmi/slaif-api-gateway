#!/usr/bin/env python3
"""Verify one pinned Codex client-tool round trip against an isolated loopback."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

try:
    import capture_codex_protocol as capture
except ModuleNotFoundError:  # Imported as a namespace package by unit tests.
    from scripts import capture_codex_protocol as capture


SAFE_CODE_MODE_INPUT = 'text("SAFE_TOOL_RESULT")'
SAFE_FINAL_TEXT = "SLAIF_CODEX_ROUNDTRIP_OK"
TOOL_ITEM_ID = "ctc_slaif_roundtrip"
TOOL_CALL_ID = "call_slaif_roundtrip"
FINAL_MESSAGE_ID = "msg_slaif_roundtrip"
RESPONSE_ONE_ID = "resp_slaif_roundtrip_one"
RESPONSE_TWO_ID = "resp_slaif_roundtrip_two"
EXPECTED_REQUESTS = 2
FIXTURE_PATH = capture.REPO_ROOT / capture.FIXTURE_RELATIVE_PATH
MAX_SUBPROCESS_OUTPUT_BYTES = 512_000


class VerificationError(RuntimeError):
    """A fixed, safe verifier failure that never carries captured payload text."""


FIRST_RESPONSE_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": RESPONSE_ONE_ID}},
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "type": "custom_tool_call",
            "id": TOOL_ITEM_ID,
            "status": "in_progress",
            "namespace": "functions",
            "name": "exec",
            "call_id": TOOL_CALL_ID,
            "input": "",
        },
    },
    {
        "type": "response.custom_tool_call_input.delta",
        "output_index": 0,
        "item_id": TOOL_ITEM_ID,
        "call_id": TOOL_CALL_ID,
        "delta": SAFE_CODE_MODE_INPUT,
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "custom_tool_call",
            "id": TOOL_ITEM_ID,
            "status": "completed",
            "namespace": "functions",
            "name": "exec",
            "call_id": TOOL_CALL_ID,
            "input": SAFE_CODE_MODE_INPUT,
        },
    },
    {
        "type": "response.completed",
        "response": {
            "id": RESPONSE_ONE_ID,
            "status": "completed",
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": None,
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 2,
            },
        },
    },
)
SECOND_RESPONSE_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": RESPONSE_TWO_ID}},
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": FINAL_MESSAGE_ID,
            "status": "in_progress",
            "role": "assistant",
            "content": [],
        },
    },
    {
        "type": "response.output_text.delta",
        "item_id": FINAL_MESSAGE_ID,
        "output_index": 0,
        "content_index": 0,
        "delta": SAFE_FINAL_TEXT,
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": FINAL_MESSAGE_ID,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": SAFE_FINAL_TEXT}],
        },
    },
    {
        "type": "response.completed",
        "response": {
            "id": RESPONSE_TWO_ID,
            "status": "completed",
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": None,
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 2,
            },
        },
    },
)


def _sse_body(events: tuple[dict[str, object], ...]) -> bytes:
    chunks = []
    for event in events:
        event_type = event["type"]
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        chunks.append(f"event: {event_type}\ndata: {payload}\n\n")
    body = "".join(chunks).encode("ascii")
    validate_sse_body(body, events=events)
    return body


def validate_sse_body(body: bytes, *, events: tuple[dict[str, object], ...]) -> None:
    """Validate one fixed mock sequence without echoing any malformed bytes."""
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise VerificationError("Roundtrip mock SSE was not ASCII.") from exc
    blocks = [block for block in text.split("\n\n") if block]
    if len(blocks) != len(events):
        raise VerificationError("Roundtrip mock SSE sequence was malformed.")
    for block, expected in zip(blocks, events, strict=True):
        lines = block.splitlines()
        if len(lines) != 2 or not lines[0].startswith("event: ") or not lines[1].startswith(
            "data: "
        ):
            raise VerificationError("Roundtrip mock SSE sequence was malformed.")
        if lines[0].removeprefix("event: ") != expected["type"]:
            raise VerificationError("Roundtrip mock SSE event order was malformed.")
        try:
            payload = json.loads(lines[1].removeprefix("data: "))
        except json.JSONDecodeError as exc:
            raise VerificationError("Roundtrip mock SSE JSON was malformed.") from exc
        if payload != expected:
            raise VerificationError("Roundtrip mock SSE event structure was malformed.")


def _write_response(connection: socket.socket, *, request_number: int) -> None:
    if request_number == 1:
        body = _sse_body(FIRST_RESPONSE_EVENTS)
    elif request_number == 2:
        body = _sse_body(SECOND_RESPONSE_EVENTS)
    else:
        raise VerificationError("Roundtrip loopback received too many requests.")
    response = b"\r\n".join(
        (
            b"HTTP/1.1 200 OK",
            b"Content-Type: text/event-stream",
            f"Content-Length: {len(body)}".encode("ascii"),
            b"Connection: close",
            b"",
            body,
        )
    )
    connection.sendall(response)


class RoundtripLoopbackServer:
    """A bounded two-request loopback server for the pinned manual verifier."""

    def __init__(self) -> None:
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._done = threading.Event()
        self.requests: list[capture.ParsedHttpRequest] = []
        self.error: VerificationError | None = None
        self.port: int | None = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(EXPECTED_REQUESTS)
        listener.settimeout(0.1)
        address = listener.getsockname()
        if address[0] != "127.0.0.1":
            listener.close()
            raise VerificationError("Roundtrip server did not bind to numeric loopback.")
        self._listener = listener
        self.port = int(address[1])
        self._thread = threading.Thread(
            target=self._serve,
            name="codex-roundtrip-loopback",
            daemon=True,
        )
        self._thread.start()

    def _serve(self) -> None:
        assert self._listener is not None
        deadline = time.monotonic() + capture.SERVER_TIMEOUT_SECONDS
        try:
            while not self._stop.is_set() and time.monotonic() < deadline:
                if len(self.requests) == EXPECTED_REQUESTS:
                    return
                try:
                    connection, peer = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if not self._stop.is_set():
                        self.error = VerificationError(
                            "Roundtrip loopback transport failed safely."
                        )
                    return
                with connection:
                    if peer[0] != "127.0.0.1":
                        self.error = VerificationError(
                            "Roundtrip loopback rejected a non-loopback peer."
                        )
                        return
                    try:
                        raw = capture._read_bounded_request(connection)
                        request = capture._parse_http_request(raw)
                        capture.sanitize_request(request)
                        _validate_http_target(request)
                        self.requests.append(request)
                        _write_response(connection, request_number=len(self.requests))
                    except (capture.CaptureError, VerificationError, OSError) as exc:
                        self.error = (
                            exc
                            if isinstance(exc, VerificationError)
                            else VerificationError(
                                "Roundtrip loopback request validation failed safely."
                            )
                        )
                        return
                    finally:
                        if "raw" in locals():
                            del raw
            if len(self.requests) != EXPECTED_REQUESTS and not self._stop.is_set():
                self.error = VerificationError(
                    "Codex did not complete both bounded loopback requests."
                )
        finally:
            self._done.set()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def result(self) -> tuple[capture.ParsedHttpRequest, capture.ParsedHttpRequest]:
        if self.error is not None:
            raise self.error
        if len(self.requests) != EXPECTED_REQUESTS:
            raise VerificationError("Roundtrip loopback requires exactly two requests.")
        return self.requests[0], self.requests[1]


def _validate_http_target(request: capture.ParsedHttpRequest) -> None:
    if request.method != "POST" or request.target != "/v1/responses":
        raise VerificationError("Roundtrip loopback received an unexpected HTTP target.")


def _request_json(request: capture.ParsedHttpRequest) -> dict[str, Any]:
    try:
        value = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("Roundtrip request body was malformed.") from exc
    if not isinstance(value, dict):
        raise VerificationError("Roundtrip request body was not an object.")
    return value


def validate_first_request(
    request: capture.ParsedHttpRequest,
    *,
    fixture: dict[str, object],
) -> None:
    """Prove the first request retains the approved immutable capture shape."""
    _validate_http_target(request)
    sanitized = capture.sanitize_request(request)
    capture_section = fixture.get("capture")
    expected = capture_section.get("request") if isinstance(capture_section, dict) else None
    if sanitized != expected:
        raise VerificationError("First roundtrip request drifted from the pinned fixture shape.")


def validate_second_request(request: capture.ParsedHttpRequest) -> None:
    """Prove one exact custom call/output pair was replayed without returning payloads."""
    _validate_http_target(request)
    body = _request_json(request)
    input_items = body.get("input")
    if not isinstance(input_items, list):
        raise VerificationError("Second roundtrip request had no input item array.")
    calls = [
        item
        for item in input_items
        if isinstance(item, dict)
        and item.get("type") == "custom_tool_call"
        and item.get("call_id") == TOOL_CALL_ID
    ]
    outputs = [
        item
        for item in input_items
        if isinstance(item, dict)
        and item.get("type") == "custom_tool_call_output"
        and item.get("call_id") == TOOL_CALL_ID
    ]
    if len(calls) != 1 or len(outputs) != 1:
        raise VerificationError("Second request did not contain one matching custom-tool pair.")
    call = calls[0]
    if (
        call.get("namespace") != "functions"
        or call.get("name") != "exec"
        or call.get("input") != SAFE_CODE_MODE_INPUT
    ):
        raise VerificationError("Second request custom-tool call did not match the fixed mock.")
    output = outputs[0].get("output")
    if isinstance(output, str):
        marker_present = "SAFE_TOOL_RESULT" in output
    elif isinstance(output, list) and 0 < len(output) <= 8:
        marker_present = False
        total_output_bytes = 0
        for part in output:
            if (
                not isinstance(part, dict)
                or set(part) != {"type", "text"}
                or part.get("type") != "input_text"
                or not isinstance(part.get("text"), str)
            ):
                raise VerificationError(
                    "Second request custom-tool output used an unapproved content shape."
                )
            text = part["text"]
            total_output_bytes += len(text.encode("utf-8"))
            marker_present = marker_present or "SAFE_TOOL_RESULT" in text
        if total_output_bytes > capture.MAX_BODY_BYTES:
            raise VerificationError("Second request custom-tool output exceeded the limit.")
    else:
        marker_present = False
    if not marker_present:
        raise VerificationError("Second request custom-tool output did not match safely.")
    forbidden_types = {
        "local_shell_call",
        "shell_call",
        "mcp_call",
        "computer_call",
        "web_search_call",
        "tool_search_call",
    }
    if any(
        isinstance(item, dict)
        and (
            item.get("type") in forbidden_types
            or item.get("name") in {"shell", "shell_command", "apply_patch"}
        )
        for item in input_items
    ):
        raise VerificationError("Second request contained unapproved tool authority.")


def validate_final_sequence(stdout: bytes) -> None:
    """Require a bounded successful Codex JSONL terminal sequence without printing it."""
    if len(stdout) > MAX_SUBPROCESS_OUTPUT_BYTES:
        raise VerificationError("Codex roundtrip output exceeded the verifier limit.")
    event_types: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            event_types.append(event["type"])
    if "turn.completed" not in event_types:
        raise VerificationError("Codex roundtrip did not reach the final completed turn.")


def _run_codex(
    codex_binary: Path,
    *,
    workdir: Path,
    port: int,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            capture._exec_command(codex_binary, workdir=workdir, port=port),
            check=False,
            capture_output=True,
            env=environment,
            timeout=capture.CODEX_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("Codex roundtrip subprocess failed safely.") from exc


def verify_roundtrip(
    *,
    codex_binary: Path,
    expected_cli_version: str,
    model: str,
    profile: str,
) -> dict[str, object]:
    capture.validate_target(
        expected_version=expected_cli_version,
        model=model,
        profile=profile,
    )
    version = capture.verify_codex_version(codex_binary, expected_cli_version)
    fixture = capture._load_fixture(FIXTURE_PATH)
    server = RoundtripLoopbackServer()
    result: subprocess.CompletedProcess[bytes] | None = None
    first_request: capture.ParsedHttpRequest | None = None
    second_request: capture.ParsedHttpRequest | None = None
    with tempfile.TemporaryDirectory(prefix="slaif-codex-roundtrip-home-") as home_name:
        with tempfile.TemporaryDirectory(prefix="slaif-codex-roundtrip-work-") as work_name:
            codex_home = Path(home_name)
            workdir = Path(work_name)
            environment = capture._isolated_environment(codex_home)
            server.start()
            assert server.port is not None
            try:
                result = _run_codex(
                    codex_binary,
                    workdir=workdir,
                    port=server.port,
                    environment=environment,
                )
            finally:
                server.stop()
            first_request, second_request = server.result()

    assert result is not None
    failure_category = capture.classify_codex_failure(result.stderr, result.stdout)
    try:
        capture.ensure_subprocess_success(
            returncode=result.returncode,
            failure_category=failure_category,
        )
    except capture.CaptureError as exc:
        raise VerificationError("Codex roundtrip subprocess exited unsuccessfully.") from exc
    validate_first_request(first_request, fixture=fixture)
    validate_second_request(second_request)
    validate_final_sequence(result.stdout)
    del first_request, second_request, result
    return {
        "result": "OK",
        "cli_version": version,
        "model": model,
        "profile": profile,
        "request_count": EXPECTED_REQUESTS,
        "first_request_matches_fixture": True,
        "tool_category": "custom",
        "tool_namespace": "functions",
        "tool_name": "exec",
        "tool_output_matched": True,
        "final_assistant_sequence": True,
        "network_scope": "127.0.0.1",
        "raw_payloads_persisted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = verify_roundtrip(
            codex_binary=args.codex_binary,
            expected_cli_version=args.expected_cli_version,
            model=args.model,
            profile=args.profile,
        )
    except (capture.CaptureError, VerificationError) as exc:
        print(f"RESULT=ERROR\nERROR={exc}", file=sys.stderr)
        return 1
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        print(f"{key.upper()}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
