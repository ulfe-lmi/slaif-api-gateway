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

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest

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
        if model.endswith("-failstream") and stream:
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
        deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                out = (self.proc.stdout.read() or b"")[:1000] if self.proc.stdout else b""
                raise AssertionError(
                    f"gateway exited during startup (exit {self.proc.returncode}): "
                    f"{out.decode('utf-8', 'replace')}"
                )
            try:
                with urllib.request.urlopen(
                    f"{self.url}/healthz", timeout=5
                ) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        if not ready:
            self.stop()
            raise AssertionError("gateway did not become ready in time")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
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

    def register_secret(self, value: str, label: str) -> None:
        if value:
            self._secrets[value] = f"<REDACTED:{label}>"

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
    ) -> CliResult:
        argv = [str(self.artifacts.console), *args]
        if json_output:
            argv.append("--json")
        proc = subprocess.run(
            argv,
            cwd=str(self.operator_dir),
            env=self.cli_env,
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
    listed = env.run_cli("institutions", "list").json
    assert "Seed Institution 205" in {row["name"] for row in listed["institutions"]}
    shown = env.run_cli("institutions", "show", "Seed Institution 205").json
    assert shown["id"] == m["institution_seed"]

    # Owner lookup: exact email list, show by UUID and by email.
    owners_listed = env.run_cli("owners", "list", "--email", m["owner_seed_email"]).json
    assert [row["id"] for row in owners_listed["owners"]] == [m["owner_seed"]]
    assert env.run_cli("owners", "show", m["owner_seed"]).json["email"] == m["owner_seed_email"]
    assert env.run_cli("owners", "show", m["owner_seed_email"]).json["id"] == m["owner_seed"]

    # Cohort lookup.
    cohorts_listed = env.run_cli("cohorts", "list").json
    assert m["cohort_seed"] in {row["id"] for row in cohorts_listed["cohorts"]}
    assert env.run_cli("cohorts", "show", m["cohort_seed"]).json["name"] == "Seed Cohort 205"

    # Key lookup by public key ID and by exact owner email.
    by_public = env.run_cli("keys", "show", m["k_policy_public"]).json
    assert by_public["id"] == m["k_policy"]
    by_email = env.run_cli(
        "keys", "list", "--owner-email", m["owner_seed_email"], "--limit", "100"
    ).json
    assert m["k_policy"] in {row["id"] for row in by_email["keys"]}

    # Complete bounded paging over the 39-row cohort (37 active + revoked +
    # suspended controls), no overlap, no loss.
    page1 = env.run_cli("keys", "list", "--cohort-id", m["cohort37"], "--limit", "20").json
    assert page1["paging"]["returned"] == 20
    assert page1["paging"]["has_more"] is True
    assert page1["paging"]["next_offset"] == 20
    page2 = env.run_cli(
        "keys", "list", "--cohort-id", m["cohort37"], "--limit", "20", "--offset", "20"
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
    refused = env.run_cli("keys", "show", bearer, expect=1)
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

    report = env.run_cli("keys", "policy", "effective", m["k_policy"]).json
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
    ).json
    assert allowed["verdict"] == "resolved"
    assert allowed["blocker"] is None
    assert allowed["endpoint_allowed"] is True
    assert allowed["bounds"]["routes_examined"] >= 3

    disabled = env.run_cli(
        "keys", "policy", "explain-route", m["k_policy"],
        "--model", models["m2"], "--endpoint", "/v1/chat/completions",
    ).json
    assert disabled["verdict"] == "blocked"
    assert disabled["blocker"] == "model-route-disabled"

    disallowed = env.run_cli(
        "keys", "policy", "explain-route", m["k_policy"],
        "--model", models["m4"], "--endpoint", "/v1/chat/completions",
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
    ).json
    inst_id = created["id"]
    assert created["name"] == "Field Institution 205"
    assert env.run_cli("institutions", "show", inst_id).json["name"] == "Field Institution 205"

    # Normalized (whitespace-padded) duplicate is refused; count unchanged.
    before = len(env.run_cli("institutions", "list").json["institutions"])
    dup = env.run_cli(
        "institutions", "create", "--name", "  Field Institution 205  ", any_failure=True
    )
    dup_text = (dup.stdout + dup.stderr).lower()
    assert "already" in dup_text or "exist" in dup_text
    after = env.run_cli("institutions", "list").json["institutions"]
    assert len(after) == before

    # (b) Owner created under the new institution; list/show resolve it.
    owner = env.run_cli(
        "owners", "create", "--name", "Field", "--surname", "Participant",
        "--email", "field-participant-205a@example.invalid",
        "--institution-id", inst_id, "--notes", "new field owner",
    ).json
    owner_id = owner["id"]
    assert owner["institution_id"] == inst_id
    assert owner_id in {row["id"] for row in env.run_cli("owners", "list").json["owners"]}

    # (c) Cohort created; supported cohort edit with omission/clear rules.
    cohort = env.run_cli(
        "cohorts", "create", "--name", "Field Cohort 205", "--description", "initial"
    ).json
    cohort_id = cohort["id"]
    edited = env.run_cli(
        "cohorts", "update", cohort_id, "--reason", "update field cohort description",
        "--description", "updated",
    ).json
    assert edited["description"] == "updated"
    assert edited["name"] == "Field Cohort 205"  # omitted field preserved
    cleared = env.run_cli(
        "cohorts", "update", cohort_id, "--reason", "clear field cohort description",
        "--clear-description",
    ).json
    assert cleared["description"] is None

    # Missing reason refuses without mutation.
    no_reason = env.run_cli(
        "cohorts", "update", cohort_id, "--description", "should not land",
        any_failure=True,
    )
    assert "reason" in (no_reason.stdout + no_reason.stderr).lower()
    assert env.run_cli("cohorts", "show", cohort_id).json["description"] is None

    # (d) owners update: move the pre-existing owner to the NEW institution,
    # preserving omitted metadata / is_active / external_id / member keys.
    moved = env.run_cli(
        "owners", "update", m["owner_move"],
        "--reason", "move owner to field institution",
        "--institution-id", inst_id,
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
    )
    assert env.sql("SELECT external_id FROM owners WHERE id = $1", m["owner_move"])[0][
        "external_id"
    ] == "ext-move-205a"

    # Unknown UUID refuses without mutation.
    unknown = env.run_cli(
        "owners", "update", str(uuid.uuid4()), "--reason", "unknown owner probe",
        "--notes", "should not land", any_failure=True,
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


def _policy_view(env: FieldEnvironment, key_id: str) -> dict[str, object]:
    row = env.run_cli("keys", "show", key_id).json
    return {field: row[field] for field in _POLICY_VIEW_FIELDS}


def _full_key_row(env: FieldEnvironment, key_id: str) -> dict[str, object]:
    return env.sql("SELECT * FROM gateway_keys WHERE id = $1", key_id)[0]


def _export_policy(env: FieldEnvironment, key_id: str) -> dict[str, object]:
    """Installed FULL canonical policy export (always JSON on stdout; the
    command has no --json flag)."""
    result = env.run_cli("keys", "policy", "export", key_id, json_output=False)
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
    export_student = _export_policy(env, src_student)
    export_chat = _export_policy(env, src_chat)
    export_deny = _export_policy(env, src_deny)

    audit_before = _audit_count(env)
    assert _clone_cohort_count(env, str(m["cohort_clone_target"])) == 0
    assert _clone_cohort_count(env, str(m["cohort_clone_target2"])) == 0

    # (a) Mixed-mode probes refuse with the fixed code BEFORE any plan work.
    both = env.run_cli(
        "keys", "clone",
        "--dry-run", str(plans / "both.json"),
        "--execute", str(plans / "both2.json"),
        any_failure=True,
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
        planned = env.run_cli(*args).json
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
    )
    assert no_channel.json["error"]["code"] == "invalid_parameter"
    two_channels = env.run_cli(
        "keys", "clone", "--execute", str(plan_files["denyall"]),
        "--reason", "two channel probe",
        "--secret-output-file", str(plans / "two.txt"),
        "--show-plaintext",
        any_failure=True,
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
        assert _export_policy(env, target) == export_of[name]
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
    assert _policy_view(env, targets_out["denyall"])["allowed_providers_state"] == "deny-all"
    assert _policy_view(env, src_student)["allowed_providers_state"] == "unrestricted"

    # Effective-source views on the actual nullable configured rate columns.
    chat_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["chat1"]
    ).json["rate_limits"]
    assert chat_eff["requests_per_window"] == {
        "configured": 42, "effective": 42, "source": "key",
    }
    assert chat_eff["window_seconds"]["configured"] == 30
    assert chat_eff["window_seconds"]["source"] == "key"
    student_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["student"]
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
    )
    env.run_cli(
        "keys", "set-rate-limits", src_chat,
        "--requests-per-minute", "43",
        "--reason", "stale-plan source mutation",
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
    ).json
    assert repeat2["status"] == "already-applied"
    assert str(repeat2["target_gateway_key_id"]) == targets_out["chat1"]
    assert (plans / "secret-repeat2.txt").exists() is False
    assert _export_policy(env, targets_out["chat1"]) == export_chat
    assert _audit_count(env) == audit_after_mutation  # dedup writes no audit
    # The executed chat1 target is unchanged by the source mutation.
    assert _full_key_row(env, targets_out["chat1"]) == target_chat1_before
    chat1_eff = env.run_cli(
        "keys", "policy", "effective", targets_out["chat1"]
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
    ).json
    assert result["rate_limit_policy"] == {
        "requests_per_minute": 1,
        "window_seconds": 10,
        "max_concurrent_requests": 1,
    }
    row_after = _full_key_row(env, k)
    rate_view = env.run_cli("keys", "policy", "effective", k).json["rate_limits"]
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
    )
    assert _full_key_row(env, k) == row_after

    # (b) Bounded lazy throttling within actual installation ceilings.
    row_before_lazy = _full_key_row(env, k)
    env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "4",
        "--reason", "field qualification lazy wait",
    ).assert_ok("lazy set")
    row_after_lazy_set = _full_key_row(env, k)
    lazy = env.run_cli("keys", "policy", "effective", k).json["lazy_throttling"]
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
    )
    assert over_wait.exit_code == 2
    assert "operator ceiling" in over_wait.stderr
    over_waiting = env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "999",
        "--reason", "excessive waiting probe", any_failure=True,
    )
    assert over_waiting.exit_code == 2
    assert "operator ceiling" in over_waiting.stderr
    # Refusals mutate nothing.
    assert _full_key_row(env, k) == row_after_lazy_set
    # --mode reject from a valid wait state removes the stored override
    # (default immediate rejection); rates and material are preserved.
    rates_before = env.run_cli("keys", "policy", "effective", k).json["rate_limits"]
    env.run_cli(
        "keys", "set-lazy-throttling", k, "--mode", "reject",
        "--reason", "lazy reject transition from wait",
    ).assert_ok("lazy reject")
    lazy_reject = env.run_cli("keys", "policy", "effective", k).json["lazy_throttling"]
    assert lazy_reject["mode"] == "reject"
    assert lazy_reject["stored_state"] == "absent"
    assert lazy_reject["source"] == "default"
    # In reject mode the numeric members are the inert schema defaults, not
    # a configured wait (mode/stored_state/source carry the distinction).
    assert (
        env.run_cli("keys", "policy", "effective", k).json["rate_limits"]
        == rates_before
    )
    # Re-establish the wait override, then --clear: a distinct verb with the
    # SAME stored outcome (no override / immediate rejection).
    env.run_cli(
        "keys", "set-lazy-throttling", k,
        "--mode", "wait", "--max-wait-seconds", "30",
        "--max-waiting-requests", "4",
        "--reason", "lazy re-wait before clear",
    ).assert_ok("lazy re-wait")
    env.run_cli(
        "keys", "set-lazy-throttling", k, "--clear",
        "--reason", "lazy clear transition",
    ).assert_ok("lazy clear")
    lazy_cleared = env.run_cli("keys", "policy", "effective", k).json["lazy_throttling"]
    assert lazy_cleared["mode"] == "reject"
    assert lazy_cleared["stored_state"] == "absent"
    assert lazy_cleared["source"] == "default"
    assert (
        env.run_cli("keys", "policy", "effective", k).json["rate_limits"]
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
    ).assert_ok("rate clear-all")
    cleared = env.run_cli("keys", "policy", "effective", k).json["rate_limits"]
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
