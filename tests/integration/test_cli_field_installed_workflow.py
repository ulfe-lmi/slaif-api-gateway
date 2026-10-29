"""Installed-CLI field-administration workflow qualification (OAP 205-a).

Proves the order's literal section-12 outcomes through the ACTUAL installed
``slaif-gateway`` executable: every operator business action is a subprocess
invocation of the owned venv's console from an owned directory OUTSIDE the
checkout, with ``PYTHONPATH`` unset, against a fictional owned labeled
PostgreSQL 16 container (loopback-only published port, tmpfs data).

Owned-artifact policy: the fixture reuses a pre-built wheel/venv ONLY after
verifying (a) the pristine source payload of the accepted commit,
(b) the wheel payload against that source (byte-identical app tree), and
(c) the installed application payload against the SELECTED wheel for both
reused and fresh installs. When no
verified artifact is available it builds the wheel and venv with standard
tooling (``python -m build`` / ``python -m venv`` + ``pip install``) under a
fresh owned tmp directory. The actual wheel SHA256 for THIS run is computed
and recorded; bit-identical ZIP rebuilding is neither required nor claimed.

The fixture seeds clearly labeled PRE-EXISTING fictional identities, keys,
routes and history through the installed package (explicitly allowed setup)
and inspects PostgreSQL with Python for preservation assertions; it never
performs an operator business action that a test later claims the CLI did.

Retained transcript safety: raw subprocess output is transient (used for
in-memory assertions only). The retained transcript and every failure
message are safe projections with known generated secret values replaced by
fixed placeholders; credential-shaped arguments are masked by shape.

IO-substitution provenance and limitations:
``tests/fixtures/cli_field_workflow/README.md``. No real provider, client,
or mail traffic occurs; provider/SMTP boundaries are owned loopback
synthetics. This module is qualification evidence, not production exercise.
"""

from __future__ import annotations

import asyncio
import base64
import email
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import tarfile
import threading
import time
import uuid
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    CodexReplayReference,
    EmailDelivery,
    OneTimeSecret,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferenceInsert,
    CodexReplayReferencesRepository,
)
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import (
    OneTimeSecretsRepository,
)
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import (
    ProviderConfigsRepository,
)
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.codex_replay_service import CodexReplayService
from slaif_gateway.services.key_service import KeyService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# --- Accepted source / wheel / installation identity -----------------------
SOURCE_SHA = "420fb8f6d9377f569d126d08f4c9e4146fc7250b"
#: The wheel SHA256 of the artifact actually SELECTED for this run is
#: computed and recorded (``identity["wheel_sha256"]``). An ordinary build
#: of the same source can carry a different ZIP hash (timestamps); the
#: source/wheel/installed payload checks provide identity, so no fixed
#: manual ZIP hash is required for any reused artifact.
REPO_ROOT = Path(__file__).resolve().parents[2]
#: Owned artifact directory (pre-built wheel/venv from setup). Reuse is gated
#: by payload/identity verification; otherwise fresh artifacts are built.
ARTIFACT_DIR = Path(os.environ.get("SLAIF205_ARTIFACTS", "/tmp/slaif205"))
WHEEL_FILE_NAME = "slaif_api_gateway-0.1.0-py3-none-any.whl"
PG_IMAGE = "postgres:16"
PG_USER = "slaif205a"
PG_DB = "slaif205a"
PUBLIC_TABLE_COUNT = 34  # 33 product tables + alembic_version at 0026 head
RUN_TOKEN = uuid.uuid4().hex[:16]
CONTAINER_NAME = f"slaif205a-{RUN_TOKEN[:12]}"

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Owned artifact resolution (portable; reuse gated by payload verification)
# --------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class Artifacts:
    pristine: Path
    wheel: Path
    wheel_sha256: str
    venv_root: Path
    venv_py: Path
    console: Path
    wheel_reused: bool
    payload_files: int
    installed_payload_files: int
    steps: list[str]


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr[:300]}")
    return proc.stdout.strip()


def _ensure_pinned_commit() -> None:
    """Make the pinned source commit available locally (shallow-safe).

    A default depth-1 checkout of a child commit (for example CI on this
    objective's PR head) does not contain the pinned ancestor object.
    Obtain EXACTLY that commit with one narrow ordinary fetch of the pinned
    SHA from origin; no workflow, branch, or working-tree changes, and no
    substitution of a different unverified source.
    """
    try:
        _git("cat-file", "-e", f"{SOURCE_SHA}^{{commit}}")
        return
    except AssertionError:
        pass
    try:
        _git("remote", "get-url", "origin")
    except AssertionError as exc:
        raise AssertionError(
            f"pinned source {SOURCE_SHA} is absent and no origin remote is "
            "available to fetch it"
        ) from exc
    proc = subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", SOURCE_SHA],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"narrow fetch of pinned source {SOURCE_SHA} failed: {proc.stderr[:300]}"
        )
    _git("cat-file", "-e", f"{SOURCE_SHA}^{{commit}}")


def _archive_pristine_source(tmp_base: Path) -> Path:
    """git archive of the accepted commit into an owned directory."""
    head = _git("rev-parse", "HEAD")
    if head != SOURCE_SHA:
        _ensure_pinned_commit()
    target = tmp_base / "pristine"
    target.mkdir(parents=True)
    archive = tmp_base / "source.tar"
    with archive.open("wb") as handle:
        proc = subprocess.run(
            ["git", "archive", "--format=tar", SOURCE_SHA],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise AssertionError(f"git archive failed: {proc.stderr[:300]}")
        handle.write(proc.stdout)
    with tarfile.open(archive, "r") as tar:
        tar.extractall(target, filter="data")
    app_init = target / "app" / "slaif_gateway" / "__init__.py"
    assert app_init.is_file(), "archived source missing app/slaif_gateway"
    archive.unlink()
    return target


def _wheel_payload_matches(pristine: Path, wheel: Path, tmp_base: Path) -> int:
    """Byte-compare the wheel's app payload against the accepted source tree.

    Returns the verified file count. Empty placeholder files may be omitted
    by the builder (observed for 4 .gitkeep files) and are excluded.
    """
    extracted = tmp_base / "wheel-extract"
    # exist_ok: a previously rejected candidate wheel may already have used
    # this owned extraction dir; only its children are cleared below.
    extracted.mkdir(parents=True, exist_ok=True)
    for stale in extracted.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()
    subprocess.run(
        [
            "python3",
            "-m",
            "zipfile",
            "-e",
            str(wheel),
            str(extracted),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    wheel_pkg = extracted / "slaif_gateway"
    src_pkg = pristine / "app" / "slaif_gateway"
    assert wheel_pkg.is_dir(), "wheel does not contain slaif_gateway package"
    wheel_files = {p.relative_to(wheel_pkg) for p in wheel_pkg.rglob("*") if p.is_file()}
    src_files = {p.relative_to(src_pkg) for p in src_pkg.rglob("*") if p.is_file()}
    omitted = src_files - wheel_files
    for rel in omitted:
        assert (src_pkg / rel).stat().st_size == 0, f"non-empty file omitted from wheel: {rel}"
    for rel in wheel_files:
        assert (src_pkg / rel).is_file(), f"wheel carries unknown file: {rel}"
        assert (
            (wheel_pkg / rel).read_bytes() == (src_pkg / rel).read_bytes()
        ), f"wheel payload differs from source: {rel}"
    return len(wheel_files)


def _build_wheel(pristine: Path, tmp_base: Path) -> tuple[Path, int]:
    """Standard tooling build: build venv + ``python -m build --wheel``.

    The freshly built wheel is payload-verified against the source before it
    is trusted (file-byte comparison; no bit-identical ZIP requirement).
    """
    build_env = tmp_base / "buildenv"
    subprocess.run(
        ["python3", "-m", "venv", str(build_env)],
        capture_output=True,
        timeout=300,
        check=True,
        env=_scrubbed_setup_env(),
    )
    build_py = build_env / "bin" / "python"
    subprocess.run(
        [str(build_py), "-m", "pip", "install", "--quiet", "build"],
        capture_output=True,
        timeout=900,
        check=True,
        env=_scrubbed_setup_env(),
    )
    outdir = tmp_base / "dist"
    subprocess.run(
        [str(build_py), "-m", "build", "--wheel", "--outdir", str(outdir), str(pristine)],
        capture_output=True,
        timeout=900,
        check=True,
        cwd=str(tmp_base),
        env=_scrubbed_setup_env(),
    )
    wheel = outdir / WHEEL_FILE_NAME
    assert wheel.is_file(), "standard wheel build produced no wheel"
    payload = _wheel_payload_matches(pristine, wheel, tmp_base)
    return wheel, payload


def _scrubbed_setup_env() -> dict[str, str]:
    """Env for setup subprocesses: the source-tree PYTHONPATH must not leak.

    With PYTHONPATH=app (and the repository cwd) visible, pip's working-set
    check finds the source-tree 0.1.0 egg-info and treats a same-version
    wheel as already installed, leaving the fresh venv empty.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def _python_for_venv() -> str:
    override = os.environ.get("SLAIF205_PYTHON", "").strip()
    if override:
        return override
    for candidate in ("python3.12", "python3"):
        found = shutil.which(candidate)
        if found:
            return found
    raise AssertionError("no python3 interpreter found for owned venv creation")


def _venv_is_usable(venv_root: Path) -> bool:
    venv_py = venv_root / "bin" / "python"
    console = venv_root / "bin" / "slaif-gateway"
    if not (venv_py.is_file() and console.is_file()):
        return False
    proc = subprocess.run(
        [
            str(venv_py),
            "-c",
            "import sys, slaif_gateway as m; print(m.__file__); print(sys.version.split()[0])",
        ],
        cwd="/tmp",
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return False
    package_file, py_version = proc.stdout.splitlines()
    if not package_file.startswith(str(venv_root)):
        return False
    major, minor, _ = (int(part) for part in py_version.split(".")[:3])
    return (major, minor) >= (3, 12)


def _installed_payload_matches(venv_root: Path, wheel_pkg: Path) -> int:
    """Byte-compare the INSTALLED application payload to the selected wheel.

    Resolves ``slaif_gateway.__file__`` through the owned venv in a scrubbed
    environment (neutral cwd, no PYTHONPATH), then compares every file under
    the resolved package directory against the SELECTED wheel's app payload
    (exact file set, byte-identical, ``__pycache__`` excluded). A stale or
    different 0.1.0 installation cannot pass this gate on path/version alone.
    """
    proc = subprocess.run(
        [
            str(venv_root / "bin" / "python"),
            "-c",
            "import sys, slaif_gateway as m; print(m.__file__); print(sys.version.split()[0])",
        ],
        cwd="/tmp",
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError("installed import probe failed (exit %d)" % proc.returncode)
    package_file = proc.stdout.splitlines()[0]
    package_dir = Path(package_file).parent
    assert str(package_dir).startswith(str(venv_root)), (
        "installed package resolves outside the owned venv"
    )
    installed_files = {
        p.relative_to(package_dir)
        for p in package_dir.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(package_dir).parts
    }
    wheel_files = {p.relative_to(wheel_pkg) for p in wheel_pkg.rglob("*") if p.is_file()}
    missing = sorted(str(r) for r in wheel_files - installed_files)
    assert not missing, f"selected wheel payload missing from install: {missing[:5]}"
    extra = sorted(str(r) for r in installed_files - wheel_files)
    assert not extra, f"install carries files absent from selected wheel: {extra[:5]}"
    for rel in wheel_files:
        assert (
            (package_dir / rel).read_bytes() == (wheel_pkg / rel).read_bytes()
        ), f"installed payload differs from selected wheel: {rel}"
    return len(installed_files)


def _resolve_artifacts(tmp_base: Path) -> Artifacts:
    steps: list[str] = []
    pristine = _archive_pristine_source(tmp_base)
    steps.append(f"git archive {SOURCE_SHA} -> {pristine}")

    wheel: Path | None = None
    wheel_reused = False
    payload_files = 0
    candidate_env = os.environ.get("SLAIF205_WHEEL", "").strip()
    candidates = (
        [Path(candidate_env)] if candidate_env else [ARTIFACT_DIR / "dist" / WHEEL_FILE_NAME]
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                payload_files = _wheel_payload_matches(pristine, candidate, tmp_base)
            except AssertionError:
                continue
            wheel = candidate
            wheel_reused = True
            steps.append(f"reused verified wheel {candidate}")
            break
    if wheel is None:
        wheel, payload_files = _build_wheel(pristine, tmp_base)
        steps.append(f"built and payload-verified wheel via python -m build -> {wheel}")

    wheel_sha = _sha256_file(wheel)

    venv_root: Path | None = None
    # The last _wheel_payload_matches call extracted the SELECTED wheel
    # (reused candidate or freshly built wheel) to this directory.
    wheel_pkg = tmp_base / "wheel-extract" / "slaif_gateway"
    assert wheel_pkg.is_dir(), "selected wheel payload extraction missing"
    if (ARTIFACT_DIR / "venv2").is_dir() and _venv_is_usable(ARTIFACT_DIR / "venv2"):
        try:
            _installed_payload_matches(ARTIFACT_DIR / "venv2", wheel_pkg)
        except AssertionError:
            steps.append(
                "stale reused venv rejected: installed payload differs from the "
                "selected wheel; replacing with a fresh owned venv"
            )
        else:
            venv_root = ARTIFACT_DIR / "venv2"
            steps.append(f"reused verified owned venv {venv_root}")
    if venv_root is None:
        venv_root = tmp_base / "venv"
        subprocess.run(
            [_python_for_venv(), "-m", "venv", str(venv_root)],
            capture_output=True,
            timeout=300,
            check=True,
            env=_scrubbed_setup_env(),
        )
        subprocess.run(
            [str(venv_root / "bin" / "python"), "-m", "pip", "install", "--quiet", str(wheel)],
            capture_output=True,
            timeout=900,
            check=True,
            cwd=str(tmp_base),
            env=_scrubbed_setup_env(),
        )
        assert _venv_is_usable(venv_root), "fresh owned venv failed identity check"
        steps.append(f"created owned venv {venv_root} and installed {wheel.name}")

    console = venv_root / "bin" / "slaif-gateway"
    assert console.is_file(), "installed console missing in owned venv"
    installed_payload = _installed_payload_matches(venv_root, wheel_pkg)
    steps.append(
        f"verified installed application payload vs selected wheel "
        f"({installed_payload} files)"
    )
    return Artifacts(
        pristine=pristine,
        wheel=wheel,
        wheel_sha256=wheel_sha,
        venv_root=venv_root,
        venv_py=venv_root / "bin" / "python",
        console=console,
        wheel_reused=wheel_reused,
        payload_files=payload_files,
        installed_payload_files=installed_payload,
        steps=steps,
    )


# --------------------------------------------------------------------------
# Minimal loopback SMTP sink (stdlib only; records DATA blocks in memory)
# --------------------------------------------------------------------------


class SmtpSink:
    def __init__(self) -> None:
        self.port = self._bind()
        self.received: list[dict[str, str]] = []
        #: Minimal deterministic IO fault (fixture only): when armed, the
        #: next DATA command is refused with a 550 and never recorded.
        self.refuse_data = False
        self.refusals = 0
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", self.port))
        self._server.listen(8)
        self._closed = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    @staticmethod
    def _bind() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            buf = b""
            conn.sendall(b"220 slaif205a-sink ESMTP\r\n")
            mail_from = rcpt_to = ""
            in_data = False
            data_chunks: list[bytes] = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    if in_data:
                        if line == b".":
                            in_data = False
                            self.received.append(
                                {
                                    "from": mail_from,
                                    "to": rcpt_to,
                                    "data": b"".join(data_chunks).decode("utf-8", "replace"),
                                }
                            )
                            conn.sendall(b"250 2.0.0 Ok: queued\r\n")
                        else:
                            data_chunks.append(line + b"\r\n")
                        continue
                    cmd = line.decode("utf-8", "replace").strip()
                    upper = cmd.upper()
                    if upper.startswith("EHLO") or upper.startswith("HELO"):
                        conn.sendall(b"250-slaif205a-sink\r\n250 8BITMIME\r\n")
                    elif upper.startswith("MAIL FROM"):
                        mail_from = cmd.split(":", 1)[1].strip()
                        conn.sendall(b"250 2.1.0 Ok\r\n")
                    elif upper.startswith("RCPT TO"):
                        rcpt_to = cmd.split(":", 1)[1].strip()
                        conn.sendall(b"250 2.1.5 Ok\r\n")
                    elif upper.startswith("DATA"):
                        if self.refuse_data:
                            self.refusals += 1
                            conn.sendall(b"550 5.0.0 Synthetic fixture refusal\r\n")
                            continue
                        in_data = True
                        data_chunks = []
                        conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif upper.startswith("QUIT"):
                        conn.sendall(b"221 2.0.0 Bye\r\n")
                        return
                    else:  # NOOP / RSET / unknown-safe
                        conn.sendall(b"250 2.0.0 Ok\r\n")
        except OSError:
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self) -> None:
        self._closed.set()
        try:
            self._server.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Loopback synthetic upstream provider (stdlib HTTP; IO substitution only).
# Scripted by the upstream model name in the request body; the retained log
# holds only (path, model, stream flag, status) — never request content.
# --------------------------------------------------------------------------


class _ProviderRequestHandler(http.server.BaseHTTPRequestHandler):
    mock: "ProviderMock"

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            doc = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            doc = {}
        model = (
            doc.get("model")
            if isinstance(doc, dict) and isinstance(doc.get("model"), str)
            else "unknown"
        )
        stream = bool(isinstance(doc, dict) and doc.get("stream"))
        if self.path.rstrip("/").endswith("/responses"):
            # Bounded synthetic Responses upstream (IO substitution only).
            if stream and model.endswith("-failstream"):
                status = self._send_responses_stream_failure(model)
            elif stream:
                status = self._send_responses_stream(model)
            else:
                status = self._send_responses(model)
        elif model.endswith("-failstream") and stream:
            status = self._send_terminal_stream_failure()
        elif stream:
            status = self._send_stream(model)
        else:
            status = self._send_completion(model)
        self.mock.record(self.path, model, stream, status)

    def _write_sse_line(self, payload: str) -> None:
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _send_completion(self, model: str) -> int:
        body = json.dumps(
            {
                "id": "fixture-completion-205a",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "fixture completion",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return 200

    def _send_stream(self, model: str) -> int:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        base = {
            "id": "fixture-stream-205a",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": model,
        }
        self._write_sse_line(json.dumps({**base, "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
        ]}))
        self._write_sse_line(json.dumps({**base, "choices": [
            {"index": 0, "delta": {"content": "fixture stream"}, "finish_reason": None}
        ]}))
        self._write_sse_line(json.dumps({**base, "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}
        ]}))
        self._write_sse_line("[DONE]")
        return 200

    def _send_terminal_stream_failure(self) -> int:
        # Wire status 200; the stream terminates with an error payload
        # instead of a valid terminal chunk / [DONE].
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        base = {
            "id": "fixture-failstream-205a",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "fixture-failstream",
        }
        self._write_sse_line(json.dumps({**base, "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
        ]}))
        self._write_sse_line(json.dumps({
            "error": {
                "message": "fixture terminal stream failure",
                "type": "fixture_stream_error",
            }
        }))
        return 200

    # -- bounded synthetic Responses upstream (order 205-e section 4) -------

    def _send_responses(self, model: str) -> int:
        # Exact bounded success JSON for the replay positive control
        # (synthetic IO, not a real backend).
        body = json.dumps(
            {
                "id": "resp-205e-fixture",
                "object": "response",
                "status": "completed",
                "model": model,
                "output": [],
                "usage": {
                    "input_tokens": 6,
                    "output_tokens": 8,
                    "total_tokens": 14,
                },
                "store": False,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return 200

    def _send_responses_stream(self, model: str) -> int:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self._write_sse_line(json.dumps({
            "type": "response.created",
            "response": {"id": "resp-205e-stream", "status": "in_progress"},
        }))
        self._write_sse_line(json.dumps({
            "type": "response.completed",
            "response": {
                "id": "resp-205e-stream",
                "status": "completed",
                "model": model,
                "output": [],
            },
        }))
        self._write_sse_line("[DONE]")
        return 200

    def _send_responses_stream_failure(self, model: str) -> int:
        # Wire status 200; the second event is an UNSUPPORTED event type, so
        # the gateway terminates the stream with a terminal failure. The
        # optional generated canary rides the first event's id so the test
        # can prove response content is never retained.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        first_id = (
            self.mock.response_canary
            if self.mock.response_canary
            else "resp-205e-failstream"
        )
        self._write_sse_line(json.dumps({
            "type": "response.created",
            "response": {"id": first_id, "status": "in_progress"},
        }))
        self._write_sse_line(json.dumps({
            "type": "response.not_a_supported_event",
        }))
        self._write_sse_line("[DONE]")
        return 200


class ProviderMock:
    """Owned loopback synthetic upstream (documented IO substitution)."""

    def __init__(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        handler = type(
            "BoundProviderHandler",
            (_ProviderRequestHandler,),
            {"mock": self},
        )
        self._httpd = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), handler
        )
        self.request_log: list[dict[str, object]] = []
        # Optional generated response canary (set per test): embedded in the
        # responses SSE failure event so the test can prove the recorded
        # store/CLI/export never retain response content.
        self.response_canary: str = ""
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def record(
        self, path: str, model: str, stream: bool, status: int
    ) -> None:
        self.request_log.append(
            {"path": path, "model": model, "stream": stream, "status": status}
        )

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Owned installed gateway (real uvicorn subprocess; loopback only)
# --------------------------------------------------------------------------


class GatewayServer:
    def __init__(self, venv_py: Path, env: dict[str, str], cwd: Path) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.proc = subprocess.Popen(
            [
                str(venv_py), "-m", "uvicorn", "slaif_gateway.main:app",
                "--host", "127.0.0.1", "--port", str(self.port),
                "--log-level", "warning",
            ],
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.url = f"http://127.0.0.1:{self.port}"
        # An unread stdout PIPE would fill and HANG the gateway; a daemon
        # drainer discards it so startup/teardown never block on output.
        # No gateway output is retained, asserted, or reported.
        self._drainer = threading.Thread(target=self._drain, daemon=True)
        self._drainer.start()
        try:
            self._wait_ready()
        except BaseException:
            self.stop()
            raise

    def _drain(self) -> None:
        assert self.proc.stdout is not None
        while True:
            chunk = self.proc.stdout.read(65536)
            if not chunk:
                return

    def _wait_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(
                    "gateway exited during startup "
                    f"(exit {self.proc.returncode})"
                )
            try:
                with urllib.request.urlopen(
                    f"{self.url}/healthz", timeout=5
                ) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        raise AssertionError("gateway did not become ready in time")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
        # EOF reaches the drainer once the process has exited; settle the
        # pipe before closing it (bounded, never blocks teardown).
        self._drainer.join(timeout=10)
        if self.proc.stdout is not None:
            try:
                self.proc.stdout.close()
            except (OSError, ValueError):
                pass
# --------------------------------------------------------------------------
# CLI result (raw output is TRANSIENT; retained fields are safe projections)
# --------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class CliResult:
    argv: tuple[str, ...]  # safe-projected
    exit_code: int
    stdout: str  # raw, transient, in-memory only
    stderr: str  # raw, transient, in-memory only
    json: object = None
    safe_stderr: str = ""  # safe projection, usable in failure messages

    def assert_ok(self, label: str) -> CliResult:
        if self.exit_code != 0:
            raise AssertionError(
                f"{label}: CLI exit {self.exit_code}: {self.safe_stderr[:500]}"
            )
        return self


def _shape_mask(argv: list[str]) -> list[str]:
    """Known credential SHAPES in argv are replaced before retention."""
    out: list[str] = []
    for arg in argv:
        if arg.startswith(("sk-slaif-", "sk-proj-")):
            out.append("<REFUSED-BEARER-SHAPE>")
        elif "Bearer " in arg and len(arg) > 20:
            out.append("<REFUSED-BEARER-SHAPE>")
        else:
            out.append(arg)
    return out


# --------------------------------------------------------------------------
# Owned environment context
# --------------------------------------------------------------------------


@dataclass(repr=False)
class FieldEnvironment:
    database_url: str  # ORM URL for application commands
    driver_url: str  # direct asyncpg URL for fixture inspection helpers
    operator_dir: Path
    cli_env: dict[str, str]
    manifest: dict[str, object]
    identity: dict[str, object]
    artifacts: Artifacts
    smtp: SmtpSink
    provider_base_url: str = ""
    gateway_url: str = ""
    transcript: list[dict[str, object]] = field(default_factory=list)
    container_id: str = ""
    pg_port: int = 0
    _secrets: dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    _gateway_launcher: Callable[[], GatewayServer] | None = field(
        default=None, repr=False, compare=False
    )

    def register_secret(self, value: str, label: str) -> None:
        if value:
            self._secrets[value] = f"<REDACTED:{label}>"

    def start_gateway(
        self, env_overrides: dict[str, str] | None = None
    ) -> GatewayServer:
        """Start the ACTUAL installed gateway on owned loopback.

        Delegates to the owning fixture, which constructs the process and
        registers it for exact teardown before readiness completes.
        ``env_overrides`` (optional) are merged over the default process
        environment; the default behavior is unchanged when omitted."""
        assert self._gateway_launcher is not None, "gateway launcher not attached"
        return self._gateway_launcher(env_overrides)

    def safe(self, text: str) -> str:
        """Safe projection: replace every known generated secret value."""
        if not text:
            return text
        for value, placeholder in sorted(
            self._secrets.items(), key=lambda item: len(item[0]), reverse=True
        ):
            text = text.replace(value, placeholder)
        return text

    def _fail_detail(self, stdout: str, stderr: str) -> str:
        """Safe failure excerpt: wrapped CLI errors are JSON on stdout, so
        prefer stderr and fall back to the (safe-projected) stdout JSON."""
        detail = _strip_ansi(stderr)
        if not detail.strip():
            detail = _strip_ansi(stdout)
        return self.safe(detail[:500])

    def run_cli(
        self,
        *args: str,
        json_output: bool = True,
        expect: int = 0,
        any_failure: bool = False,
        timeout: int = 120,
        label: str = "",
        env: dict[str, str] | None = None,
    ) -> CliResult:
        argv = [str(self.artifacts.console), *args]
        if json_output:
            argv.append("--json")
        proc_env = dict(self.cli_env)
        if env:
            proc_env.update(env)
        proc = subprocess.run(
            argv,
            cwd=str(self.operator_dir),
            env=proc_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        parsed = None
        if json_output and proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed = None
        safe_argv = tuple(self.safe(arg) for arg in _shape_mask(argv))
        result = CliResult(
            argv=safe_argv,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            json=parsed,
            safe_stderr=self.safe(_strip_ansi(proc.stderr)),
        )
        self.transcript.append(
            {
                "label": label,
                "argv": list(safe_argv),
                "exit_code": proc.returncode,
                "stdout": self.safe(_strip_ansi(proc.stdout)),
                "stderr": self.safe(_strip_ansi(proc.stderr)),
            }
        )
        expected_failure = any_failure or (expect != 0)
        if expected_failure:
            if proc.returncode == 0:
                raise AssertionError(
                    f"CLI expected a nonzero exit but succeeded: "
                    f"{self._fail_detail(proc.stdout, proc.stderr)}"
                )
            if expect != 0 and not any_failure and proc.returncode != expect:
                raise AssertionError(
                    f"CLI exit {proc.returncode} (expected {expect}): "
                    f"{self._fail_detail(proc.stdout, proc.stderr)}"
                )
        elif proc.returncode != expect:
            raise AssertionError(
                f"CLI exit {proc.returncode} (expected {expect}): "
                f"{self._fail_detail(proc.stdout, proc.stderr)}"
            )
        return result

    def sql(self, query: str, *params: object) -> list[dict[str, object]]:
        """Inspect PostgreSQL via the installed driver (fixture assertion)."""
        script = (
            "import asyncio, asyncpg, json, sys\n"
            "async def main():\n"
            "    conn = await asyncpg.connect(sys.argv[1])\n"
            "    rows = await conn.fetch(sys.argv[2], *json.loads(sys.argv[3]))\n"
            "    out = []\n"
            "    for row in rows:\n"
            "        out.append({k: (v if isinstance(v, (int, float, bool)) or v is None else str(v)) for k, v in dict(row).items()})\n"
            "    print(json.dumps(out))\n"
            "    await conn.close()\n"
            "asyncio.run(main())\n"
        )
        proc = subprocess.run(
            [
                str(self.artifacts.venv_py),
                "-c",
                script,
                self.driver_url,
                query,
                json.dumps([str(p) for p in params]),
            ],
            cwd=str(self.operator_dir),
            env={
                "PATH": self.cli_env["PATH"],
                "PYTHONPATH": "",
            },
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError(self.safe(f"sql helper failed: {proc.stderr[:500]}"))
        return json.loads(proc.stdout)

    def gateway_request(
        self,
        method: str,
        path: str,
        bearer: str | None = None,
        body: object | None = None,
    ) -> tuple[int, object]:
        """Synthetic client stimulus against the installed owned gateway
        (real middleware/auth/policy/admission/diagnostics; HTTP is
        synthetic). Returns (status, parsed-json-or-text)."""
        req = urllib.request.Request(
            f"{self.gateway_url}{path}",
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            method=method,
        )
        req.add_header("Content-Type", "application/json")
        if bearer is not None:
            req.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        try:
            parsed: object = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw.decode("utf-8", "replace")
        return status, parsed

    def gateway_request_with_headers(
        self,
        method: str,
        path: str,
        bearer: str | None = None,
        body: object | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, object, dict[str, str]]:
        """Like :meth:`gateway_request`, but also returns the lower-cased
        response headers. The response's ``X-SLAIF-Diagnostic-ID`` is the
        correlation authority for diagnostics lookups (never time/IP/body
        guesses). The body is the JSON parse when possible, else the raw
        decoded text (finite SSE included)."""
        req = urllib.request.Request(
            f"{self.gateway_url}{path}",
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            method=method,
        )
        req.add_header("Content-Type", "application/json")
        if bearer is not None:
            req.add_header("Authorization", f"Bearer {bearer}")
        for name, value in (extra_headers or {}).items():
            req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                status = resp.status
                headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            headers = {k.lower(): v for k, v in exc.headers.items()}
        text = raw.decode("utf-8", "replace")
        try:
            parsed: object = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text
        return status, parsed, headers

    def persist_transcript(self, outcome: str) -> dict[str, object]:
        """Persist the labeled in-memory transcript and the safe installation
        identity as 0600 files under an owned 0700 per-run directory OUTSIDE
        the checkout (order 205-c section 7). The run token makes the
        directory unique per process run, so another run is never
        overwritten. A write failure is an EVIDENCE failure (it raises); the
        fixture teardown always completes regardless."""
        run_dir = ARTIFACT_DIR / "transcripts" / RUN_TOKEN
        run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(run_dir, 0o700)
        payload_records = [self._safe_record(record) for record in self.transcript]
        payload = {
            "run_token": RUN_TOKEN,
            "outcome": outcome,
            "record_count": len(self.transcript),
            "records": payload_records,
        }
        identity = dict(self.identity)
        identity.update(
            {
                "run_token": RUN_TOKEN,
                "container_id": self.container_id,
                "pg_port": self.pg_port,
            }
        )
        paths = {
            "transcript": run_dir / "transcript.json",
            "identity": run_dir / "identity.json",
        }
        digests: dict[str, str] = {}
        for name, document in (("transcript", payload), ("identity", identity)):
            path = paths[name]
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2)
                handle.write("\n")
            os.chmod(path, 0o600)
            digests[name] = _sha256_file(path)
        return {
            "directory": str(run_dir),
            "paths": {name: str(path) for name, path in paths.items()},
            "sha256": digests,
            "record_count": len(self.transcript),
            "labeled": [
                str(record["label"])
                for record in self.transcript
                if str(record.get("label", "")).startswith(outcome)
            ],
        }

    def _safe_record(self, record: dict[str, object]) -> dict[str, object]:
        """Reapply the current safe projection at serialization time.

        Secrets registered AFTER a CLI call was captured (for example a
        key token observed transiently through the SMTP sink) must also be
        scrubbed from the persisted transcript bytes, not only from
        records captured later."""
        safe = dict(record)
        for name in ("stdout", "stderr"):
            if isinstance(safe.get(name), str):
                safe[name] = self.safe(safe[name])
        if isinstance(safe.get("argv"), list):
            safe["argv"] = [self.safe(str(a)) for a in safe["argv"]]
        return safe
SEED_SCRIPT = r"""
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.codex_qualification import CODEX_RESPONSES_POLICY
from slaif_gateway.services.key_service import KeyService

M1 = "slaif205a-model-a"
M2 = "slaif205a-model-b"
M3 = "slaif205a-model-c"
M4 = "slaif205a-model-d"


async def main() -> None:
    settings = Settings(
        APP_ENV="development",
        DATABASE_URL=os.environ["DATABASE_URL"],
        TOKEN_HMAC_SECRET=os.environ["TOKEN_HMAC_SECRET"],
        ACTIVE_HMAC_KEY_VERSION=os.environ["ACTIVE_HMAC_KEY_VERSION"],
        ONE_TIME_SECRET_ENCRYPTION_KEY=os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"],
    )
    from slaif_gateway.modules.clients.codex_0162 import (
        bootstrap_codex_compatibility_profile,
    )

    bootstrap_codex_compatibility_profile(settings.CODEX_COMPATIBILITY_PROFILE_FILE)
    session_factory = get_sessionmaker(settings)
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            institutions = InstitutionsRepository(session)
            owners = OwnersRepository(session)
            cohorts = CohortsRepository(session)
            keys = GatewayKeysRepository(session)
            routes = ModelRoutesRepository(session)
            providers = ProviderConfigsRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys,
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
                model_routes_repository=routes,
            )

            inst_seed = await institutions.create_institution(
                name="Seed Institution 205", country="SI", notes="pre-existing fixture"
            )
            owner_seed = await owners.create_owner(
                name="Seed",
                surname="Owner",
                email="seed-owner-205a@example.invalid",
                institution_id=inst_seed.id,
                external_id="ext-seed-205a",
                notes="seed notes preserved",
            )
            owner_move = await owners.create_owner(
                name="Move",
                surname="Owner",
                email="move-owner-205a@example.invalid",
                external_id="ext-move-205a",
                notes="move notes preserved",
            )
            owner_clone_target = await owners.create_owner(
                name="Clone",
                surname="Target",
                email="clone-target-205a@example.invalid",
                institution_id=inst_seed.id,
            )
            cohort_seed = await cohorts.create_cohort(
                name="Seed Cohort 205", description="pre-existing seed cohort"
            )
            cohort37 = await cohorts.create_cohort(name="Batch Cohort 37")
            cohort_clone_target = await cohorts.create_cohort(name="Clone Target Cohort 205")
            # Both independent chat targets are cloned into this ONE existing
            # cohort (fresh operation UUIDs issue a second key to the same
            # owner/cohort; dedup is by source+operation, not by cohort).
            cohort_clone_target2 = await cohorts.create_cohort(
                name="Clone Target Cohort 205-2"
            )

            member_active = await keys.create_gateway_key_record(
                public_key_id=f"seed_member_active_{uuid.uuid4().hex[:12]}",
                token_hash=uuid.uuid4().hex,
                owner_id=owner_seed.id,
                cohort_id=cohort_seed.id,
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=30),
            )
            member_revoked = await keys.create_gateway_key_record(
                public_key_id=f"seed_member_revoked_{uuid.uuid4().hex[:12]}",
                token_hash=uuid.uuid4().hex,
                owner_id=owner_seed.id,
                cohort_id=cohort_seed.id,
                status="revoked",
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=30),
            )
            move_member = await keys.create_gateway_key_record(
                public_key_id=f"move_member_{uuid.uuid4().hex[:12]}",
                token_hash=uuid.uuid4().hex,
                owner_id=owner_move.id,
                cohort_id=cohort_seed.id,
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=30),
            )

            batch_ids = []
            for index in range(37):
                row = await keys.create_gateway_key_record(
                    public_key_id=f"batch205a_{index:02d}_{uuid.uuid4().hex[:8]}",
                    token_hash=uuid.uuid4().hex,
                    owner_id=owner_seed.id,
                    cohort_id=cohort37.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=30),
                )
                batch_ids.append(str(row.id))
            batch_revoked = await keys.create_gateway_key_record(
                public_key_id=f"batch_revoked_{uuid.uuid4().hex[:8]}",
                token_hash=uuid.uuid4().hex,
                owner_id=owner_seed.id,
                cohort_id=cohort37.id,
                status="revoked",
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=30),
            )
            batch_suspended = await keys.create_gateway_key_record(
                public_key_id=f"batch_suspended_{uuid.uuid4().hex[:8]}",
                token_hash=uuid.uuid4().hex,
                owner_id=owner_seed.id,
                cohort_id=cohort37.id,
                status="suspended",
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(days=30),
            )

            provider = await providers.create_provider_config(
                provider="openai",
                display_name="OpenAI Fixture",
                base_url="https://openai-fixture.example.invalid/v1",
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                kind="openai_compatible",
                enabled=True,
            )
            route_a = await routes.create_model_route(
                requested_model=M1, provider="openai", upstream_model="fixture-a",
                endpoint="/v1/chat/completions", enabled=True,
            )
            route_b = await routes.create_model_route(
                requested_model=M2, provider="openai", upstream_model="fixture-b",
                endpoint="/v1/chat/completions", enabled=True,
            )
            route_c = await routes.create_model_route(
                requested_model=M3, provider="openai", upstream_model="fixture-c",
                endpoint="/v1/chat/completions", enabled=True,
            )
            route_d = await routes.create_model_route(
                requested_model=M4, provider="openai", upstream_model="fixture-d",
                endpoint="/v1/chat/completions", enabled=True,
            )

            k_policy = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner_seed.id,
                    cohort_id=cohort_seed.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=365),
                    allowed_models=[M1, M2, M3],
                    allowed_endpoints=["/v1/chat/completions"],
                    rate_limit_policy={"requests_per_minute": 7, "window_seconds": 60},
                    responses_policy=dict(CODEX_RESPONSES_POLICY),
                )
            )
            k_source_chat = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner_seed.id,
                    cohort_id=cohort_seed.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=365),
                    allowed_models=[M1, M2],
                    allowed_endpoints=["/v1/chat/completions", "/v1/responses"],
                    allowed_providers=["openai"],
                    cost_limit_eur=Decimal("500.00"),
                    token_limit_total=2000000,
                    request_limit_total=5000,
                    rate_limit_policy={"requests_per_minute": 42, "window_seconds": 30},
                    lazy_throttling_policy={
                        "mode": "wait",
                        "max_wait_seconds": 30,
                        "max_waiting_requests": 4,
                    },
                    responses_policy=dict(CODEX_RESPONSES_POLICY),
                )
            )
            k_source_denyall = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner_seed.id,
                    cohort_id=cohort_seed.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=365),
                    # M1/M4 routes stay enabled for the whole fixture, so a
                    # clone CREATE from this deny-all source passes the
                    # normal enabled-model validation (M3 is disabled later).
                    allowed_models=[M1, M4],
                    allowed_endpoints=["/v1/chat/completions"],
                    allowed_providers=[],
                )
            )
            # Positive clone sources: every allowed model keeps an ENABLED
            # route for the whole fixture (clone CREATE runs the normal
            # enabled-model validation). DoD2's explain-route cases keep the
            # dedicated k_policy / k_source_chat fixtures with disabled M2/M3.
            # Student/beta source: UNLIMITED lifetime quotas, UNRESTRICTED
            # providers, fully INHERITED (NULL) rate members, plus the
            # nontrivial pinned Responses/Codex module policy and a bounded
            # lazy-throttling policy.
            k_student = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner_seed.id,
                    cohort_id=cohort_seed.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=365),
                    allowed_models=[M1, M4],
                    allowed_endpoints=["/v1/chat/completions"],
                    lazy_throttling_policy={
                        "mode": "wait",
                        "max_wait_seconds": 30,
                        "max_waiting_requests": 4,
                    },
                    responses_policy=dict(CODEX_RESPONSES_POLICY),
                )
            )
            k_source_chat_clone = await key_service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=owner_seed.id,
                    cohort_id=cohort_seed.id,
                    valid_from=now - timedelta(hours=1),
                    valid_until=now + timedelta(days=365),
                    allowed_models=[M1, M4],
                    allowed_endpoints=["/v1/chat/completions", "/v1/responses"],
                    allowed_providers=["openai"],
                    cost_limit_eur=Decimal("500.00"),
                    token_limit_total=2000000,
                    request_limit_total=5000,
                    rate_limit_policy={"requests_per_minute": 42, "window_seconds": 30},
                    lazy_throttling_policy={
                        "mode": "wait",
                        "max_wait_seconds": 30,
                        "max_waiting_requests": 4,
                    },
                    responses_policy=dict(CODEX_RESPONSES_POLICY),
                )
            )

            # Key creation validates that each allowed model has an ENABLED
            # route, so the routes were created enabled. Now leave exactly ONE
            # of the key's three allowed models (M1) on an enabled route; M2
            # and M3 become disabled, M4 stays enabled but is NOT in the
            # key's allow-list.
            assert await routes.update_model_route_metadata(route_b.id, enabled=False)
            assert await routes.update_model_route_metadata(route_c.id, enabled=False)

            manifest = {
                "models": {"m1": M1, "m2": M2, "m3": M3, "m4": M4},
                "institution_seed": str(inst_seed.id),
                "owner_seed": str(owner_seed.id),
                "owner_seed_email": "seed-owner-205a@example.invalid",
                "owner_move": str(owner_move.id),
                "owner_move_email": "move-owner-205a@example.invalid",
                "owner_clone_target": str(owner_clone_target.id),
                "cohort_seed": str(cohort_seed.id),
                "cohort37": str(cohort37.id),
                "cohort_clone_target": str(cohort_clone_target.id),
                "member_active": str(member_active.id),
                "member_revoked": str(member_revoked.id),
                "move_member": str(move_member.id),
                "batch_key_ids": batch_ids,
                "batch_revoked": str(batch_revoked.id),
                "batch_suspended": str(batch_suspended.id),
                "provider_openai": str(provider.id),
                "route_a": str(route_a.id),
                "route_b": str(route_b.id),
                "route_c": str(route_c.id),
                "route_d": str(route_d.id),
                "k_policy": str(k_policy.gateway_key_id),
                "k_policy_public": k_policy.public_key_id,
                "k_source_chat": str(k_source_chat.gateway_key_id),
                "k_source_chat_public": k_source_chat.public_key_id,
                "k_source_denyall": str(k_source_denyall.gateway_key_id),
                "k_source_denyall_public": k_source_denyall.public_key_id,
                "k_student": str(k_student.gateway_key_id),
                "k_student_public": k_student.public_key_id,
                "k_source_chat_clone": str(k_source_chat_clone.gateway_key_id),
                "k_source_chat_clone_public": k_source_chat_clone.public_key_id,
                "cohort_clone_target2": str(cohort_clone_target2.id),
            }
            print("SEED_MANIFEST " + json.dumps(manifest))


asyncio.run(main())
"""


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_pg_ready(
    driver_url: str, venv_py: Path, timeout_seconds: float = 120.0
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        proc = subprocess.run(
            [
                str(venv_py),
                "-c",
                "import asyncio, asyncpg, sys\n"
                "async def main():\n"
                "    conn = await asyncpg.connect(sys.argv[1], timeout=3)\n"
                "    await conn.close()\n"
                "asyncio.run(main())\n",
                driver_url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return
        time.sleep(1.0)
    raise AssertionError(f"PostgreSQL not ready in {int(timeout_seconds)}s")


def _migrate(pristine: Path, venv_py: Path, database_url: str) -> None:
    proc = subprocess.run(
        [str(venv_py), "-m", "alembic", "upgrade", "head"],
        cwd=str(pristine),
        env={
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "DATABASE_URL": database_url,
            "APP_ENV": "development",
        },
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise AssertionError(f"alembic upgrade head failed (exit {proc.returncode})")


class _OwnedFieldEnvironment:
    def __init__(self, tmp_base: Path) -> None:
        self._tmp_base = tmp_base
        self._env: FieldEnvironment | None = None
        self._container_id = ""
        self._password_file: Path | None = None
        self._smtp: SmtpSink | None = None
        self._provider: ProviderMock | None = None
        self._gateway: GatewayServer | None = None
        self._artifacts: Artifacts | None = None
        self._operator_dir = tmp_base / "operator"

    # -- installed gateway (order 205-c section 4) --------------------------
    def start_gateway(
        self, env_overrides: dict[str, str] | None = None
    ) -> GatewayServer:
        """Start the ACTUAL installed ``slaif_gateway.main:app`` on owned
        loopback against the owned PG. The process is registered for exact
        teardown before readiness completes, so a startup failure still
        cleans up (GatewayServer stops its own process on every failure
        path).

        Combined module runs: if a previous test (e.g. DoD5) already started
        the gateway, the EXACT prior owned process is stopped and joined
        before the handle is replaced, so the run never leaks a live child.
        ``env_overrides`` (optional) are merged over the default process
        environment; the default behavior is unchanged when omitted."""
        assert self._env is not None, "start_gateway before environment setup"
        if self._gateway is not None:
            prior = self._gateway
            prior.stop()
            if prior.proc.poll() is None:
                raise AssertionError(
                    "prior owned gateway did not terminate (fixed detail)"
                )
            self._gateway = None
        env = self._env
        proc_env = dict(env.cli_env)
        if env_overrides:
            proc_env.update(env_overrides)
        gateway = GatewayServer(
            venv_py=env.artifacts.venv_py,
            env=proc_env,
            cwd=env.operator_dir,
        )
        self._gateway = gateway  # registered; _teardown stops it
        env.gateway_url = gateway.url
        return gateway

    # -- exact-resource teardown (re-checks the per-run token) ---------------
    def _remove_container(self) -> None:
        if not self._container_id:
            return
        try:
            labels = json.loads(
                subprocess.run(
                    ["docker", "inspect", "--format", "{{json .Config.Labels}}",
                     self._container_id],
                    capture_output=True,
                    text=True,
                    timeout=60,
                ).stdout
            )
        except (AssertionError, json.JSONDecodeError):
            proc = subprocess.run(
                ["docker", "inspect", self._container_id],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if "No such object" in proc.stderr:
                return  # genuinely already absent
            raise AssertionError("cannot verify exact owned container labels")
        if labels.get("slaif205a.run") != RUN_TOKEN:
            raise AssertionError("refusing removal: container run-token mismatch")
        subprocess.run(
            ["docker", "rm", "-f", self._container_id],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        check = subprocess.run(
            ["docker", "inspect", self._container_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check.returncode == 0:
            raise AssertionError("owned container removal did not take effect")

    def _teardown(self) -> None:
        try:
            if self._gateway is not None:
                self._gateway.stop()
            if self._provider is not None:
                self._provider.stop()
            if self._smtp is not None:
                self._smtp.stop()
        finally:
            self._remove_container()
            if self._password_file is not None and self._password_file.exists():
                try:
                    self._password_file.unlink()
                except OSError:
                    pass

    # -- setup ----------------------------------------------------------------
    def __enter__(self) -> FieldEnvironment:
        self._operator_dir.mkdir(parents=True, exist_ok=True)
        (self._operator_dir / "home").mkdir(parents=True, exist_ok=True)
        try:
            return self._setup()
        except Exception:
            self._teardown()
            raise

    def _setup(self) -> FieldEnvironment:
        artifacts = _resolve_artifacts(self._tmp_base)
        self._artifacts = artifacts

        password = "slaif205a-" + secrets.token_hex(8)
        password_file = self._operator_dir / "pg-main-password"
        previous_umask = os.umask(0o077)
        try:
            password_file.write_text(password)
        finally:
            os.umask(previous_umask)
        assert (password_file.stat().st_mode & 0o777) == 0o600, "password file not 0600"
        self._password_file = password_file  # registered immediately

        port = _pick_free_port()
        run = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "--label", f"slaif205a.run={RUN_TOKEN}",
                "--label", f"slaif205a.owner=uid{os.getuid()}",
                "--label", "slaif205a.purpose=field-workflow-qualification",
                "--label", "slaif205a.order=205-a",
                "-e", f"POSTGRES_USER={PG_USER}",
                "-e", f"POSTGRES_PASSWORD={password}",
                "-e", f"POSTGRES_DB={PG_DB}",
                "--tmpfs", "/var/lib/postgresql/data:size=512m",
                "-p", f"127.0.0.1:{port}:5432",
                PG_IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if run.returncode != 0:
            raise AssertionError(f"docker run failed (exit {run.returncode})")
        self._container_id = run.stdout.strip().splitlines()[-1]  # registered immediately

        # Inspect exact ownership / loopback publish / tmpfs BEFORE migrations.
        inspect = json.loads(
            subprocess.run(
                ["docker", "inspect", "--format", "{{json .}}", self._container_id],
                capture_output=True,
                text=True,
                timeout=60,
            ).stdout
        )
        labels = inspect.get("Config", {}).get("Labels", {}) or {}
        assert labels.get("slaif205a.run") == RUN_TOKEN, "run token label mismatch"
        assert labels.get("slaif205a.order") == "205-a", "order label mismatch"
        assert (
            labels.get("slaif205a.purpose") == "field-workflow-qualification"
        ), "purpose label mismatch"
        tmpfs = (inspect.get("HostConfig") or {}).get("Tmpfs") or {}
        assert "/var/lib/postgresql/data" in tmpfs, "tmpfs data dir missing"
        bindings = (inspect.get("HostConfig") or {}).get("PortBindings") or {}
        configured = (bindings.get("5432/tcp") or [{}])[0]
        assert configured.get("HostIp") == "127.0.0.1", "configured binding not loopback"
        port_map = (
            (inspect.get("NetworkSettings", {}).get("Ports") or {}).get("5432/tcp") or []
        )
        published = (port_map or [{}])[0]
        assert published.get("HostIp") == "127.0.0.1", "published port not loopback-only"
        assert published.get("HostPort") == str(port), "published port mismatch"

        orm_url = f"postgresql+asyncpg://{PG_USER}:{password}@127.0.0.1:{port}/{PG_DB}"
        driver_url = f"postgresql://{PG_USER}:{password}@127.0.0.1:{port}/{PG_DB}"
        _wait_pg_ready(driver_url, artifacts.venv_py)
        _migrate(artifacts.pristine, artifacts.venv_py, orm_url)
        proc = subprocess.run(
            [
                str(artifacts.venv_py),
                "-c",
                "import asyncio, asyncpg, sys\n"
                "async def main():\n"
                "    conn = await asyncpg.connect(sys.argv[1])\n"
                "    print(await conn.fetchval(\"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"))\n"
                "    print(await conn.fetchval(\"SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='request_diagnostics'\"))\n"
                "    await conn.close()\n"
                "asyncio.run(main())\n",
                driver_url,
            ],
            cwd=str(self._operator_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, "table count probe failed"
        table_count, diag_count = (int(line) for line in proc.stdout.split())
        assert table_count == PUBLIC_TABLE_COUNT, (
            f"expected {PUBLIC_TABLE_COUNT} public tables at 0026 head, got {table_count}"
        )
        assert diag_count == 1, "request_diagnostics table missing at 0026 head"

        smtp = SmtpSink()
        self._smtp = smtp  # registered immediately

        hmac_secret = "slaif205a-" + secrets.token_hex(16)
        enc_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
        cli_env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": str(self._operator_dir / "home"),
            "LANG": "C.UTF-8",
            "NO_COLOR": "1",
            "APP_ENV": "development",
            "DATABASE_URL": orm_url,
            "TOKEN_HMAC_SECRET_V1": hmac_secret,
            "TOKEN_HMAC_SECRET": hmac_secret,
            "ACTIVE_HMAC_KEY_VERSION": "1",
            "ONE_TIME_SECRET_ENCRYPTION_KEY": enc_key,
            "GATEWAY_KEY_PREFIX": "sk-slaif-",
            "ENABLE_EMAIL_DELIVERY": "false",
            "ENABLE_REDIS_RATE_LIMITS": "false",
            "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE": "100",
            "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS": "5",
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": str(smtp.port),
            "SMTP_FROM": "fixture@slaif205a.invalid",
        }

        seed_script = self._operator_dir / "seed_fixture_205a.py"
        seed_script.write_text(SEED_SCRIPT)
        proc = subprocess.run(
            [str(artifacts.venv_py), str(seed_script)],
            cwd=str(self._operator_dir),
            env=cli_env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, f"seed failed (exit {proc.returncode})"
        manifest_line = next(
            (
                line
                for line in proc.stdout.splitlines()
                if line.startswith("SEED_MANIFEST ")
            ),
            None,
        )
        assert manifest_line, "seed manifest missing"
        manifest = json.loads(manifest_line[len("SEED_MANIFEST "):])

        # Installed identity facts, verified in a scrubbed environment.
        proc = subprocess.run(
            [
                str(artifacts.venv_py),
                "-c",
                "import sys, slaif_gateway as m; print(m.__file__); print(sys.version.split()[0])",
            ],
            cwd="/tmp",
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, "installed import probe failed"
        package_file, py_version = proc.stdout.splitlines()
        assert package_file.startswith(str(artifacts.venv_root)), (
            "package does not resolve from the owned venv"
        )
        identity = {
            "source_sha": SOURCE_SHA,
            "wheel_sha256": artifacts.wheel_sha256,
            "wheel_path": str(artifacts.wheel),
            "wheel_reused": artifacts.wheel_reused,
            "payload_files_verified": artifacts.payload_files,
            "installed_payload_files_verified": artifacts.installed_payload_files,
            "console": str(artifacts.console),
            "venv_root": str(artifacts.venv_root),
            "package_file": package_file,
            "venv_python": py_version,
            "artifact_steps": list(artifacts.steps),
        }

        env = FieldEnvironment(
            database_url=orm_url,
            driver_url=driver_url,
            operator_dir=self._operator_dir,
            cli_env=cli_env,
            manifest=manifest,
            identity=identity,
            artifacts=artifacts,
            smtp=smtp,
            container_id=self._container_id,
            pg_port=port,
        )
        # Known generated secrets are tracked privately and substituted in
        # every retained projection (URLs first, longest values first).
        env.register_secret(orm_url, "database-url")
        env.register_secret(driver_url, "database-url")
        env.register_secret(password, "postgres-password")
        env.register_secret(hmac_secret, "hmac-secret")
        env.register_secret(enc_key, "encryption-key")
        self._env = env
        env._gateway_launcher = self.start_gateway
        return env

    def __exit__(self, *exc: object) -> None:
        self._teardown()


@pytest.fixture(scope="session")
def field_workflow(tmp_path_factory: pytest.TempPathFactory) -> FieldEnvironment:
    tmp_base = tmp_path_factory.mktemp("slaif205-field")
    with _OwnedFieldEnvironment(tmp_base) as env:
        yield env


# --------------------------------------------------------------------------
# DoD 0: installed identity (order section 11 items 1-2)
# --------------------------------------------------------------------------


def test_dod0_installed_identity(field_workflow: FieldEnvironment) -> None:
    identity = field_workflow.identity
    assert identity["source_sha"] == SOURCE_SHA
    # The ACTUAL selected wheel SHA for this run must be recorded; payload
    # verification (not a manual ZIP hash) is the identity gate.
    assert re.fullmatch(r"[0-9a-f]{64}", str(identity["wheel_sha256"])), (
        "actual selected wheel SHA256 not recorded"
    )
    assert identity["payload_files_verified"] >= 400
    assert identity["installed_payload_files_verified"] >= 400
    assert str(identity["console"]).startswith(str(identity["venv_root"]))
    assert identity["package_file"].startswith(str(identity["venv_root"]))
    assert identity["package_file"].endswith("slaif_gateway/__init__.py")
    assert "site-packages" in identity["package_file"]
    assert field_workflow.pg_port > 0
    assert field_workflow.container_id


# --------------------------------------------------------------------------
# DoD 1-3: identities, lookup, bounded paging, bearer refusal
# --------------------------------------------------------------------------


def test_dod1_lookup_and_bounded_paging(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest

    # Institution lookup: list + show by name.
    listed = env.run_cli("institutions", "list", label="dod1-institutions-list-01").json
    assert "Seed Institution 205" in {row["name"] for row in listed["institutions"]}
    shown = env.run_cli("institutions", "show", "Seed Institution 205", label="dod1-institutions-show-02").json
    assert shown["id"] == m["institution_seed"]

    # Owner lookup: exact email list, show by UUID and by email.
    owners_listed = env.run_cli("owners", "list", "--email", m["owner_seed_email"], label="dod1-owners-list-03").json
    assert [row["id"] for row in owners_listed["owners"]] == [m["owner_seed"]]
    assert env.run_cli("owners", "show", m["owner_seed"], label="dod1-owners-show-04").json["email"] == m["owner_seed_email"]
    assert env.run_cli("owners", "show", m["owner_seed_email"], label="dod1-owners-show-05").json["id"] == m["owner_seed"]

    # Cohort lookup.
    cohorts_listed = env.run_cli("cohorts", "list", label="dod1-cohorts-list-06").json
    assert m["cohort_seed"] in {row["id"] for row in cohorts_listed["cohorts"]}
    assert env.run_cli("cohorts", "show", m["cohort_seed"], label="dod1-cohorts-show-07").json["name"] == "Seed Cohort 205"

    # Key lookup by public key ID and by exact owner email.
    by_public = env.run_cli("keys", "show", m["k_policy_public"], label="dod1-keys-show-08").json
    assert by_public["id"] == m["k_policy"]
    by_email = env.run_cli(
        "keys", "list", "--owner-email", m["owner_seed_email"], "--limit", "100",
        label="dod1-keys-list-09",
    ).json
    assert m["k_policy"] in {row["id"] for row in by_email["keys"]}

    # Complete bounded paging over the 39-row cohort (37 active + revoked +
    # suspended controls), no overlap, no loss.
    page1 = env.run_cli("keys", "list", "--cohort-id", m["cohort37"], "--limit", "20", label="dod1-keys-list-10").json
    assert page1["paging"]["returned"] == 20
    assert page1["paging"]["has_more"] is True
    assert page1["paging"]["next_offset"] == 20
    page2 = env.run_cli(
        "keys", "list", "--cohort-id", m["cohort37"], "--limit", "20", "--offset", "20",
        label="dod1-keys-list-11",
    ).json
    assert page2["paging"]["returned"] == 19
    assert page2["paging"]["has_more"] is False
    assert page2["paging"]["next_offset"] is None
    ids = [row["id"] for row in page1["keys"] + page2["keys"]]
    assert len(ids) == 39 and len(set(ids)) == 39
    expected = set(m["batch_key_ids"]) | {m["batch_revoked"], m["batch_suspended"]}
    assert set(ids) == expected

    # Full bearer-shaped lookup refuses WITHOUT echo (fixed safe message).
    bearer = "sk-slaif-" + "0" * 8 + secrets.token_hex(16)
    refused = env.run_cli("keys", "show", bearer, expect=1, label="dod1-keys-show-12")
    combined = refused.stdout + refused.stderr
    assert "Full key material cannot be used for lookup" in combined
    assert "public key ID" in combined
    assert bearer not in combined, env.safe("bearer echoed in refusal output")
    # The synthetic bearer must not survive into the retained transcript.
    for entry in env.transcript:
        assert bearer not in json.dumps(entry)


# --------------------------------------------------------------------------
# DoD 1-3: effective policy and route explanation (configuration-only)
# --------------------------------------------------------------------------


def test_dod2_effective_policy_and_route_explanation(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    models = m["models"]

    report = env.run_cli("keys", "policy", "effective", m["k_policy"], label="dod2-keys-policy-01").json
    assert report["scope"] == "configuration-only"
    rate = report["rate_limits"]
    # Configured versus inherited rate members with explicit sources.
    assert rate["requests_per_window"] == {
        "configured": 7,
        "effective": 7,
        "source": "key",
    }
    assert rate["tokens_per_window"] == {
        "configured": None,
        "effective": 100,
        "source": "deployment",
    }
    assert rate["concurrency"] == {
        "configured": None,
        "effective": 5,
        "source": "deployment",
    }
    assert rate["window_seconds"]["configured"] == 60
    assert rate["window_seconds"]["source"] == "key"
    # Unlimited lifetime quotas are explicit, never guessed.
    assert report["quotas"]["cost_eur"]["unlimited"] is True
    assert report["quotas"]["cost_eur"]["configured"] is None
    assert report["quotas"]["tokens"]["unlimited"] is True
    # Allow-lists and the pinned Responses/Codex module identity.
    assert report["allowlists"]["allowed_models"] == [
        models["m1"],
        models["m2"],
        models["m3"],
    ]
    assert report["allowlists"]["allowed_endpoints"] == ["/v1/chat/completions"]
    assert report["allowlists"]["state"] == "unrestricted"
    assert report["responses_profile"]["policy_state"] == "valid"

    # Three allowed models, but only ONE enabled endpoint/model route.
    allowed = env.run_cli(
        "keys", "policy", "explain-route", m["k_policy"],
        "--model", models["m1"], "--endpoint", "/v1/chat/completions",
        label="dod2-keys-policy-02",
    ).json
    assert allowed["verdict"] == "resolved"
    assert allowed["blocker"] is None
    assert allowed["endpoint_allowed"] is True
    assert allowed["bounds"]["routes_examined"] >= 3

    disabled = env.run_cli(
        "keys", "policy", "explain-route", m["k_policy"],
        "--model", models["m2"], "--endpoint", "/v1/chat/completions",
        label="dod2-keys-policy-03",
    ).json
    assert disabled["verdict"] == "blocked"
    assert disabled["blocker"] == "model-route-disabled"

    disallowed = env.run_cli(
        "keys", "policy", "explain-route", m["k_policy"],
        "--model", models["m4"], "--endpoint", "/v1/chat/completions",
        label="dod2-keys-policy-04",
    ).json
    assert disallowed["verdict"] == "blocked"
    assert disallowed["blocker"] == "model-not-allowed-for-key"


# --------------------------------------------------------------------------
# DoD 3: record operations through installed commands
# --------------------------------------------------------------------------


def test_dod3_record_operations(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest

    # (a) Create the fictional target institution exactly once.
    created = env.run_cli(
        "institutions", "create", "--name", "Field Institution 205",
        "--country", "SI", "--notes", "field qualification target",
        label="dod3-institutions-create-01",
    ).json
    inst_id = created["id"]
    assert created["name"] == "Field Institution 205"
    assert env.run_cli("institutions", "show", inst_id, label="dod3-institutions-show-02").json["name"] == "Field Institution 205"

    # Normalized (whitespace-padded) duplicate is refused; count unchanged.
    before = len(env.run_cli("institutions", "list", label="dod3-institutions-list-03").json["institutions"])
    dup = env.run_cli(
        "institutions", "create", "--name", "  Field Institution 205  ", any_failure=True,
        label="dod3-institutions-create-04",
    )
    dup_text = (dup.stdout + dup.stderr).lower()
    assert "already" in dup_text or "exist" in dup_text
    after = env.run_cli("institutions", "list", label="dod3-institutions-list-05").json["institutions"]
    assert len(after) == before

    # (b) Owner created under the new institution; list/show resolve it.
    owner = env.run_cli(
        "owners", "create", "--name", "Field", "--surname", "Participant",
        "--email", "field-participant-205a@example.invalid",
        "--institution-id", inst_id, "--notes", "new field owner",
        label="dod3-owners-create-06",
    ).json
    owner_id = owner["id"]
    assert owner["institution_id"] == inst_id
    assert owner_id in {row["id"] for row in env.run_cli("owners", "list", label="dod3-owners-list-07").json["owners"]}

    # (c) Cohort created; supported cohort edit with omission/clear rules.
    cohort = env.run_cli(
        "cohorts", "create", "--name", "Field Cohort 205", "--description", "initial",
        label="dod3-cohorts-create-08",
    ).json
    cohort_id = cohort["id"]
    edited = env.run_cli(
        "cohorts", "update", cohort_id, "--reason", "update field cohort description",
        "--description", "updated",
        label="dod3-cohorts-update-09",
    ).json
    assert edited["description"] == "updated"
    assert edited["name"] == "Field Cohort 205"  # omitted field preserved
    cleared = env.run_cli(
        "cohorts", "update", cohort_id, "--reason", "clear field cohort description",
        "--clear-description",
        label="dod3-cohorts-update-10",
    ).json
    assert cleared["description"] is None

    # Missing reason refuses without mutation.
    no_reason = env.run_cli(
        "cohorts", "update", cohort_id, "--description", "should not land",
        any_failure=True,
        label="dod3-cohorts-update-11",
    )
    assert "reason" in (no_reason.stdout + no_reason.stderr).lower()
    assert env.run_cli("cohorts", "show", cohort_id, label="dod3-cohorts-show-12").json["description"] is None

    # (d) owners update: move the pre-existing owner to the NEW institution,
    # preserving omitted metadata / is_active / external_id / member keys.
    moved = env.run_cli(
        "owners", "update", m["owner_move"],
        "--reason", "move owner to field institution",
        "--institution-id", inst_id,
        label="dod3-owners-update-13",
    ).json
    assert moved["id"] == m["owner_move"]
    assert moved["institution_id"] == inst_id
    assert moved["is_active"] is True  # omitted -> preserved
    rows = env.sql("SELECT external_id, notes FROM owners WHERE id = $1", m["owner_move"])
    assert rows[0]["external_id"] == "ext-move-205a"
    assert rows[0]["notes"] == "move notes preserved"
    member_rows = env.sql(
        "SELECT id, status, owner_id FROM gateway_keys WHERE id = $1", m["move_member"]
    )
    assert member_rows[0]["status"] == "active"
    assert member_rows[0]["owner_id"] == m["owner_move"]

    # Conflicting replacement + clear flags refuse without mutation.
    env.run_cli(
        "owners", "update", m["owner_move"], "--reason", "conflict probe",
        "--external-id", "conflicting", "--clear-external-id", any_failure=True,
        label="dod3-owners-update-14",
    )
    assert env.sql("SELECT external_id FROM owners WHERE id = $1", m["owner_move"])[0][
        "external_id"
    ] == "ext-move-205a"

    # Unknown UUID refuses without mutation.
    unknown = env.run_cli(
        "owners", "update", str(uuid.uuid4()), "--reason", "unknown owner probe",
        "--notes", "should not land", any_failure=True,
        label="dod3-owners-update-15",
    )
    assert unknown.exit_code != 0

    # No invented cohort-institution relationship: the cohort surface carries
    # no institution flag at all (proven on the ACTUAL installed help).
    help_proc = subprocess.run(
        [str(env.artifacts.console), "cohorts", "update", "--help"],
        cwd=str(env.operator_dir),
        env=env.cli_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert help_proc.returncode == 0
    assert "--institution" not in _strip_ansi(help_proc.stdout)
    final = env.run_cli(
        "cohorts", "update", cohort_id, "--reason", "final field cohort edit",
        "--description", "final",
        label="dod3-cohorts-update-16",
    ).json
    assert final["description"] == "final"


# --------------------------------------------------------------------------
# DoD 4: exact student/beta + TWO chat clones
# --------------------------------------------------------------------------

_POLICY_VIEW_FIELDS = (
    "allowed_models",
    "allowed_endpoints",
    "allow_all_models",
    "allow_all_endpoints",
    "allowed_providers",
    "allowed_providers_state",
    "rate_limit_policy",
    "responses_policy",
    "chat_streaming_live_burn_policy",
    "external_tool_policy",
    "key_purpose",
    "capability_policy_mode",
)


def _policy_view(
    env: FieldEnvironment, key_id: str, label: str = ""
) -> dict[str, object]:
    row = env.run_cli("keys", "show", key_id, label=label).json
    return {field: row[field] for field in _POLICY_VIEW_FIELDS}


def _full_key_row(env: FieldEnvironment, key_id: str) -> dict[str, object]:
    return env.sql("SELECT * FROM gateway_keys WHERE id = $1", key_id)[0]


def _export_policy(
    env: FieldEnvironment, key_id: str, label: str = ""
) -> dict[str, object]:
    """Installed FULL canonical policy export (always JSON on stdout; the
    command has no --json flag)."""
    result = env.run_cli(
        "keys", "policy", "export", key_id, json_output=False, label=label
    )
    document = json.loads(result.stdout)
    assert document.get("schema_version") == 1
    return document


def _clone_cohort_count(env: FieldEnvironment, cohort_id: str) -> int:
    return (
        env.sql(
            "SELECT count(*)::int AS c FROM gateway_keys WHERE cohort_id = $1",
            cohort_id,
        )[0]["c"]
    )


def _audit_count(env: FieldEnvironment) -> int:
    return env.sql("SELECT count(*)::int AS c FROM audit_log")[0]["c"]


def test_dod4_exact_student_beta_and_chat_clones(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    plans = env.operator_dir / "clone-plans"
    plans.mkdir(exist_ok=True)

    src_student = str(m["k_student"])            # unlimited/inherited positive source
    src_chat = str(m["k_source_chat_clone"])     # nontrivial positive chat source
    src_deny = str(m["k_source_denyall"])        # deny-all control
    src_student_before = _full_key_row(env, src_student)
    src_chat_before = _full_key_row(env, src_chat)
    src_deny_before = _full_key_row(env, src_deny)
    export_student = _export_policy(env, src_student, label="dod4-export-policy-01")
    export_chat = _export_policy(env, src_chat, label="dod4-export-policy-02")
    export_deny = _export_policy(env, src_deny, label="dod4-export-policy-03")

    audit_before = _audit_count(env)
    assert _clone_cohort_count(env, str(m["cohort_clone_target"])) == 0
    assert _clone_cohort_count(env, str(m["cohort_clone_target2"])) == 0

    # (a) Mixed-mode probes refuse with the fixed code BEFORE any plan work.
    both = env.run_cli(
        "keys", "clone",
        "--dry-run", str(plans / "both.json"),
        "--execute", str(plans / "both2.json"),
        any_failure=True,
        label="dod4-keys-clone-04",
    )
    assert both.json["error"]["code"] == "invalid_parameter"
    for flag, label in (
        ("--show-plaintext", "dry-pt"),
        ("--secret-output-file", "dry-file"),
    ):
        probe = env.run_cli(
            "keys", "clone", "--dry-run", str(plans / f"{label}.json"),
            "--source-key-id", src_chat,
            "--target-owner-id", str(m["owner_clone_target"]),
            "--validity-mode", "copy-source-expiry",
            flag, *(["dry-file.txt"] if flag == "--secret-output-file" else []),
            any_failure=True,
            label="dod4-keys-clone-05",
        )
        assert probe.json["error"]["code"] == "invalid_parameter", label

    # (b) Reviewed plans for ALL FOUR targets (dry-run mutates nothing).
    # Student/beta in its own cohort; the TWO independent chat targets share
    # ONE existing cohort (distinct operations from the same source).
    targets = {
        "student": (src_student, str(m["cohort_clone_target"])),
        "chat1": (src_chat, str(m["cohort_clone_target2"])),
        "chat2": (src_chat, str(m["cohort_clone_target2"])),
        "denyall": (src_deny, None),
    }
    plan_files: dict[str, Path] = {}
    for name, (source, cohort) in targets.items():
        plan_file = plans / f"clone-{name}.json"
        args = [
            "keys", "clone", "--dry-run", str(plan_file),
            "--source-key-id", source,
            "--target-owner-id", str(m["owner_clone_target"]),
            "--validity-mode", "copy-source-expiry",
        ]
        if cohort is not None:
            args += ["--target-cohort-id", cohort]
        planned = env.run_cli(*args, label="dod4-call-06").json
        plan_files[name] = plan_file
        assert planned["source_gateway_key_id"] == source
        assert planned["validity"]["mode"] == "copy-source-expiry"
        assert planned["operation_uuid"]
        assert planned["target_cohort_id"] == cohort
        assert (plan_file.stat().st_mode & 0o777) == 0o600
        plan_text = plan_file.read_text()
        assert "source_fingerprint" in plan_text
        assert "sk-slaif-" not in plan_text and "sk-proj-" not in plan_text
    for cohort in (
        str(m["cohort_clone_target"]),
        str(m["cohort_clone_target2"]),
    ):
        assert _clone_cohort_count(env, cohort) == 0
    assert _audit_count(env) == audit_before
    assert _full_key_row(env, src_chat) == src_chat_before

    # (c) Unknown typed field in an OTHERWISE VALID plan: strict refusal,
    # no echo of the field or its value, no writes.
    unknown_file = plans / "clone-unknown-field.json"
    unknown_doc = json.loads(plan_files["student"].read_text())
    unknown_doc["bogus_typed_field"] = {"nested": "value"}
    unknown_file.write_text(json.dumps(unknown_doc))
    unknown = env.run_cli(
        "keys", "clone", "--execute", str(unknown_file),
        "--reason", "unknown typed field probe",
        "--secret-output-file", str(plans / "secret-unknown.txt"),
        any_failure=True,
        label="dod4-keys-clone-07",
    )
    assert unknown.json["error"]["code"] == "cli_error"
    assert "bogus_typed_field" not in unknown.json["error"]["message"]
    assert (plans / "secret-unknown.txt").exists() is False
    assert _clone_cohort_count(env, str(m["cohort_clone_target"])) == 0

    # (d) Execute requires EXACTLY ONE explicit one-time key channel, with
    # every other execute argument valid.
    no_channel = env.run_cli(
        "keys", "clone", "--execute", str(plan_files["denyall"]),
        "--reason", "no channel probe", any_failure=True,
        label="dod4-keys-clone-08",
    )
    assert no_channel.json["error"]["code"] == "invalid_parameter"
    two_channels = env.run_cli(
        "keys", "clone", "--execute", str(plan_files["denyall"]),
        "--reason", "two channel probe",
        "--secret-output-file", str(plans / "two.txt"),
        "--show-plaintext",
        any_failure=True,
        label="dod4-keys-clone-09",
    )
    assert two_channels.json["error"]["code"] == "invalid_parameter"
    assert (plans / "two.txt").exists() is False  # refused before any write

    # (e) Execute all four with the single secure-file channel.
    executed: dict[str, dict[str, object]] = {}
    targets_out: dict[str, str] = {}
    for name in ("student", "chat1", "chat2", "denyall"):
        secret_file = plans / f"secret-{name}.txt"
        result = env.run_cli(
            "keys", "clone", "--execute", str(plan_files[name]),
            "--reason", f"clone {name} target",
            "--secret-output-file", str(secret_file),
            label="dod4-keys-clone-10",
        ).json
        assert result["status"] == "created", result
        target = str(result["target_gateway_key_id"])
        targets_out[name] = target
        assert (secret_file.stat().st_mode & 0o777) == 0o600
        plaintext = secret_file.read_text()
        assert plaintext.startswith("sk-slaif-")
        secret_file.unlink()  # generated key file deleted; never retained
        for entry in env.transcript:
            assert plaintext not in json.dumps(entry)
        executed[name] = result

    # Distinct independent material for every target (private Boolean
    # comparisons only; token material is never echoed or retained).
    all_ids = [targets_out[n] for n in targets_out] + [src_student, src_chat, src_deny]
    hashes = [
        env.sql("SELECT token_hash AS h FROM gateway_keys WHERE id = $1", key_id)[0]["h"]
        for key_id in all_ids
    ]
    assert len(set(hashes)) == len(all_ids)

    # Both chat targets live in the ONE existing cohort: exactly two distinct
    # keys, both owned by the reviewed target owner.
    chat_cohort = str(m["cohort_clone_target2"])
    chat_rows = env.sql(
        "SELECT id AS id, owner_id AS owner_id FROM gateway_keys "
        "WHERE cohort_id = $1 ORDER BY id",
        chat_cohort,
    )
    assert {str(r["id"]) for r in chat_rows} == {
        targets_out["chat1"], targets_out["chat2"],
    }
    assert all(str(r["owner_id"]) == str(m["owner_clone_target"]) for r in chat_rows)

    # (f) Per-target clone contract.
    source_of = {
        "student": src_student, "chat1": src_chat, "chat2": src_chat, "denyall": src_deny,
    }
    before_of = {
        "student": src_student_before, "chat1": src_chat_before,
        "chat2": src_chat_before, "denyall": src_deny_before,
    }
    cohort_of = {
        "student": m["cohort_clone_target"], "chat1": m["cohort_clone_target2"],
        "chat2": m["cohort_clone_target2"], "denyall": None,
    }
    export_of = {
        "student": export_student, "chat1": export_chat,
        "chat2": export_chat, "denyall": export_deny,
    }
    for name, target in targets_out.items():
        row = _full_key_row(env, target)
        source_before = before_of[name]
        # Reviewed target selection: owner and cohort identities.
        assert row["owner_id"] == str(m["owner_clone_target"])
        assert row["cohort_id"] == cohort_of[name]
        assert row["status"] == "active"
        # copy-source-expiry: fresh valid_from at EXECUTION time (the source
        # is an hour old), SAME reviewed valid_until.
        assert row["valid_until"] == source_before["valid_until"]
        assert row["valid_from"] > source_before["valid_from"]
        # FULL canonical configuration equality via the installed export.
        assert _export_policy(env, target, label="dod4-export-policy-11") == export_of[name]
        # Actual nullable configured columns equal the source row-for-row.
        for column in (
            "cost_limit_eur", "token_limit_total", "request_limit_total",
            "rate_limit_requests_per_minute", "rate_limit_tokens_per_minute",
            "max_concurrent_requests", "allowed_models", "allowed_endpoints",
            "allow_all_models", "allow_all_endpoints", "key_purpose",
            "capability_policy_mode",
        ):
            assert row[column] == source_before[column], column
        # Independent identity; the raw metadata deliberately gains the
        # clone receipt/provenance, so it is compared via that receipt, not
        # by source==target byte equality.
        assert row["id"] != source_before["id"]
        assert row["public_key_id"] != source_before["public_key_id"]
        assert row["key_hint"] != source_before["key_hint"]
        receipt = json.loads(row["metadata"])["clone_receipt"]
        assert receipt["operation_uuid"] == executed[name]["operation_uuid"]
        assert receipt["source_gateway_key_id"] == source_of[name]
        # Zero usage, reservations, holds, templates, replay state.
        assert float(row["cost_used_eur"]) == 0.0
        assert int(row["tokens_used_total"]) == 0
        assert int(row["requests_used_total"]) == 0
        assert float(row["cost_reserved_eur"]) == 0.0
        assert int(row["tokens_reserved_total"]) == 0
        assert int(row["requests_reserved_total"]) == 0
        assert row["external_tool_fence_state"] == "none"
        assert row["template_id"] is None and row["template_revision_id"] is None
        for table in (
            "quota_reservations", "codex_replay_references", "usage_ledger",
        ):
            assert (
                env.sql(
                    f"SELECT count(*)::int AS c FROM {table} WHERE gateway_key_id = $1",
                    target,
                )[0]["c"]
                == 0
            )

    # (g) The positive sources are NONTRIVIAL, not generic empty clones.
    assert export_chat["rate_limit_policy"] == {
        "requests_per_minute": 42, "window_seconds": 30,
    }
    assert export_chat["lazy_throttling_policy"] == {
        "mode": "wait", "max_wait_seconds": 30, "max_waiting_requests": 4,
    }
    # Numeric(18,9) storage scale renders the exact stored decimal.
    assert Decimal(str(export_chat["cost_limit_eur"])) == Decimal("500.00")
    assert export_chat["token_limit_total"] == 2000000
    assert export_chat["request_limit_total"] == 5000
    assert export_chat["allowed_providers"] == ["openai"]
    assert export_chat["responses_policy"] is not None
    assert "client_module" in json.dumps(export_chat["responses_policy"])
    # Student/beta: unlimited quotas + inherited rate members, yet the
    # pinned Codex policy and bounded lazy policy are present and exact.
    assert export_student["cost_limit_eur"] is None
    assert export_student["token_limit_total"] is None
    assert export_student["request_limit_total"] is None
    assert export_student["rate_limit_policy"] is None
    assert export_student["responses_policy"] == export_chat["responses_policy"]
    assert export_student["lazy_throttling_policy"] == export_chat["lazy_throttling_policy"]
    # Deny-all control: empty provider allow-list, distinct from unrestricted.
    assert export_deny["allowed_providers"] == []
    assert _policy_view(env, targets_out["denyall"], label="dod4-policy-view-12")["allowed_providers_state"] == "deny-all"
    assert _policy_view(env, src_student, label="dod4-policy-view-13")["allowed_providers_state"] == "unrestricted"

    # Effective-source views on the actual nullable configured rate columns.
    chat_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["chat1"],
        label="dod4-keys-policy-14",
    ).json["rate_limits"]
    assert chat_eff["requests_per_window"] == {
        "configured": 42, "effective": 42, "source": "key",
    }
    assert chat_eff["window_seconds"]["configured"] == 30
    assert chat_eff["window_seconds"]["source"] == "key"
    student_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["student"],
        label="dod4-keys-policy-15",
    ).json["rate_limits"]
    assert student_eff["requests_per_window"]["configured"] is None
    assert student_eff["requests_per_window"]["source"] == "none"

    # (h) Sources are unchanged BEFORE the deliberate mutation probe.
    target_chat1_before = _full_key_row(env, targets_out["chat1"])
    assert _full_key_row(env, src_student) == src_student_before
    assert _full_key_row(env, src_chat) == src_chat_before
    assert _full_key_row(env, src_deny) == src_deny_before
    # Each executed clone writes TWO audits: the shared key-creation audit
    # plus the clone-operation audit; nothing else was written.
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM audit_log WHERE action = 'gateway_key_cloned'"
        )[0]["c"]
        == 4
    )
    assert _audit_count(env) == audit_before + 8

    # (i) Exact repeat of a COMPLETED plan deduplicates: no new key,
    # secret, or audit.
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM one_time_secrets WHERE gateway_key_id = $1",
            targets_out["chat1"],
        )[0]["c"]
        == 1
    )
    repeat = env.run_cli(
        "keys", "clone", "--execute", str(plan_files["chat1"]),
        "--reason", "exact repeat of completed clone plan",
        "--secret-output-file", str(plans / "secret-repeat.txt"),
        label="dod4-keys-clone-16",
    ).json
    assert repeat["status"] == "already-applied"
    assert str(repeat["target_gateway_key_id"]) == targets_out["chat1"]
    assert (plans / "secret-repeat.txt").exists() is False  # no second secret written
    assert _clone_cohort_count(env, chat_cohort) == 2
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM one_time_secrets WHERE gateway_key_id = $1",
            targets_out["chat1"],
        )[0]["c"]
        == 1
    )
    assert _audit_count(env) == audit_before + 8  # dedup writes no audit

    # (j) Stale law: a NEVER-EXECUTED plan refuses after the source changes
    # (fixed code, no writes), while the COMPLETED plan still deduplicates.
    stale_file = plans / "clone-stale.json"
    env.run_cli(
        "keys", "clone", "--dry-run", str(stale_file),
        "--source-key-id", src_chat,
        "--target-owner-id", str(m["owner_clone_target"]),
        "--target-cohort-id", str(m["cohort_clone_target2"]),
        "--validity-mode", "copy-source-expiry",
        label="dod4-keys-clone-17",
    )
    env.run_cli(
        "keys", "set-rate-limits", src_chat,
        "--requests-per-minute", "43",
        "--reason", "stale-plan source mutation",
        label="dod4-keys-set-rate-limits-18",
    ).assert_ok("source rate mutation")
    # The deliberate source mutation writes its own single audit row; the
    # stale refusal and the dedup re-run must add nothing beyond it.
    audit_after_mutation = _audit_count(env)
    assert audit_after_mutation == audit_before + 9
    stale = env.run_cli(
        "keys", "clone", "--execute", str(stale_file),
        "--reason", "stale never-executed plan probe",
        "--secret-output-file", str(plans / "secret-stale.txt"),
        any_failure=True,
        label="dod4-keys-clone-19",
    )
    assert stale.json["error"]["code"] == "key_clone_stale_plan"
    assert (plans / "secret-stale.txt").exists() is False
    assert _clone_cohort_count(env, chat_cohort) == 2
    assert _audit_count(env) == audit_after_mutation  # stale writes no audit

    # The completed plan deduplicates BEFORE fresh source validation, even
    # after the source edit: same target, no new secret, no new audit.
    repeat2 = env.run_cli(
        "keys", "clone", "--execute", str(plan_files["chat1"]),
        "--reason", "repeat of completed plan after source mutation",
        "--secret-output-file", str(plans / "secret-repeat2.txt"),
        label="dod4-keys-clone-20",
    ).json
    assert repeat2["status"] == "already-applied"
    assert str(repeat2["target_gateway_key_id"]) == targets_out["chat1"]
    assert (plans / "secret-repeat2.txt").exists() is False
    assert _export_policy(env, targets_out["chat1"], label="dod4-export-policy-21") == export_chat
    assert _audit_count(env) == audit_after_mutation  # dedup writes no audit
    # The executed chat1 target is unchanged by the source mutation.
    assert _full_key_row(env, targets_out["chat1"]) == target_chat1_before
    chat1_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["chat1"],
        label="dod4-keys-policy-22",
    ).json["rate_limits"]
    assert chat1_eff["requests_per_window"] == {
        "configured": 42, "effective": 42, "source": "key",
    }


# --------------------------------------------------------------------------
# DoD 6: rates, bounded lazy configuration, exact-37 batch
# --------------------------------------------------------------------------

_RATE_ROW_COLUMNS = (
    "rate_limit_requests_per_minute",
    "rate_limit_tokens_per_minute",
    "max_concurrent_requests",
    "metadata",  # actual DB column (ORM attribute is metadata_json)
    "updated_at",
)


def test_dod6_rates_lazy_and_exact37_batch(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    k = str(m["k_policy"])
    row_before = _full_key_row(env, k)

    # (a) Operational rates within actual installation bounds.
    result = env.run_cli(
        "keys", "set-rate-limits", k,
        "--requests-per-minute", "1", "--window-seconds", "10",
        "--concurrent-requests", "1",
        "--reason", "field qualification operational rate",
        label="dod6-keys-set-rate-limits-01",
    ).json
    assert result["rate_limit_policy"] == {
        "requests_per_minute": 1,
        "window_seconds": 10,
        "max_concurrent_requests": 1,
    }
    row_after = _full_key_row(env, k)
    rate_view = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-02").json["rate_limits"]
    assert rate_view["requests_per_window"] == {
        "configured": 1, "effective": 1, "source": "key",
    }
    assert rate_view["window_seconds"]["configured"] == 10
    assert rate_view["window_seconds"]["source"] == "key"
    assert rate_view["concurrency"] == {
        "configured": 1, "effective": 1, "source": "key",
    }
    # Unrelated quotas / expiry / material preserved.
    for column, before, after in (
        (c, row_before[c], row_after[c]) for c in row_before if c not in _RATE_ROW_COLUMNS
    ):
        assert before == after, f"unrelated column {column} changed"
    # The rate WINDOW lives inside metadata["rate_limit_policy"];
    # compare the metadata with exactly that key popped from both sides.
    meta_before = (
        json.loads(row_before["metadata"]) if row_before["metadata"] else {}
    )
    meta_after = (
        json.loads(row_after["metadata"]) if row_after["metadata"] else {}
    )
    meta_before.pop("rate_limit_policy", None)
    meta_after.pop("rate_limit_policy", None)
    assert meta_before == meta_after, "unrelated metadata_json fields changed"
    stored_rate = env.sql(
        "SELECT metadata->'rate_limit_policy' AS r FROM gateway_keys WHERE id = $1",
        k,
    )[0]["r"]
    # The metadata block carries ONLY the rate window; the rps/concurrency
    # members live in the dedicated nullable key columns (checked below via
    # the effective view and the source-equality column loop in DoD4).
    assert json.loads(stored_rate) == {"window_seconds": 10}
    assert row_after["rate_limit_requests_per_minute"] == 1
    assert row_after["max_concurrent_requests"] == 1
    assert row_after["rate_limit_tokens_per_minute"] is None

    # Non-positive bound refuses without mutation.
    env.run_cli(
        "keys", "set-rate-limits", k, "--requests-per-minute", "0",
        "--reason", "non-positive probe", any_failure=True,
        label="dod6-keys-set-rate-limits-03",
    )
    assert _full_key_row(env, k) == row_after

    # (b) Bounded lazy throttling within actual installation ceilings.
    row_before_lazy = _full_key_row(env, k)
    env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "4",
        "--reason", "field qualification lazy wait",
        label="dod6-keys-set-lazy-throttling-04",
    ).assert_ok("lazy set")
    row_after_lazy_set = _full_key_row(env, k)
    lazy = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-05").json["lazy_throttling"]
    assert lazy["mode"] == "wait"
    assert lazy["max_wait_seconds"] == 30
    assert lazy["max_waiting_requests"] == 4
    assert lazy["stored_state"] == "wait-configured"
    assert lazy["source"] == "key"
    # Unknown mode refuses before any mutation.
    # (Option-level validation is a NATIVE Typer BadParameter: exit 2 with a
    # fixed safe stderr message and no JSON payload.)
    bad_mode = env.run_cli(
        "keys", "set-lazy-throttling", k, "--mode", "bogus",
        "--reason", "invalid mode probe", any_failure=True,
        label="dod6-keys-set-lazy-throttling-06",
    )
    assert bad_mode.exit_code == 2
    assert "wait or reject" in bad_mode.stderr
    # Excessive bounds refuse WITH the other mandatory bound supplied, so
    # the refusal is the installation ceiling (120s / 16 waiting), not a
    # missing input.
    over_wait = env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "5000",
        "--max-waiting-requests", "4",
        "--reason", "excessive wait probe", any_failure=True,
        label="dod6-keys-set-lazy-throttling-07",
    )
    assert over_wait.exit_code == 2
    assert "operator ceiling" in over_wait.stderr
    over_waiting = env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "999",
        "--reason", "excessive waiting probe", any_failure=True,
        label="dod6-keys-set-lazy-throttling-08",
    )
    assert over_waiting.exit_code == 2
    assert "operator ceiling" in over_waiting.stderr
    # Refusals mutate nothing.
    assert _full_key_row(env, k) == row_after_lazy_set
    # --mode reject from a valid wait state removes the stored override
    # (default immediate rejection); rates and material are preserved.
    rates_before = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-09").json["rate_limits"]
    env.run_cli(
        "keys", "set-lazy-throttling", k, "--mode", "reject",
        "--reason", "lazy reject transition from wait",
        label="dod6-keys-set-lazy-throttling-10",
    ).assert_ok("lazy reject")
    lazy_reject = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-11").json["lazy_throttling"]
    assert lazy_reject["mode"] == "reject"
    assert lazy_reject["stored_state"] == "absent"
    assert lazy_reject["source"] == "default"
    # In reject mode the numeric members are the inert schema defaults, not
    # a configured wait (mode/stored_state/source carry the distinction).
    assert (
        env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-12").json["rate_limits"]
        == rates_before
    )
    # Re-establish the wait override, then --clear: a distinct verb with the
    # SAME stored outcome (no override / immediate rejection).
    env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "4",
        "--reason", "lazy re-wait before clear",
        label="dod6-keys-set-lazy-throttling-13",
    ).assert_ok("lazy re-wait")
    env.run_cli(
        "keys", "set-lazy-throttling", k, "--clear",
        "--reason", "lazy clear transition",
        label="dod6-keys-set-lazy-throttling-14",
    ).assert_ok("lazy clear")
    lazy_cleared = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-15").json["lazy_throttling"]
    assert lazy_cleared["mode"] == "reject"
    assert lazy_cleared["stored_state"] == "absent"
    assert lazy_cleared["source"] == "default"
    assert (
        env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-16").json["rate_limits"]
        == rates_before
    )
    # The lazy transitions only touched the lazy override plus updated_at.
    row_after_lazy = _full_key_row(env, k)
    for column, before, after in (
        (c, row_before_lazy[c], row_after_lazy[c])
        for c in row_before_lazy
        if c not in ("metadata", "updated_at")
    ):
        assert before == after, f"lazy transition changed unrelated column {column}"
    meta_lazy_before = json.loads(row_before_lazy["metadata"])
    meta_lazy_after = json.loads(row_after_lazy["metadata"])
    meta_lazy_before.pop("lazy_throttling_policy", None)
    meta_lazy_after.pop("lazy_throttling_policy", None)
    assert meta_lazy_before == meta_lazy_after

    # (c) Reset-to-inherit is explicit, never mislabeled.
    env.run_cli(
        "keys", "set-rate-limits", k, "--clear-all",
        "--reason", "reset operational rate to deployment inheritance",
        label="dod6-keys-set-rate-limits-17",
    ).assert_ok("rate clear-all")
    cleared = env.run_cli("keys", "policy", "effective", k, label="dod6-keys-policy-18").json["rate_limits"]
    assert cleared["requests_per_window"] == {
        "configured": None, "effective": None, "source": "none",
    }
    assert cleared["tokens_per_window"] == {
        "configured": None, "effective": 100, "source": "deployment",
    }

    # (d) Exact-37 cohort batch: preview, stale refusal, UUID re-review, apply.
    policy_file = env.operator_dir / "batch-policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rate_limit_policy": {
                    "requests_per_minute": 5,
                    "tokens_per_minute": 25,
                    "max_concurrent_requests": 2,
                    "window_seconds": 15,
                },
            }
        )
    )
    cohort37 = str(m["cohort37"])
    plan_file = env.operator_dir / "batch-cohort-plan.json"
    plan = env.run_cli(
        "keys", "batch", "plan",
        "--cohort-id", cohort37,
        "--policy-file", str(policy_file),
        "--plan-file", str(plan_file),
        label="dod6-keys-batch-19",
    ).json
    p = plan["plan"]
    assert p["selection_kind"] == "cohort"
    assert p["selected_count"] == 37
    assert p["changed_count"] == 37
    assert p["unchanged_count"] == 0
    # Cohort selection applies the status filter at the DB boundary: only
    # the 37 ACTIVE members are selected and the cohort preview reports no
    # per-key exclusions (that contract is explicit-UUID selection below).
    assert p["excluded_by_status"] == []
    assert len(p["keys"]) == 37
    plan_text = plan_file.read_text()
    assert "source_fingerprint" in plan_text and "post_fingerprint" in plan_text

    # New cohort member created with the INSTALLED command AFTER preview.
    member_secret = env.operator_dir / "new-member-secret.txt"
    created = env.run_cli(
        "keys", "create",
        "--owner-id", str(m["owner_seed"]),
        "--cohort-id", cohort37,
        "--valid-days", "30",
        "--allowed-model", str(m["models"]["m1"]),
        "--allowed-endpoint", "/v1/chat/completions",
        "--reason", "new cohort member created after batch preview",
        "--secret-output-file", str(member_secret),
        label="dod6-keys-create-20",
    ).json
    member_secret.unlink()
    new_key_id = str(created["gateway_key_id"])
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM gateway_keys WHERE cohort_id = $1 AND status = 'active'",
            cohort37,
        )[0]["c"]
        == 38
    )

    # The saved cohort plan is now STALE: apply refuses, ZERO changes/audits.
    # The no-new-audit baseline is sampled AFTER the deliberate membership
    # change (the installed create writes its own audit), immediately before
    # the stale apply.
    audit_before = _audit_count(env)
    stale_apply = env.run_cli(
        "keys", "batch", "apply",
        "--plan-file", str(plan_file),
        "--reason", "stale cohort plan apply probe",
        any_failure=True,
        label="dod6-keys-batch-21",
    )
    # KeyBatchStaleError is a KeyManagementError subclass carrying its own
    # fixed safe error code: the installed boundary surfaces that code
    # directly (it is not a plain KeyBatchError command failure).
    assert stale_apply.json["error"]["code"] == "key_batch_stale"
    assert _audit_count(env) == audit_before
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM gateway_keys WHERE cohort_id = $1 AND rate_limit_requests_per_minute = 5",
            cohort37,
        )[0]["c"]
        == 0
    )

    # Re-review an EXPLICIT exact-37 UUID selection (does not include the
    # new member), then apply to the original set only.
    key_args: list[str] = []
    for key_id in m["batch_key_ids"]:
        key_args += ["--key-id", str(key_id)]
    plan2_file = env.operator_dir / "batch-uuid-plan.json"
    plan2 = env.run_cli(
        "keys", "batch", "plan",
        *key_args,
        "--policy-file", str(policy_file),
        "--plan-file", str(plan2_file),
        label="dod6-keys-batch-22",
    ).json
    p2 = plan2["plan"]
    assert p2["selection_kind"] == "keys"
    assert p2["selected_count"] == 37
    assert p2["changed_count"] == 37
    assert new_key_id not in json.dumps(p2)
    assert p2["excluded_by_status"] == []

    # Explicit-UUID selection that ALSO names the revoked/suspended controls
    # REPORTS them as excluded (never selected, never changed).
    probe_args = [*key_args,
                  "--key-id", str(m["batch_revoked"]),
                  "--key-id", str(m["batch_suspended"])]
    probe_file = env.operator_dir / "batch-uuid-probe.json"
    probe = env.run_cli(
        "keys", "batch", "plan",
        *probe_args,
        "--policy-file", str(policy_file),
        "--plan-file", str(probe_file),
        label="dod6-keys-batch-23",
    ).json
    pp = probe["plan"]
    assert pp["selection_kind"] == "keys"
    assert pp["selected_count"] == 37
    assert {e["status"] for e in pp["excluded_by_status"]} == {"revoked", "suspended"}
    assert {e["key_id"] for e in pp["excluded_by_status"]} == {
        str(m["batch_revoked"]), str(m["batch_suspended"]),
    }
    assert str(m["batch_revoked"]) not in json.dumps(pp["keys"])

    sample = str(m["batch_key_ids"][0])
    sample_before = _full_key_row(env, sample)
    applied = env.run_cli(
        "keys", "batch", "apply",
        "--plan-file", str(plan2_file),
        "--reason", "apply reviewed exact-37 batch",
        label="dod6-keys-batch-24",
    ).json
    assert applied["status"] == "applied"
    assert applied["selected_count"] == 37
    assert applied["changed_count"] == 37
    assert applied["unchanged_count"] == 0

    # Exactly 37 keys carry the canonical configuration; metadata window too.
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM gateway_keys "
            "WHERE cohort_id = $1 AND rate_limit_requests_per_minute = 5 "
            "AND rate_limit_tokens_per_minute = 25 AND max_concurrent_requests = 2",
            cohort37,
        )[0]["c"]
        == 37
    )
    assert (
        env.sql(
            "SELECT count(*)::int AS c FROM gateway_keys "
            "WHERE cohort_id = $1 "
            "AND metadata->'rate_limit_policy'->>'window_seconds' = '15'",
            cohort37,
        )[0]["c"]
        == 37
    )
    # New / revoked / suspended members remain untouched.
    for untouched in (new_key_id, str(m["batch_revoked"]), str(m["batch_suspended"])):
        assert (
            env.sql(
                "SELECT rate_limit_requests_per_minute AS r FROM gateway_keys WHERE id = $1",
                untouched,
            )[0]["r"]
            is None
        )
    # Per-key audits were written for exactly the 37 applied keys.
    audit_after = env.sql("SELECT count(*)::int AS c FROM audit_log")[0]["c"]
    assert audit_after - audit_before == 37

    # Unrelated fields / usage / material preserved on an applied key.
    sample_row = _full_key_row(env, sample)
    for column, before, after in (
        (c, sample_before[c], sample_row[c]) for c in sample_before if c not in _RATE_ROW_COLUMNS
    ):
        assert before == after, f"batch changed unrelated column {column}"
    # Batch window is stored in metadata["rate_limit_policy"]; compare
    # the metadata with exactly that key popped from both sides.
    meta_sample_before = (
        json.loads(sample_before["metadata"])
        if sample_before["metadata"]
        else {}
    )
    meta_sample_after = (
        json.loads(sample_row["metadata"]) if sample_row["metadata"] else {}
    )
    meta_sample_before.pop("rate_limit_policy", None)
    meta_sample_after.pop("rate_limit_policy", None)
    assert meta_sample_before == meta_sample_after, (
        "batch changed unrelated metadata_json fields"
    )
    assert float(sample_row["cost_used_eur"]) == 0.0
    assert int(sample_row["tokens_used_total"]) == 0
    assert sample_row["valid_from"] and sample_row["valid_until"]


# --------------------------------------------------------------------------
# DoD 5: actual filtered model discovery through the installed gateway
# (order 205-c section 4). The gateway is the ACTUAL installed
# ``slaif_gateway.main:app`` (real middleware/auth/policy/catalog); the HTTP
# stimulus is synthetic. Administrative mutations are installed CLI calls.
# --------------------------------------------------------------------------


def test_dod5_filtered_model_discovery(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    m1 = str(m["models"]["m1"])
    m2 = str(m["models"]["m2"])
    m3 = str(m["models"]["m3"])
    m4 = str(m["models"]["m4"])

    # (a) Dedicated synthetic key issued through the INSTALLED CLI with ONE
    # explicit secure output channel. The generated value is registered
    # BEFORE the private file is removed. (Seed keys are pre-existing
    # fixture setup; this is the operator-issued key under demonstration.)
    bearer_file = env.operator_dir / "discovery-bearer.txt"
    created = env.run_cli(
        "keys", "create",
        "--owner-id", str(m["owner_seed"]),
        "--cohort-id", str(m["cohort_seed"]),
        "--valid-days", "30",
        "--allowed-model", m1,
        "--allowed-endpoint", "/v1/chat/completions",
        "--reason", "discovery qualification key",
        "--secret-output-file", str(bearer_file),
        label="dod5-discovery-keys-create",
    ).json
    bearer = bearer_file.read_text().strip()
    key_prefix = env.cli_env["GATEWAY_KEY_PREFIX"]
    bearer_has_prefix = bearer.startswith(key_prefix) and len(bearer) > len(key_prefix)
    assert bearer_has_prefix, "issued key does not carry the configured prefix"
    env.register_secret(bearer, "discovery-bearer")
    bearer_file.unlink()
    key_id = str(created["gateway_key_id"])
    assert key_id

    # (b) Baseline: effective policy and key material/expiry BEFORE the grant.
    effective_before = env.run_cli(
        "keys", "policy", "effective", key_id,
        label="dod5-discovery-policy-before",
    ).json
    assert effective_before["allowlists"]["allowed_models"] == [m1]
    assert effective_before["allowlists"]["allowed_endpoints"] == [
        "/v1/chat/completions"
    ]
    row_before = _full_key_row(env, key_id)
    export_before = _export_policy(env, key_id, label="dod5-discovery-export-before")
    metadata_before = env.sql(
        "SELECT metadata FROM gateway_keys WHERE id = $1", key_id
    )[0]["metadata"]

    # (c) Actual installed gateway on owned loopback against the owned PG.
    env.start_gateway()

    # (d) Denied BEFORE the grant: OpenAI-shaped 403 error, no model data.
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 403
    assert isinstance(body, dict) and "error" in body

    # (e) Bearer-shaped LOOKUP refusal with a known synthetic value: the
    # refusal must not echo it, and the retained record must carry the
    # shape mask, not the value (artifact canary evidence).
    canary_bearer = key_prefix + "0" * 8 + secrets.token_hex(16)
    env.register_secret(canary_bearer, "canary-bearer")
    refused = env.run_cli(
        "keys", "show", canary_bearer, expect=1,
        label="dod5-discovery-bearer-refusal",
    )
    refusal_no_echo = canary_bearer not in (refused.stdout + refused.stderr)
    assert refusal_no_echo, "canary bearer echoed in refusal output"
    assert "Full key material cannot be used for lookup" in (
        refused.stdout + refused.stderr
    )

    # (f) Installed policy grant. Endpoint arrays REPLACE, so the inference
    # endpoint is explicitly retained while /v1/models is added.
    env.run_cli(
        "keys", "policy", "update", key_id,
        "--allowed-endpoint", "/v1/chat/completions",
        "--allowed-endpoint", "/v1/models",
        "--reason", "grant model discovery endpoint",
        label="dod5-discovery-policy-grant",
    ).assert_ok("policy update grant")

    # (g) Actual filtered GET /v1/models: exactly the ONE permitted model
    # with an enabled, visible route on the enabled provider.
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert isinstance(body, dict)
    data = body["data"]
    assert [row["id"] for row in data] == [m1]
    for row in data:
        assert row["object"] == "model"
        assert row["created"] == 0
        assert row["owned_by"] == "openai"
    visible = {row["id"] for row in data}
    # m4: enabled visible route on the enabled provider but NOT in the key's
    # model allow-list -> a genuine allow-list exclusion (the route/provider
    # dimensions do not already hide it). m2/m3: routes disabled in the
    # pre-existing fixture state.
    assert m4 not in visible
    assert m2 not in visible and m3 not in visible

    # (h) Explicit PROVIDER allow-list controls (arrays REPLACE): an explicit
    # single-provider list still serves the permitted model; an EMPTY list
    # denies every provider, so the catalog empties even though the model is
    # allowed and its route is enabled (the only excluding dimension is the
    # provider allow-list); unrestricted restores it.
    env.run_cli(
        "keys", "policy", "update", key_id,
        "--allowed-provider", "openai",
        "--reason", "explicit provider allow-list",
        label="dod5-discovery-provider-allow",
    ).assert_ok("provider allow")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert [row["id"] for row in body["data"]] == [m1]
    env.run_cli(
        "keys", "policy", "update", key_id,
        "--provider-none",
        "--reason", "deny all providers control",
        label="dod5-discovery-provider-none",
    ).assert_ok("provider none")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert body["data"] == []
    env.run_cli(
        "keys", "policy", "update", key_id,
        "--provider-all",
        "--reason", "restore unrestricted provider access",
        label="dod5-discovery-provider-all",
    ).assert_ok("provider all")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert [row["id"] for row in body["data"]] == [m1]

    # (i) DISABLED-PROVIDER control: the sole provider goes disabled, so the
    # catalog empties even though the model is allowed and the route enabled;
    # re-enabling restores exactly the filtered set.
    env.run_cli(
        "providers", "disable", "openai", label="dod5-discovery-provider-disable"
    ).assert_ok("provider disable")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert body["data"] == []
    env.run_cli(
        "providers", "enable", "openai", label="dod5-discovery-provider-enable"
    ).assert_ok("provider enable")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert [row["id"] for row in body["data"]] == [m1]

    # (j) Disabled-route control: the ONLY permitted route goes disabled,
    # so the catalog empties even though the allow-list still names m1;
    # re-enabling restores exactly the filtered set.
    route_a = str(m["route_a"])
    env.run_cli(
        "routes", "disable", route_a, label="dod5-discovery-route-disable"
    ).assert_ok("route disable")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert body["data"] == []
    env.run_cli(
        "routes", "enable", route_a, label="dod5-discovery-route-enable"
    ).assert_ok("route enable")
    status, body = env.gateway_request("GET", "/v1/models", bearer=bearer)
    assert status == 200
    assert [row["id"] for row in body["data"]] == [m1]

    # (k) After all controls, the net policy change is ONLY the endpoint
    # array: model restrictions, the (restored) provider state, rates,
    # quotas and the Responses profile unchanged; key material and expiry
    # unchanged (a lawful authentication last-used timestamp is not a
    # policy mutation and is intentionally not compared).
    effective_after = env.run_cli(
        "keys", "policy", "effective", key_id,
        label="dod5-discovery-policy-after",
    ).json
    assert effective_after["allowlists"]["allowed_models"] == [m1]
    assert effective_after["allowlists"]["allowed_endpoints"] == [
        "/v1/chat/completions",
        "/v1/models",
    ]
    assert effective_after["allowlists"]["state"] == "unrestricted"
    for section in ("rate_limits", "quotas", "responses_profile"):
        assert effective_after[section] == effective_before[section]
    # Canonical service-owned configuration: the ONLY change across the
    # whole version-1 document is the endpoint array member.
    export_after = _export_policy(
        env, key_id, label="dod5-discovery-export-after"
    )
    assert export_before["allowed_endpoints"] == ["/v1/chat/completions"]
    assert export_after["allowed_endpoints"] == [
        "/v1/chat/completions",
        "/v1/models",
    ]
    before_rest = {
        key: value for key, value in export_before.items()
        if key != "allowed_endpoints"
    }
    after_rest = {
        key: value for key, value in export_after.items()
        if key != "allowed_endpoints"
    }
    assert before_rest == after_rest, (
        "grant changed more than the endpoint array in the canonical policy"
    )
    # Storage level: the metadata-backed policy (provider allow-list state,
    # Responses profile, ...) is untouched.
    metadata_after = env.sql(
        "SELECT metadata FROM gateway_keys WHERE id = $1", key_id
    )[0]["metadata"]
    assert metadata_after == metadata_before
    row_after = _full_key_row(env, key_id)
    material_changed = row_after["token_hash"] != row_before["token_hash"]
    assert not material_changed, "grant changed the key material"
    expiry_changed = (
        row_after["valid_from"] != row_before["valid_from"]
        or row_after["valid_until"] != row_before["valid_until"]
    )
    assert not expiry_changed, "grant changed the key validity window"
    for column in (
        "cost_limit_eur", "token_limit_total", "request_limit_total",
        "allowed_models", "allow_all_models", "allow_all_endpoints",
    ):
        assert row_after[column] == row_before[column], column

    # (l) Persist the labeled transcript and safe identity for this outcome.
    persisted = env.persist_transcript("dod5-discovery")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    assert persisted["labeled"] == [
        "dod5-discovery-keys-create",
        "dod5-discovery-policy-before",
        "dod5-discovery-export-before",
        "dod5-discovery-bearer-refusal",
        "dod5-discovery-policy-grant",
        "dod5-discovery-provider-allow",
        "dod5-discovery-provider-none",
        "dod5-discovery-provider-all",
        "dod5-discovery-provider-disable",
        "dod5-discovery-provider-enable",
        "dod5-discovery-route-disable",
        "dod5-discovery-route-enable",
        "dod5-discovery-policy-after",
        "dod5-discovery-export-after",
    ]
    # Actual labeled argv boundaries survive (the operator transcript is not
    # reduced to booleans), while every known generated secret is absent
    # from the persisted bytes.
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    document = json.loads(transcript_path.read_text())
    records = document["records"]
    by_label = {str(record["label"]): record for record in records}
    create_record = by_label["dod5-discovery-keys-create"]
    assert create_record["argv"][1:3] == ["keys", "create"]
    grant_record = by_label["dod5-discovery-policy-grant"]
    assert key_id in grant_record["argv"]
    refusal_record = by_label["dod5-discovery-bearer-refusal"]
    argv_masked = "<REFUSED-BEARER-SHAPE>" in refusal_record["argv"]
    assert argv_masked, "bearer-shaped argv not shape-masked in the transcript"
    refusal_unmasked = any(
        canary_bearer in arg for arg in refusal_record["argv"]
    )
    assert not refusal_unmasked, "canary bearer retained in a transcript argv"
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )




# --------------------------------------------------------------------------
# DoD 7: two configured completion services (order 205-c section 5).
# Fictional module providers/pricing/routes through the EXISTING installed
# commands, reusing the objective-199 qualified shapes (exact public/
# upstream/profile mappings, module kind, non-streaming, zero retries).
# No provider HTTP occurs; configuration activation is not credential,
# execution, or protocol-compatibility qualification.
# --------------------------------------------------------------------------

ZAP_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {
            "chat_text": True,
            "chat_streaming": False,
            "chat_function_tools": True,
        },
        "codex_limits": {
            "context_window_tokens": 1050000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 128000,
        },
        "media_input_estimation": {
            "version": 1,
            "image_tokens": 1024,
            "video_tokens": 2048,
            "video_frames": 8,
        },
        "completion_service": {"version": 1, "profile": "zap-it-v1"},
    },
}

FACIAL_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {"chat_text": True, "chat_streaming": False},
        "completion_service": {"version": 1, "profile": "facial-scoring-v1"},
    },
}


def test_dod7_two_configured_completion_services(
    field_workflow: FieldEnvironment,
) -> None:
    env = field_workflow

    # (a) Two fictional module providers, DISABLED preparation (installed
    # default), distinct origins and env-reference NAMES (names only, no
    # credential values), custom timeouts, retries 0.
    for slug, display, base, env_ref, timeout in (
        ("svc-a", "Svc A", "https://svc-a.example/api", "SVC_A_KEY", 30),
        ("svc-b", "Svc B", "https://svc-b.example/api", "SVC_B_KEY", 180),
    ):
        added = env.run_cli(
            "providers", "add",
            "--provider", slug,
            "--display-name", display,
            "--kind", "module",
            "--base-url", base,
            "--api-key-env-var", env_ref,
            "--timeout-seconds", str(timeout),
            "--max-retries", "0",
            "--reason", "fictional module preparation",
            label=f"dod7-providers-add-{slug}",
        ).json
        assert added["enabled"] is False, "installed default: stays DISABLED"
        assert added["kind"] == "module"
        assert added["max_retries"] == 0
        assert added["timeout_seconds"] == timeout
        assert added["api_key_env_var"] == env_ref

    # (b) Pricing rows through the existing installed command; exact Decimal
    # semantics surfaced as decimal strings in JSON.
    for slug, model in (
        ("svc-a", "zap-it-1"),
        ("svc-b", "facial-manipulation-scoring"),
    ):
        rule = env.run_cli(
            "pricing", "add",
            "--provider", slug,
            "--model", model,
            "--input-price-per-1m", "0.01",
            "--output-price-per-1m", "0.03",
            label=f"dod7-pricing-add-{slug}",
        ).json
        assert rule["model"] == model
        listed = env.run_cli(
            "pricing", "list", "--provider", slug,
            label=f"dod7-pricing-list-{slug}",
        ).json
        rows = [
            row for row in listed["pricing_rules"] if row["model"] == model
        ]
        assert len(rows) == 1
        # Exact Decimal semantics at the storage scale (Numeric 18,9):
        # equal values, not string identity.
        assert Decimal(rows[0]["input_price_per_1m"]) == Decimal("0.01")
        assert Decimal(rows[0]["output_price_per_1m"]) == Decimal("0.03")
        assert rows[0]["currency"] == "EUR"
        assert rows[0]["enabled"] is True

    # (c) Capabilities-file routes prepared DISABLED (deliberate installed
    # default), non-streaming, on the zero-retry module providers, with the
    # exact bundled profile mappings.
    zap_caps_file = env.operator_dir / "dod7-zap-caps.json"
    facial_caps_file = env.operator_dir / "dod7-facial-caps.json"
    zap_caps_file.write_text(json.dumps(ZAP_CAPS))
    facial_caps_file.write_text(json.dumps(FACIAL_CAPS))
    routes: dict[str, str] = {}
    for name, model, slug, caps_file in (
        ("zap", "zap-it-1", "svc-a", zap_caps_file),
        ("facial", "facial-manipulation-scoring", "svc-b", facial_caps_file),
    ):
        created = env.run_cli(
            "routes", "add",
            "--requested-model", model,
            "--match-type", "exact",
            "--provider", slug,
            "--upstream-model", model,
            "--no-streaming",
            "--capabilities-file", str(caps_file),
            "--priority", "100",
            "--reason", "two-service workflow route preparation",
            label=f"dod7-routes-add-{name}",
        ).json
        assert created["enabled"] is False, (
            "capabilities-file preparation stays DISABLED"
        )
        assert created["supports_streaming"] is False
        routes[name] = str(created["id"])

    # (d) Inspect the prepared state: capabilities, provider facts, disabled.
    shown_zap = env.run_cli(
        "routes", "show", routes["zap"], label="dod7-routes-show-zap"
    ).json
    assert shown_zap["capabilities"] == ZAP_CAPS["capabilities"]
    assert shown_zap["enabled"] is False
    assert shown_zap["supports_streaming"] is False
    shown_facial = env.run_cli(
        "routes", "show", routes["facial"], label="dod7-routes-show-facial"
    ).json
    assert shown_facial["capabilities"] == FACIAL_CAPS["capabilities"]
    assert shown_facial["enabled"] is False
    for slug, timeout, env_ref, base in (
        ("svc-a", 30, "SVC_A_KEY", "https://svc-a.example/api"),
        ("svc-b", 180, "SVC_B_KEY", "https://svc-b.example/api"),
    ):
        shown = env.run_cli(
            "providers", "show", slug, label=f"dod7-providers-show-{slug}"
        ).json
        assert shown["kind"] == "module"
        assert shown["enabled"] is False
        assert shown["timeout_seconds"] == timeout
        assert shown["max_retries"] == 0
        assert shown["api_key_env_var"] == env_ref
        assert shown["base_url"] == base

    # (e) Existing useful refusals: incompatible kind/profile/streaming/
    # retry combinations are denied with fixed safe errors, zero rows.
    streaming = env.run_cli(
        "routes", "add",
        "--requested-model", "zap-it-1",
        "--match-type", "exact",
        "--provider", "svc-a",
        "--upstream-model", "zap-it-1",
        "--capabilities-file", str(zap_caps_file),
        "--priority", "100",
        "--reason", "streaming profile probe",
        any_failure=True,
        label="dod7-routes-reject-streaming",
    )
    assert streaming.json["error"]["code"] == "invalid_value"
    assert "does not support streaming on this route" in streaming.json[
        "error"
    ]["message"]
    kind = env.run_cli(
        "routes", "add",
        "--requested-model", "zap-it-1",
        "--match-type", "exact",
        "--provider", "openai",
        "--upstream-model", "zap-it-1",
        "--no-streaming",
        "--capabilities-file", str(zap_caps_file),
        "--priority", "100",
        "--reason", "kind-mismatch profile probe",
        any_failure=True,
        label="dod7-routes-reject-kind",
    )
    assert kind.json["error"]["code"] == "invalid_value"
    assert "requires a module provider kind" in kind.json["error"]["message"]
    retry_provider = env.run_cli(
        "providers", "add",
        "--provider", "svc-retry",
        "--display-name", "Svc Retry",
        "--kind", "module",
        "--base-url", "https://svc-retry.example/api",
        "--api-key-env-var", "SVC_RETRY_KEY",
        "--timeout-seconds", "30",
        "--max-retries", "1",
        "--reason", "retry provider probe",
        label="dod7-providers-add-retry-probe",
    ).json
    assert retry_provider["max_retries"] == 1
    retry_route = env.run_cli(
        "routes", "add",
        "--requested-model", "zap-it-1",
        "--match-type", "exact",
        "--provider", "svc-retry",
        "--upstream-model", "zap-it-1",
        "--no-streaming",
        "--capabilities-file", str(zap_caps_file),
        "--priority", "100",
        "--reason", "retry profile probe",
        any_failure=True,
        label="dod7-routes-reject-retry",
    )
    assert retry_route.json["error"]["code"] == "invalid_value"
    assert "must not retry" in retry_route.json["error"]["message"]

    # (f) SEPARATE explicit activation of BOTH providers and BOTH routes.
    for slug in ("svc-a", "svc-b"):
        enabled = env.run_cli(
            "providers", "enable", slug, label=f"dod7-providers-enable-{slug}"
        ).json
        assert enabled["enabled"] is True
    for name in ("zap", "facial"):
        enabled = env.run_cli(
            "routes", "enable", routes[name],
            label=f"dod7-routes-enable-{name}",
        ).json
        assert enabled["enabled"] is True
    for name, caps in (("zap", ZAP_CAPS), ("facial", FACIAL_CAPS)):
        shown = env.run_cli(
            "routes", "show", routes[name],
            label=f"dod7-routes-show-enabled-{name}",
        ).json
        assert shown["enabled"] is True
        assert shown["capabilities"] == caps["capabilities"]

    # (g) Partial provider update preserves omitted siblings; the unrelated
    # provider is untouched.
    openai_before = env.run_cli(
        "providers", "show", "openai", label="dod7-providers-show-openai"
    ).json
    svc_a_before = env.run_cli(
        "providers", "show", "svc-a", label="dod7-providers-show-svca"
    ).json
    updated = env.run_cli(
        "providers", "update", "svc-a",
        "--timeout-seconds", "45",
        "--reason", "adjust upstream timeout",
        label="dod7-providers-update-svca",
    ).json
    assert updated["timeout_seconds"] == 45
    for column in (
        "provider", "display_name", "kind", "base_url",
        "api_key_env_var", "enabled", "max_retries",
    ):
        assert updated[column] == svc_a_before[column], column
    openai_after = env.run_cli(
        "providers", "show", "openai", label="dod7-providers-show-openai-2"
    ).json
    assert openai_after == openai_before

    # (h) Persist the labeled transcript and safe identity for this outcome.
    persisted = env.persist_transcript("dod7")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    expected_labels = {
        "dod7-providers-add-svc-a",
        "dod7-providers-add-svc-b",
        "dod7-pricing-add-svc-a",
        "dod7-pricing-list-svc-a",
        "dod7-pricing-add-svc-b",
        "dod7-pricing-list-svc-b",
        "dod7-routes-add-zap",
        "dod7-routes-add-facial",
        "dod7-routes-show-zap",
        "dod7-routes-show-facial",
        "dod7-providers-show-svc-a",
        "dod7-providers-show-svc-b",
        "dod7-routes-reject-streaming",
        "dod7-routes-reject-kind",
        "dod7-providers-add-retry-probe",
        "dod7-routes-reject-retry",
        "dod7-providers-enable-svc-a",
        "dod7-routes-enable-zap",
        "dod7-providers-enable-svc-b",
        "dod7-routes-enable-facial",
        "dod7-routes-show-enabled-zap",
        "dod7-routes-show-enabled-facial",
        "dod7-providers-show-openai",
        "dod7-providers-show-svca",
        "dod7-providers-update-svca",
        "dod7-providers-show-openai-2",
    }
    assert set(persisted["labeled"]) == expected_labels
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )


# --------------------------------------------------------------------------
# DoD 8: stable route context/media updates (order 205-c section 6).
# Two dedicated routes on the existing openai_compatible provider are
# prepared disabled with coherent initial capability data; each receives
# its OWN reviewed two-step plan (dry-run then execute, plan bound to the
# route UUID), so the multi-route change is explicitly selected, never a
# hidden global edit. The context ceiling genuinely INCREASES to 400000
# from a lower valid value on route 1 and to 420000 on route 2 (separate
# multi-leaf plan). A re-applied plan is refused stale with zero
# additional mutation/audit. Pre-existing fictional ledger/replay ROUTE
# links, a nontrivial key's policy/material, and the installed
# completion-profile/module data are all proven unchanged. No
# delete/recreate, no SQL business mutation, no shared-service bypass.
# --------------------------------------------------------------------------

M8 = "slaif205a-model-e"
M8B = "slaif205a-model-f"

M8_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {
            "chat_text": True,
            "chat_streaming": True,
            "chat_function_tools": True,
        },
        "codex_limits": {
            "context_window_tokens": 105000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 65536,
        },
        "media_input_estimation": {
            "version": 1,
            "image_tokens": 1000,
            "video_tokens": 2000,
            "video_frames": 8,
        },
    },
}

M8B_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {
            "chat_text": True,
            "chat_streaming": True,
            "chat_function_tools": False,
        },
        "codex_limits": {
            "context_window_tokens": 210000,
            "default_max_output_tokens": 16384,
            "max_output_tokens": 32768,
        },
        "media_input_estimation": {
            "version": 1,
            "image_tokens": 500,
            "video_tokens": 1000,
            "video_frames": 4,
        },
    },
}


def _profile_data_fingerprint(env: FieldEnvironment) -> dict[str, str]:
    """SHA256 over the INSTALLED completion-service profile/module data
    (bundled versioned data the routes may reference). Route edits must
    never touch it."""
    package_file = Path(str(env.identity["package_file"]))
    profile_dir = (
        package_file.parent / "modules" / "servers" / "completion_service" / "profiles"
    )
    assert profile_dir.is_dir(), "installed completion profile data missing"
    fingerprint: dict[str, str] = {}
    for file in sorted(profile_dir.iterdir()):
        if file.is_file():
            fingerprint[file.name] = _sha256_file(file)
    assert fingerprint, "installed completion profile data empty"
    return fingerprint


async def _plant_dod8_history(
    orm_url: str, owner_id: uuid.UUID, route_id: uuid.UUID
) -> dict[str, str]:
    """Plant the DoD8 pre-existing history rows (fixture setup, one session).

    Mirrors the 199 ORM planting pattern: typed UUID/datetime columns through
    SQLAlchemy, so no raw string-bound driver SQL. Fictional linkage only:
    constant synthetic digests, no gateway-key plaintext.
    """
    engine = create_async_engine(orm_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    past = now - timedelta(days=2)
    try:
        async with factory() as session:
            async with session.begin():
                key = await GatewayKeysRepository(session).create_gateway_key_record(
                    public_key_id=f"pk_hist_205c_{uuid.uuid4().hex[:8]}",
                    token_hash=uuid.uuid4().hex * 2,
                    owner_id=owner_id,
                    valid_from=past,
                    valid_until=now + timedelta(days=30),
                    allowed_models=[M8],
                )
                request_id = f"req-205c-{uuid.uuid4().hex[:8]}"
                ledger = UsageLedger(
                    request_id=request_id,
                    gateway_key_id=key.id,
                    owner_id=owner_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model=M8,
                    resolved_model=M8,
                    started_at=past,
                    finished_at=past,
                )
                session.add(ledger)
                await session.flush()
                replay = CodexReplayReference(
                    gateway_key_id=key.id,
                    usage_ledger_id=ledger.id,
                    source_request_id=request_id,
                    provider="openai",
                    route_id=route_id,
                    upstream_model="fixture-e",
                    item_kind="reasoning",
                    item_id_hmac="a" * 64,
                    hmac_key_version=1,
                    expires_at=now + timedelta(days=365),
                )
                session.add(replay)
                await session.flush()
                return {
                    "key_id": str(key.id),
                    "ledger_id": str(ledger.id),
                    "replay_id": str(replay.id),
                    "request_id": request_id,
                }
    finally:
        await engine.dispose()


def test_dod8_stable_route_context_media_updates(
    field_workflow: FieldEnvironment,
) -> None:
    env = field_workflow
    m = env.manifest
    plans = env.operator_dir / "dod8-plans"
    plans.mkdir(exist_ok=True)
    caps_file = env.operator_dir / "dod8-m8-caps.json"
    caps_file_b = env.operator_dir / "dod8-m8b-caps.json"
    caps_file.write_text(json.dumps(M8_CAPS))
    caps_file_b.write_text(json.dumps(M8B_CAPS))

    # Two dedicated routes, prepared DISABLED (capabilities-file default),
    # with coherent LOW context values the increases will move from.
    created = env.run_cli(
        "routes", "add",
        "--requested-model", M8,
        "--match-type", "exact",
        "--provider", "openai",
        "--upstream-model", "fixture-e",
        "--capabilities-file", str(caps_file),
        "--priority", "100",
        "--reason", "stable-update qualification route",
        label="dod8-routes-add",
    ).json
    route_id = str(created["id"])
    assert created["enabled"] is False
    created_b = env.run_cli(
        "routes", "add",
        "--requested-model", M8B,
        "--match-type", "exact",
        "--provider", "openai",
        "--upstream-model", "fixture-f",
        "--capabilities-file", str(caps_file_b),
        "--priority", "100",
        "--reason", "stable-update qualification route second target",
        label="dod8-routes-add-second",
    ).json
    route_b_id = str(created_b["id"])
    assert created_b["enabled"] is False
    assert route_b_id != route_id

    # Fictional historical linkage (fixture setup, NOT an operator action):
    # a pre-existing key + usage-ledger row + replay reference bound to the
    # FIRST route, planted through the ORM (199 reference pattern) with
    # typed UUID/datetime parameters rather than raw string-bound SQL.
    # Constant synthetic digests only; no generated plaintext exists, so
    # nothing new needs secret registration.
    hist = asyncio.run(
        _plant_dod8_history(
            env.driver_url.replace("postgresql://", "postgresql+asyncpg://", 1),
            uuid.UUID(str(m["owner_seed"])),
            uuid.UUID(route_id),
        )
    )
    hist_key_id = hist["key_id"]
    hist_ledger_id = hist["ledger_id"]
    hist_replay_id = hist["replay_id"]

    def _replay_snapshot() -> dict[str, object]:
        return env.sql(
            "SELECT id, gateway_key_id, usage_ledger_id, source_request_id, "
            "provider, route_id, upstream_model, item_kind, item_id_hmac, "
            "hmac_key_version, created_at, expires_at "
            "FROM codex_replay_references WHERE id = $1",
            str(hist_replay_id),
        )[0]

    replay_before = _replay_snapshot()
    ledger_before = env.sql(
        "SELECT id, gateway_key_id, request_id FROM usage_ledger WHERE id = $1",
        str(hist_ledger_id),
    )[0]
    hist_key_before = _full_key_row(env, hist_key_id)

    # Meaningful existing key policy (pinned Responses/Codex module policy
    # plus configured rates) and its private material/validity window.
    k_policy = str(m["k_policy"])
    policy_export_before = _export_policy(
        env, k_policy, label="dod8-policy-export-before"
    )
    policy_row_before = _full_key_row(env, k_policy)

    # Installed completion-profile / module data snapshot.
    profile_before = _profile_data_fingerprint(env)

    snapshot_fields = (
        "requested_model", "match_type", "provider", "upstream_model",
        "priority", "enabled", "supports_streaming", "visible_in_models",
    )

    def _route_show(route_uuid: str, label: str) -> dict[str, object]:
        return env.run_cli("routes", "show", route_uuid, label=label).json

    def _other_routes(label: str) -> dict[str, object]:
        rows = env.run_cli("routes", "list", label=label).json["routes"]
        return {
            row["id"]: {
                key: row[key] for key in (*snapshot_fields, "capabilities")
            }
            for row in rows
            if row["id"] not in (route_id, route_b_id)
        }

    baseline = _route_show(route_id, "dod8-routes-show-baseline")
    baseline_b = _route_show(route_b_id, "dod8-routes-show-baseline-second")
    others_before = _other_routes("dod8-routes-list-before")
    assert baseline["id"] == route_id
    assert baseline["capabilities"]["codex_limits"] == {
        "context_window_tokens": 105000,
        "default_max_output_tokens": 32768,
        "max_output_tokens": 65536,
    }
    assert baseline["capabilities"]["media_input_estimation"] == {
        "version": 1, "image_tokens": 1000, "video_tokens": 2000, "video_frames": 8,
    }
    assert baseline_b["capabilities"]["codex_limits"] == {
        "context_window_tokens": 210000,
        "default_max_output_tokens": 16384,
        "max_output_tokens": 32768,
    }
    audit_before = _audit_count(env)

    # (a) Reviewed plan 1 on route 1 raises the context admission ceiling
    # to 400000 (a genuine increase from 105000); output values remain
    # valid and unchanged. The dry-run is READ-ONLY.
    plan1 = plans / "dod8-context.json"
    preview = env.run_cli(
        "routes", "update", route_id, "--dry-run", str(plan1),
        "--codex-context-window-tokens", "400000",
        label="dod8-plan-context",
    ).json
    assert preview["route_id"] == route_id
    assert preview["capabilities_mode"] == "partial"
    assert preview["plan_written"] is True
    assert (plan1.stat().st_mode & 0o777) == 0o600
    assert _route_show(route_id, "dod8-routes-show-after-dryrun") == baseline
    assert _audit_count(env) == audit_before
    applied1 = env.run_cli(
        "routes", "update", route_id, "--execute", str(plan1),
        "--reason", "raise context ceiling to 400000",
        label="dod8-execute-context",
    ).json
    assert applied1["id"] == route_id
    after1 = _route_show(route_id, "dod8-routes-show-after-ctx")
    assert after1["id"] == baseline["id"]
    assert after1["created_at"] == baseline["created_at"]
    assert after1["capabilities"]["codex_limits"] == {
        "context_window_tokens": 400000,
        "default_max_output_tokens": 32768,
        "max_output_tokens": 65536,
    }
    # Deep sibling capabilities and unrelated route fields preserved.
    assert after1["capabilities"]["media_input_estimation"] == (
        baseline["capabilities"]["media_input_estimation"]
    )
    assert after1["capabilities"]["chat_completions"] == (
        baseline["capabilities"]["chat_completions"]
    )
    for column in snapshot_fields:
        assert after1[column] == baseline[column], column
    # The second target route is untouched by route 1's plan.
    assert _route_show(route_b_id, "dod8-routes-show-second-after-ctx") == baseline_b
    assert _audit_count(env) == audit_before + 1

    # (b) SEPARATE reviewed plan for route 1's media leaves (multi-field,
    # same route): the context headroom from (a) is preserved.
    plan2 = plans / "dod8-media.json"
    preview2 = env.run_cli(
        "routes", "update", route_id, "--dry-run", str(plan2),
        "--media-image-tokens", "1500",
        "--media-video-tokens", "3000",
        "--media-video-frames", "16",
        label="dod8-plan-media",
    ).json
    assert preview2["route_id"] == route_id
    assert (plan2.stat().st_mode & 0o777) == 0o600
    applied2 = env.run_cli(
        "routes", "update", route_id, "--execute", str(plan2),
        "--reason", "adjust media estimation leaves",
        label="dod8-execute-media",
    ).json
    assert applied2["id"] == route_id
    after2 = _route_show(route_id, "dod8-routes-show-after-media")
    assert after2["capabilities"]["media_input_estimation"] == {
        "version": 1, "image_tokens": 1500, "video_tokens": 3000, "video_frames": 16,
    }
    assert after2["capabilities"]["codex_limits"] == {
        "context_window_tokens": 400000,
        "default_max_output_tokens": 32768,
        "max_output_tokens": 65536,
    }
    assert after2["created_at"] == baseline["created_at"]
    assert _route_show(route_b_id, "dod8-routes-show-second-after-media") == baseline_b
    assert _audit_count(env) == audit_before + 2

    # (c) The SECOND explicitly selected route gets its OWN reviewed plan:
    # a genuine context increase (210000 -> 420000) plus one media leaf,
    # in one multi-leaf plan. Route 1 is untouched by it.
    plan3 = plans / "dod8-second-route.json"
    preview3 = env.run_cli(
        "routes", "update", route_b_id, "--dry-run", str(plan3),
        "--codex-context-window-tokens", "420000",
        "--media-image-tokens", "1200",
        label="dod8-plan-second-route",
    ).json
    assert preview3["route_id"] == route_b_id
    assert (plan3.stat().st_mode & 0o777) == 0o600
    assert _route_show(route_b_id, "dod8-routes-show-second-after-dryrun") == baseline_b
    applied3 = env.run_cli(
        "routes", "update", route_b_id, "--execute", str(plan3),
        "--reason", "second target reviewed context and media leaves",
        label="dod8-execute-second-route",
    ).json
    assert applied3["id"] == route_b_id
    after_b = _route_show(route_b_id, "dod8-routes-show-second-final")
    assert after_b["id"] == baseline_b["id"]
    assert after_b["created_at"] == baseline_b["created_at"]
    assert after_b["capabilities"]["codex_limits"] == {
        "context_window_tokens": 420000,
        "default_max_output_tokens": 16384,
        "max_output_tokens": 32768,
    }
    assert after_b["capabilities"]["media_input_estimation"] == {
        "version": 1, "image_tokens": 1200, "video_tokens": 1000, "video_frames": 4,
    }
    assert _route_show(route_id, "dod8-routes-show-first-after-second") == after2
    assert _audit_count(env) == audit_before + 3

    # (d) The applied plan1 is intentionally STALE now: re-applying it
    # refuses with zero additional mutation/audit.
    stale = env.run_cli(
        "routes", "update", route_id, "--execute", str(plan1),
        "--reason", "stale plan probe",
        any_failure=True,
        label="dod8-execute-stale",
    )
    assert stale.json["error"]["code"] == "invalid_value"
    assert "no longer matches" in stale.json["error"]["message"]
    assert _route_show(route_id, "dod8-routes-show-stale-check") == after2
    assert _audit_count(env) == audit_before + 3

    # (e) Mixed-mode edit flags on --execute are refused: a plan is applied
    # exactly as reviewed. (Command-body BadParameter is a NATIVE Typer
    # usage error: exit 2 with a fixed safe stderr message, no JSON
    # payload; compare renderer-normalized text, not raw terminal bytes.)
    mixed = env.run_cli(
        "routes", "update", route_id, "--execute", str(plan2),
        "--media-image-tokens", "1",
        "--reason", "mixed mode probe",
        any_failure=True,
        label="dod8-execute-mixed-probe",
    )
    assert mixed.exit_code == 2
    mixed_normalized = " ".join(_strip_ansi(mixed.stderr).split())
    mixed_has_fixed_message = "Edit flags are --dry-run only" in mixed_normalized
    assert mixed_has_fixed_message, "mixed-mode fixed refusal message missing"
    assert _route_show(route_id, "dod8-routes-show-mixed-check") == after2
    assert _audit_count(env) == audit_before + 3

    # (f) Every unrelated route is unchanged (no hidden global update).
    others_after = _other_routes("dod8-routes-list-after")
    assert set(others_after) == set(others_before)
    for route_uuid, before in others_before.items():
        after = others_after[route_uuid]
        for key, value in before.items():
            assert after[key] == value, f"unrelated route changed {key}"

    # (g) Pre-existing ledger/replay ROUTE links and their key are stable.
    replay_after = _replay_snapshot()
    replay_stable = replay_after == replay_before
    assert replay_stable, "replay reference linkage changed by route edits"
    assert str(replay_after["route_id"]) == route_id
    ledger_after = env.sql(
        "SELECT id, gateway_key_id, request_id FROM usage_ledger WHERE id = $1",
        str(hist_ledger_id),
    )[0]
    assert ledger_after == ledger_before
    hist_key_after = _full_key_row(env, hist_key_id)
    hist_key_stable = (
        hist_key_after["token_hash"] == hist_key_before["token_hash"]
        and hist_key_after["valid_from"] == hist_key_before["valid_from"]
        and hist_key_after["valid_until"] == hist_key_before["valid_until"]
        and hist_key_after["allowed_models"] == hist_key_before["allowed_models"]
    )
    assert hist_key_stable, "historical linkage key changed by route edits"

    # (h) The nontrivial existing key's policy, material and validity are
    # unchanged by the route edits (no new key state is copied by route
    # edits).
    policy_export_after = _export_policy(
        env, k_policy, label="dod8-policy-export-after"
    )
    policy_export_unchanged = policy_export_after == policy_export_before
    assert policy_export_unchanged, "route edits changed an existing key policy"
    policy_row_after = _full_key_row(env, k_policy)
    policy_material_stable = (
        policy_row_after["token_hash"] == policy_row_before["token_hash"]
        and policy_row_after["valid_from"] == policy_row_before["valid_from"]
        and policy_row_after["valid_until"] == policy_row_before["valid_until"]
    )
    assert policy_material_stable, "route edits changed key material/validity"

    # (i) Installed completion-profile / module data untouched.
    profile_after = _profile_data_fingerprint(env)
    profile_unchanged = profile_after == profile_before
    assert profile_unchanged, "route edits changed installed profile data"

    # (j) Persist the labeled transcript and safe identity for this outcome.
    persisted = env.persist_transcript("dod8")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    expected_labels = {
        "dod8-routes-add",
        "dod8-routes-add-second",
        "dod8-policy-export-before",
        "dod8-routes-show-baseline",
        "dod8-routes-show-baseline-second",
        "dod8-routes-list-before",
        "dod8-plan-context",
        "dod8-routes-show-after-dryrun",
        "dod8-execute-context",
        "dod8-routes-show-after-ctx",
        "dod8-routes-show-second-after-ctx",
        "dod8-plan-media",
        "dod8-execute-media",
        "dod8-routes-show-after-media",
        "dod8-routes-show-second-after-media",
        "dod8-plan-second-route",
        "dod8-routes-show-second-after-dryrun",
        "dod8-execute-second-route",
        "dod8-routes-show-second-final",
        "dod8-routes-show-first-after-second",
        "dod8-execute-stale",
        "dod8-routes-show-stale-check",
        "dod8-execute-mixed-probe",
        "dod8-routes-show-mixed-check",
        "dod8-routes-list-after",
        "dod8-policy-export-after",
    }
    assert set(persisted["labeled"]) == expected_labels
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )


# ---------------------------------------------------------------------------
# DoD9 (205-d): installed once-only mail delivery and inspection
# ---------------------------------------------------------------------------

# Mail-enabled owned subprocess settings (loopback sink only; no real SMTP).
MAIL_ENV = {"ENABLE_EMAIL_DELIVERY": "true"}

# DoD11: explicit configured replay reference lifetime (exactly 30 days),
# supplied through the installed CLI subprocess environment.
REPLAY_TTL_SECONDS = 2592000
REPLAY_ENV = {"CODEX_REPLAY_REFERENCE_TTL_SECONDS": str(REPLAY_TTL_SECONDS)}


def _smtp_data_body(data: str) -> str:
    """Decode the SMTP DATA message's MIME transfer encoding to text.

    The serialized message may be transfer-encoded (for example
    quoted-printable when the body is not ASCII) and its long lines are
    wrapped by the MIME generator, so raw substring or whitespace
    splitting on the wire bytes is not a reliable read of the logical
    body.
    """
    message = email.message_from_string(data)
    payload = message.get_payload(decode=True)
    if payload is None:
        return data
    return payload.decode("utf-8", "replace")


def _extract_key_token(body: str, prefix: str) -> str:
    """Extract the full generated key token from a decoded email body.

    All whitespace is removed first so a MIME line wrap inside the token
    cannot truncate it; the key shape is ``<prefix><public_id>.<secret>``
    and the token run stops at the template's closing quote. Returns
    ``""`` when the prefix is absent.
    """
    normalized = re.sub(r"\s+", "", body)
    start = normalized.find(prefix)
    if start < 0:
        return ""
    match = re.match(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", normalized[start + len(prefix):])
    return prefix + (match.group(0) if match else "")


async def _plant_dod9_history(
    orm_url: str, owner_id: uuid.UUID, allowed_model: str, owner_email: str
) -> dict[str, dict[str, str]]:
    """Plant DoD9 historical delivery states (fixture setup, one session).

    Three clearly labeled PRE-EXISTING (key, one-time-secret, delivery)
    triples for unsafe-state inspection: a `sending` delivery, an
    `ambiguous` delivery, and a `pending` delivery bound to an EXPIRED
    one-time secret. Fixture setup only: constant synthetic payloads that
    are never decryptable or sent; these rows are not operator actions and
    do not pretend to prove SMTP-accepted/DB-failed handling.

    Every planted delivery is bound to the owner's CURRENT email address
    (recipient == owner.email), so the unsafe-state cases reach their
    intended delivery-status / secret-expiry guards rather than any
    recipient-binding confound.
    """
    engine = create_async_engine(orm_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    past = now - timedelta(days=3)
    try:
        async with factory() as session:
            async with session.begin():
                planted: dict[str, dict[str, str]] = {}
                for tag, delivery_status, secret_status in (
                    ("sending", "sending", "pending"),
                    ("ambiguous", "ambiguous", "pending"),
                    ("expired", "pending", "expired"),
                ):
                    key = await GatewayKeysRepository(
                        session
                    ).create_gateway_key_record(
                        public_key_id=f"pk_hist_205d_{tag}_{uuid.uuid4().hex[:8]}",
                        token_hash=uuid.uuid4().hex * 2,
                        owner_id=owner_id,
                        valid_from=past,
                        valid_until=now + timedelta(days=30),
                        allowed_models=[allowed_model],
                    )
                    secret = OneTimeSecret(
                        purpose="gateway_key_email",
                        owner_id=owner_id,
                        gateway_key_id=key.id,
                        encrypted_payload="synthetic-205d-encrypted-payload",
                        nonce="synthetic-205d-nonce",
                        encryption_key_version=1,
                        expires_at=(
                            now + timedelta(days=30)
                            if secret_status == "pending"
                            else now - timedelta(days=1)
                        ),
                        consumed_at=None,
                        status=secret_status,
                        created_at=past,
                    )
                    session.add(secret)
                    await session.flush()
                    delivery = EmailDelivery(
                        owner_id=owner_id,
                        gateway_key_id=key.id,
                        one_time_secret_id=secret.id,
                        recipient_email=owner_email,
                        subject="205-d historical delivery fixture",
                        template_name="gateway_key_email",
                        status=delivery_status,
                        created_at=past,
                    )
                    session.add(delivery)
                    await session.flush()
                    planted[tag] = {
                        "key_id": str(key.id),
                        "secret_id": str(secret.id),
                        "delivery_id": str(delivery.id),
                    }
                return planted
    finally:
        await engine.dispose()


def test_dod9_mail_delivery_and_inspection(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    prefix = env.cli_env["GATEWAY_KEY_PREFIX"]
    sink = env.smtp
    plans = env.operator_dir / "dod9-plans"
    plans.mkdir(exist_ok=True)

    def _count(table: str) -> int:
        return int(env.sql(f"SELECT count(*) AS c FROM {table}")[0]["c"])

    base_keys = _count("gateway_keys")
    base_deliveries = _count("email_deliveries")
    base_ledger = _count("usage_ledger")
    base_msgs = len(sink.received)
    base_refusals = sink.refusals
    assert base_msgs == 0 and base_refusals == 0
    # Clone source: k_student is the fully-routable positive source (M1 +
    # M4 keep enabled routes); k_policy deliberately carries disabled M2/M3
    # routes and would refuse clone CREATE's enabled-model validation.
    k_source_before = _full_key_row(env, m["k_student"])

    # Clearly labeled PRE-EXISTING fixture states (fixture setup, NOT
    # operator actions): sending / ambiguous / expired-secret histories.
    orm_url = env.driver_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    try:
        hist = asyncio.run(
            _plant_dod9_history(
                orm_url,
                uuid.UUID(str(m["owner_seed"])),
                m["models"]["m1"],
                m["owner_seed_email"],
            )
        )
    except Exception:
        raise AssertionError(
            "dod9 fixture planting failed (fixed safe detail; no SQL retained)"
        ) from None

    # 1) Newly cloned key, EXACTLY-ONE explicit delivery channel:
    # --email-delivery pending (no file, no show-plaintext).
    plan1 = plans / "dod9-clone-1.json"
    env.run_cli(
        "keys", "clone",
        "--dry-run", str(plan1),
        "--source-key-id", m["k_student"],
        "--target-owner-id", m["owner_seed"],
        "--validity-mode", "copy-source-expiry",
        label="dod9-clone-dry-run-1",
    )
    assert plan1.is_file()
    assert stat.S_IMODE(plan1.stat().st_mode) == 0o600
    cloned = env.run_cli(
        "keys", "clone",
        "--execute", str(plan1),
        "--reason", "205-d mail qualification clone",
        "--email-delivery", "pending",
        label="dod9-clone-execute-1",
    ).json
    target1 = str(cloned["target_gateway_key_id"])
    secret1 = str(cloned["one_time_secret_id"])
    delivery1 = str(cloned["email_delivery_id"])
    assert cloned["status"] == "created"
    # The pending channel performs NO send and reports NO delivery status:
    # the prepared row's actual pending state is proven by `email show`
    # below, not by a send result.
    assert "email_delivery_status" not in cloned
    assert "plaintext_key" not in cloned
    plaintext_in_output = prefix in env.transcript[-1]["stdout"]
    assert not plaintext_in_output, "clone output exposed key material"

    # 2) Inspect the prepared pending delivery through installed commands.
    shown = env.run_cli(
        "email", "show", delivery1, env=MAIL_ENV, label="dod9-email-show-pending-1"
    ).json
    assert shown["status"] == "pending"
    assert shown["recipient_email"] == m["owner_seed_email"]
    assert shown["one_time_secret_id"] == secret1
    listed = env.run_cli(
        "email", "list", "--delivery-id", delivery1, env=MAIL_ENV,
        label="dod9-email-list-pending-1",
    ).json
    assert [item["delivery_id"] for item in listed["items"]] == [delivery1]

    # 3) Actual synchronous send; ONE SMTP DATA acceptance on the sink.
    sent = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret1,
        "--email-delivery-id", delivery1,
        "--reason", "initial 205-d send",
        "--send-now",
        env=MAIL_ENV,
        label="dod9-send-now-1",
    ).json
    assert sent["status"] == "sent"
    assert sent["email_delivery_id"] == delivery1
    assert sent["one_time_secret_id"] == secret1
    assert len(sink.received) == base_msgs + 1
    assert sink.refusals == base_refusals
    message = sink.received[-1]
    assert message["to"].strip("<>") == m["owner_seed_email"]
    # Decode the MIME transfer encoding and read the FULL logical body:
    # the key line is longer than the MIME generator's wrap width, so a
    # raw wire-bytes fragment is not the complete generated key.
    key1 = _extract_key_token(_smtp_data_body(message["data"]), prefix)
    key1_observed = key1.startswith(prefix) and len(key1) > len(prefix) + 12
    # Register the transiently observed FULL key BEFORE any persistence.
    env.register_secret(key1, "dod9-cloned-key-1")
    assert key1_observed, "generated key not observed transiently via the sink"
    secret_row = env.sql(
        "SELECT status, consumed_at FROM one_time_secrets WHERE id = $1", secret1
    )[0]
    assert secret_row["status"] == "consumed"
    assert secret_row["consumed_at"]
    shown_sent = env.run_cli(
        "email", "show", delivery1, env=MAIL_ENV, label="dod9-email-show-sent-1"
    ).json
    assert shown_sent["status"] == "sent"
    assert shown_sent["sent_at"]
    assert shown_sent["one_time_secret"]["status"] == "consumed"

    # 4) Exact repeat: refused, no additional SMTP send, no re-consumption.
    repeat = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret1,
        "--email-delivery-id", delivery1,
        "--send-now",
        env=MAIL_ENV,
        expect=1,
        label="dod9-send-now-repeat-1",
    ).json
    assert repeat["status"] == "failed"
    assert len(sink.received) == base_msgs + 1
    assert sink.refusals == base_refusals
    secret_row = env.sql(
        "SELECT status, consumed_at FROM one_time_secrets WHERE id = $1", secret1
    )[0]
    assert secret_row["status"] == "consumed"

    # 5) Second newly cloned key; minimal definite sink refusal (fixture IO
    # fault, not business-service mocking).
    plan2 = plans / "dod9-clone-2.json"
    env.run_cli(
        "keys", "clone",
        "--dry-run", str(plan2),
        "--source-key-id", m["k_student"],
        "--target-owner-id", m["owner_seed"],
        "--validity-mode", "copy-source-expiry",
        label="dod9-clone-dry-run-2",
    )
    cloned2 = env.run_cli(
        "keys", "clone",
        "--execute", str(plan2),
        "--reason", "205-d mail qualification clone second",
        "--email-delivery", "pending",
        label="dod9-clone-execute-2",
    ).json
    target2 = str(cloned2["target_gateway_key_id"])
    secret2 = str(cloned2["one_time_secret_id"])
    delivery2 = str(cloned2["email_delivery_id"])
    assert target2 != target1
    key2_before = env.sql(
        "SELECT id, public_key_id, token_hash FROM gateway_keys WHERE id = $1",
        target2,
    )[0]
    sink.refuse_data = True
    refused = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret2,
        "--email-delivery-id", delivery2,
        "--reason", "second 205-d send",
        "--send-now",
        env=MAIL_ENV,
        expect=1,
        label="dod9-send-now-2-refused",
    ).json
    assert refused["status"] == "failed"
    assert refused["error_code"] == "smtp_send_error"
    assert sink.refusals == base_refusals + 1
    assert len(sink.received) == base_msgs + 1
    shown_failed = env.run_cli(
        "email", "show", delivery2, env=MAIL_ENV, label="dod9-email-show-failed-2"
    ).json
    assert shown_failed["status"] == "failed"
    assert shown_failed["failed_at"]
    assert (
        shown_failed["last_recorded_failure"]["error_code"] == "smtp_send_error"
    )

    # No automatic retry: the next refusals add no SMTP attempt at all.
    no_flag = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret2,
        "--email-delivery-id", delivery2,
        "--send-now",
        env=MAIL_ENV,
        expect=1,
        label="dod9-retry-missing-flag-2",
    ).json
    assert no_flag["error"]["code"] == "invalid_parameter"
    assert "FAILED" in no_flag["error"]["message"]
    blank = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret2,
        "--email-delivery-id", delivery2,
        "--retry-failed",
        "--reason", "   ",
        "--send-now",
        env=MAIL_ENV,
        expect=1,
        label="dod9-retry-blank-reason-2",
    ).json
    assert blank["error"]["code"] == "invalid_parameter"
    assert sink.refusals == base_refusals + 1
    assert len(sink.received) == base_msgs + 1

    # Explicit --retry-failed with exact selection + nonblank reason: one
    # safe retry to success, no replacement key or secret.
    sink.refuse_data = False
    retried = env.run_cli(
        "email", "send-pending-key",
        "--one-time-secret-id", secret2,
        "--email-delivery-id", delivery2,
        "--reason", "explicit 205-d retry after synthetic SMTP refusal",
        "--retry-failed",
        "--send-now",
        env=MAIL_ENV,
        label="dod9-retry-failed-2",
    ).json
    assert retried["status"] == "sent"
    assert retried["one_time_secret_id"] == secret2
    assert len(sink.received) == base_msgs + 2
    assert sink.refusals == base_refusals + 1
    # The retry message carries the SAME target key material; observe the
    # full token from the decoded body and register it before persistence.
    key2_token = _extract_key_token(
        _smtp_data_body(sink.received[-1]["data"]), prefix
    )
    key2_observed = (
        key2_token.startswith(prefix) and len(key2_token) > len(prefix) + 12
    )
    env.register_secret(key2_token, "dod9-cloned-key-2")
    assert key2_observed, "retried key not observed transiently via the sink"
    distinct_keys = key2_token != key1
    assert distinct_keys, "retry reused the first clone's key material"
    key2_after = env.sql(
        "SELECT id, public_key_id, token_hash FROM gateway_keys WHERE id = $1",
        target2,
    )[0]
    key2_unchanged = key2_before == key2_after
    assert key2_unchanged, "retry replaced key material"
    listed2 = env.run_cli(
        "email", "list", "--key-id", target2, env=MAIL_ENV, label="dod9-email-list-key-2"
    ).json
    assert [item["delivery_id"] for item in listed2["items"]] == [delivery2]
    secrets2 = int(
        env.sql(
            "SELECT count(*) AS c FROM one_time_secrets WHERE gateway_key_id = $1",
            target2,
        )[0]["c"]
    )
    assert secrets2 == 1

    # 5b) ACTUAL installed read-only inspection of the planted unsafe
    # lifecycles BEFORE any send probe: each planted delivery must show its
    # delivery status, current-owner recipient binding, exact secret
    # binding, and the one-time-secret lifecycle with the fixed blocking
    # reason. A refusal response alone is not the inspection proof.
    expected_lifecycle = {
        "sending": (
            "sending",
            "present",
            "This delivery is already in progress. Do not retry automatically; rotate the key if delivery cannot be confirmed.",
        ),
        "ambiguous": (
            "ambiguous",
            "present",
            "SMTP may have accepted this email, but finalization did not complete. Do not retry; rotate the key if receipt cannot be confirmed.",
        ),
        "expired": (
            "pending",
            "expired",
            "The one-time secret is expired; rotate the key and create a new delivery.",
        ),
    }
    for tag, (delivery_status, secret_status, blocking_reason) in (
        expected_lifecycle.items()
    ):
        h = hist[tag]
        pre_show = env.run_cli(
            "email", "show", h["delivery_id"], env=MAIL_ENV,
            label=f"dod9-email-show-hist-{tag}-pre",
        ).json
        assert pre_show["status"] == delivery_status, tag
        assert pre_show["recipient_email"] == m["owner_seed_email"], tag
        assert pre_show["one_time_secret_id"] == h["secret_id"], tag
        assert pre_show["gateway_key_id"] == h["key_id"], tag
        assert pre_show["one_time_secret"]["status"] == secret_status, tag
        assert pre_show["one_time_secret"]["can_send"] is False, tag
        assert (
            pre_show["one_time_secret"]["blocking_reason"] == blocking_reason
        ), tag
        pre_listed = env.run_cli(
            "email", "list", "--delivery-id", h["delivery_id"], env=MAIL_ENV,
            label=f"dod9-email-list-hist-{tag}-pre",
        ).json
        assert (
            [item["delivery_id"] for item in pre_listed["items"]]
            == [h["delivery_id"]]
        ), tag
        assert pre_listed["items"][0]["status"] == delivery_status, tag

    # 6) Clearly labeled PRE-EXISTING fixture states: unsafe retry/resend
    # refused with NO additional SMTP attempt. These are planted fixture
    # rows (not actual IO) and do not prove SMTP-accepted/DB-failed handling.
    for tag, expected_code, expected_status in (
        ("sending", "email_delivery_in_progress", "failed"),
        ("ambiguous", "email_delivery_ambiguous", "ambiguous"),
        ("expired", "one_time_secret_expired", "failed"),
    ):
        h = hist[tag]
        before_msgs = len(sink.received)
        before_refusals = sink.refusals
        result = env.run_cli(
            "email", "send-pending-key",
            "--one-time-secret-id", h["secret_id"],
            "--email-delivery-id", h["delivery_id"],
            "--send-now",
            env=MAIL_ENV,
            expect=1,
            label=f"dod9-hist-{tag}-refused",
        ).json
        assert result["status"] == expected_status
        assert result["error_code"] == expected_code
        assert len(sink.received) == before_msgs
        assert sink.refusals == before_refusals
    expired_after = env.run_cli(
        "email", "show", hist["expired"]["delivery_id"], env=MAIL_ENV,
        label="dod9-email-show-expired-after",
    ).json
    # Actual post-state: the expired-secret attempt records the delivery
    # as failed (no SMTP acceptance occurred).
    assert expired_after["status"] == "failed"
    assert expired_after["one_time_secret"]["status"] == "expired"
    assert expired_after["one_time_secret"]["can_send"] is False
    assert (
        expired_after["last_recorded_failure"]["error_code"]
        == "one_time_secret_expired"
    )

    # 7) One key / one bound lifecycle, no usage duplication, unrelated
    # state unchanged.
    secrets1 = int(
        env.sql(
            "SELECT count(*) AS c FROM one_time_secrets WHERE gateway_key_id = $1",
            target1,
        )[0]["c"]
    )
    assert secrets1 == 1
    assert _count("usage_ledger") == base_ledger
    assert _count("gateway_keys") == base_keys + 5
    assert _count("email_deliveries") == base_deliveries + 5
    k_source_after = _full_key_row(env, m["k_student"])
    source_unchanged = k_source_before == k_source_after
    assert source_unchanged, "clone source key row changed"

    # 8) Persist the safe requirement-indexed transcript for this case.
    persisted = env.persist_transcript("dod9")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    expected_labels = {
        "dod9-clone-dry-run-1",
        "dod9-clone-execute-1",
        "dod9-email-show-pending-1",
        "dod9-email-list-pending-1",
        "dod9-send-now-1",
        "dod9-email-show-sent-1",
        "dod9-send-now-repeat-1",
        "dod9-clone-dry-run-2",
        "dod9-clone-execute-2",
        "dod9-send-now-2-refused",
        "dod9-email-show-failed-2",
        "dod9-retry-missing-flag-2",
        "dod9-retry-blank-reason-2",
        "dod9-retry-failed-2",
        "dod9-email-list-key-2",
        "dod9-email-show-hist-sending-pre",
        "dod9-email-list-hist-sending-pre",
        "dod9-email-show-hist-ambiguous-pre",
        "dod9-email-list-hist-ambiguous-pre",
        "dod9-email-show-hist-expired-pre",
        "dod9-email-list-hist-expired-pre",
        "dod9-hist-sending-refused",
        "dod9-hist-ambiguous-refused",
        "dod9-hist-expired-refused",
        "dod9-email-show-expired-after",
    }
    assert set(persisted["labeled"]) == expected_labels
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )


# ---------------------------------------------------------------------------
# DoD11 (205-d): installed reviewed replay-reference expiry maintenance
# ---------------------------------------------------------------------------
# Fixture setup only: clearly labeled PRE-EXISTING reference/ledger rows
# through the installed package's own ORM objects (explicitly allowed
# setup), then ALL operator business actions through the installed console.
# The planted rows are schema-valid (the codex_replay_references CHECK
# constraints are preserved; this test never relaxes a database check).


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


async def _plant_dod11_history(
    orm_url: str,
    key_id: uuid.UUID,
    route_id: uuid.UUID,
    owner_id: uuid.UUID,
    provider: str,
    upstream_model: str,
) -> dict[str, dict[str, object]]:
    """Plant DoD11 replay reference states (fixture setup, one session).

    Five clearly labeled PRE-EXISTING references bound to ONE active,
    in-validity key, each with its own ledger (constant synthetic digests,
    no gateway-key plaintext). Every row satisfies the actual
    ``codex_replay_references`` CHECK constraints (kind ``reasoning`` keeps
    null call/tool fields; provider/upstream match the ACTUAL route):

    - ``extend``:        finalized v1, created now-20d, expires now+5d
      (eligible; extended to created+TTL);
    - ``noshorten``:     finalized v1, created now-5d, expires now+200d
      (eligible; max() keeps the later stored expiry, no write);
    - ``expired``:       finalized v1, created now-10d, expires now-2d
      (excluded by the default run; restored by the explicit
      --include-expired plan);
    - ``hmacv2``:        finalized v2, created now-1d, expires now+30d
      (excluded: hmac_version_unavailable);
    - ``pendingledger``: non-finalized ledger, v1, created now-1d,
      expires now+30d (excluded: ledger_not_finalized).

    These rows are not operator actions and do not prove replay playback,
    provider qualification, or authentication.
    """
    engine = create_async_engine(orm_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    day = timedelta(days=1)
    specs = {
        "extend": (1, True, now - 20 * day, now + 5 * day),
        "noshorten": (1, True, now - 5 * day, now + 200 * day),
        "expired": (1, True, now - 10 * day, now - 2 * day),
        "hmacv2": (2, True, now - day, now + 30 * day),
        "pendingledger": (1, False, now - day, now + 30 * day),
    }
    planted: dict[str, dict[str, object]] = {}
    try:
        async with factory() as session:
            async with session.begin():
                for tag, (version, finalized, created, expires) in specs.items():
                    request_id = f"req-205d11-{tag}-{uuid.uuid4().hex[:8]}"
                    ledger = UsageLedger(
                        request_id=request_id,
                        gateway_key_id=key_id,
                        owner_id=owner_id,
                        endpoint="/v1/responses",
                        provider=provider,
                        success=True if finalized else None,
                        accounting_status="finalized" if finalized else "pending",
                        started_at=created,
                        finished_at=created,
                    )
                    session.add(ledger)
                    await session.flush()
                    reference_id = uuid.uuid4()
                    item_id_hmac = hashlib.sha256(
                        f"item-205d11-{tag}".encode("utf-8")
                    ).hexdigest()
                    await CodexReplayReferencesRepository(session).upsert_many(
                        [
                            CodexReplayReferenceInsert(
                                id=reference_id,
                                gateway_key_id=key_id,
                                usage_ledger_id=ledger.id,
                                source_request_id=request_id,
                                provider=provider,
                                route_id=route_id,
                                upstream_model=upstream_model,
                                item_kind="reasoning",
                                item_id_hmac=item_id_hmac,
                                call_id_hmac=None,
                                hmac_key_version=version,
                                tool_namespace=None,
                                tool_name=None,
                                created_at=created,
                                expires_at=expires,
                            )
                        ]
                    )
                    planted[tag] = {
                        "reference_id": str(reference_id),
                        "ledger_id": str(ledger.id),
                        "request_id": request_id,
                        "item_id_hmac": item_id_hmac,
                        "created": created,
                        "expires": expires,
                    }
    finally:
        await engine.dispose()
    return planted


def _full_row(env: FieldEnvironment, table: str, row_id: str) -> dict[str, object]:
    return env.sql(f"SELECT * FROM {table} WHERE id = $1", row_id)[0]


def _changed_columns(
    before: dict[str, object], after: dict[str, object]
) -> list[str]:
    return sorted(c for c in before if str(before[c]) != str(after[c]))


def test_dod11_replay_expiry_maintenance(field_workflow: FieldEnvironment) -> None:
    env = field_workflow
    m = env.manifest
    key_id = str(m["k_student"])
    route_id = str(m["route_a"])
    plans = env.operator_dir / "dod11-plans"
    plans.mkdir(exist_ok=True)
    audit_before = _audit_count(env)

    # Clearly labeled PRE-EXISTING fixture states (fixture setup, NOT
    # operator actions). The fixed safe caller boundary keeps any raw
    # driver/SQL detail out of retained evidence.
    orm_url = env.driver_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    try:
        planted = asyncio.run(
            _plant_dod11_history(
                orm_url,
                uuid.UUID(key_id),
                uuid.UUID(route_id),
                uuid.UUID(str(m["owner_seed"])),
                "openai",
                "fixture-a",
            )
        )
    except Exception:
        raise AssertionError(
            "dod11 fixture planting failed (fixed safe detail; no SQL retained)"
        ) from None

    # Register every planted private identifier/digest BEFORE any retained
    # projection or SQL inspection.
    for tag, row in planted.items():
        env.register_secret(str(row["reference_id"]), f"dod11-{tag}-reference-id")
        env.register_secret(str(row["ledger_id"]), f"dod11-{tag}-ledger-id")
        env.register_secret(str(row["request_id"]), f"dod11-{tag}-request-id")
        env.register_secret(str(row["item_id_hmac"]), f"dod11-{tag}-item-hmac")

    # Pre-state snapshots: the full key row, every reference row, every
    # ledger row (column-level preservation oracles).
    key_before = _full_key_row(env, key_id)
    ref_before = {
        tag: _full_row(env, "codex_replay_references", str(row["reference_id"]))
        for tag, row in planted.items()
    }
    ledger_before = {
        tag: _full_row(env, "usage_ledger", str(row["ledger_id"]))
        for tag, row in planted.items()
    }

    # 1) Actual installed inspection under the explicit configured TTL.
    inspected = env.run_cli(
        "codex", "replay", "inspect", "--key-id", key_id,
        env=REPLAY_ENV, label="dod11-inspect-pre",
    ).json
    assert inspected["configured_ttl_seconds"] == REPLAY_TTL_SECONDS
    assert inspected["keys"] == 1
    assert inspected["keys_active_or_valid"] == 1
    assert inspected["references"] == 5
    assert inspected["active_references"] == 4
    assert inspected["expired_references"] == 1
    assert inspected["per_key"][0]["key_id"] == key_id
    assert inspected["per_key"][0]["key_status"] == "active"

    # 2) Reviewed dry-run plan under the CONFIGURED default TTL (no
    # explicit --ttl-seconds flag), written to a NEW 0600 file.
    plan_file = plans / "dod11-extend-1.json"
    extend = env.run_cli(
        "codex", "replay", "extend",
        "--key-id", key_id,
        "--output", str(plan_file),
        env=REPLAY_ENV, label="dod11-extend-dry-run",
    ).json
    assert extend["mode"] == "dry-run"
    assert extend["plan_file"] == str(plan_file)
    assert extend["ttl_is_configured_default"] is True
    assert extend["ttl_seconds"] == REPLAY_TTL_SECONDS
    assert extend["configured_ttl_seconds"] == REPLAY_TTL_SECONDS
    assert extend["include_expired"] is False
    assert extend["selected_keys"] == 1
    assert extend["eligible_references"] == 2
    assert extend["exclusion_counts"] == {
        "key_not_active_or_valid": 0,
        "ledger_not_finalized": 1,
        "unsupported_kind": 0,
        "hmac_version_unavailable": 1,
        "outside_lifetime": 0,
        "expired_not_included": 1,
    }
    ext = planted["extend"]
    ns = planted["noshorten"]
    assert extend["old_expiry_range"] == [
        _iso_z(ext["expires"]),  # type: ignore[arg-type]
        _iso_z(ns["expires"]),  # type: ignore[arg-type]
    ]
    assert extend["new_expiry_range"] == [
        _iso_z(ext["created"] + timedelta(seconds=REPLAY_TTL_SECONDS)),  # type: ignore[arg-type]
        _iso_z(ns["expires"]),  # type: ignore[arg-type]
    ]
    assert plan_file.is_file()
    assert stat.S_IMODE(plan_file.stat().st_mode) == 0o600

    # 3) Mixed-mode law: --execute with a preview/edit flag is refused
    # (exit 2, fixed stderr, no plan read, no database access).
    mixed = env.run_cli(
        "codex", "replay", "extend",
        "--execute", str(plan_file),
        "--ttl-seconds", "1234",
        env=REPLAY_ENV, expect=2, label="dod11-extend-mixed-refused",
    )
    mixed_fixed = "reviewed plan file only" in mixed.safe_stderr
    assert mixed_fixed, "mixed-mode refusal did not carry the fixed message"
    mixed_echo = "1234" in mixed.safe_stderr or plan_file.name in mixed.safe_stderr
    assert not mixed_echo, "mixed-mode refusal echoed supplied values"
    assert _audit_count(env) == audit_before

    # 4) Apply the reviewed plan: exactly ONE value change (monotonic).
    applied = env.run_cli(
        "codex", "replay", "extend",
        "--execute", str(plan_file),
        "--reason", "205-d reviewed replay expiry extension",
        env=REPLAY_ENV, label="dod11-extend-execute",
    ).json
    assert applied["mode"] == "execute"
    assert applied["applied"] is True
    assert applied["already_applied"] is False
    assert applied["updated_references"] == 1
    assert applied["range_descriptors_source"] == "reviewed_plan"
    assert _audit_count(env) == audit_before + 1

    # 5) Exact persisted post-state after the first apply: the extended
    # row lands exactly on created+TTL; the no-shorten row keeps its later
    # stored expiry; every excluded row is untouched. Column-level
    # preservation: ONLY expires_at may change, and only on the extended
    # row; digests/route/model/source/ledger/key/quotas are all preserved.
    def _ref(tag: str) -> dict[str, object]:
        return _full_row(
            env, "codex_replay_references", str(planted[tag]["reference_id"])
        )

    expected_after_1 = {
        "extend": ext["created"] + timedelta(seconds=REPLAY_TTL_SECONDS),
        "noshorten": ns["expires"],
        "expired": planted["expired"]["expires"],
        "hmacv2": planted["hmacv2"]["expires"],
        "pendingledger": planted["pendingledger"]["expires"],
    }
    for tag, want in expected_after_1.items():
        row = _ref(tag)
        expiry_same = datetime.fromisoformat(str(row["expires_at"])) == want
        assert expiry_same, f"{tag}: expiry not the exact reviewed target"
        created_same = (
            datetime.fromisoformat(str(row["created_at"]))
            == planted[tag]["created"]
        )
        assert created_same, f"{tag}: original creation time changed"
        owner_same = str(row["gateway_key_id"]) == key_id
        assert owner_same, f"{tag}: key ownership changed"
    assert _changed_columns(ref_before["extend"], _ref("extend")) == ["expires_at"]
    for tag in ("noshorten", "expired", "hmacv2", "pendingledger"):
        assert not _changed_columns(ref_before[tag], _ref(tag)), (
            f"{tag}: an untouched reference column changed"
        )
    for tag in planted:
        assert not _changed_columns(
            ledger_before[tag],
            _full_row(env, "usage_ledger", str(planted[tag]["ledger_id"])),
        ), f"{tag}: the bound ledger row changed"
    assert not _changed_columns(key_before, _full_key_row(env, key_id)), (
        "the replay key row (policy/quotas/material) changed"
    )
    ref_after_1 = {tag: _ref(tag) for tag in planted}

    # 6) Exact repeat: already applied, zero writes, zero duplicate audits.
    repeated = env.run_cli(
        "codex", "replay", "extend",
        "--execute", str(plan_file),
        "--reason", "205-d repeat of the applied extension",
        env=REPLAY_ENV, label="dod11-extend-repeat",
    ).json
    assert repeated["applied"] is False
    assert repeated["already_applied"] is True
    assert repeated["updated_references"] == 0
    assert _audit_count(env) == audit_before + 1

    # 7) SECOND reviewed plan: the explicitly expired reference is
    # restored by the --include-expired preview (all other rows unchanged),
    # then applied as its own exact no-op-free operation.
    plan2_file = plans / "dod11-extend-2.json"
    extend2 = env.run_cli(
        "codex", "replay", "extend",
        "--key-id", key_id,
        "--include-expired",
        "--output", str(plan2_file),
        env=REPLAY_ENV, label="dod11-extend2-dry-run",
    ).json
    assert extend2["mode"] == "dry-run"
    assert extend2["plan_file"] == str(plan2_file)
    assert extend2["include_expired"] is True
    assert extend2["ttl_is_configured_default"] is True
    assert extend2["selected_keys"] == 1
    assert extend2["eligible_references"] == 3
    assert extend2["exclusion_counts"] == {
        "key_not_active_or_valid": 0,
        "ledger_not_finalized": 1,
        "unsupported_kind": 0,
        "hmac_version_unavailable": 1,
        "outside_lifetime": 0,
        "expired_not_included": 0,
    }
    c = planted["expired"]
    assert extend2["old_expiry_range"] == [
        _iso_z(c["expires"]),  # type: ignore[arg-type]
        _iso_z(ns["expires"]),  # type: ignore[arg-type]
    ]
    assert extend2["new_expiry_range"] == [
        _iso_z(ext["created"] + timedelta(seconds=REPLAY_TTL_SECONDS)),  # type: ignore[arg-type]
        _iso_z(ns["expires"]),  # type: ignore[arg-type]
    ]
    assert plan2_file.is_file()
    assert stat.S_IMODE(plan2_file.stat().st_mode) == 0o600

    applied2 = env.run_cli(
        "codex", "replay", "extend",
        "--execute", str(plan2_file),
        "--reason", "205-d explicit include-expired restoration",
        env=REPLAY_ENV, label="dod11-extend2-execute",
    ).json
    assert applied2["applied"] is True
    assert applied2["already_applied"] is False
    assert applied2["updated_references"] == 1
    assert _audit_count(env) == audit_before + 2

    # 8) Exact post-state after the explicit expired restoration: ONLY the
    # expired row changed (exactly to created+TTL); every other row, all
    # ledgers, and the key row are byte-for-byte unchanged from the
    # first-apply snapshots.
    c_after = _ref("expired")
    assert _changed_columns(ref_after_1["expired"], c_after) == ["expires_at"]
    assert (
        datetime.fromisoformat(str(c_after["expires_at"]))
        == c["created"] + timedelta(seconds=REPLAY_TTL_SECONDS)
    )
    for tag in ("extend", "noshorten", "hmacv2", "pendingledger"):
        assert not _changed_columns(ref_after_1[tag], _ref(tag)), (
            f"{tag}: the second plan touched an unrelated row"
        )
    for tag in planted:
        assert not _changed_columns(
            ledger_before[tag],
            _full_row(env, "usage_ledger", str(planted[tag]["ledger_id"])),
        ), f"{tag}: the bound ledger row changed"
    assert not _changed_columns(key_before, _full_key_row(env, key_id)), (
        "the replay key row changed after the second plan"
    )

    # 9) Post-state inspection: the restored row is active again.
    inspected_after = env.run_cli(
        "codex", "replay", "inspect", "--key-id", key_id,
        env=REPLAY_ENV, label="dod11-inspect-post",
    ).json
    assert inspected_after["references"] == 5
    assert inspected_after["active_references"] == 5
    assert inspected_after["expired_references"] == 0

    # 10) Persist the safe requirement-indexed transcript for this case.
    persisted = env.persist_transcript("dod11")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    expected_labels = {
        "dod11-inspect-pre",
        "dod11-extend-dry-run",
        "dod11-extend-mixed-refused",
        "dod11-extend-execute",
        "dod11-extend-repeat",
        "dod11-extend2-dry-run",
        "dod11-extend2-execute",
        "dod11-inspect-post",
    }
    assert set(persisted["labeled"]) == expected_labels
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )


# ---------------------------------------------------------------------------
# Config (205-d section 6): installed finite process-configuration
# inspection. Every CLI invocation below is a FRESH installed subprocess,
# so per-call environment overrides are process-local by construction.
# ---------------------------------------------------------------------------


def test_dod_config_process_inspection(field_workflow: FieldEnvironment) -> None:
    env = field_workflow

    # 1) Base snapshot: the EXACT 45-field allowlist, process-local scope,
    # the fixed restart scope on every entry, the exact fixed limitations,
    # and configured/default provenance per entry.
    base = env.run_cli("config", "show", label="dodcfg-show-base").json
    config = base["config"]
    assert config["snapshot_scope"] == "current CLI process cached Settings"
    assert config["limitations"] == [
        "snapshot is the CURRENT CLI process's cached Settings, not live API/worker state",
        "configured/default source comes from this process's model_fields_set",
        "no database, network, broker, or provider access was performed",
        "no credential values or secret file contents are exposed",
        "a configured database URL is not connectivity or authentication proof",
        "external reverse-proxy request-size limits are NOT observed by this command",
    ]
    entries = config["settings"]
    assert len(entries) == 45
    fixed_restart_scope = (
        "process restart; Compose env_file changes require recreating the "
        "affected containers (a plain restart does not reload them)"
    )
    for name, entry in entries.items():
        assert set(entry) == {"value", "source", "restart_scope"}, name
        assert entry["restart_scope"] == fixed_restart_scope, name
    assert entries["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["source"] == "default"
    assert entries["DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE"]["source"] == "default"
    # cli_env supplies this value for every fixture subprocess.
    assert entries["DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE"]["value"] == 100
    assert entries["DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE"]["source"] == "configured"

    # 2) Explicit overrides through the subprocess environment report the
    # configured source and the overridden values in a FRESH process.
    shown = env.run_cli(
        "config", "show",
        env={
            "CODEX_REPLAY_REFERENCE_TTL_SECONDS": str(REPLAY_TTL_SECONDS),
            "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE": "311",
        },
        label="dodcfg-show-overridden",
    ).json
    entries = shown["config"]["settings"]
    assert len(entries) == 45
    assert entries["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["value"] == REPLAY_TTL_SECONDS
    assert (
        entries["CODEX_REPLAY_REFERENCE_TTL_SECONDS"]["source"] == "configured"
    )
    assert entries["DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE"]["value"] == 311
    assert entries["DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE"]["source"] == "configured"

    # 3) Text mode: fixed operator-readable scope header.
    text = env.run_cli(
        "config", "show", json_output=False, label="dodcfg-show-text"
    )
    header_ok = (
        "Process configuration snapshot (current CLI process; not live "
        "API/worker state):" in text.stdout
    )
    assert header_ok, "text snapshot missing the fixed scope header"

    # 4) Invalid numeric Settings value (generated credential-shaped
    # canary in a numeric field): fixed safe unavailable payload, exit 1,
    # NO echoed value and NO raw traceback.
    canary = f"sk-slaif-{secrets.token_hex(24)}"
    env.register_secret(canary, "dodcfg-invalid-numeric")
    invalid = env.run_cli(
        "config", "show",
        env={"SMTP_PORT": canary},
        expect=1,
        label="dodcfg-show-invalid",
    )
    assert invalid.json["error"]["code"] == "configuration_unavailable"
    assert invalid.json["error"]["message"] == (
        "Process configuration could not be loaded. Check the deployment "
        "environment and try again."
    )
    raw = invalid.stdout + invalid.stderr
    no_traceback = "Traceback" not in raw
    assert no_traceback, "invalid-numeric refusal leaked a raw traceback"
    canary_echo = canary in raw
    assert not canary_echo, "invalid-numeric refusal echoed the supplied value"

    # 5) Persist the safe requirement-indexed transcript for this case.
    persisted = env.persist_transcript("dodcfg")
    run_dir = Path(persisted["directory"])
    transcript_path = Path(persisted["paths"]["transcript"])
    identity_path = Path(persisted["paths"]["identity"])
    assert (run_dir.stat().st_mode & 0o777) == 0o700
    assert (transcript_path.stat().st_mode & 0o777) == 0o600
    assert (identity_path.stat().st_mode & 0o777) == 0o600
    assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
    assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
    assert persisted["record_count"] == len(env.transcript)
    expected_labels = {
        "dodcfg-show-base",
        "dodcfg-show-overridden",
        "dodcfg-show-text",
        "dodcfg-show-invalid",
    }
    assert set(persisted["labeled"]) == expected_labels
    persisted_bytes = (
        transcript_path.read_bytes() + identity_path.read_bytes()
    )
    secret_in_persisted = any(
        secret.encode("utf-8") in persisted_bytes for secret in env._secrets
    )
    assert not secret_in_persisted, (
        "a generated secret is present in the persisted transcript/identity"
    )

# --------------------------------------------------------------------------
# DoD 10: actual gateway-recorded compatibility-failure diagnostics
# (order 205-e section 5) — real installed gateway + real installed CLI,
# request content capture OFF. No diagnostic rows are planted: every stored
# record comes from the middleware observer on an actual HTTP response.
# --------------------------------------------------------------------------

M10_RESP = "slaif205e-model-responses"
M10_RESP_FAIL = "slaif205e-model-responses-failstream"
M10_CODEX = "slaif205e-model-codex"
M10_REPLAY = "slaif205e-model-replay"
U10_RESP = "fixture-responses-205e"
U10_RESP_FAIL = "fixture-responses-205e-failstream"
# The seeded route_a requested model (defined inside SEED_SCRIPT; the
# endpoint-denial case needs a chat-allowed model for the chat-only key).
M10_CHAT = "slaif205a-model-a"
DIAG_ID_HEADER = "x-slaif-diagnostic-id"
# The CLI reads its own process Settings (205-c process-scope law): the
# operator CLI for this case declares the same explicit owned overrides
# the gateway process runs with (recording enabled, maximum write timeout).
DIAG_CLI_ENV = {
    "REQUEST_DIAGNOSTICS_ENABLED": "true",
    "REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS": "1000",
}
# The pinned historical 0147 tuple (native 201): the exact five Codex gates
# plus the full local tool set.
CODEX_POLICY_0147 = {
    "version": 1,
    "allowed_capabilities": [
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
    ],
    "allowed_local_tool_types": ["function", "custom"],
}


@dataclass(frozen=True, slots=True, repr=False)
class _D10ReplayCandidate:
    item_kind: str
    item_id: str | None
    call_id: str | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None


def _d10_settings(orm_url: str, cli_env: dict[str, str]) -> Settings:
    """Fixture-process Settings bound to the EXACT fixture credentials
    (so keys created in-process validate against the gateway process)."""
    return Settings(
        DATABASE_URL=orm_url,
        APP_ENV=cli_env.get("APP_ENV", "development"),
        TOKEN_HMAC_SECRET_V1=cli_env["TOKEN_HMAC_SECRET_V1"],
        TOKEN_HMAC_SECRET=cli_env["TOKEN_HMAC_SECRET"],
        ACTIVE_HMAC_KEY_VERSION=cli_env["ACTIVE_HMAC_KEY_VERSION"],
        ONE_TIME_SECRET_ENCRYPTION_KEY=cli_env["ONE_TIME_SECRET_ENCRYPTION_KEY"],
        GATEWAY_KEY_PREFIX=cli_env["GATEWAY_KEY_PREFIX"],
    )


async def _plant_dod10_world(
    orm_url: str,
    cli_env: dict[str, str],
    mock_base_url: str,
    owner_id: str,
    cohort_id: str,
) -> dict[str, str]:
    """Labeled fixture setup (NOT operator business work): re-point the
    seeded "openai" provider config at the owned loopback ProviderMock and
    create four labeled routes + pricing and four labeled keys (native 201
    shapes) that the ACTUAL installed gateway will exercise:

    - ``route_resp``:      responses route, function/custom tools OFF
      (unsupported function-tool capability case);
    - ``route_resp_fail``: responses streaming route whose upstream model
      makes the mock emit an UNSUPPORTED SSE event (stream failure case);
    - ``route_codex``:     Codex route with the exact numeric codex_limits
      contract 400/64/256 (context-window rejection case);
    - ``route_replay``:    Codex route for the replay reference case.

    Product-equivalent ORM/services inside the pytest process; no
    request_diagnostics row is ever created here.
    """
    engine = create_async_engine(orm_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                providers = ProviderConfigsRepository(session)
                provider = await providers.get_provider_config_by_provider(
                    "openai"
                )
                assert provider is not None, "seeded openai provider missing"
                provider.base_url = mock_base_url

                routes = ModelRoutesRepository(session)
                pricing = PricingRulesRepository(session)
                now = datetime.now(UTC)
                resp_caps = {
                    "responses": {
                        "text": True,
                        "stateless": True,
                        "streaming": True,
                        "function_tools": False,
                        "custom_tools": False,
                    }
                }
                codex_caps = {
                    "responses": {
                        "text": True,
                        "stateless": True,
                        "codex_request_envelope": True,
                        "codex_encrypted_reasoning_replay": True,
                        "codex_client_tools": True,
                        "codex_streaming_tool_events": True,
                    },
                    "codex_limits": {
                        "context_window_tokens": 400,
                        "default_max_output_tokens": 64,
                        "max_output_tokens": 256,
                    },
                }
                codex_accounting = {
                    "codex_accounting": {
                        "long_context_threshold_tokens": 272000,
                        "long_context_input_multiplier": "1.5",
                        "long_context_output_multiplier": "1.5",
                        "cache_write_input_price_per_1m": "1.250000000",
                    }
                }
                r_resp = await routes.create_model_route(
                    requested_model=M10_RESP, provider="openai",
                    upstream_model=U10_RESP, match_type="exact",
                    endpoint="/v1/responses", priority=1,
                    visible_in_models=True, supports_streaming=True,
                    capabilities=resp_caps,
                    notes="205-e labeled responses fixture route",
                )
                r_resp_fail = await routes.create_model_route(
                    requested_model=M10_RESP_FAIL, provider="openai",
                    upstream_model=U10_RESP_FAIL, match_type="exact",
                    endpoint="/v1/responses", priority=1,
                    visible_in_models=True, supports_streaming=True,
                    capabilities=resp_caps,
                    notes="205-e labeled responses stream-failure route",
                )
                r_codex = await routes.create_model_route(
                    requested_model=M10_CODEX, provider="openai",
                    upstream_model=M10_CODEX, match_type="exact",
                    endpoint="/v1/responses", priority=1,
                    visible_in_models=True, supports_streaming=True,
                    capabilities=codex_caps,
                    notes="205-e labeled codex context-fixture route",
                )
                r_replay = await routes.create_model_route(
                    requested_model=M10_REPLAY, provider="openai",
                    upstream_model=M10_REPLAY, match_type="exact",
                    endpoint="/v1/responses", priority=1,
                    visible_in_models=True, supports_streaming=True,
                    capabilities=codex_caps,
                    notes="205-e labeled codex replay-fixture route",
                )
                for upstream in (U10_RESP, U10_RESP_FAIL):
                    await pricing.create_pricing_rule(
                        provider="openai", upstream_model=upstream,
                        endpoint="/v1/responses",
                        valid_from=now - timedelta(days=1),
                        currency="EUR",
                        input_price_per_1m=Decimal("1.000000000"),
                        output_price_per_1m=Decimal("1.000000000"),
                        request_price=Decimal("0.000000000"),
                        notes="205-e labeled fixture pricing",
                    )
                for upstream in (M10_CODEX, M10_REPLAY):
                    await pricing.create_pricing_rule(
                        provider="openai", upstream_model=upstream,
                        endpoint="/v1/responses",
                        valid_from=now - timedelta(days=1),
                        currency="EUR",
                        input_price_per_1m=Decimal("1.000000000"),
                        cached_input_price_per_1m=Decimal("0.250000000"),
                        output_price_per_1m=Decimal("1.000000000"),
                        reasoning_price_per_1m=Decimal("2.000000000"),
                        request_price=Decimal("0.000000000"),
                        pricing_metadata=codex_accounting,
                        notes="205-e labeled codex fixture pricing",
                    )

                key_service = KeyService(
                    settings=_d10_settings(orm_url, cli_env),
                    gateway_keys_repository=GatewayKeysRepository(session),
                    one_time_secrets_repository=OneTimeSecretsRepository(
                        session
                    ),
                    audit_repository=AuditRepository(session),
                )

                def _key_input(models, endpoints, policy=None, note=""):
                    return CreateGatewayKeyInput(
                        owner_id=uuid.UUID(owner_id),
                        cohort_id=uuid.UUID(cohort_id),
                        valid_from=now - timedelta(minutes=5),
                        valid_until=now + timedelta(days=1),
                        cost_limit_eur=Decimal("10.000000000"),
                        token_limit_total=100_000,
                        request_limit_total=100,
                        allowed_models=models,
                        allowed_endpoints=endpoints,
                        key_purpose="standard",
                        capability_policy_mode="standard",
                        calibration_metadata={},
                        confirm_trusted_calibration=False,
                        responses_policy=policy,
                        note=note,
                    )

                k_diag = await key_service.create_gateway_key(
                    _key_input(
                        [M10_RESP, M10_RESP_FAIL], ["/v1/responses"],
                        note="205-e labeled diagnostics key",
                    )
                )
                k_chatonly = await key_service.create_gateway_key(
                    _key_input(
                        [M10_CHAT], ["/v1/chat/completions"],
                        note="205-e labeled chat-only endpoint key",
                    )
                )
                k_codex = await key_service.create_gateway_key(
                    _key_input(
                        [M10_CODEX], ["/v1/responses"],
                        policy=CODEX_POLICY_0147,
                        note="205-e labeled codex context key",
                    )
                )
                k_replay = await key_service.create_gateway_key(
                    _key_input(
                        [M10_REPLAY], ["/v1/responses"],
                        policy=CODEX_POLICY_0147,
                        note="205-e labeled codex replay key",
                    )
                )
        return {
            "route_resp": str(r_resp.id),
            "route_resp_fail": str(r_resp_fail.id),
            "route_codex": str(r_codex.id),
            "route_replay": str(r_replay.id),
            "k_diag": str(k_diag.gateway_key_id),
            "k_chatonly": str(k_chatonly.gateway_key_id),
            "k_codex": str(k_codex.gateway_key_id),
            "k_replay": str(k_replay.gateway_key_id),
            "k_diag_plain": k_diag.plaintext_key,
            "k_chatonly_plain": k_chatonly.plaintext_key,
            "k_codex_plain": k_codex.plaintext_key,
            "k_replay_plain": k_replay.plaintext_key,
        }
    finally:
        await engine.dispose()


async def _seed_dod10_replay_reference(
    orm_url: str,
    cli_env: dict[str, str],
    key_id: str,
    owner_id: str,
    cohort_id: str,
    route_id: str,
    model: str,
    item_id: str,
    source_request_id: str,
) -> tuple[datetime, datetime]:
    """Genuine service-persisted replay reference (fixture setup, NOT
    operator work): a successful FINALIZED ledger plus the reference
    persisted by the ACTUAL CodexReplayService at now-60s (inside the key
    validity) with the long default lifetime — the same deterministic
    chronology law as native 201 / the 205-d replay case."""
    engine = create_async_engine(orm_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seed_now = datetime.now(UTC) - timedelta(seconds=60)
    try:
        async with factory() as session:
            async with session.begin():
                usage = UsageLedgerRepository(session)
                ledger = await usage.create_success_record(
                    request_id=source_request_id,
                    gateway_key_id=uuid.UUID(key_id),
                    owner_id=uuid.UUID(owner_id),
                    cohort_id=uuid.UUID(cohort_id),
                    endpoint="/v1/responses",
                    provider="openai",
                    started_at=seed_now,
                    finished_at=seed_now,
                    requested_model=model,
                    resolved_model=model,
                    streaming=False,
                )
                replay = CodexReplayService(
                    repository=CodexReplayReferencesRepository(session),
                    settings=_d10_settings(orm_url, cli_env),
                )
                persisted = await replay.persist_validated_references(
                    candidates=(
                        _D10ReplayCandidate(
                            item_kind="reasoning",
                            item_id=item_id,
                            call_id=None,
                            tool_namespace=None,
                            tool_name=None,
                        ),
                    ),
                    gateway_key_id=uuid.UUID(key_id),
                    usage_ledger_id=ledger.id,
                    source_request_id=source_request_id,
                    provider="openai",
                    route_id=uuid.UUID(route_id),
                    upstream_model=model,
                    now=seed_now,
                )
                assert persisted == 1
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT created_at, expires_at FROM "
                        "codex_replay_references WHERE gateway_key_id = :kid"
                    ),
                    {"kid": uuid.UUID(key_id)},
                )
            ).one()
            return row[0], row[1]
    finally:
        await engine.dispose()


def _diag_cli_lookup(
    env: FieldEnvironment,
    request_id: str,
    *,
    namespace: str = "gateway",
    label: str = "dod10-lookup",
    want: str = "found",
    attempts: int = 16,
) -> CliResult:
    """Bounded readiness poll against the ACTUAL correlation ID (the
    observer writes after the forwarded response, so network completion
    can precede the DB commit). Indexed actual CLI retries; no arbitrary
    sleeps of record, no fabricated rows."""
    last: CliResult | None = None
    for attempt in range(1, attempts + 1):
        last = env.run_cli(
            "diagnostics", "request", "show",
            "--request-id", request_id, "--namespace", namespace,
            label=f"{label}-{attempt}", env=DIAG_CLI_ENV,
        )
        payload = last.json if isinstance(last.json, dict) else {}
        if payload.get("outcome") == want:
            return last
        time.sleep(0.5)
    got = (last.json if isinstance(last.json, dict) else {}).get("outcome")
    raise AssertionError(
        f"{label}: lookup outcome {got!r} never reached {want!r} "
        "(fixed detail; no row content retained)"
    )


def _dod10_key_state(env: FieldEnvironment, key_id: str) -> dict[str, object]:
    """Exact per-key accounting state (fixture SQL assertion)."""
    counters = env.sql(
        "SELECT cost_used_eur, tokens_used_total, requests_used_total, "
        "cost_reserved_eur, tokens_reserved_total, requests_reserved_total "
        "FROM gateway_keys WHERE id = $1",
        key_id,
    )
    ledger = env.sql(
        "SELECT accounting_status, success FROM usage_ledger "
        "WHERE gateway_key_id = $1",
        key_id,
    )
    reservations = env.sql(
        "SELECT status FROM quota_reservations WHERE gateway_key_id = $1",
        key_id,
    )

    def _flag(value: object) -> str:
        if value is True:
            return "true"
        if value is False:
            return "false"
        return "none"

    return {
        "counters": counters[0] if counters else None,
        "ledger_rows": len(ledger),
        "ledger_states": sorted(
            (str(r.get("accounting_status")), _flag(r.get("success")))
            for r in ledger
        ),
        "reservation_states": sorted(str(r["status"]) for r in reservations),
    }


def _dod10_store_contains(env: FieldEnvironment, needle: str) -> bool:
    """Boolean-only content scan of the ENTIRE diagnostics store."""
    rows = env.sql("SELECT * FROM request_diagnostics")
    return any(
        needle in str(value) for row in rows for value in row.values()
    )


def test_dod10_actual_gateway_recorded_diagnostics(
    field_workflow: FieldEnvironment,
) -> None:
    env = field_workflow
    m = env.manifest
    orm_url = env.database_url

    # Labeled fixture setup (NOT operator business work): owned loopback
    # ProviderMock + re-pointed provider base_url + labeled routes/keys.
    # The mock's FULL lifetime (seeding, gateway startup, and every case
    # below) runs inside this try/finally, so a startup failure cannot
    # leak the second mock.
    mock = ProviderMock()
    try:
        try:
            planted = asyncio.run(
                _plant_dod10_world(
                    orm_url, env.cli_env, mock.base_url,
                    m["owner_seed"], m["cohort_seed"],
                )
            )
        except Exception:
            raise AssertionError(
                "dod10 fixture planting failed (fixed safe detail; no "
                "SQL retained)"
            ) from None

        for label in ("k_diag_plain", "k_chatonly_plain", "k_codex_plain",
                      "k_replay_plain"):
            env.register_secret(planted[label], f"dod10-{label}")
        body_canary = "dod10-body-canary-" + secrets.token_hex(16)
        resp_canary = "dod10-resp-canary-" + secrets.token_hex(16)
        mock.response_canary = resp_canary
        fake_upstream = "sk-proj-" + secrets.token_hex(24)
        env.register_secret(fake_upstream, "dod10-fake-upstream-key")

        # The ACTUAL installed gateway with explicit owned process overrides:
        # diagnostics recording ON, content capture deterministically OFF,
        # the valid maximum write timeout (production default unchanged).
        # Starting it also proves the EXACT prior owned process (DoD5 in a
        # combined module run) was stopped and terminated.
        capture_dir = env.operator_dir / "dod10-capture"
        env.start_gateway(env_overrides={
            "REQUEST_DIAGNOSTICS_ENABLED": "true",
            "REQUEST_CAPTURE_ENABLED": "false",
            "REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS": "1000",
            "REQUEST_CAPTURE_DIR": str(capture_dir),
            "OPENAI_UPSTREAM_API_KEY": fake_upstream,
        })
        # ---- 1. Pre-auth 401: recorded with NO key identity --------------
        state_diag_base = _dod10_key_state(env, planted["k_diag"])
        assert state_diag_base["ledger_rows"] == 0
        status, _payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer="sk-slaif-" + "0" * 40,
            body={"model": M10_RESP, "input": body_canary},
        )
        assert status == 401, f"preauth expected 401, got {status}"
        diag_401 = headers.get(DIAG_ID_HEADER)
        assert diag_401, "no X-SLAIF-Diagnostic-ID correlation header"
        rec = _diag_cli_lookup(env, diag_401, label="dod10-preauth").json
        record = rec["record"]
        assert record["http_status"] == 401
        assert record["stream_outcome"] == "http_rejection"
        assert record["gateway_key_id"] is None
        # The client sent NO X-Request-ID: the retained client ID is the
        # middleware-generated request ID (a deliberately retained safe
        # correlation ID in req-<uuid> shape), not client content.
        client_id_val = record["client_request_id"]
        assert client_id_val is None or re.fullmatch(
            r"req-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
            r"-[0-9a-f]{4}-[0-9a-f]{12}",
            client_id_val,
        )
        assert record["route_id"] is None
        # pre-auth never attributes a key/owner/route/ledger: no stored
        # row claims any labeled key (never guess an owner)
        claimed = {
            row.get("gateway_key_id")
            for row in env.sql("SELECT gateway_key_id FROM request_diagnostics")
        }
        labeled_keys = {
            planted["k_diag"], planted["k_chatonly"],
            planted["k_codex"], planted["k_replay"], m["k_student"],
        }
        assert claimed.isdisjoint(labeled_keys), (
            "a stored row claims a labeled key for the pre-auth 401"
        )
        assert _dod10_key_state(env, planted["k_diag"]) == state_diag_base

        # ---- 2. Authenticated endpoint denial ----------------------------
        status, payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_chatonly_plain"],
            body={"model": M10_CHAT, "input": "bounded"},
        )
        assert status == 403, f"endpoint denial expected 403, got {status}"
        public_code = payload["error"]["code"]
        assert public_code == "endpoint_not_allowed"
        rec = _diag_cli_lookup(
            env, headers.get(DIAG_ID_HEADER), label="dod10-endpoint"
        ).json["record"]
        assert rec["error_code"] == public_code
        assert rec["http_status"] == 403
        assert rec["stream_outcome"] == "http_rejection"
        assert rec["endpoint_template"] == "/v1/responses"
        # endpoint policy rejects BEFORE route resolution: no route facts
        assert rec["route_id"] is None
        assert rec["route_pattern"] is None
        assert rec["gateway_key_id"] == planted["k_chatonly"]
        state_chatonly = _dod10_key_state(env, planted["k_chatonly"])
        assert state_chatonly["ledger_rows"] == 0
        assert state_chatonly["reservation_states"] == []

        # ---- 3. Unsupported function-tool capability ---------------------
        fn_body = {
            "model": M10_RESP,
            "input": "bounded " + body_canary,
            "tools": [{
                "type": "function",
                "name": "lookup",
                "description": "lookup thing",
                "parameters": {"type": "object", "properties": {}},
            }],
        }
        status, payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_diag_plain"], body=fn_body,
        )
        assert 400 <= status < 500, f"function tool denial, got {status}"
        public_code = payload["error"]["code"]
        assert public_code == "responses_function_tool_capability_not_supported"
        rec = _diag_cli_lookup(
            env, headers.get(DIAG_ID_HEADER), label="dod10-functool"
        ).json["record"]
        assert rec["error_code"] == public_code
        assert rec["http_status"] == status
        assert rec["stream_outcome"] == "http_rejection"
        # the ACTUALLY RESOLVED route identity at the trusted boundary
        assert rec["route_id"] == planted["route_resp"]
        assert rec["route_pattern"] == M10_RESP
        assert rec["gateway_key_id"] == planted["k_diag"]
        assert _dod10_key_state(env, planted["k_diag"]) == state_diag_base

        # ---- 4. Codex context-window rejection ---------------------------
        status, payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_codex_plain"],
            body={
                "model": M10_CODEX,
                "input": "x" * 3000,
                "prompt_cache_key": "dod10-context",
            },
        )
        assert status == 400, f"context rejection expected 400, got {status}"
        public_code = payload["error"]["code"]
        assert public_code == "responses_codex_context_window_exceeded"
        rec = _diag_cli_lookup(
            env, headers.get(DIAG_ID_HEADER), label="dod10-context"
        ).json["record"]
        assert rec["error_code"] == public_code
        assert rec["http_status"] == 400
        assert rec["stream_outcome"] == "http_rejection"
        assert rec["route_id"] == planted["route_codex"]
        assert rec["route_pattern"] == M10_CODEX
        # actual decision numbers and configured ceilings, not hints
        assert rec["source"] == "responses_route_limits"
        assert rec["context_window_tokens"] == 400
        assert rec["estimated_input_tokens"] is not None
        assert rec["estimated_input_tokens"] > 336
        assert rec["limits"] == {
            "max_output_tokens": 256,
            "max_input_tokens": 1050000,
            "context_window_tokens": 400,
        }
        assert rec["output_allowance_tokens"] == 64
        assert rec["gateway_key_id"] == planted["k_codex"]
        state_codex = _dod10_key_state(env, planted["k_codex"])
        assert state_codex["ledger_rows"] == 0
        assert state_codex["reservation_states"] == []

        # ---- 5. Unsupported provider stream event (wire 200) -------------
        state_stream_before = _dod10_key_state(env, planted["k_diag"])
        status, body, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_diag_plain"],
            body={"model": M10_RESP_FAIL, "input": "bounded", "stream": True},
        )
        assert status == 200, f"stream wire status expected 200, got {status}"
        assert isinstance(body, str)
        assert body.count("responses_stream_event_not_supported") == 1
        rec = _diag_cli_lookup(
            env, headers.get(DIAG_ID_HEADER), label="dod10-stream"
        ).json["record"]
        assert rec["stream_outcome"] == "stream_failure"
        # the record keeps the ACTUAL wire status, not a success guess
        assert rec["http_status"] == 200
        assert rec["source"] == "responses_stream_failure"
        assert rec["error_code"] == "responses_stream_event_not_supported"
        assert rec["route_pattern"] == M10_RESP_FAIL
        assert rec["gateway_key_id"] == planted["k_diag"]
        state_stream_after = _dod10_key_state(env, planted["k_diag"])
        # the interruption finalizes exactly one failed ledger row and one
        # released reservation; reserved counters fully back to baseline
        assert state_stream_after["ledger_rows"] == (
            state_stream_before["ledger_rows"] + 1
        )
        assert ("failed", "false") in state_stream_after["ledger_states"]
        assert "released" in state_stream_after["reservation_states"]
        counters = state_stream_after["counters"]
        assert float(counters["cost_reserved_eur"]) == 0.0
        assert int(counters["tokens_reserved_total"]) == 0
        assert int(counters["requests_reserved_total"]) == 0

        # ---- 6. Replay: genuine reference positive, then expired ---------
        item_id = "rs-205e-" + secrets.token_hex(12)
        source_request_id = "req-205e-" + secrets.token_hex(12)
        env.register_secret(item_id, "dod10-replay-item-id")
        created_at, expires_at = asyncio.run(
            _seed_dod10_replay_reference(
                orm_url, env.cli_env, planted["k_replay"],
                m["owner_seed"], m["cohort_seed"],
                planted["route_replay"], M10_REPLAY,
                item_id, source_request_id,
            )
        )
        assert created_at < expires_at
        assert expires_at > datetime.now(UTC), (
            "seeded reference must still be active (long initial lifetime)"
        )
        replay_body = {
            "model": M10_REPLAY,
            "input": [
                {
                    "type": "reasoning",
                    "id": item_id,
                    "encrypted_content": "enc-205e",
                }
            ],
        }
        ledger_before = _dod10_key_state(env, planted["k_replay"])["ledger_rows"]
        assert ledger_before == 1  # the seeded finalized ledger only
        status, _payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_replay_plain"], body=replay_body,
        )
        assert status == 200, (
            f"replay positive expected 200, got {status} (synthetic IO "
            "control, not backend qualification)"
        )
        ok_diag = headers.get(DIAG_ID_HEADER)
        assert ok_diag, "no correlation header on the replay positive 200"
        # a successful 200 never records (bounded negative poll)
        nf = _diag_cli_lookup(
            env, ok_diag, label="dod10-replay-ok", want="not_found",
            attempts=6,
        )
        assert nf.json["outcome"] == "not_found"
        assert _dod10_key_state(env, planted["k_replay"])["ledger_rows"] == (
            ledger_before + 1
        )

        # Deterministic expiry: ONLY the selected reference moves, to a
        # timestamp after creation but already before the gateway's current
        # time (no sleep, no race, chronology CHECK preserved).
        env.sql(
            "UPDATE codex_replay_references SET expires_at = "
            "created_at + interval '30 seconds' WHERE gateway_key_id = $1",
            planted["k_replay"],
        )
        saved = env.sql(
            "SELECT expires_at FROM codex_replay_references "
            "WHERE gateway_key_id = $1",
            planted["k_replay"],
        )
        assert len(saved) == 1
        saved_expires = datetime.fromisoformat(str(saved[0]["expires_at"]))
        assert created_at < saved_expires < datetime.now(UTC)

        state_before_deny = _dod10_key_state(env, planted["k_replay"])
        status, payload, headers = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_replay_plain"], body=replay_body,
        )
        assert status == 404, f"expired replay expected 404, got {status}"
        public_code = payload["error"]["code"]
        # the public code is deliberately opaque (not_found vs expired is
        # not disclosed)
        assert public_code == "responses_codex_replay_reference_not_found"
        rec = _diag_cli_lookup(
            env, headers.get(DIAG_ID_HEADER), label="dod10-replay-expired"
        ).json["record"]
        assert rec["error_code"] == public_code
        assert rec["http_status"] == 404
        assert rec["stream_outcome"] == "http_rejection"
        # replay verification precedes route resolution: no route facts
        assert rec["route_id"] is None
        assert rec["route_pattern"] is None
        assert rec["gateway_key_id"] == planted["k_replay"]
        # the denied replay changed NO accounting state
        assert _dod10_key_state(env, planted["k_replay"]) == state_before_deny

        # ---- 7. Ambiguous client ID: two genuine failures, one ID --------
        client_id = "dod10-client-" + secrets.token_hex(8)
        _s, _p, h_first = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_diag_plain"], body=fn_body,
            extra_headers={"X-Request-ID": client_id},
        )
        _s, _p, h_second = env.gateway_request_with_headers(
            "POST", "/v1/responses",
            bearer=planted["k_diag_plain"], body=fn_body,
            extra_headers={"X-Request-ID": client_id},
        )
        g_first = h_first.get(DIAG_ID_HEADER)
        g_second = h_second.get(DIAG_ID_HEADER)
        assert g_first and g_second and g_first != g_second
        amb = _diag_cli_lookup(
            env, client_id, namespace="any", label="dod10-ambiguous",
            want="ambiguous",
        )
        assert amb.json["match_count"] == 2
        candidates = {
            c["gateway_request_id"] for c in amb.json["candidates"]
        }
        assert candidates == {g_first, g_second}
        # the offered gateway IDs disambiguate to the exact rows
        for gateway_id in (g_first, g_second):
            found = _diag_cli_lookup(
                env, gateway_id, label=f"dod10-amb-{gateway_id[:8]}",
                attempts=3,
            )
            assert found.json["record"]["gateway_request_id"] == gateway_id

        # ---- 8. CLI status / not-found / typed unavailable ---------------
        retained = env.sql(
            "SELECT count(*) AS c FROM request_diagnostics"
        )
        retained_n = int(retained[0]["c"])
        st = env.run_cli(
            "diagnostics", "status", "--json", label="dod10-status-json",
            env=DIAG_CLI_ENV,
        ).json
        assert st["recording_enabled"] is True
        assert st["store_available"] is True
        assert st["retained_records"] == retained_n
        assert st["write_timeout_ms"] == 1000
        assert st["max_records"] == 10000
        assert st["retention_seconds"] == 604800
        txt = env.run_cli(
            "diagnostics", "status", json_output=False,
            label="dod10-status-text", env=DIAG_CLI_ENV,
        )
        assert txt.stdout.startswith("recording enabled;")

        absent = env.run_cli(
            "diagnostics", "request", "show",
            "--request-id", "dod10-not-present", "--namespace", "any",
            label="dod10-not-found", env=DIAG_CLI_ENV,
        )
        assert absent.exit_code == 0
        assert absent.json["outcome"] == "not_found"

        # typed unavailable: a controlled CLI process with a syntactically
        # valid but unreachable owned-loopback DB URL (never the shared PG)
        fake_dbpass = "dod10-unreachable-" + secrets.token_hex(16)
        env.register_secret(fake_dbpass, "dod10-unreachable-db-password")
        unreachable_url = (
            f"postgresql+asyncpg://diag205e:{fake_dbpass}"
            "@127.0.0.1:1/diag205e-unreachable"
        )
        env.register_secret(unreachable_url, "dod10-unreachable-database-url")
        bad_env = {
            "DATABASE_URL": unreachable_url,
            "REQUEST_DIAGNOSTICS_ENABLED": "true",
        }
        st_un = env.run_cli(
            "diagnostics", "status", "--json",
            label="dod10-status-unavailable", env=bad_env,
        )
        assert st_un.exit_code == 0
        assert st_un.json["store_available"] is False
        assert st_un.json["recording_enabled"] is True
        sh_un = env.run_cli(
            "diagnostics", "request", "show",
            "--request-id", diag_401, "--namespace", "gateway",
            label="dod10-show-unavailable", expect=1, env=bad_env,
        )
        assert sh_un.json["outcome"] == "unavailable"

        # ---- 9. Capture OFF + content-free store + safe export -----------
        capture_files = []
        if capture_dir.exists():
            capture_files = [
                str(p.relative_to(capture_dir))
                for p in capture_dir.rglob("*")
                if p.is_file()
            ]
        assert not capture_files, (
            "request capture artifacts were created while capture is OFF"
        )
        assert not _dod10_store_contains(env, body_canary), (
            "request body content reached the stored diagnostics"
        )
        assert not _dod10_store_contains(env, resp_canary), (
            "response content reached the stored diagnostics"
        )
        assert not _dod10_store_contains(env, fake_upstream), (
            "a generated upstream credential reached the stored diagnostics"
        )
        assert not _dod10_store_contains(env, item_id), (
            "a raw replay item id reached the stored diagnostics"
        )

        # Persist the safe requirement-indexed transcript for this case.
        persisted = env.persist_transcript("dod10")
        run_dir = Path(persisted["directory"])
        transcript_path = Path(persisted["paths"]["transcript"])
        identity_path = Path(persisted["paths"]["identity"])
        assert (run_dir.stat().st_mode & 0o777) == 0o700
        assert (transcript_path.stat().st_mode & 0o777) == 0o600
        assert (identity_path.stat().st_mode & 0o777) == 0o600
        assert _sha256_file(transcript_path) == persisted["sha256"]["transcript"]
        assert _sha256_file(identity_path) == persisted["sha256"]["identity"]
        assert persisted["record_count"] == len(env.transcript)
        labeled = set(persisted["labeled"])
        for required in (
            "dod10-preauth-1", "dod10-endpoint-1", "dod10-functool-1",
            "dod10-context-1", "dod10-stream-1", "dod10-replay-ok-1",
            "dod10-replay-expired-1", "dod10-ambiguous-1",
            "dod10-status-json", "dod10-status-text", "dod10-not-found",
            "dod10-status-unavailable", "dod10-show-unavailable",
        ):
            # the first successful poll attempt carries the "-1" suffix
            assert any(
                lbl == required or lbl.startswith(required)
                for lbl in labeled
            ), f"missing labeled record {required}"
        persisted_bytes = (
            transcript_path.read_bytes() + identity_path.read_bytes()
        )
        secret_in_persisted = any(
            secret.encode("utf-8") in persisted_bytes
            for secret in env._secrets
        )
        assert not secret_in_persisted, (
            "a generated secret is present in the persisted "
            "transcript/identity"
        )
        canary_in_persisted = (
            body_canary.encode("utf-8") in persisted_bytes
            or resp_canary.encode("utf-8") in persisted_bytes
        )
        assert not canary_in_persisted, (
            "a generated body/response canary is present in the persisted "
            "transcript/identity"
        )
    finally:
        mock.stop()
