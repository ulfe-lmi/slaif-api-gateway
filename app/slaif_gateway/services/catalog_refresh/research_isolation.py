"""Objective 183 (R2): the ONE minimal enforced execution boundary for the
isolated Codex researcher.

Whole-process isolation (CLI AND spawned tools/children) is provided by a
per-task Docker boundary on the verified local daemon
(``unix:///var/run/docker.sock``, used by EVERY control command):

- the researcher container is nonroot (uid 65534), read-only root
  filesystem, caps dropped, no-new-privileges, PID/memory/CPU bounded,
  task-only mounts (the verified pinned static binary, the owned task
  workspace - all inputs read-only; the empty parent-created task-local
  CODEX_HOME/home/outputs are writable scratch the CLI itself uses, and they
  hold no auth material), and NO inherited host environment (the container
  env is verified after create to contain ONLY the image base variables and
  the explicit task variables);
- the researcher joins ONLY a task-internal bridge network created with
  ``--internal`` AND the standard isolated gateway mode
  (``com.docker.network.bridge.gateway_mode_ipv4=isolated``, IPv6 disabled);
  the actual ``.Internal``/``.EnableIPv6``/``.Options`` flags are
  re-verified from the daemon, and the network is re-verified at
  researcher-attach time;
- BEFORE any model work an owned probe container on that internal network
  proves the boundary: the task relay is reachable (readiness from an
  isolated-network PEER, never a host socket to the container IP) while an
  owned host canary listener on the egress bridge, the external internet,
  the upstream host, and host canary files (repo/docker-socket/codex-home)
  are all UNreachable/absent. Any failure or unexpected connectivity
  REFUSES the task (no researcher container is ever started);
- the ONLY model connection is a task-owned relay container that validates
  the synthetic task credential, the exact path, and the configured model,
  and REFUSES non-inference authorities (background, hosted/container tools,
  any non-empty tool list, previous-response/conversation references,
  store) BEFORE serving or forwarding anything. In forward mode it proxies
  to the operator endpoint with the operator credential - held in a
  private task-owned 0400 file (never argv, never env, never logs) that the
  researcher never mounts and never sees;
- the structured result is the CLI's own final message written via
  ``--output-last-message`` directly to the ONE expected output path; the
  parent captures it with the existing anchored, no-follow, bounded
  regular-file reader on a held output-directory descriptor (links,
  specials, growing files, and oversize results are refused);
- an unavailable boundary REFUSES research (safe code); there is never an
  unsandboxed fallback to host execution.

Cleanup tracks the EXACT created resource IDs and, in ``finally`` semantics
(ordinary Python exceptions included), removes ONLY label-verified owned
resources. A resource that cannot be removed makes the result
observable (``cleanup_errors``) and a would-be success is refused
(``cleanup_incomplete``) - success is never claimed while resources remain.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import filesystem as fs

# Pinned official base image BY DIGEST (tag inspection is unreliable on
# migrated hosts; the digest is the exact qualified image). The static-pie
# codex binary runs unmodified inside it (verified in the preflight
# capability probe).
RESEARCH_IMAGE = "python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f"
# Candidate internal subnets (private, outside Docker's default pool); the
# first creatable one is used. The gateway is .1 of the subnet.
_INTERNAL_SUBNETS: tuple[tuple[str, str], ...] = (
    ("10.183.0.0/24", "10.183.0.1"),
    ("10.184.0.0/24", "10.184.0.1"),
    ("10.185.0.0/24", "10.185.0.1"),
)
DOCKER_CMD_TIMEOUT = 60  # seconds per control command (create/inspect/rm)
IMAGE_PULL_TIMEOUT = 300
RESEARCHER_PORT = 8787
MAX_RESULT_BYTES = 256 * 1024
MAX_CLI_BYTES = 512 * 1024 * 1024
MAX_RELAY_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RELAY_RESPONSE_BYTES = 8 * 1024 * 1024
# Fixed nonroot, unprivileged fallback user for the researcher CLI when the
# invoking process is root (a nonroot invocation runs the researcher as the
# invoking user, matching the relay/probe convention, so the parent-owned
# workspace stays parent-cleanable).
RESEARCHER_UID = "65534:65534"
# The verified local Docker daemon endpoint (183 preflight). Every control
# command uses EXACTLY this endpoint.
_DOCKER = ["docker", "-H", "unix:///var/run/docker.sock"]

# Image-provided env names of the pinned base image (measured via
# ``docker image inspect`` on the digest). Any other variable inside a
# task container is a refusal.
_IMAGE_ENV_NAMES = frozenset({"PATH", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"})
_RESEARCHER_ENV_ALLOW = _IMAGE_ENV_NAMES | {
    "HOME", "CODEX_HOME", "LANG", "PYTHONUNBUFFERED", "SLAIF_RESEARCH_API_KEY",
}
_RELAY_ENV_ALLOW = _IMAGE_ENV_NAMES | {
    "SLAIF_RELAY_TASK_KEY", "SLAIF_RELAY_MODEL", "SLAIF_RELAY_MODE",
    "SLAIF_RELAY_LOG", "SLAIF_RELAY_CANNED_SSE", "SLAIF_RELAY_UPSTREAM_BASE",
    "SLAIF_RELAY_UPSTREAM_KEY_FILE", "SLAIF_RELAY_ALLOW_HTTP",
    "SLAIF_RELAY_TOOL_SEQUENCE", "SLAIF_RELAY_MARKERS_FILE",
}
_PROBE_ENV_ALLOW = _IMAGE_ENV_NAMES

__all__ = [
    "RESEARCH_IMAGE",
    "TaskExecution",
    "verify_cli_binary",
    "write_relay_assets",
    "execute_task",
]


class _BoundaryUnavailable(Exception):
    """Safe refusal (code only; never raw error text)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class TaskExecution:
    """One measured, bounded task execution (or an honest refusal)."""

    status: str  # "completed" | "unavailable" | "child_failure"
    failure_code: str | None = None
    exit_code: int | None = None
    elapsed_ms: int = 0
    output_bytes: bytes | None = None
    output_sha256: str | None = None
    probe: dict[str, Any] = field(default_factory=dict)
    relay_requests: int = 0
    detail: str = ""
    cleanup_errors: tuple[str, ...] = ()
    # The EXACT ownership label and created resource IDs of this
    # invocation (label-verified cleanup). Consumers can verify each owned
    # ID is gone by label filter - no global before/after diff, no
    # prefix-matching sweep.
    owned_label: str = ""
    owned_ids: tuple[str, ...] = ()


def _docker(*args: str, timeout: int = DOCKER_CMD_TIMEOUT) -> str:
    proc = subprocess.run(
        [*_DOCKER, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker {args[0]} failed rc={proc.returncode}")
    return proc.stdout.strip()


def _docker_ok(*args: str, timeout: int = DOCKER_CMD_TIMEOUT) -> bool:
    """True ONLY for returncode 0; any other rc or transport error is False."""
    try:
        proc = subprocess.run(
            [*_DOCKER, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _inspect_labels(kind: str, ref: str, label: str) -> bool:
    """Ownership check BEFORE any removal: the label nonce must match.

    Containers carry labels under ``.Config.Labels``; networks under
    ``.Labels``. The ``key=value`` argument is split before the lookup so a
    correctly matching owned label is accepted (and nothing else is).
    """
    key, sep, value = label.partition("=")
    if not sep or not key or not value:
        return False
    fmt = "{{json .Config.Labels}}" if kind == "container" else "{{json .Labels}}"
    try:
        raw = _docker(kind, "inspect", "--format", fmt, ref)
        labels = json.loads(raw or "{}")
    except Exception:
        return False
    return isinstance(labels, dict) and labels.get(key) == value


def verify_cli_binary(path: str) -> str:
    """Parent-side verification of the real CLI binary before mounting.

    Returns the SHA-256 (64 hex) or raises _BoundaryUnavailable. The binary
    must be a regular file of bounded size; the hash is the identity the
    task identity records (never assumed).
    """
    try:
        resolved = Path(path).resolve()
        st = resolved.stat()
        if not st.st_size or st.st_size > MAX_CLI_BYTES:
            raise _BoundaryUnavailable("cli_unbounded")
        digest = hashlib.sha256()
        with open(resolved, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except _BoundaryUnavailable:
        raise
    except (OSError, ValueError):
        raise _BoundaryUnavailable("cli_unavailable") from None


# --- embedded task assets (stdlib only; no dependencies in the image) -------

_RELAY_SCRIPT = r'''
"""SLAIF 183 research relay: the ONLY model-egress path for the researcher.

Inference-only: validates the synthetic task credential, the exact path,
and the configured model, then REFUSES non-inference request authorities
(background, hosted/container tools, any non-empty tool list,
previous-response/conversation references, store) BEFORE serving or
forwarding. Mock mode serves the parent-prepared response; forward mode
proxies to the operator endpoint with the operator credential read from a
private task-owned file (never argv/env/logs; the researcher never holds
it). Redirects refused, TLS verified (urllib defaults) for real external
endpoints, HTTP upstreams only when explicitly flagged as owned synthetic
mocks, finite timeout, finite request/response bounds (an oversized
upstream response is refused, never truncated into a success). Never logs
credential material.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hashlib

TASK_KEY = os.environ["SLAIF_RELAY_TASK_KEY"]
MODEL = os.environ["SLAIF_RELAY_MODEL"]
MODE = os.environ.get("SLAIF_RELAY_MODE", "mock")
UPSTREAM_BASE = os.environ.get("SLAIF_RELAY_UPSTREAM_BASE", "")
KEY_FILE = os.environ.get("SLAIF_RELAY_UPSTREAM_KEY_FILE", "")
ALLOW_HTTP = os.environ.get("SLAIF_RELAY_ALLOW_HTTP", "") == "1"
CANNED_SSE = os.environ.get("SLAIF_RELAY_CANNED_SSE", "")
LOG_PATH = os.environ.get("SLAIF_RELAY_LOG", "/tmp/relay.log")
MAX_REQUEST = 2 * 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
# Qualification-only mock-model tool loop: prepared intermediate
# function-call turns (the REAL CLI executes the local tools inside the
# enforced worker; the relay only serves the parent-prepared replies) and
# safe observations (per request the relay logs which marker NAMES appeared
# in the request body and, per call_id, which markers appear in the ACTUAL
# function_call_output content - the same text also occurs in function_call
# arguments/history without execution, so output checks are call_id-matched;
# raw values and tool output are never logged).
TOOL_SEQUENCE = os.environ.get("SLAIF_RELAY_TOOL_SEQUENCE", "")
MARKERS_FILE = os.environ.get("SLAIF_RELAY_MARKERS_FILE", "")
TURN_DELIM = "@@SLAIF_MOCK_TURN@@"
MARKERS = {}
if MARKERS_FILE:
    try:
        with open(MARKERS_FILE, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in loaded.items()
        ):
            MARKERS = {k: v for k, v in loaded.items() if v}
    except (OSError, ValueError):
        MARKERS = {}


def _next_turn():
    state = LOG_PATH + ".turn"
    n = 0
    try:
        with open(state, "r", encoding="utf-8") as handle:
            n = int(handle.read().strip() or "0")
    except (OSError, ValueError):
        n = 0
    n += 1
    try:
        with open(state, "w", encoding="utf-8") as handle:
            handle.write(str(n))
    except OSError:
        pass
    return n

# Reviewed LOCAL (client-executed) tool catalog for codex-cli 0.162.1,
# measured from the synthetic request inside the enforced nonroot worker
# (see 183-a tool inventory). These declarations execute only inside the
# independently enforced researcher container (task-only FS, isolated
# network, no credentials); they do NOT authorize provider tool execution
# or network access. Anything else - hosted web/search/container tools,
# MCP/connectors, unknown types/names/schemas - is refused before any
# serve/forward. Request content can never enlarge this catalog.
def _tool_sha(parameters):
    return hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

# Minimal reviewed catalog: the qualified codex-cli 0.162.1 invocation
# (web_search="disabled", features.multi_agent=false, features.goals=false,
# --disable view_image - all verified against the actual request) advertises
# exactly these local declarations. exec_command/write_stdin perform file
# reads and PTY commands INSIDE the enforced worker; request_user_input is a
# core exec tool that is inert in non-interactive exec. Unneeded
# delegation/goal/image tools are disabled at the CLI and would be refused
# here anyway.
_LOCAL_FUNCTIONS = {
    ("function", "exec_command", "737c530cc1b1ec463c14971d7bd4e1066ad2d6d3f525a40acc83199996818451"),
    ("function", "write_stdin", "acec976d202087f8bccc24e24c10107dacc10a225824a9d08ca80e6c28aad6fb"),
    ("function", "request_user_input", "23ee6f1a8cd81c9d2491cbd33a3cb09d755e6c85d368f3beb346753cfd4558a3"),
}
_LOCAL_NAMESPACES: set = set()
_LOCAL_TOOL_NAMES = {name for _t, name, _s in _LOCAL_FUNCTIONS}

if MODE == "forward":
    scheme = UPSTREAM_BASE.split("://", 1)[0].lower()
    if scheme == "https":
        pass
    elif scheme == "http" and ALLOW_HTTP:
        pass
    else:
        raise SystemExit("upstream scheme refused")


def _log(entry):
    try:
        with open(LOG_PATH, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _upstream_key():
    with open(KEY_FILE, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _authority_violation(request):
    """Non-inference authorities are refused BEFORE any serve/forward."""
    if request.get("background"):
        return "background"
    if "hosted_tools" in request or "container" in request:
        return "hosted"
    if "previous_response_id" in request or "conversation" in request:
        return "state_reference"
    if request.get("store"):
        return "store"
    tools = request.get("tools")
    if tools is None:
        return None
    if not isinstance(tools, list):
        return "tools_shape"
    for tool in tools:
        if not isinstance(tool, dict):
            return "tools_unreviewed"
        ttype = tool.get("type")
        if ttype == "function":
            if ("function", tool.get("name"), _tool_sha(tool.get("parameters"))) not in _LOCAL_FUNCTIONS:
                return "tools_unreviewed"
        elif ttype == "namespace":
            inner = []
            for item in tool.get("tools") or []:
                if not isinstance(item, dict) or item.get("type") != "function":
                    return "tools_unreviewed"
                inner.append(("function", item.get("name"), _tool_sha(item.get("parameters"))))
            key = ("namespace", tool.get("name"), tuple(sorted(inner)))
            if key not in _LOCAL_NAMESPACES:
                return "tools_unreviewed"
        else:
            # web_search / file_search / code_interpreter / mcp / computer_use /
            # custom / anything unknown: provider-hosted authority refused
            return "tools_unreviewed"
    choice = request.get("tool_choice")
    if isinstance(choice, str) and choice not in ("auto", "none", "required"):
        if choice not in _LOCAL_TOOL_NAMES:
            return "tool_choice_unreviewed"
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _reject(self, code, message):
        self._send(code, json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode())

    def _auth_ok(self):
        return self.headers.get("authorization", "") == "Bearer " + TASK_KEY

    def do_GET(self):
        if self.path == "/v1/ping":
            self._send(200, b'{"ok":true}')
            _log({"path": self.path, "result": "ping"})
        elif self.path == "/v1/models":
            body = json.dumps({"object": "list", "data": [{"id": MODEL, "object": "model"}]}).encode()
            self._send(200, body)
            _log({"path": self.path, "result": "models"})
        else:
            self._reject(404, "not found")
            _log({"path": self.path, "result": "not_found"})

    def do_POST(self):
        if self.path != "/v1/responses":
            self._reject(404, "not found")
            _log({"path": self.path, "result": "not_found"})
            return
        if not self._auth_ok():
            self._reject(401, "unauthorized")
            _log({"path": self.path, "result": "rejected_auth"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        if length > MAX_REQUEST:
            self._reject(413, "request too large")
            _log({"path": self.path, "result": "rejected_oversize"})
            return
        body = self.rfile.read(length) if 0 < length <= MAX_REQUEST else b""
        try:
            request = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._reject(400, "invalid json")
            _log({"path": self.path, "result": "rejected_bad_json"})
            return
        if not isinstance(request, dict) or request.get("model") != MODEL:
            self._reject(400, "model mismatch")
            _log({"path": self.path, "result": "rejected_model"})
            return
        violation = _authority_violation(request)
        if violation:
            self._reject(400, "authority refused")
            _log({"path": self.path, "result": "rejected_authority_" + violation})
            return
        if MODE == "mock":
            body_text = body.decode("utf-8", "replace")
            markers_present = None
            if MARKERS:
                markers_present = {name: (value in body_text) for name, value in MARKERS.items()}
            # Per-call observation of ACTUAL local-tool results: only
            # input items of type function_call_output are inspected
            # (call_id-matched), with a digest plus marker presence; the
            # raw output text is never logged.
            call_outputs = None
            request_input = request.get("input")
            if isinstance(request_input, list):
                collected = []
                for item in request_input:
                    if not isinstance(item, dict) or item.get("type") != "function_call_output":
                        continue
                    raw_output = item.get("output")
                    text = (
                        raw_output
                        if isinstance(raw_output, str)
                        else json.dumps(raw_output, ensure_ascii=False)
                    )
                    record = {
                        "call_id": item.get("call_id"),
                        "output_sha256": hashlib.sha256(
                            text.encode("utf-8", "replace")
                        ).hexdigest(),
                    }
                    if MARKERS:
                        record["markers"] = {
                            name: (value in text) for name, value in MARKERS.items()
                        }
                    collected.append(record)
                call_outputs = collected
            if TOOL_SEQUENCE:
                try:
                    with open(TOOL_SEQUENCE, "rb") as handle:
                        sequence = handle.read(2 * 1024 * 1024)
                except OSError:
                    self._reject(500, "canned unavailable")
                    _log({"path": self.path, "result": "canned_unavailable"})
                    return
                blocks = [
                    b for b in sequence.decode("utf-8", "replace").split(TURN_DELIM) if b.strip()
                ]
                n = _next_turn()
                if n <= len(blocks):
                    sse = blocks[n - 1].encode("utf-8")
                    turn = f"tool_turn_{n}"
                else:
                    try:
                        with open(CANNED_SSE, "rb") as handle:
                            sse = handle.read(2 * 1024 * 1024)
                    except OSError:
                        self._reject(500, "canned unavailable")
                        _log({"path": self.path, "result": "canned_unavailable"})
                        return
                    turn = "final"
            else:
                try:
                    with open(CANNED_SSE, "rb") as handle:
                        sse = handle.read(2 * 1024 * 1024)
                except OSError:
                    self._reject(500, "canned unavailable")
                    _log({"path": self.path, "result": "canned_unavailable"})
                    return
                turn = "canned"
            self._send(200, sse, "text/event-stream")
            entry = {"path": self.path, "model": MODEL, "result": "mock_served", "turn": turn}
            if markers_present is not None:
                entry["body_markers"] = markers_present
            if call_outputs:
                entry["call_outputs"] = call_outputs
            _log(entry)
            return
        url = UPSTREAM_BASE.rstrip("/") + "/responses"
        forward = urllib.request.Request(url, data=body, method="POST")
        for header in ("accept", "content-type"):
            value = self.headers.get(header)
            if value:
                forward.add_header(header, value)
        forward.add_header("authorization", "Bearer " + _upstream_key())

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise RuntimeError("redirect_following_refused")

        try:
            with urllib.request.build_opener(NoRedirect).open(forward, timeout=60) as response:
                payload = response.read(MAX_RESPONSE + 1)
                status = response.status
                content_type = response.headers.get("content-type", "text/event-stream")
        except Exception as exc:  # safe code only
            self._reject(502, "upstream error")
            _log({"path": self.path, "model": MODEL, "result": "forward_failed", "error": type(exc).__name__})
            return
        if len(payload) > MAX_RESPONSE:
            self._reject(502, "upstream response too large")
            _log({"path": self.path, "model": MODEL, "result": "upstream_oversized"})
            return
        if status != 200:
            self._reject(502, "upstream error")
            _log({"path": self.path, "model": MODEL, "result": "upstream_status", "status": status})
            return
        self._send(status, payload, content_type)
        _log({"path": self.path, "model": MODEL, "result": "forwarded", "status": status})


ThreadingHTTPServer(("0.0.0.0", 8787), Handler).serve_forever()
'''

_PROBE_SCRIPT = r'''
"""SLAIF 183 researcher-network boundary probe: an owned peer container on
the researcher (isolated internal) network that proves, BEFORE any model
work: the task relay is reachable (readiness from an isolated-network
peer) while the owned host canary listener, the external internet, the
upstream host, and host canary files are all unreachable/absent."""
import json
import os
import socket
import sys


def try_connect(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


relay_ip, relay_port, canary_ip, canary_port, external, upstream_host, canaries, upstream_port = sys.argv[1:9]
canary_paths = [p for p in canaries.split(",") if p]
result = {
    "relay_reachable": try_connect(relay_ip, int(relay_port)),
    "host_canary_reachable": try_connect(canary_ip, int(canary_port)) if canary_ip else False,
    "external_reachable": try_connect(external, 443),
    "canaries_present": [p for p in canary_paths if os.path.exists(p)],
}
if upstream_host:
    # the ACTUAL configured upstream endpoint (host + port from the URL)
    result["upstream_direct_reachable"] = try_connect(upstream_host, int(upstream_port))
print(json.dumps(result))
'''


def _canned_sse(model: str, result_json: str) -> bytes:
    """The prepared mock-model SSE sequence (measured CLI acceptance order).

    The delta carries the prepared structured result verbatim; the CLI's
    --output-schema validation is what accepts it.
    """
    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"

    response_base = {
        "id": "resp_mock_183",
        "object": "response",
        "created_at": 0,
        "status": "in_progress",
        "model": model,
        "output": [],
        "error": None,
        "usage": None,
    }
    parts = [
        sse("response.created", {"type": "response.created", "response": response_base}),
        sse(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"id": "msg_mock_183", "type": "message", "status": "in_progress", "role": "assistant", "content": []},
            },
        ),
        sse(
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "item_id": "msg_mock_183",
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
        ),
        sse(
            "response.output_text.delta",
            {
                "type": "response.output_text.delta",
                "item_id": "msg_mock_183",
                "output_index": 0,
                "content_index": 0,
                "delta": result_json,
            },
        ),
        sse(
            "response.output_text.done",
            {
                "type": "response.output_text.done",
                "item_id": "msg_mock_183",
                "output_index": 0,
                "content_index": 0,
                "text": result_json,
            },
        ),
        sse(
            "response.content_part.done",
            {
                "type": "response.content_part.done",
                "item_id": "msg_mock_183",
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": result_json, "annotations": []},
            },
        ),
        sse(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "msg_mock_183",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": result_json, "annotations": []}],
                },
            },
        ),
        sse(
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    **response_base,
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_mock_183",
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": result_json, "annotations": []}],
                        }
                    ],
                },
            },
        ),
    ]
    return "".join(parts).encode("utf-8")


def write_relay_assets(
    workspace: Path,
    *,
    model: str,
    mode: str,
    canned_result_json: str | None,
    upstream_key: str = "",
    tool_sequence_sse: bytes | None = None,
    body_markers: Mapping[str, str] | None = None,
) -> tuple[Path, Path]:
    """Parent-owned relay inputs (inside the task workspace, never in the
    repository). Returns (assets_dir, log_dir): assets is mounted read-only
    into the relay at /relay (the relay runs as the invoking UID, so the
    private 0500/0400 caller-owned files are readable), the log directory
    read-write at /relay-out. In forward mode the operator credential is a
    private 0400 file inside the read-only assets mount - never argv/env.

    ``tool_sequence_sse`` / ``body_markers`` are qualification-only mock
    assets (mock mode): prepared intermediate function-call turns and safe
    body-marker names for observing the real CLI's local-tool results.
    """
    assets = workspace / "relay"
    assets.mkdir(parents=True, exist_ok=True)
    assets.chmod(0o700)
    script = assets / "relay.py"
    script.write_text(_RELAY_SCRIPT, encoding="utf-8")
    script.chmod(0o500)
    if mode == "mock":
        canned = assets / "canned.sse"
        canned.write_bytes(_canned_sse(model, canned_result_json or "{}"))
        canned.chmod(0o400)
        if tool_sequence_sse is not None:
            seq = assets / "tool-sequence.sse"
            seq.write_bytes(tool_sequence_sse)
            seq.chmod(0o400)
        if body_markers:
            markers = assets / "body-markers.json"
            markers.write_text(json.dumps(dict(body_markers)), encoding="utf-8")
            markers.chmod(0o400)
    else:
        key_file = assets / "upstream-key"
        key_file.write_text(upstream_key, encoding="utf-8")
        key_file.chmod(0o400)
    log_dir = workspace / "relay-out"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_dir.chmod(0o755)
    return assets, log_dir


def _flat_env(entries: list[str]) -> list[str]:
    """Flat ``--env VALUE`` argv fragments (no nested lists)."""
    return [arg for entry in entries for arg in ("--env", entry)]


def _create_network(label: str, name: str, args: list[str]) -> str:
    return _docker("network", "create", *args, "--label", label, name)


def _upstream_target_from_url(url: str) -> tuple[str, int]:
    """Bounded parse of the configured upstream URL into (host, port).

    The port is the URL's explicit port, or the scheme default (443 https /
    80 http). The boundary probe must target the ACTUAL configured endpoint
    (not a fixed port), so the researcher-network negative is a meaningful
    refusal of the live upstream itself."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        raise ValueError("bad url")
    hostport = rest.split("/", 1)[0].split("@")[-1]
    if ":" in hostport:
        host, port_text = hostport.rsplit(":", 1)
        if not port_text.isdigit():
            raise ValueError("bad url")
        port = int(port_text)
    else:
        host, port = hostport, (443 if scheme == "https" else 80)
    if not (1 <= port <= 65535) or not host or any(ch in host for ch in (" ", '"', "'", "[", "]")):
        raise ValueError("bad url")
    return host, port


def _container_env_names(ref: str) -> set[str]:
    raw = _docker("inspect", "--format", "{{json .Config.Env}}", ref)
    entries = json.loads(raw or "[]")
    names: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            names.add(entry.split("=", 1)[0])
    return names


def _container_mounts(ref: str) -> dict[str, tuple[str, bool]]:
    """Destination -> (type, RW) for every mount of the container."""
    raw = _docker("inspect", "--format", "{{json .Mounts}}", ref)
    mounts: dict[str, tuple[str, bool]] = {}
    for entry in json.loads(raw or "[]"):
        if isinstance(entry, dict) and entry.get("Destination"):
            mounts[str(entry["Destination"])] = (str(entry.get("Type", "")), bool(entry.get("RW")))
    return mounts


def execute_task(
    workspace: Path,
    *,
    task_name: str,
    models_json: str,
    evidence_path: Path,
    agent_md: Path,
    output_schema: Path,
    cli_bin: str,
    cli_sha256: str,
    model_name: str,
    mode: str,
    canned_result_json: str | None = None,
    upstream_base: str = "",
    upstream_key: str = "",
    timeout_seconds: int = 120,
    repo_root: Path | None = None,
    external_probe_host: str = "1.1.1.1",
    upstream_http_allowed: bool = False,
    owned_egress: tuple[str, str] | None = None,
    extra_cli_args: tuple[str, ...] = (),
    mock_tool_sequence_sse: bytes | None = None,
    mock_body_markers: Mapping[str, str] | None = None,
) -> TaskExecution:
    """Run ONE research task inside its owned Docker boundary.

    ``workspace`` must be parent-owned scratch OUTSIDE ``repo_root``; the
    researcher mounts it read-only except ``workspace/outputs``. The
    structured result is captured with the anchored no-follow bounded
    reader from ``workspace/outputs/research-result.json`` (the CLI's own
    ``--output-last-message`` target - no tool-based file write).

    ``owned_egress`` (qualification only) reuses a caller-owned egress
    network ``(name, "key=value" label)`` - label-verified before reuse and
    NEVER removed by this boundary - so a test-owned synthetic upstream can
    share the relay's narrow egress segment.

    ``mock_tool_sequence_sse`` / ``mock_body_markers`` (qualification only,
    mock mode) drive the real CLI's local-tool loop: prepared intermediate
    function-call turns plus safe body-marker names so a test can observe
    which tool results reached the model without persisting raw tool output.
    """
    started = time.monotonic()
    nonce = secrets.token_hex(6)
    label = f"slaif.183.owned={nonce}"
    prefix = f"slaif-rs-{nonce}"
    internal_name = f"{prefix}-internal"
    egress_name = f"{prefix}-egress"
    relay_name = f"{prefix}-relay"
    researcher_name = f"{prefix}-researcher"
    probe_name = f"{prefix}-probe"
    timeout_seconds = max(10, min(600, int(timeout_seconds)))

    # exact created resources (kind, id, display name) for cleanup
    resources: list[tuple[str, str, str]] = []
    removed: set[str] = set()
    cleanup_errors: list[str] = []
    canary_holder: dict[str, socket.socket | None] = {"sock": None}

    def _cleanup_all() -> None:
        for kind, res_id, name in reversed(list(resources)):
            if res_id in removed:
                continue
            try:
                if not _inspect_labels(kind, res_id, label):
                    # the exact created IDs are tracked; a failed ownership
                    # check is an observable anomaly, never a silent skip
                    cleanup_errors.append(f"{kind}:{name}:ownership_check_failed")
                    continue
                if kind == "container":
                    _docker("rm", "--force", res_id)
                else:
                    _docker("network", "rm", res_id)
                removed.add(res_id)
            except Exception:
                cleanup_errors.append(f"{kind}:{name}")
        canary_sock = canary_holder.get("sock")
        if canary_sock is not None:
            try:
                canary_sock.close()
            except OSError:
                pass

    def finish(status: str, failure_code: str | None = None, **kwargs: Any) -> TaskExecution:
        # cleanup ONLY owned resources (label-verified), ALWAYS (including
        # after ordinary exceptions, via the caller's except handlers).
        _cleanup_all()
        detail_parts: list[str] = []
        if kwargs.get("detail"):
            detail_parts.append(str(kwargs["detail"]))
        if cleanup_errors:
            detail_parts.append("cleanup failures: " + ", ".join(cleanup_errors))
        if cleanup_errors and status == "completed":
            # never claim success while owned resources remain
            status = "child_failure"
            failure_code = "cleanup_incomplete"
            kwargs.pop("output_bytes", None)
            kwargs.pop("output_sha256", None)
        kwargs.pop("detail", None)  # folded into the detail above
        return TaskExecution(
            status=status,
            failure_code=failure_code,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            cleanup_errors=tuple(cleanup_errors),
            detail="; ".join(detail_parts),
            owned_label=label,
            owned_ids=tuple(res_id for _kind, res_id, _name in resources),
            **kwargs,
        )

    def register(kind: str, res_id: str, name: str) -> None:
        resources.append((kind, res_id, name))

    try:
        return _execute_inner(
            started=started,
            label=label,
            prefix=prefix,
            internal_name=internal_name,
            egress_name=egress_name,
            relay_name=relay_name,
            researcher_name=researcher_name,
            probe_name=probe_name,
            timeout_seconds=timeout_seconds,
            workspace=workspace,
            task_name=task_name,
            models_json=models_json,
            evidence_path=evidence_path,
            agent_md=agent_md,
            output_schema=output_schema,
            cli_bin=cli_bin,
            cli_sha256=cli_sha256,
            model_name=model_name,
            mode=mode,
            canned_result_json=canned_result_json,
            upstream_base=upstream_base,
            upstream_key=upstream_key,
            repo_root=repo_root,
            external_probe_host=external_probe_host,
            upstream_http_allowed=upstream_http_allowed,
            owned_egress=owned_egress,
            extra_cli_args=extra_cli_args,
            mock_tool_sequence_sse=mock_tool_sequence_sse,
            mock_body_markers=mock_body_markers,
            resources=resources,
            removed=removed,
            cleanup_errors=cleanup_errors,
            register=register,
            finish=finish,
            canary_holder=canary_holder,
        )
    except _BoundaryUnavailable as exc:
        return finish("unavailable", exc.code)
    except Exception:
        return finish("unavailable", "boundary_error")


# ---------------------------------------------------------------------------


def _execute_inner(
    *,
    started: float,
    label: str,
    prefix: str,
    internal_name: str,
    egress_name: str,
    relay_name: str,
    researcher_name: str,
    probe_name: str,
    timeout_seconds: int,
    workspace: Path,
    task_name: str,
    models_json: str,
    evidence_path: Path,
    agent_md: Path,
    output_schema: Path,
    cli_bin: str,
    cli_sha256: str,
    model_name: str,
    mode: str,
    canned_result_json: str | None,
    upstream_base: str,
    upstream_key: str,
    repo_root: Path | None,
    external_probe_host: str,
    upstream_http_allowed: bool,
    owned_egress: tuple[str, str] | None,
    extra_cli_args: tuple[str, ...],
    mock_tool_sequence_sse: bytes | None,
    mock_body_markers: Mapping[str, str] | None,
    resources: list[tuple[str, str, str]],
    removed: set[str],
    cleanup_errors: list[str],
    register,
    finish,
    canary_holder: dict[str, socket.socket | None],
) -> TaskExecution:
    # --- preflight: the enforcement boundary must exist -------------------
    if not shutil.which("docker"):
        return finish("unavailable", "docker_cli_missing")
    if not _docker_ok("version", timeout=15):
        return finish("unavailable", "docker_daemon_unavailable")
    if not _docker_ok("image", "inspect", RESEARCH_IMAGE, timeout=15):
        # one bounded pull of the pinned official digest, then refuse.
        if not _docker_ok("pull", RESEARCH_IMAGE, timeout=IMAGE_PULL_TIMEOUT):
            return finish("unavailable", "research_image_unavailable")
        if not _docker_ok("image", "inspect", RESEARCH_IMAGE, timeout=15):
            return finish("unavailable", "research_image_unavailable")
    try:
        actual_sha = verify_cli_binary(cli_bin)
    except _BoundaryUnavailable as exc:
        return finish("unavailable", exc.code)
    if actual_sha != cli_sha256:
        return finish("unavailable", "cli_sha256_mismatch")
    if mode == "forward":
        scheme = upstream_base.split("://", 1)[0].lower()
        if scheme == "http" and not upstream_http_allowed:
            # verified HTTPS for real external endpoints; HTTP only for
            # explicit owned synthetic mocks
            return finish("unavailable", "upstream_scheme_unverified")
        if scheme != "https" and scheme != "http":
            return finish("unavailable", "upstream_scheme_unverified")
        try:
            upstream_host, upstream_port = _upstream_target_from_url(upstream_base)
        except ValueError:
            return finish("unavailable", "upstream_unverifiable")
    else:
        upstream_host, upstream_port = "", 0

    # workspace must stay outside the repository
    try:
        ws = workspace.resolve()
        if repo_root is not None and ws.is_relative_to(repo_root.resolve()):
            return finish("unavailable", "workspace_in_repo")
    except (OSError, ValueError):
        return finish("unavailable", "workspace_invalid")
    try:
        # private host parent; stage public assets/output for the chosen
        # nonroot UIDs (relay/probe run as the invoking UID, researcher as
        # 65534 which needs the world-writable outputs leaf under 0700)
        ws.chmod(0o700)
        (ws / "inputs").mkdir(parents=True, exist_ok=True)
        (ws / "inputs").chmod(0o755)
        # config/home/outputs: empty parent-created scratch that the CLI
        # (uid 65534) must write; world-writable is confined by the 0700
        # workspace parent and holds no auth material
        for sub in ("config", "home"):
            (ws / sub).mkdir(parents=True, exist_ok=True)
            (ws / sub).chmod(0o777)
        outputs_dir = ws / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.chmod(0o777)
        for input_file in (evidence_path, agent_md, output_schema, ws / "inputs" / "task.json"):
            if input_file.is_file():
                input_file.chmod(0o644)
        missing = [
            p for p in (
                Path(cli_bin), evidence_path, agent_md, output_schema,
                ws / "inputs" / "task.json",
            ) if not p.is_file()
        ]
        if missing:
            return finish("unavailable", "workspace_invalid")
    except OSError:
        return finish("unavailable", "workspace_invalid")

    # --- networks: isolated internal (researcher) + narrow egress (relay) -
    internal_net: str | None = None
    for subnet, gateway in _INTERNAL_SUBNETS:
        try:
            internal_net = _create_network(
                label,
                internal_name,
                [
                    "--driver", "bridge",
                    "--internal",
                    "--ipv6=false",
                    "--subnet", subnet,
                    "--gateway", gateway,
                    "--opt", "com.docker.network.bridge.gateway_mode_ipv4=isolated",
                ],
            )
            break
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            internal_net = None
    if internal_net is None:
        return finish("unavailable", "internal_network_unavailable")
    register("network", internal_net, internal_name)
    # verify the ACTUAL network configuration (not just the create flags)
    try:
        net_cfg = json.loads(_docker("network", "inspect", "--format", "{{json .IPAM.Config}}", internal_net))
        options = json.loads(_docker("network", "inspect", "--format", "{{json .Options}}", internal_net))
        internal_flag = _docker("network", "inspect", "--format", "{{.Internal}}", internal_net)
        ipv6_flag = _docker("network", "inspect", "--format", "{{.EnableIPv6}}", internal_net)
    except Exception:
        return finish("unavailable", "internal_network_unavailable")
    if (
        not net_cfg
        or net_cfg[0].get("Gateway") not in {g for _s, g in _INTERNAL_SUBNETS}
        or options.get("com.docker.network.bridge.gateway_mode_ipv4") != "isolated"
        or internal_flag.strip() != "true"
        or ipv6_flag.strip() != "false"
    ):
        return finish("unavailable", "internal_network_not_isolated")
    egress_id = ""
    if owned_egress is not None:
        egress_ref, egress_label = owned_egress
        egress_key, egress_sep, egress_value = egress_label.partition("=")
        if not egress_sep or not egress_key or not egress_value:
            return finish("unavailable", "egress_network_unavailable")
        try:
            raw_labels = json.loads(_docker("network", "inspect", "--format", "{{json .Labels}}", egress_ref) or "{}")
        except Exception:
            return finish("unavailable", "egress_network_unavailable")
        if not isinstance(raw_labels, dict) or raw_labels.get(egress_key) != egress_value:
            return finish("unavailable", "egress_network_unavailable")
        egress_id = egress_ref  # caller-owned: verified, reused, NOT cleaned up here
        # the relay must attach to the CALLER's egress network (name or ID):
        # the auto-generated egress_name is only created in the adapter-owned
        # branch below
        egress_name = egress_ref
    else:
        try:
            egress_id = _create_network(label, egress_name, ["--driver", "bridge"])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            return finish("unavailable", "egress_network_unavailable")
        register("network", egress_id, egress_name)

    # --- owned host canary: a live listener ONLY the egress side can reach -
    canary_ip = ""
    canary_port = 0
    canary_sock = None
    try:
        egress_cfg = json.loads(_docker("network", "inspect", "--format", "{{json .IPAM.Config}}", egress_id))
        canary_ip = egress_cfg[0]["Gateway"]
        canary_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        canary_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        canary_sock.bind((canary_ip, 0))
        canary_sock.listen(8)
        canary_port = canary_sock.getsockname()[1]
        with socket.create_connection((canary_ip, canary_port), timeout=1.0):
            pass  # the owned listener is alive on the host side
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, json.JSONDecodeError):
        if canary_sock is not None:
            try:
                canary_sock.close()
            except OSError:
                pass
        return finish("unavailable", "host_canary_unavailable")
    canary_holder["sock"] = canary_sock

    # --- relay container (internal always; egress only in forward mode) ---
    task_key = "slr-" + secrets.token_hex(16)  # synthetic task credential only
    invoking_uid = f"{os.getuid()}:{os.getgid()}"
    relay_assets, relay_log_dir = write_relay_assets(
        ws,
        model=model_name,
        mode=mode,
        canned_result_json=canned_result_json,
        upstream_key=upstream_key,
        tool_sequence_sse=mock_tool_sequence_sse if mode == "mock" else None,
        body_markers=mock_body_markers if mode == "mock" else None,
    )
    relay_env = [
        f"SLAIF_RELAY_TASK_KEY={task_key}",
        f"SLAIF_RELAY_MODEL={model_name}",
        f"SLAIF_RELAY_MODE={mode}",
        "SLAIF_RELAY_LOG=/relay-out/relay-log.txt",
        "SLAIF_RELAY_CANNED_SSE=/relay/canned.sse",
    ]
    if mode == "mock":
        if mock_tool_sequence_sse is not None:
            relay_env.append("SLAIF_RELAY_TOOL_SEQUENCE=/relay/tool-sequence.sse")
        if mock_body_markers:
            relay_env.append("SLAIF_RELAY_MARKERS_FILE=/relay/body-markers.json")
    if mode == "forward":
        relay_env.append(f"SLAIF_RELAY_UPSTREAM_BASE={upstream_base}")
        relay_env.append("SLAIF_RELAY_UPSTREAM_KEY_FILE=/relay/upstream-key")
        if upstream_http_allowed:
            relay_env.append("SLAIF_RELAY_ALLOW_HTTP=1")
    try:
        network_args = ["--network", internal_name]
        if mode == "forward":
            network_args.append("--network")
            network_args.append(egress_name)
        relay_id = _docker(
            "create",
            "--name", relay_name,
            "--label", label,
            "--pull=never",
            *network_args,
            "--read-only",
            "--user", invoking_uid,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64",
            "--memory", "256m",
            "--cpus", "1",
            *_flat_env(relay_env),
            "-v", f"{relay_assets}:/relay:ro",
            "-v", f"{relay_log_dir}:/relay-out:rw",
            RESEARCH_IMAGE,
            "python", "/relay/relay.py",
        )
        register("container", relay_id, relay_name)
        _docker("start", relay_id)
        if _container_env_names(relay_id) - _RELAY_ENV_ALLOW:
            return finish("unavailable", "relay_config_mismatch")
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return finish("unavailable", "relay_unavailable")

    # the relay IP on the internal network (control-plane read only; the
    # readiness itself is proven by the isolated-network peer below)
    relay_ip = ""
    for _attempt in range(20):
        try:
            relay_ip = _docker("inspect", "--format",
                               "{{(index .NetworkSettings.Networks \"" + internal_name + "\").IPAddress}}", relay_id)
            if relay_ip:
                break
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            relay_ip = ""
        time.sleep(0.5)
    if not relay_ip:
        return finish("unavailable", "relay_not_reachable")

    # --- boundary probe: readiness + negatives from an owned PEER ---------
    probe_script = ws / "probe.py"
    probe_script.write_text(_PROBE_SCRIPT, encoding="utf-8")
    probe_script.chmod(0o500)
    canary_files = ",".join(
        part for part in (
            str(repo_root) if repo_root else "",
            "/run/docker.sock",
            os.path.expanduser("~/.codex"),
        ) if part
    )
    probe: dict[str, Any] = {}
    probe_id = ""
    try:
        probe_id = _docker(
            "create",
            "--name", probe_name,
            "--label", label,
            "--pull=never",
            "--network", internal_name,
            "--read-only",
            "--user", invoking_uid,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64",
            "--memory", "128m",
            "--cpus", "1",
            "-v", f"{probe_script}:{probe_script}:ro",
            RESEARCH_IMAGE,
            "python", str(probe_script),
            relay_ip,
            str(RESEARCHER_PORT),
            canary_ip,
            str(canary_port),
            external_probe_host,
            upstream_host,
            canary_files,
            str(upstream_port),
        )
        register("container", probe_id, probe_name)
        raw = _docker("start", "--attach", probe_id)
        lines = [line for line in raw.splitlines() if line.strip()]
        probe = json.loads(lines[-1]) if lines else {}
        if _docker("inspect", "--format", "{{.State.ExitCode}}", probe_id) != "0":
            probe = {"probe_error": True}
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        probe = {"probe_error": True}
    finally:
        if probe_id:
            try:
                if not _inspect_labels("container", probe_id, label):
                    cleanup_errors.append(f"container:{probe_name}:ownership_check_failed")
                else:
                    _docker("rm", "--force", probe_id)
                    removed.add(probe_id)
            except Exception:
                cleanup_errors.append(f"container:{probe_name}")

    probe_failures: list[str] = []
    if probe.get("probe_error"):
        probe_failures.append("probe_error")
    else:
        if probe.get("relay_reachable") is not True:
            probe_failures.append("relay_unreachable")
        if probe.get("host_canary_reachable") is not False:
            probe_failures.append("host_canary_reachable")
        if probe.get("external_reachable") is not False:
            probe_failures.append("external_reachable")
        if mode == "forward" and probe.get("upstream_direct_reachable") is not False:
            probe_failures.append("upstream_direct_reachable")
        if probe.get("canaries_present"):
            probe_failures.append("canary_present")
    if probe_failures:
        # REFUSE before any model execution; never attach-and-continue
        return finish("unavailable", "boundary_probe_failed", probe=probe,
                      detail="boundary probe: " + ",".join(probe_failures))

    # --- researcher container: the real CLI, whole-process boundary -------
    # The researcher runs as the INVOKING user (same convention as the relay
    # and probe containers) so files the CLI creates inside the parent-owned
    # workspace mounts remain deletable by the parent during required
    # cleanup; a root invocation keeps the fixed unprivileged 65534 (root
    # cleanup is permission-blind, the container must never be root).
    researcher_uid = RESEARCHER_UID if os.getuid() == 0 else invoking_uid
    researcher_env = [
        "HOME=/workspace/home",
        "CODEX_HOME=/workspace/config",
        "PATH=/opt/codex:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"SLAIF_RESEARCH_API_KEY={task_key}",
        "LANG=C.UTF-8",
        "PYTHONUNBUFFERED=1",
    ]
    provider_toml = (
        'model_providers.slaif_research='
        '{name="SLAIF Research Relay",'
        f'base_url="http://{relay_name}:{RESEARCHER_PORT}/v1",'
        'wire_api="responses",env_key="SLAIF_RESEARCH_API_KEY"}'
    )
    prompt = (
        "Read /workspace/AGENTS.md and /workspace/inputs/task.json. Follow the "
        "instruction template exactly and transcribe only the captured evidence. "
        "Respond with the structured result as your final message; the gateway "
        "records that final message at the configured output path. Do not use "
        "tools and do not write files."
    )
    expected_mounts = {
        "/opt/codex/codex": False,
        "/workspace/inputs/evidence": False,
        "/workspace/AGENTS.md": False,
        "/workspace/inputs/output-schema.json": False,
        "/workspace/inputs/task.json": False,
        "/workspace/outputs": True,
        "/workspace/config": True,
        "/workspace/home": True,
    }
    try:
        researcher_id = _docker(
            "create",
            "--name", researcher_name,
            "--label", label,
            "--pull=never",
            "--network", internal_name,
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m,mode=1777",
            "--user", researcher_uid,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "128",
            "--memory", "1g",
            "--cpus", "2",
            *_flat_env(researcher_env),
            "-w", "/workspace",
            "-v", f"{cli_bin}:/opt/codex/codex:ro",
            "-v", f"{evidence_path}:/workspace/inputs/evidence:ro",
            "-v", f"{agent_md}:/workspace/AGENTS.md:ro",
            "-v", f"{output_schema}:/workspace/inputs/output-schema.json:ro",
            "-v", f"{ws / 'inputs' / 'task.json'}:/workspace/inputs/task.json:ro",
            "-v", f"{ws / 'outputs'}:/workspace/outputs:rw",
            "-v", f"{ws / 'config'}:/workspace/config:rw",
            "-v", f"{ws / 'home'}:/workspace/home:rw",
            RESEARCH_IMAGE,
            "/opt/codex/codex", "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            # WORKER-ONLY sandbox override (the order permits a CLI sandbox
            # override inside an independently qualified outer container):
            # the outer boundary above enforces nonroot, read-only root,
            # dropped capabilities, no-new-privileges, isolated internal
            # network, task-only mounts, and the env allowlist. It is
            # required on hosts where the kernel/AppArmor denies
            # unprivileged user namespaces (the CLI's nested bwrap cannot
            # start there); the CLI's own sandbox layer adds nothing beyond
            # the enforced outer limits inside this container.
            "--sandbox", "danger-full-access",
            "-m", model_name,
            "-c", 'model_provider="slaif_research"',
            "-c", provider_toml,
            "--output-schema", "/workspace/inputs/output-schema.json",
            "--output-last-message", "/workspace/outputs/research-result.json",
            *extra_cli_args,
            prompt,
        )
        register("container", researcher_id, researcher_name)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return finish("unavailable", "researcher_unavailable", probe=probe)

    # verify the ACTUAL configuration before any execution
    try:
        net_settings = json.loads(
            _docker("inspect", "--format", "{{json .NetworkSettings.Networks}}", researcher_id) or "{}"
        )
        if set(net_settings) != {internal_name}:
            return finish("unavailable", "researcher_network_attachment", probe=probe)
        if _container_env_names(researcher_id) - _RESEARCHER_ENV_ALLOW:
            return finish("unavailable", "researcher_config_mismatch:env", probe=probe)
        if _docker("inspect", "--format", "{{.Config.User}}", researcher_id).strip() != researcher_uid:
            return finish("unavailable", "researcher_config_mismatch:user", probe=probe)
        mounts = _container_mounts(researcher_id)
        bind_mounts = {d: rw for d, (kind, rw) in mounts.items() if kind == "bind"}
        non_bind = {d: kind for d, (kind, _rw) in mounts.items() if kind != "bind"}
        # the /tmp tmpfs is reported only once the container is running;
        # pre-run it is absent, and it must never be anything but a tmpfs
        if (
            bind_mounts != expected_mounts
            or (set(non_bind) - {"/tmp"})
            or ("/tmp" in non_bind and non_bind["/tmp"] != "tmpfs")
        ):
            return finish("unavailable", "researcher_config_mismatch:mounts", probe=probe)
        net_cfg = json.loads(_docker("network", "inspect", "--format", "{{json .IPAM.Config}}", internal_net))
        options = json.loads(_docker("network", "inspect", "--format", "{{json .Options}}", internal_net))
        internal_flag = _docker("network", "inspect", "--format", "{{.Internal}}", internal_net)
        ipv6_flag = _docker("network", "inspect", "--format", "{{.EnableIPv6}}", internal_net)
        if (
            not net_cfg
            or net_cfg[0].get("Gateway") not in {g for _s, g in _INTERNAL_SUBNETS}
            or options.get("com.docker.network.bridge.gateway_mode_ipv4") != "isolated"
            or internal_flag.strip() != "true"
            or ipv6_flag.strip() != "false"
        ):
            return finish("unavailable", "internal_network_not_isolated", probe=probe)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return finish("unavailable", "researcher_config_mismatch:network", probe=probe)

    # --- run with a finite task timeout ------------------------------------
    timed_out = False
    try:
        subprocess.run(
            [*_DOCKER, "start", "--attach", researcher_id],
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            _docker("kill", researcher_id, timeout=30)
        except Exception:
            pass
    except (OSError, subprocess.TimeoutExpired):
        return finish("unavailable", "researcher_run_unavailable", probe=probe)

    exit_code: int | None = None
    try:
        raw_exit = _docker("inspect", "--format", "{{.State.ExitCode}}", researcher_id)
        exit_code = int(raw_exit) if raw_exit.strip().lstrip("-").isdigit() else None
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError):
        exit_code = None

    output_path = outputs_dir / "research-result.json"
    if timed_out:
        return finish(
            "child_failure", "child_timeout",
            exit_code=exit_code, probe=probe,
            detail="task child timed out; no partial data accepted",
        )
    if exit_code != 0:
        return finish(
            "child_failure", f"child_exit_{exit_code if exit_code is not None else 'unknown'}",
            exit_code=exit_code, probe=probe,
        )
    # anchored, no-follow, bounded regular-file read on the held output dir
    try:
        output_bytes = fs.anchored_read(outputs_dir, "research-result.json", MAX_RESULT_BYTES)
    except fs.CatalogRefreshSealError as exc:
        message = str(exc)
        if "exceeds the size bound" in message:
            code = "output_too_large"
        elif output_path.exists():
            code = "output_unreadable"
        else:
            code = "output_missing"
        return finish("child_failure", code, exit_code=exit_code, probe=probe)

    relay_requests = _count_relay_lines(ws / "relay-out" / "relay-log.txt")
    return finish(
        "completed",
        exit_code=0,
        output_bytes=output_bytes,
        output_sha256=hashlib.sha256(output_bytes).hexdigest(),
        probe=probe,
        relay_requests=relay_requests,
    )


def _count_relay_lines(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0
