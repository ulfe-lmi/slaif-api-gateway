#!/usr/bin/env python3
"""Verify the generated Codex profile-v2 layout against numeric loopback only."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from slaif_gateway.services.codex_qualification import (
    CODEX_CLI_VERSION,
    CODEX_MODEL,
    CodexProfileArtifacts,
    render_codex_profile,
)

try:
    import capture_codex_protocol as capture
except ModuleNotFoundError:  # Imported as a namespace package by unit tests.
    from scripts import capture_codex_protocol as capture


CODEX_BINARY = Path("/usr/bin/codex")
PROFILE_NAME = "slaif"
PROVIDER_NAME = "slaif"
SAFE_FINAL_MARKER = "SLAIF_CODEX_PROFILE_OK"
SAFE_PROMPT = "Return the verifier marker only."
EXPECTED_REQUESTS = 1
MAX_SUBPROCESS_OUTPUT_BYTES = 512_000


class VerificationError(RuntimeError):
    """A fixed verifier failure that contains no request, response, or secret data."""


def parse_verifier_arguments(arguments: Sequence[str]) -> None:
    """Reject every argument without reflecting operator-controlled text."""

    if arguments:
        raise VerificationError("Verifier accepts no arguments.")


@dataclass(frozen=True, slots=True)
class RequestFacts:
    model_matched: bool
    content_encoding_absent: bool
    authorization_present: bool
    streamed_responses_json: bool


MOCK_EVENTS: tuple[dict[str, object], ...] = (
    {"type": "response.created", "response": {"id": "resp_profile_v2"}},
    {
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": "msg_profile_v2",
            "status": "in_progress",
            "role": "assistant",
            "content": [],
        },
    },
    {
        "type": "response.output_text.delta",
        "item_id": "msg_profile_v2",
        "output_index": 0,
        "content_index": 0,
        "delta": SAFE_FINAL_MARKER,
    },
    {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": "msg_profile_v2",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": SAFE_FINAL_MARKER}],
        },
    },
    {
        "type": "response.completed",
        "response": {
            "id": "resp_profile_v2",
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


def validate_profile_documents(artifacts: CodexProfileArtifacts) -> None:
    """Validate the exact separate, credential-free profile-v2 documents."""

    base = tomllib.loads(artifacts.base_config_toml)
    profile = tomllib.loads(artifacts.profile_config_toml)
    if base != {
        "model_providers": {
            PROVIDER_NAME: {
                "name": "OpenAI",
                "base_url": base["model_providers"][PROVIDER_NAME]["base_url"],
                "env_key": "OPENAI_API_KEY",
                "wire_api": "responses",
                "requires_openai_auth": False,
                "supports_websockets": False,
            }
        }
    }:
        raise VerificationError("Generated base provider fragment was not exact.")
    if profile != {
        "model": CODEX_MODEL,
        "model_provider": PROVIDER_NAME,
        "features": {"remote_compaction_v2": False},
    }:
        raise VerificationError("Generated named profile-v2 document was not exact.")
    combined = artifacts.base_config_toml + artifacts.profile_config_toml
    forbidden = (
        "model_catalog_json",
        "profile =",
        "[profiles",
        "sk-",
        "SLAIF_CODEX_PROFILE_DUMMY",
    )
    if any(value in combined for value in forbidden):
        raise VerificationError("Generated profile documents contained a forbidden value.")


def build_codex_command(*, workdir: Path) -> list[str]:
    """Build the command that applies the named profile without model/provider overrides."""

    return [
        str(CODEX_BINARY),
        "--ask-for-approval",
        "never",
        "--profile",
        PROFILE_NAME,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(workdir),
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        'model_reasoning_effort="low"',
        "-c",
        'model_verbosity="low"',
        "-c",
        "model_providers.slaif.request_max_retries=0",
        "-c",
        "model_providers.slaif.stream_max_retries=0",
        "-c",
        "model_providers.slaif.stream_idle_timeout_ms=5000",
        SAFE_PROMPT,
    ]


def _sse_body() -> bytes:
    return "".join(
        "event: "
        + str(event["type"])
        + "\ndata: "
        + json.dumps(event, sort_keys=True, separators=(",", ":"))
        + "\n\n"
        for event in MOCK_EVENTS
    ).encode("ascii")


def _write_response(connection: socket.socket) -> None:
    body = _sse_body()
    connection.sendall(
        b"\r\n".join(
            (
                b"HTTP/1.1 200 OK",
                b"Content-Type: text/event-stream",
                f"Content-Length: {len(body)}".encode("ascii"),
                b"Connection: close",
                b"",
                body,
            )
        )
    )


def validate_request(request: capture.ParsedHttpRequest) -> RequestFacts:
    """Reduce one bounded raw request to safe booleans without returning content."""

    if request.method != "POST" or request.target != "/v1/responses":
        raise VerificationError("Loopback received an unexpected HTTP target.")
    headers = {name.lower(): value for name, value in request.headers}
    if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise VerificationError("Codex request was not ordinary Responses JSON.")
    content_encoding_absent = "content-encoding" not in headers
    if not content_encoding_absent:
        raise VerificationError("Codex request unexpectedly used content encoding.")
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("Codex request JSON was malformed.") from exc
    if not isinstance(body, dict):
        raise VerificationError("Codex request JSON was not an object.")
    model_matched = body.get("model") == CODEX_MODEL
    streamed_responses_json = body.get("stream") is True
    authorization_present = bool(headers.get("authorization"))
    del body
    if not model_matched or not streamed_responses_json or not authorization_present:
        raise VerificationError("Codex request did not match the selected profile.")
    return RequestFacts(
        model_matched=model_matched,
        content_encoding_absent=content_encoding_absent,
        authorization_present=authorization_present,
        streamed_responses_json=streamed_responses_json,
    )


class ProfileLoopbackServer:
    """A single-request server bound only to IPv4 numeric loopback."""

    def __init__(self) -> None:
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.facts: RequestFacts | None = None
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
            raise VerificationError("Verifier server was not bound to numeric loopback.")
        self._listener = listener
        self.port = int(address[1])
        self._thread = threading.Thread(
            target=self._serve,
            name="codex-profile-v2-loopback",
            daemon=True,
        )
        self._thread.start()

    def _serve(self) -> None:
        assert self._listener is not None
        deadline = time.monotonic() + capture.SERVER_TIMEOUT_SECONDS
        try:
            while not self._stop.is_set() and time.monotonic() < deadline:
                try:
                    connection, peer = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if not self._stop.is_set():
                        self.error = VerificationError("Loopback transport failed safely.")
                    return
                with connection:
                    if peer[0] != "127.0.0.1":
                        self.error = VerificationError("A non-loopback peer was rejected.")
                        return
                    try:
                        raw = capture._read_bounded_request(connection)
                        request = capture._parse_http_request(raw)
                        self.facts = validate_request(request)
                        del request, raw
                        _write_response(connection)
                        return
                    except (capture.CaptureError, VerificationError, OSError):
                        self.error = VerificationError("Loopback request validation failed safely.")
                        return
            if not self._stop.is_set():
                self.error = VerificationError("Codex made no bounded loopback request.")
        finally:
            if "raw" in locals():
                del raw

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def result(self) -> RequestFacts:
        if self.error is not None:
            raise self.error
        if self.facts is None:
            raise VerificationError("Verifier requires exactly one loopback request.")
        return self.facts


def _isolated_environment(codex_home: Path) -> dict[str, str]:
    dead_proxy = "http://127.0.0.1:9"
    return {
        "ALL_PROXY": dead_proxy,
        "CODEX_HOME": str(codex_home),
        "HOME": str(codex_home),
        "HTTPS_PROXY": dead_proxy,
        "HTTP_PROXY": dead_proxy,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1",
        "OPENAI_API_KEY": "SLAIF_CODEX_PROFILE_DUMMY",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RUST_BACKTRACE": "0",
        "XDG_CACHE_HOME": str(codex_home / "cache"),
        "XDG_CONFIG_HOME": str(codex_home / "config"),
        "XDG_DATA_HOME": str(codex_home / "data"),
        "all_proxy": dead_proxy,
        "http_proxy": dead_proxy,
        "https_proxy": dead_proxy,
        "no_proxy": "127.0.0.1",
    }


def _validate_completed(stdout: bytes, stderr: bytes) -> None:
    if len(stdout) > MAX_SUBPROCESS_OUTPUT_BYTES or len(stderr) > MAX_SUBPROCESS_OUTPUT_BYTES:
        raise VerificationError("Codex subprocess output exceeded the safe bound.")
    event_types: set[str] = set()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            event_types.add(event["type"])
    if "turn.completed" not in event_types:
        raise VerificationError("Codex did not complete the bounded profile turn.")
    combined = (stdout + b"\n" + stderr).lower()
    if any(
        marker in combined
        for marker in (
            b"legacy profile",
            b"model catalog",
            b"model_catalog",
            b"catalog decode",
            b"decode model",
        )
    ):
        raise VerificationError("Codex emitted a forbidden profile/catalog warning.")


def verify() -> dict[str, object]:
    version = capture.verify_codex_version(CODEX_BINARY, CODEX_CLI_VERSION)
    server = ProfileLoopbackServer()
    result: subprocess.CompletedProcess[bytes] | None = None
    facts: RequestFacts | None = None
    with tempfile.TemporaryDirectory(prefix="slaif-codex-profile-v2-") as root_name:
        root = Path(root_name)
        codex_home = root / "codex-home"
        workdir = root / "empty-workdir"
        codex_home.mkdir(mode=0o700)
        workdir.mkdir(mode=0o700)
        server.start()
        assert server.port is not None
        artifacts = render_codex_profile(f"http://127.0.0.1:{server.port}/v1")
        validate_profile_documents(artifacts)
        base_target = codex_home / "config.toml"
        profile_target = codex_home / "slaif.config.toml"
        base_target.write_text(artifacts.base_config_toml, encoding="utf-8")
        profile_target.write_text(artifacts.profile_config_toml, encoding="utf-8")
        base_target.chmod(0o600)
        profile_target.chmod(0o600)
        environment = _isolated_environment(codex_home)
        try:
            result = subprocess.run(
                build_codex_command(workdir=workdir),
                check=False,
                capture_output=True,
                env=environment,
                timeout=capture.CODEX_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VerificationError("Codex profile subprocess failed safely.") from exc
        finally:
            server.stop()
        facts = server.result()
        if "SLAIF_CODEX_PROFILE_DUMMY" in base_target.read_text() or (
            "SLAIF_CODEX_PROFILE_DUMMY" in profile_target.read_text()
        ):
            raise VerificationError("A dummy credential was written to profile files.")

    assert result is not None and facts is not None
    if result.returncode != 0:
        raise VerificationError("Codex profile subprocess exited unsuccessfully.")
    _validate_completed(result.stdout, result.stderr)
    del result
    return {
        "result": "OK",
        "cli_version": version,
        "cli_version_matched": version == CODEX_CLI_VERSION,
        "profile_v2_applied": True,
        "model_matched": facts.model_matched,
        "provider_matched": True,
        "bundled_catalog_used": True,
        "v1_compaction_selected": True,
        "request_count": EXPECTED_REQUESTS,
        "content_encoding_absent": facts.content_encoding_absent,
        "loopback_only": True,
        "raw_payloads_persisted": False,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parse_verifier_arguments(sys.argv[1:] if arguments is None else arguments)
        summary = verify()
    except (capture.CaptureError, VerificationError) as exc:
        print(f"RESULT=ERROR\nERROR={exc}", file=sys.stderr)
        return 1
    for key, value in summary.items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        print(f"{key.upper()}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
