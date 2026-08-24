#!/usr/bin/env python3
"""Small socket-level OpenAI-compatible provider double for production qualification.

The process deliberately records only safe booleans and counters. It never logs
request bodies, authorization values, prompts, completions, or canary values.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


EXPECTED_KEY = os.environ.get("PROVIDER_DOUBLE_KEY", "qualification-provider-secret")
MODEL = os.environ.get("PROVIDER_DOUBLE_MODEL", "qualification-model")
PORT = int(os.environ.get("PROVIDER_DOUBLE_PORT", "8090"))
CANARIES = tuple(
    value
    for value in (
        os.environ.get("GATEWAY_KEY_CANARY"),
        os.environ.get("UPSTREAM_KEY_CANARY"),
        os.environ.get("PROMPT_CANARY"),
        os.environ.get("COMPLETION_CANARY"),
        os.environ.get("MEDIA_CANARY"),
        os.environ.get("MALFORMED_CANARY"),
        os.environ.get("AUTHORIZATION_CANARY"),
    )
    if value
)


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.mode = "normal"
        self.delay_seconds = 0.0
        self.stream_pause_seconds = 0.0
        self.completion = "qualification-output"
        self.canaries = set(CANARIES)
        self.requests = 0
        self.auth_ok = 0
        self.auth_bad = 0
        self.canary_seen = False
        self.paths: dict[str, int] = {}

    def configure(self, payload: dict[str, Any]) -> None:
        mode = payload.get("mode", "normal")
        if mode not in {
            "normal",
            "http_error",
            "timeout",
            "malformed_json",
            "malformed_sse",
            "incomplete_sse",
            "client_abort",
        }:
            raise ValueError("unsupported provider-double mode")
        delay = float(payload.get("delay_seconds", 0.0))
        if delay < 0 or delay > 600:
            raise ValueError("delay_seconds out of bounds")
        pause = float(payload.get("stream_pause_seconds", 0.0))
        if pause < 0 or pause > 600:
            raise ValueError("stream_pause_seconds out of bounds")
        completion = payload.get("completion")
        if completion is not None and (not isinstance(completion, str) or len(completion) > 512):
            raise ValueError("completion must be a short string")
        with self.lock:
            self.mode = mode
            self.delay_seconds = delay
            self.stream_pause_seconds = pause
            if isinstance(completion, str) and completion:
                self.completion = completion
            extra_canaries = payload.get("canaries", [])
            if isinstance(extra_canaries, list):
                self.canaries.update(value for value in extra_canaries if isinstance(value, str) and value)

    def observe(self, path: str, authorization: str | None, body: bytes) -> None:
        body_text = body.decode("utf-8", errors="replace")
        with self.lock:
            self.requests += 1
            self.paths[path] = self.paths.get(path, 0) + 1
            if authorization == f"Bearer {EXPECTED_KEY}":
                self.auth_ok += 1
            else:
                self.auth_bad += 1
            if any(canary in body_text for canary in self.canaries):
                self.canary_seen = True

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "mode": self.mode,
                "requests": self.requests,
                "auth_ok": self.auth_ok,
                "auth_bad": self.auth_bad,
                "canary_seen": self.canary_seen,
                "paths": dict(self.paths),
                "stream_pause_seconds": self.stream_pause_seconds,
            }


STATE = State()


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def chat_response(model: str, completion: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-qualification",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": completion},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    }


def chat_chunks(model: str, completion: str) -> list[dict[str, object]]:
    return [
        {
            "id": "chatcmpl-qualification",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": completion}, "finish_reason": None}
            ],
        },
        {
            "id": "chatcmpl-qualification",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        },
    ]


def responses_response(model: str, completion: str) -> dict[str, object]:
    return {
        "id": "resp-qualification",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": model,
        "output": [
            {
                "id": "msg-qualification",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": completion, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        "store": False,
    }


def responses_events(model: str, completion: str) -> list[dict[str, object]]:
    completed = responses_response(model, completion)
    return [
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {"id": "resp-qualification", "object": "response", "created_at": 1, "status": "in_progress", "model": model},
        },
        {
            "type": "response.output_text.delta",
            "sequence_number": 1,
            "item_id": "msg-qualification",
            "output_index": 0,
            "content_index": 0,
            "delta": "qualification-output",
        },
        {"type": "response.completed", "sequence_number": 2, "response": completed},
    ]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: int, payload: object) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 2_000_000:
            raise ValueError("request body too large")
        return self.rfile.read(length)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        if self.path == "/state":
            self._send(200, STATE.snapshot())
            return
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "qualification"}]})
            return
        self._send(404, {"error": {"message": "not found", "type": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/control":
            try:
                STATE.configure(json.loads(self._read_body() or b"{}"))
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": {"message": str(exc), "type": "invalid_request"}})
                return
            self._send(200, STATE.snapshot())
            return

        if not self.path.startswith("/v1/"):
            self._send(404, {"error": {"message": "not found", "type": "not_found"}})
            return

        body = self._read_body()
        STATE.observe(self.path, self.headers.get("Authorization"), body)
        with STATE.lock:
            mode = STATE.mode
            delay = STATE.delay_seconds
            completion = STATE.completion
        if mode == "timeout":
            time.sleep(delay or 301.0)
        elif delay:
            time.sleep(delay)
        if mode == "http_error":
            self._send(503, {"error": {"message": "qualification provider failure", "type": "upstream_error", "code": "qualification_provider_error"}})
            return

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            request = {}
        model = request.get("model") if isinstance(request, dict) else None
        model = model if isinstance(model, str) else MODEL
        streaming = bool(request.get("stream")) if isinstance(request, dict) else False
        if mode == "malformed_json" and not streaming:
            self._send(200, "{" + (os.environ.get("MALFORMED_CANARY") or "qualification-malformed-json"))
            return
        if mode in {"malformed_sse", "incomplete_sse", "client_abort"} or streaming:
            self._send_sse(self.path, model, mode, completion)
            return
        payload = responses_response(model, completion) if self.path.endswith("/responses") else chat_response(model, completion)
        self._send(200, payload)

    def _send_sse(self, path: str, model: str, mode: str, completion: str) -> None:
        events: list[object]
        if mode == "malformed_sse":
            events = ["data: {" + (os.environ.get("MALFORMED_CANARY") or "qualification-malformed-sse") + "\n\n"]
        elif path.endswith("/responses"):
            events = [f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in responses_events(model, completion)]
        else:
            events = [f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in chat_chunks(model, completion)]
        if mode == "incomplete_sse":
            events = events[:1]
        if mode == "client_abort":
            events = events[:1]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in events:
            if isinstance(event, str):
                data = event.encode("utf-8")
            else:
                data = str(event).encode("utf-8")
            try:
                self.wfile.write(data)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            if mode == "client_abort":
                time.sleep(0.2)
            elif STATE.stream_pause_seconds and event is events[0]:
                time.sleep(STATE.stream_pause_seconds)
            else:
                time.sleep(0.03)
        if mode not in {"incomplete_sse", "client_abort", "malformed_sse"}:
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
