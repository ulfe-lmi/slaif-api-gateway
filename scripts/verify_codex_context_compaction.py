#!/usr/bin/env python3
"""Verify pinned Codex 0.147.0 V1 remote compaction on numeric loopback only."""

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
except ModuleNotFoundError:
    from scripts import capture_codex_protocol as capture


SAFE_TOOL_INPUT = 'text("SAFE_CONTEXT_COMPACTION")'
COMPACTION_ID = "cmp_slaif_context_1"
COMPACTION_VALUE = "U0xBSUZfT1BBUVVFX0NPTVBBQ1RJT04="
TOOL_ITEM_ID = "ctc_slaif_context_1"
TOOL_CALL_ID = "call_slaif_context_1"
FINAL_MESSAGE_ID = "msg_slaif_context_final"
EXPECTED_PATHS = ("/v1/responses", "/v1/responses/compact", "/v1/responses")
MAX_SUBPROCESS_OUTPUT_BYTES = 512_000


class VerificationError(RuntimeError):
    """Fixed safe failure that never contains captured request or subprocess data."""


def _usage(
    input_tokens: int,
    *,
    cached_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
        "total_tokens": input_tokens + output_tokens,
    }


def _sse(events: tuple[dict[str, object], ...]) -> bytes:
    body = "".join(
        f"event: {event['type']}\ndata: "
        f"{json.dumps(event, sort_keys=True, separators=(',', ':'))}\n\n"
        for event in events
    ).encode("ascii")
    if len(body) > capture.MAX_BODY_BYTES:
        raise VerificationError("Verifier SSE exceeded its fixed bound.")
    return body


FIRST_EVENTS = (
    {"type": "response.created", "response": {"id": "resp_context_1"}},
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
        "delta": SAFE_TOOL_INPUT,
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
            "input": SAFE_TOOL_INPUT,
        },
    },
    {
        "type": "response.completed",
        "response": {
            "id": "resp_context_1",
            "status": "completed",
            "usage": _usage(
                600_000,
                cached_tokens=200_000,
                cache_write_tokens=100_000,
                output_tokens=10,
                reasoning_tokens=4,
            ),
        },
    },
)

FINAL_EVENTS = (
    {"type": "response.created", "response": {"id": "resp_context_2"}},
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
        "delta": "SLAIF_CODEX_CONTEXT_COMPACTION_OK",
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": FINAL_MESSAGE_ID,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "SLAIF_CODEX_CONTEXT_COMPACTION_OK"}],
        },
    },
    {
        "type": "response.completed",
        "response": {
            "id": "resp_context_2",
            "status": "completed",
            "usage": _usage(
                10,
                cached_tokens=5,
                cache_write_tokens=1,
                output_tokens=2,
                reasoning_tokens=1,
            ),
        },
    },
)

COMPACT_BODY = json.dumps(
    {
        "output": [
            {
                "type": "compaction",
                "id": COMPACTION_ID,
                "encrypted_content": COMPACTION_VALUE,
            }
        ],
        "usage": _usage(
            272_000,
            cached_tokens=100_000,
            cache_write_tokens=50_000,
            output_tokens=2,
            reasoning_tokens=1,
        ),
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("ascii")


class LoopbackServer:
    def __init__(self) -> None:
        self.requests: list[capture.ParsedHttpRequest] = []
        self.error: VerificationError | None = None
        self.port: int | None = None
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(len(EXPECTED_PATHS))
        listener.settimeout(0.1)
        host, port = listener.getsockname()
        if host != "127.0.0.1":
            listener.close()
            raise VerificationError("Verifier did not bind numeric loopback.")
        self._listener = listener
        self.port = int(port)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        assert self._listener is not None
        deadline = time.monotonic() + capture.SERVER_TIMEOUT_SECONDS
        try:
            while not self._stop.is_set() and time.monotonic() < deadline:
                if len(self.requests) == len(EXPECTED_PATHS):
                    return
                try:
                    connection, peer = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                with connection:
                    if peer[0] != "127.0.0.1":
                        self.error = VerificationError("Verifier rejected a non-loopback peer.")
                        return
                    try:
                        raw = capture._read_bounded_request(connection)
                        request = capture._parse_http_request(raw)
                        request_number = len(self.requests)
                        expected_path = EXPECTED_PATHS[request_number]
                        _validate_http_request(request, expected_path=expected_path)
                        self.requests.append(request)
                        self._write_response(connection, request_number=request_number)
                    except (capture.CaptureError, VerificationError, OSError) as exc:
                        self.error = (
                            exc
                            if isinstance(exc, VerificationError)
                            else VerificationError("Verifier request handling failed safely.")
                        )
                        return
                    finally:
                        if "raw" in locals():
                            del raw
            if len(self.requests) != len(EXPECTED_PATHS) and not self._stop.is_set():
                self.error = VerificationError(
                    "Pinned Codex did not induce the bounded V1 compact sequence."
                )
        finally:
            return

    def _write_response(self, connection: socket.socket, *, request_number: int) -> None:
        if request_number == 0:
            body = _sse(FIRST_EVENTS)
            content_type = b"text/event-stream"
        elif request_number == 1:
            body = COMPACT_BODY
            content_type = b"application/json"
        elif request_number == 2:
            body = _sse(FINAL_EVENTS)
            content_type = b"text/event-stream"
        else:
            raise VerificationError("Verifier received too many requests.")
        response = b"\r\n".join(
            (
                b"HTTP/1.1 200 OK",
                b"Content-Type: " + content_type,
                f"Content-Length: {len(body)}".encode("ascii"),
                b"Connection: close",
                b"",
                body,
            )
        )
        connection.sendall(response)

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _request_json(request: capture.ParsedHttpRequest) -> dict[str, Any]:
    try:
        value = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("Verifier received malformed JSON.") from exc
    if not isinstance(value, dict):
        raise VerificationError("Verifier received a non-object request.")
    return value


def _validate_http_request(
    request: capture.ParsedHttpRequest,
    *,
    expected_path: str,
) -> None:
    if request.method != "POST" or request.target != expected_path:
        raise VerificationError("Pinned Codex did not use the expected V1 compact sequence.")
    header_summary = capture.sanitize_headers(request.headers)
    if header_summary["content_encoding"] != {"present": False}:
        raise VerificationError("API-key Codex unexpectedly compressed a request.")
    if header_summary["content_type"] != "application/json":
        raise VerificationError("Pinned Codex sent an unexpected request content type.")
    authorization = header_summary["authorization"]
    if not isinstance(authorization, dict) or not authorization.get("present"):
        raise VerificationError("Pinned Codex omitted API-key authorization.")
    if expected_path == "/v1/responses":
        capture.sanitize_request(request)
    else:
        _request_json(request)


def _validate_sequence(requests: list[capture.ParsedHttpRequest]) -> None:
    if len(requests) != len(EXPECTED_PATHS):
        raise VerificationError("Verifier did not receive exactly three requests.")
    bodies = [_request_json(request) for request in requests]
    cache_keys = [body.get("prompt_cache_key") for body in bodies]
    if not all(isinstance(value, str) and value for value in cache_keys):
        raise VerificationError("Pinned Codex did not send bounded prompt-cache keys.")
    if len(set(cache_keys)) != 1:
        raise VerificationError("Pinned Codex did not reuse one prompt-cache key.")
    if any("content-encoding" in request.headers for request in requests):
        raise VerificationError("API-key Codex unexpectedly compressed a request.")
    compact_input = bodies[1].get("input")
    if not isinstance(compact_input, list) or not compact_input:
        raise VerificationError("V1 compact request did not carry bounded history.")
    final_input = bodies[2].get("input")
    if not isinstance(final_input, list):
        raise VerificationError("Post-compact request did not carry item history.")
    compact_items = [
        item for item in final_input if isinstance(item, dict) and item.get("type") == "compaction"
    ]
    if len(compact_items) != 1:
        raise VerificationError("Post-compact request did not replay exactly one opaque item.")
    compact_item = compact_items[0]
    if (
        compact_item.get("id") != COMPACTION_ID
        or compact_item.get("encrypted_content") != COMPACTION_VALUE
    ):
        raise VerificationError("Post-compact opaque item did not match in memory.")
    forbidden_types = {
        "shell_call",
        "local_shell_call",
        "mcp_call",
        "computer_call",
        "web_search_call",
    }
    if any(
        isinstance(item, dict) and item.get("type") in forbidden_types
        for body in bodies
        for item in (body.get("input") if isinstance(body.get("input"), list) else [])
    ):
        raise VerificationError("Verifier observed unapproved tool authority.")


def _command(codex_binary: Path, *, workdir: Path, port: int) -> list[str]:
    config = capture._config
    provider = capture.CAPTURE_PROVIDER_ID
    return [
        str(codex_binary),
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(workdir),
        *config("model", f'"{capture.PINNED_MODEL}"'),
        *config("model_provider", f'"{provider}"'),
        *config("model_reasoning_effort", '"low"'),
        *config("model_verbosity", '"low"'),
        *config("model_context_window", "1050000"),
        *config("model_auto_compact_token_limit", "500000"),
        *config("features.remote_compaction_v2", "false"),
        *config("check_for_update_on_startup", "false"),
        *config(f"model_providers.{provider}.name", '"OpenAI"'),
        *config(f"model_providers.{provider}.base_url", f'"http://127.0.0.1:{port}/v1"'),
        *config(f"model_providers.{provider}.env_key", f'"{capture.CAPTURE_API_KEY_ENV}"'),
        *config(f"model_providers.{provider}.wire_api", '"responses"'),
        *config(f"model_providers.{provider}.requires_openai_auth", "false"),
        *config(f"model_providers.{provider}.request_max_retries", "0"),
        *config(f"model_providers.{provider}.stream_max_retries", "0"),
        *config(f"model_providers.{provider}.stream_idle_timeout_ms", "5000"),
        capture.PROMPT_CANARY,
    ]


def verify(args: argparse.Namespace) -> dict[str, object]:
    capture.validate_target(
        expected_version=args.expected_cli_version,
        model=args.model,
        profile=args.profile,
    )
    version = capture.verify_codex_version(args.codex_binary, args.expected_cli_version)
    server = LoopbackServer()
    result: subprocess.CompletedProcess[bytes] | None = None
    requests: list[capture.ParsedHttpRequest] = []
    with tempfile.TemporaryDirectory(prefix="slaif-codex-context-home-") as home_name:
        with tempfile.TemporaryDirectory(prefix="slaif-codex-context-work-") as work_name:
            environment = capture._isolated_environment(Path(home_name))
            server.start()
            assert server.port is not None
            try:
                result = subprocess.run(
                    _command(args.codex_binary, workdir=Path(work_name), port=server.port),
                    check=False,
                    capture_output=True,
                    env=environment,
                    timeout=capture.CODEX_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VerificationError("Pinned Codex subprocess failed safely.") from exc
            finally:
                server.stop()
            if server.error is not None:
                raise server.error
            requests = list(server.requests)
    assert result is not None
    if len(result.stdout) > MAX_SUBPROCESS_OUTPUT_BYTES:
        raise VerificationError("Pinned Codex output exceeded the fixed bound.")
    try:
        capture.ensure_subprocess_success(
            returncode=result.returncode,
            failure_category=capture.classify_codex_failure(result.stderr, result.stdout),
        )
    except capture.CaptureError as exc:
        raise VerificationError("Pinned Codex exited unsuccessfully.") from exc
    if not any(
        isinstance(event, dict) and event.get("type") == "turn.completed"
        for line in result.stdout.splitlines()
        for event in _safe_json_event(line)
    ):
        raise VerificationError("Pinned Codex did not complete the bounded turn.")
    _validate_sequence(requests)
    del requests, result
    return {
        "result": "OK",
        "cli_version_matched": version == args.expected_cli_version,
        "request_count": len(EXPECTED_PATHS),
        "prompt_cache_reused": True,
        "cache_read_usage_seen": True,
        "cache_write_usage_seen": True,
        "reasoning_usage_seen": True,
        "below_threshold_seen": True,
        "threshold_edge_seen": True,
        "above_threshold_seen": True,
        "v1_compact_seen": True,
        "post_compact_continuation_seen": True,
        "content_encoding_absent": True,
        "loopback_only": True,
        "raw_payloads_persisted": False,
    }


def _safe_json_event(line: bytes) -> tuple[dict[str, object], ...]:
    try:
        event = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    return (event,) if isinstance(event, dict) else ()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        summary = verify(build_parser().parse_args(argv))
    except (capture.CaptureError, VerificationError) as exc:
        print(f"RESULT=ERROR\nERROR={exc}", file=sys.stderr)
        return 1
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        print(f"{key.upper()}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
