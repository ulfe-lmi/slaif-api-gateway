#!/usr/bin/env python3
"""Verify pinned Codex encrypted-reasoning replay on an isolated loopback."""

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


SAFE_CODE_MODE_ONE = 'text("SAFE_REPLAY_ONE")'
SAFE_CODE_MODE_TWO = 'text("SAFE_REPLAY_TWO")'
SAFE_FINAL_TEXT = "SLAIF_CODEX_REASONING_REPLAY_OK"
SYNTHETIC_ENCRYPTED_REASONING = "U0xBSUZfU1lOVEhFVElDX1JFQVNPTklOR19SRVBMQVk="
FIRST_TOOL_ITEM_ID = "ctc_slaif_replay_one"
FIRST_TOOL_CALL_ID = "call_slaif_replay_one"
REASONING_ITEM_ID = "rs_slaif_replay"
SECOND_TOOL_ITEM_ID = "ctc_slaif_replay_two"
SECOND_TOOL_CALL_ID = "call_slaif_replay_two"
FINAL_MESSAGE_ID = "msg_slaif_replay"
RESPONSE_ONE_ID = "resp_slaif_replay_one"
RESPONSE_TWO_ID = "resp_slaif_replay_two"
RESPONSE_THREE_ID = "resp_slaif_replay_three"
EXPECTED_REQUESTS = 3
FIXTURE_PATH = capture.REPO_ROOT / capture.FIXTURE_RELATIVE_PATH
MAX_SUBPROCESS_OUTPUT_BYTES = 512_000


class VerificationError(RuntimeError):
    """A fixed, safe verifier failure that never carries captured payload text."""


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 1,
        "input_tokens_details": None,
        "output_tokens": 1,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 2,
    }


def _tool_events(
    *,
    output_index: int,
    item_id: str,
    call_id: str,
    source: str,
) -> tuple[dict[str, object], ...]:
    return (
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {
                "type": "custom_tool_call",
                "id": item_id,
                "status": "in_progress",
                "namespace": "functions",
                "name": "exec",
                "call_id": call_id,
                "input": "",
            },
        },
        {
            "type": "response.custom_tool_call_input.delta",
            "output_index": output_index,
            "item_id": item_id,
            "call_id": call_id,
            "delta": source,
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {
                "type": "custom_tool_call",
                "id": item_id,
                "status": "completed",
                "namespace": "functions",
                "name": "exec",
                "call_id": call_id,
                "input": source,
            },
        },
    )


REASONING_ITEM: dict[str, object] = {
    "type": "reasoning",
    "id": REASONING_ITEM_ID,
    "summary": [],
    "encrypted_content": SYNTHETIC_ENCRYPTED_REASONING,
}
REASONING_REPLAY_INPUT_ITEM: dict[str, object] = {
    **REASONING_ITEM,
    "content": None,
}

FIRST_RESPONSE_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": RESPONSE_ONE_ID}},
    *_tool_events(
        output_index=0,
        item_id=FIRST_TOOL_ITEM_ID,
        call_id=FIRST_TOOL_CALL_ID,
        source=SAFE_CODE_MODE_ONE,
    ),
    {
        "type": "response.completed",
        "response": {
            "id": RESPONSE_ONE_ID,
            "status": "completed",
            "usage": _usage(),
        },
    },
)

SECOND_RESPONSE_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": RESPONSE_TWO_ID}},
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "type": "reasoning",
            "id": REASONING_ITEM_ID,
            "summary": [],
        },
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": REASONING_ITEM,
    },
    *_tool_events(
        output_index=1,
        item_id=SECOND_TOOL_ITEM_ID,
        call_id=SECOND_TOOL_CALL_ID,
        source=SAFE_CODE_MODE_TWO,
    ),
    {
        "type": "response.completed",
        "response": {
            "id": RESPONSE_TWO_ID,
            "status": "completed",
            "usage": _usage(),
        },
    },
)

THIRD_RESPONSE_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": RESPONSE_THREE_ID}},
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
            "id": RESPONSE_THREE_ID,
            "status": "completed",
            "usage": _usage(),
        },
    },
)


def _sse_body(events: tuple[dict[str, object], ...]) -> bytes:
    chunks: list[str] = []
    for event in events:
        event_type = event["type"]
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
        chunks.append(f"event: {event_type}\ndata: {payload}\n\n")
    body = "".join(chunks).encode("ascii")
    validate_sse_body(body, events=events)
    return body


def validate_sse_body(body: bytes, *, events: tuple[dict[str, object], ...]) -> None:
    """Validate one fixed mock sequence without echoing malformed bytes."""
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise VerificationError("Reasoning replay mock SSE was not ASCII.") from exc
    blocks = [block for block in text.split("\n\n") if block]
    if len(blocks) != len(events):
        raise VerificationError("Reasoning replay mock SSE sequence was malformed.")
    for block, expected in zip(blocks, events, strict=True):
        lines = block.splitlines()
        if (
            len(lines) != 2
            or not lines[0].startswith("event: ")
            or not lines[1].startswith("data: ")
        ):
            raise VerificationError("Reasoning replay mock SSE sequence was malformed.")
        if lines[0].removeprefix("event: ") != expected["type"]:
            raise VerificationError("Reasoning replay mock SSE event order was malformed.")
        try:
            payload = json.loads(lines[1].removeprefix("data: "))
        except json.JSONDecodeError as exc:
            raise VerificationError("Reasoning replay mock SSE JSON was malformed.") from exc
        if payload != expected:
            raise VerificationError("Reasoning replay mock SSE structure was malformed.")


def _write_response(connection: socket.socket, *, request_number: int) -> None:
    sequences = (
        FIRST_RESPONSE_EVENTS,
        SECOND_RESPONSE_EVENTS,
        THIRD_RESPONSE_EVENTS,
    )
    if request_number < 1 or request_number > len(sequences):
        raise VerificationError("Reasoning replay loopback received too many requests.")
    body = _sse_body(sequences[request_number - 1])
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


class ReasoningReplayLoopbackServer:
    """A bounded three-request loopback server for the manual verifier."""

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
            raise VerificationError("Reasoning replay server did not bind to numeric loopback.")
        self._listener = listener
        self.port = int(address[1])
        self._thread = threading.Thread(
            target=self._serve,
            name="codex-reasoning-replay-loopback",
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
                            "Reasoning replay loopback transport failed safely."
                        )
                    return
                with connection:
                    if peer[0] != "127.0.0.1":
                        self.error = VerificationError(
                            "Reasoning replay loopback rejected a non-loopback peer."
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
                                "Reasoning replay request validation failed safely."
                            )
                        )
                        return
                    finally:
                        if "raw" in locals():
                            del raw
            if len(self.requests) != EXPECTED_REQUESTS and not self._stop.is_set():
                self.error = VerificationError(
                    "Codex did not complete three bounded loopback requests."
                )
        finally:
            self._done.set()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def result(
        self,
    ) -> tuple[
        capture.ParsedHttpRequest,
        capture.ParsedHttpRequest,
        capture.ParsedHttpRequest,
    ]:
        if self.error is not None:
            raise self.error
        if len(self.requests) != EXPECTED_REQUESTS:
            raise VerificationError("Reasoning replay requires exactly three requests.")
        return self.requests[0], self.requests[1], self.requests[2]


def _validate_http_target(request: capture.ParsedHttpRequest) -> None:
    if request.method != "POST" or request.target != "/v1/responses":
        raise VerificationError("Reasoning replay received an unexpected HTTP target.")


def _request_json(request: capture.ParsedHttpRequest) -> dict[str, Any]:
    try:
        value = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("Reasoning replay request body was malformed.") from exc
    if not isinstance(value, dict):
        raise VerificationError("Reasoning replay request body was not an object.")
    return value


def _input_items(request: capture.ParsedHttpRequest) -> list[object]:
    _validate_http_target(request)
    value = _request_json(request).get("input")
    if not isinstance(value, list):
        raise VerificationError("Reasoning replay request had no input item array.")
    return value


def _contains_safe_output(value: object, *, marker: str) -> bool:
    if isinstance(value, str):
        return marker in value
    if not isinstance(value, list) or not 0 < len(value) <= 8:
        return False
    total_bytes = 0
    matched = False
    for part in value:
        if (
            not isinstance(part, dict)
            or set(part) != {"type", "text"}
            or part.get("type") != "input_text"
            or not isinstance(part.get("text"), str)
        ):
            return False
        text_value = part["text"]
        total_bytes += len(text_value.encode("utf-8"))
        matched = matched or marker in text_value
    return matched and total_bytes <= capture.MAX_BODY_BYTES


def _validate_tool_pair(
    items: list[object],
    *,
    item_id: str,
    call_id: str,
    source: str,
    marker: str,
) -> None:
    calls = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("type") == "custom_tool_call"
        and item.get("id") == item_id
        and item.get("call_id") == call_id
    ]
    outputs = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("type") == "custom_tool_call_output"
        and item.get("call_id") == call_id
    ]
    if len(calls) != 1 or len(outputs) != 1:
        raise VerificationError("Reasoning replay lacked one exact tool pair.")
    call = calls[0]
    if (
        call.get("namespace") != "functions"
        or call.get("name") != "exec"
        or call.get("input") != source
    ):
        raise VerificationError("Reasoning replay tool call differed from the fixed mock.")
    if not _contains_safe_output(outputs[0].get("output"), marker=marker):
        raise VerificationError("Reasoning replay tool output differed from the fixed mock.")


def _reject_unapproved_tools(items: list[object]) -> None:
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
        for item in items
    ):
        raise VerificationError("Reasoning replay contained unapproved tool authority.")


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
        raise VerificationError("First reasoning replay request drifted from the fixture.")


def validate_second_request(request: capture.ParsedHttpRequest) -> None:
    """Prove the first exact harmless call/output continuation in memory."""
    items = _input_items(request)
    _reject_unapproved_tools(items)
    _validate_tool_pair(
        items,
        item_id=FIRST_TOOL_ITEM_ID,
        call_id=FIRST_TOOL_CALL_ID,
        source=SAFE_CODE_MODE_ONE,
        marker="SAFE_REPLAY_ONE",
    )


def validate_third_request(request: capture.ParsedHttpRequest) -> None:
    """Prove encrypted reasoning plus both exact tool continuations in memory."""
    items = _input_items(request)
    _reject_unapproved_tools(items)
    reasoning_items = [
        item for item in items if isinstance(item, dict) and item.get("type") == "reasoning"
    ]
    if len(reasoning_items) != 1:
        raise VerificationError("Third request reasoning count was not exactly one.")
    reasoning = reasoning_items[0]
    if set(reasoning) != set(REASONING_REPLAY_INPUT_ITEM):
        raise VerificationError(
            "Third request reasoning fields were not exact: "
            f"field_count={len(reasoning)}; "
            f"status_present={'status' in reasoning}; "
            f"content_present={'content' in reasoning}."
        )
    if reasoning.get("id") != REASONING_ITEM_ID:
        raise VerificationError("Third request reasoning ID did not match in memory.")
    if reasoning.get("summary") != REASONING_REPLAY_INPUT_ITEM["summary"]:
        raise VerificationError("Third request reasoning summary did not match in memory.")
    if reasoning.get("encrypted_content") != SYNTHETIC_ENCRYPTED_REASONING:
        raise VerificationError("Third request opaque reasoning did not match in memory.")
    if reasoning.get("content") is not None:
        raise VerificationError("Third request reasoning content was not null.")
    _validate_tool_pair(
        items,
        item_id=FIRST_TOOL_ITEM_ID,
        call_id=FIRST_TOOL_CALL_ID,
        source=SAFE_CODE_MODE_ONE,
        marker="SAFE_REPLAY_ONE",
    )
    _validate_tool_pair(
        items,
        item_id=SECOND_TOOL_ITEM_ID,
        call_id=SECOND_TOOL_CALL_ID,
        source=SAFE_CODE_MODE_TWO,
        marker="SAFE_REPLAY_TWO",
    )


def validate_final_sequence(stdout: bytes) -> None:
    """Require a bounded successful Codex JSONL terminal sequence without printing it."""
    if len(stdout) > MAX_SUBPROCESS_OUTPUT_BYTES:
        raise VerificationError("Codex reasoning replay output exceeded the verifier limit.")
    event_types: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            event_types.append(event["type"])
    if "turn.completed" not in event_types:
        raise VerificationError("Codex reasoning replay did not complete the turn.")


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
        raise VerificationError("Codex reasoning replay subprocess failed safely.") from exc


def verify_reasoning_replay(
    *,
    codex_binary: Path,
    expected_cli_version: str,
    model: str,
    profile: str,
    fixture_path: Path,
) -> dict[str, object]:
    capture.validate_target(
        expected_version=expected_cli_version,
        model=model,
        profile=profile,
    )
    if fixture_path.resolve() != FIXTURE_PATH.resolve():
        raise VerificationError("Reasoning replay fixture path was not the pinned fixture.")
    version = capture.verify_codex_version(codex_binary, expected_cli_version)
    fixture = capture._load_fixture(fixture_path)
    server = ReasoningReplayLoopbackServer()
    result: subprocess.CompletedProcess[bytes] | None = None
    requests: tuple[capture.ParsedHttpRequest, ...] = ()
    with tempfile.TemporaryDirectory(prefix="slaif-codex-replay-home-") as home_name:
        with tempfile.TemporaryDirectory(prefix="slaif-codex-replay-work-") as work_name:
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
            requests = server.result()

    assert result is not None
    failure_category = capture.classify_codex_failure(result.stderr, result.stdout)
    try:
        capture.ensure_subprocess_success(
            returncode=result.returncode,
            failure_category=failure_category,
        )
    except capture.CaptureError as exc:
        raise VerificationError("Codex reasoning replay exited unsuccessfully.") from exc
    validate_first_request(requests[0], fixture=fixture)
    validate_second_request(requests[1])
    validate_third_request(requests[2])
    validate_final_sequence(result.stdout)
    del requests, result
    return {
        "result": "OK",
        "cli_version_matched": version == expected_cli_version,
        "model_matched": model == capture.PINNED_MODEL,
        "profile_matched": profile == capture.PINNED_PROFILE,
        "request_count": EXPECTED_REQUESTS,
        "reasoning_item_count": 1,
        "tool_pair_count": 2,
        "reasoning_replayed": True,
        "tool_outputs_matched": True,
        "final_assistant_sequence": True,
        "loopback_only": True,
        "tool_types": "custom",
        "raw_payloads_persisted": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = verify_reasoning_replay(
            codex_binary=args.codex_binary,
            expected_cli_version=args.expected_cli_version,
            model=args.model,
            profile=args.profile,
            fixture_path=args.fixture,
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
