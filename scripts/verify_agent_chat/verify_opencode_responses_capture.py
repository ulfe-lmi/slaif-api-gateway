"""Actual-client OpenCode Responses capture/verification against loopback fake.

Narrowly named OpenCode verifier for OAP 228-a. Runs the pinned OpenCode
1.19.3 executable (native @ai-sdk/openai -> Responses API) against the shared
loopback_responses_fake.py in a fully task-owned, isolated run root (private
HOME/XDG, synthetic bearer, --pure, bounded timeout). Only 127.0.0.1 traffic;
no provider, no user profile, no real key.

Probes (each in its own session):
  text      single-turn streaming text (sentinel exact match)
  toolloop  two-turn read-tool continuation gated on the exact unpredictable
            marker extracted from the correlated native function_call_output
            (never an unconditional file read)
  reasoning turn one emits reasoning (synthetic encrypted_content) + tool
            call; the continuation records per-item encrypted-reasoning
            replay FACTS (presence/shape/short hash/equality) without gating
            the sentinel on them

Gates and honesty rules mirror verify_opencode_chat_capture.py:
  - pinned binary SHA-256 preflight; overrides labelled override_unqualified
    and can never all_pass;
  - per-probe structural facts captured BEFORE the probe journal is deleted;
  - the report is written even on failure with explicit error labels;
  - session evidence is a real cross-request predicate (short SHA-256
    prefixes only);
  - private run-root artifacts deleted by default and deletion verified;
    --keep-run-root retains them and is labelled;
  - owned processes only, deterministic termination; non-termination fails.

Emission: sanitized structural JSON report (field names/types/counts,
predicate booleans, short public hashes, SDK provenance). Never prints
markers, prompts, arguments, results, raw IDs, or raw bodies.

Stdlib only. Exit 0 only when every enabled probe's gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

PINNED_EXECUTABLE = "/home/janezp/.local/share/opencode-bin/releases/v1.19.3/opencode"
PINNED_EXECUTABLE_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
CLIENT_VERSION = "1.19.3"
PROVIDER = "agent-responses-fake"
MODEL = "agent-responses-fake-model"
DUMMY_KEY_PREFIX = "sk-slaif-dummy"
TEXT_SENTINEL = "AGENT_RESP_TEXT_OK"
REASONING_SENTINEL = "AGENT_RESP_REASONING_OK"
FAKE_READY_TIMEOUT_S = 20.0
SESSION_HEADER_NAMES = ("x-opencode-session-id", "x-session-affinity", "x-session-id")
BASELINE_TOOL_NAMES = ("bash", "edit", "glob", "grep", "read",
                       "skill", "task", "todowrite", "write")


def die(msg: str) -> None:
    """Preflight failure before any run evidence exists (safe fixed text)."""
    print(f"FAIL {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def safe_load_json(path: Path):
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return None


def free_loopback_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def build_run_root(run_root: Path) -> None:
    if run_root.exists():
        die(f"run root already exists: {run_root}")
    for sub in ("home", "config", "workspace", "run", "logs", "tmp"):
        (run_root / sub).mkdir(parents=True)
    for p in run_root.rglob("*"):
        p.chmod(0o700 if p.is_dir() else 0o600)
    run_root.chmod(0o700)


def write_config(run_root: Path, port: int, deny_webfetch: bool) -> Path:
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            PROVIDER: {
                "npm": "@ai-sdk/openai",
                "name": "SLAIF 228 Loopback",
                "options": {
                    "baseURL": f"http://127.0.0.1:{port}/v1",
                    "apiKey": f"{DUMMY_KEY_PREFIX}-{secrets.token_hex(4)}-loopback",
                    "timeout": 240000,
                    "setCacheKey": False,
                },
                "models": {
                    MODEL: {
                        "name": "SLAIF 228 Test Model",
                        "tool_call": True,
                        "limit": {"context": 245760, "input": 245760, "output": 32768},
                        "options": {"reasoningEffort": "xhigh", "store": False},
                    }
                },
            }
        },
    }
    if deny_webfetch:
        cfg["permission"] = {"webfetch": "deny"}
    path = run_root / "config" / "opencode-228.json"
    write_private(path, (json.dumps(cfg, indent=2) + "\n").encode())
    return path


def client_env(run_root: Path, config_path: Path) -> dict:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(run_root / "home"),
        "XDG_CONFIG_HOME": str(run_root / "home" / ".config"),
        "XDG_CACHE_HOME": str(run_root / "home" / ".cache"),
        "XDG_DATA_HOME": str(run_root / "home" / ".local" / "share"),
        "TMPDIR": str(run_root / "tmp"),
        "OPENCODE_CONFIG": str(config_path),
    }


def run_client(exe: str, run_root: Path, config_path: Path, prompt: str,
               title: str, timeout: int) -> tuple[int | None, str | None, float]:
    """Run one bounded client invocation in its own process group.

    Returns (return_code, error_label, elapsed_s). On timeout the owned child
    group is killed deterministically and the probe records 'client_timeout'.
    """
    out = run_root / "logs" / f"{title.replace(' ', '_')}.out"
    err = run_root / "logs" / f"{title.replace(' ', '_')}.err"
    cmd = [exe, "--pure", "run", "--dir", str(run_root / "workspace"),
           "--format", "json", "--title", title,
           "--model", f"{PROVIDER}/{MODEL}", prompt]
    start = time.monotonic()
    with open(out, "wb") as fo, open(err, "wb") as fe:
        proc = subprocess.Popen(cmd, env=client_env(run_root, config_path),
                                stdout=fo, stderr=fe, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            return None, "client_timeout", round(time.monotonic() - start, 3)
    return rc, None, round(time.monotonic() - start, 3)


def last_text_event(out_path: Path) -> str | None:
    """Last text part from the client JSON event log; None on any parse issue."""
    text = None
    try:
        for line in out_path.read_text(errors="replace").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            part = e.get("part") or {}
            if e.get("type") == "text" and part.get("type") == "text":
                value = part.get("text")
                if isinstance(value, str):
                    text = value
    except OSError:
        return None
    return text


def _session_hint_value(entry: dict) -> str | None:
    headers = entry.get("headers", {})
    values = []
    for name in SESSION_HEADER_NAMES:
        for k, v in headers.items():
            if k.lower() == name and isinstance(v, str):
                values.append(v)
    return values[0] if values else None


def _input_item_shape(item: dict) -> dict:
    f = {
        "type": item.get("type"),
        "keys_sorted": sorted(k for k in item.keys() if isinstance(k, str)),
        "id_present": item.get("id") is not None,
        "status_present": item.get("status") is not None,
    }
    t = item.get("type")
    if t == "message" or (
            t is None and item.get("role") is not None and "content" in item):
        f["role"] = item.get("role")
        c = item.get("content")
        f["content_form"] = type(c).__name__
        if isinstance(c, list):
            f["content_part_types"] = sorted(
                {p.get("type") for p in c if isinstance(p, dict)})
    elif t == "function_call":
        f["call_id_present"] = item.get("call_id") is not None
        f["name_present"] = item.get("name") is not None
        f["arguments_present"] = item.get("arguments") is not None
        f["arguments_type"] = type(item.get("arguments")).__name__
    elif t == "function_call_output":
        f["call_id_present"] = item.get("call_id") is not None
        f["output_present"] = item.get("output") is not None
        f["output_type"] = type(item.get("output")).__name__
    elif t == "reasoning":
        enc = item.get("encrypted_content")
        f["encrypted_content_present"] = enc is not None
        if enc is not None:
            f["encrypted_sha256_8"] = hashlib.sha256(
                str(enc).encode()).hexdigest()[:8]
            f["encrypted_byte_length"] = len(str(enc))
    return f


def per_request_structural(run_root: Path) -> dict:
    """Sanitized structural facts from the private journal (never raw bodies).

    Must be called BEFORE the probe journal is deleted.
    """
    journal = run_root / "run" / "requests.jsonl"
    try:
        lines = journal.read_text(errors="replace").splitlines()
        journal_state = "present"
    except OSError:
        lines = []
        journal_state = "absent"
    requests = []
    for line in lines:
        try:
            e = json.loads(line)
        except Exception:
            continue
        if not isinstance(e, dict) or e.get("method") != "POST" \
                or e.get("path") != "/v1/responses":
            continue
        try:
            b = json.loads(e["body"])
        except Exception:
            b = None
        if not isinstance(b, dict):
            b = {}
        tools = b.get("tools") if isinstance(b.get("tools"), list) else []
        tool_names = [t.get("name") for t in tools
                      if isinstance(t, dict) and t.get("name") is not None]
        strict_present = sum(1 for t in tools
                             if isinstance(t, dict) and "strict" in t)
        raw_input = b.get("input")
        item_shapes = [_input_item_shape(i) for i in raw_input
                       if isinstance(raw_input, list)
                       and isinstance(i, dict)]
        session_value = _session_hint_value(e)
        requests.append({
            "top_level_fields": sorted(k for k in b.keys() if isinstance(k, str)),
            "top_level_field_count": len(b),
            "model": b.get("model"),
            "max_output_tokens": b.get("max_output_tokens"),
            "store": b.get("store"),
            "include": sorted(b["include"])
                if isinstance(b.get("include"), list) else b.get("include"),
            "reasoning": b.get("reasoning"),
            "tool_choice": b.get("tool_choice"),
            "stream": b.get("stream"),
            "tools_count": len(tools),
            "tool_names": tool_names,
            "tool_declaration_form": ("flat" if tools and isinstance(tools[0], dict)
                                      and "name" in tools[0] else None),
            "tool_declaration_strict_present_count": strict_present,
            "input_item_count": len(item_shapes),
            "input_item_shapes": item_shapes,
            "user_agent": e.get("headers", {}).get("User-Agent")
                if isinstance(e.get("headers"), dict) else None,
            "session_header_names_present": sorted(
                k for k in (e.get("headers") or {})
                if isinstance(k, str) and k.lower() in
                {n.lower() for n in SESSION_HEADER_NAMES}),
            "session_value_sha256_8": hashlib.sha256(session_value.encode()).hexdigest()[:8]
                if session_value is not None else None,
            "session_headers_equal_within_request": len({
                v for n in SESSION_HEADER_NAMES for k, v in (e.get("headers") or {}).items()
                if isinstance(k, str) and k.lower() == n}) <= 1,
        })
    return {"requests": requests, "request_count": len(requests),
            "journal_state": journal_state}


def contract_facts(structural: dict) -> dict:
    """Wire-contract FACTS (not gates) from the first request of the probe."""
    reqs = structural.get("requests", [])
    if not reqs:
        return {"observed": False}
    b = reqs[0]
    return {
        "observed": True,
        "max_output_tokens_is_32000": b.get("max_output_tokens") == 32000,
        "max_output_tokens_value": b.get("max_output_tokens"),
        "store_is_false": b.get("store") is False,
        "include_is_reasoning_encrypted_content":
            b.get("include") == ["reasoning.encrypted_content"],
        "reasoning_effort_is_xhigh":
            isinstance(b.get("reasoning"), dict)
            and b["reasoning"].get("effort") == "xhigh",
        "tool_choice_is_auto": b.get("tool_choice") == "auto",
        "stream_is_true": b.get("stream") is True,
        "tools_count": b.get("tools_count"),
        "tool_names_match_baseline_set":
            sorted(b.get("tool_names") or []) == sorted(BASELINE_TOOL_NAMES),
        "tool_declaration_flat": b.get("tool_declaration_form") == "flat",
        "all_tools_declare_strict":
            b.get("tool_declaration_strict_present_count") == b.get("tools_count"),
    }


def session_facts(structural: dict) -> dict:
    """Cross-request session-stability predicates (short hashes only)."""
    requests = structural.get("requests", [])
    hashes = [r["session_value_sha256_8"] for r in requests
              if r["session_value_sha256_8"] is not None]
    within_ok = all(r["session_headers_equal_within_request"] for r in requests)
    if len(hashes) >= 2:
        stable_across = len(set(hashes)) == 1
    else:
        stable_across = None
    return {
        "request_count": len(requests),
        "session_value_sha256_8_first": hashes[0] if hashes else None,
        "stable_across_requests": stable_across,
        "headers_equal_within_each_request": within_ok,
    }


def terminate_fake(fake_proc, fake_log) -> bool:
    """Deterministically terminate only the owned fake process group."""
    try:
        os.killpg(os.getpgid(fake_proc.pid), signal.SIGTERM)
        fake_proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(fake_proc.pid), signal.SIGKILL)
            fake_proc.wait(timeout=5)
        except Exception:
            try:
                fake_log.close()
            except Exception:
                pass
            return False
    try:
        fake_log.close()
    except Exception:
        pass
    return fake_proc.returncode is not None


def wait_fake_ready(port: int, deadline_s: float = FAKE_READY_TIMEOUT_S) -> tuple[bool, float]:
    start = time.monotonic()
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True, round(time.monotonic() - start, 3)
        except OSError:
            if time.monotonic() - start >= deadline_s:
                return False, round(time.monotonic() - start, 3)
            time.sleep(0.25)


def _pinned_binary_openai_versions(exe: str) -> dict:
    """Scan the pinned bun-compiled exe for bundled @ai-sdk/openai copies.

    The pinned OpenCode binary bundles the OpenAI provider SDK inside its
    bunfs payload; there is no runtime npm install of @ai-sdk/openai. The
    package entry exports openai/createOpenAI/VERSION, while nested
    transitive copies export createOpenAI only.
    """
    out = {"scanned": False, "package_entry_version": None,
           "nested_copy_versions": []}
    try:
        with open(exe, "rb") as f:
            data = f.read()
    except OSError:
        return out
    out["scanned"] = True
    for m in re.finditer(re.escape(b"ai-sdk/openai/"), data):
        off = m.start()
        vers = re.findall(rb'"(\d+\.\d+\.\d+)"',
                          data[max(0, off - 65536):off])
        ver = vers[-1].decode() if vers else None
        end = data.find(b"/$bunfs/root/", off + 1)
        stop = min(off + 8192, end) if end > off else off + 8192
        after = data[off:stop]
        if b"as openai" in after and b"as VERSION" in after:
            out["package_entry_version"] = ver
        else:
            out["nested_copy_versions"].append(ver)
    return out


def _ua_facts(ua: str | None) -> dict:
    pu = re.search(r"ai-sdk/provider-utils/([\d.]+)", ua or "")
    rt = re.search(r"runtime/(bun/[\d.]+)", ua or "")
    return {
        "ai_sdk_provider_utils_version": pu.group(1) if pu else None,
        "runtime": rt.group(1) if rt else None,
    }


def sdk_provenance(run_root: Path, exe: str, observed_ua: str | None) -> dict:
    """SDK provenance: the pinned bun-compiled exe bundles @ai-sdk/openai.

    Read BEFORE cleanup: binary read of the pinned exe plus a check that no
    runtime npm install of the provider SDK occurred under the run-owned
    home; the observed client User-Agent supplies provider-utils/runtime.
    """
    binary = _pinned_binary_openai_versions(exe)
    installed = any(
        p.is_dir()
        for p in Path(run_root, "home").rglob("node_modules/@ai-sdk")
    ) if (run_root / "home").exists() else False
    ua = _ua_facts(observed_ua)
    return {
        "installation_mode": "bundled_in_pinned_executable",
        "runtime_npm_install_observed": installed,
        "ai_sdk_openai_package_entry_version":
            binary["package_entry_version"],
        "ai_sdk_openai_nested_copy_versions": binary["nested_copy_versions"],
        "ai_sdk_openai_binary_scan": binary["scanned"],
        "ai_sdk_provider_utils_version":
            ua["ai_sdk_provider_utils_version"],
        "runtime": ua["runtime"],
        "observed_user_agent": observed_ua,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--executable", default=PINNED_EXECUTABLE)
    ap.add_argument("--expect-sha256", default=PINNED_EXECUTABLE_SHA256)
    ap.add_argument("--config", choices=["default", "denyweb"], default="denyweb")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--skip-toolloop", action="store_true")
    ap.add_argument("--skip-reasoning", action="store_true")
    ap.add_argument("--report", required=True)
    ap.add_argument("--keep-run-root", action="store_true",
                    help="retain the private run root (default: delete it after the report)")
    args = ap.parse_args()

    exe = args.executable
    if not os.path.isfile(exe):
        die(f"executable missing: {exe}")
    got_sha = sha256_file(exe)
    if got_sha != args.expect_sha256:
        die(f"executable sha256 mismatch: {got_sha}")
    pinned_identity = (
        os.path.realpath(exe) == os.path.realpath(PINNED_EXECUTABLE)
        and args.expect_sha256 == PINNED_EXECUTABLE_SHA256)

    run_root = Path(args.run_root)
    if not args.keep_run_root:
        report_real = os.path.realpath(args.report)
        root_real = os.path.realpath(run_root)
        if report_real == root_real or report_real.startswith(root_real + os.sep):
            die("report path is inside the run root and would be deleted by default cleanup")
    build_run_root(run_root)
    port = free_loopback_port()
    config_path = write_config(run_root, port, deny_webfetch=(args.config == "denyweb"))

    fake = Path(__file__).with_name("loopback_responses_fake.py")
    fake_env = dict(os.environ, AGENT_RESP_FAKE_RUN=str(run_root),
                    AGENT_RESP_FAKE_WORKSPACE=str(run_root / "workspace"))
    fake_log = open(run_root / "logs" / "fake.log", "wb")
    fake_proc = subprocess.Popen([sys.executable, str(fake), str(port)],
                                 env=fake_env, stdout=fake_log,
                                 stderr=subprocess.STDOUT, start_new_session=True)

    gates: dict = {}
    global_errors: list[str] = []
    fake_ready = False
    fake_ready_s = None
    session_hashes: list[str | None] = []
    try:
        fake_ready, fake_ready_s = wait_fake_ready(port)
        if not fake_ready:
            global_errors.append("fake_not_ready_within_deadline")

        def clear_probe_journal() -> None:
            (run_root / "run" / "requests.jsonl").unlink(missing_ok=True)
            (run_root / "run" / "state.json").unlink(missing_ok=True)

        if fake_ready:
            # ---- text probe (its own session) -----------------------------
            (run_root / "run" / "scenario.json").write_text(json.dumps(
                {"mode": "text", "final_text": TEXT_SENTINEL}))
            (run_root / "run" / "scenario.json").chmod(0o600)
            rc, err_label, elapsed = run_client(
                exe, run_root, config_path,
                f"Reply with exactly {TEXT_SENTINEL}. Do not use tools, inspect files, or run commands.",
                "228 text", args.timeout)
            final = last_text_event(run_root / "logs" / "228_text.out")
            structural = per_request_structural(run_root)
            gates["text"] = {
                "exit_code": rc, "error": err_label, "elapsed_s": elapsed,
                "final_text_exact": final == TEXT_SENTINEL,
                "session": session_facts(structural),
                "structural": structural,
                "contract_facts": contract_facts(structural),
                "pass": rc == 0 and final == TEXT_SENTINEL,
            }
            if gates["text"]["session"]["session_value_sha256_8_first"]:
                session_hashes.append(gates["text"]["session"]["session_value_sha256_8_first"])
            clear_probe_journal()

            # ---- toolloop probe (fresh session, two main requests) --------
            if not args.skip_toolloop:
                marker = f"SLAIF228-MARK-{secrets.token_hex(12)}"
                write_private(run_root / "workspace" / "probe.txt", marker.encode())
                write_private(run_root / "run" / "expected_marker.bin",
                              marker.encode())
                (run_root / "run" / "scenario.json").write_text(json.dumps(
                    {"mode": "toolloop", "tool_file": "probe.txt"}))
                (run_root / "run" / "scenario.json").chmod(0o600)
                rc, err_label, elapsed = run_client(
                    exe, run_root, config_path,
                    "Read the file probe.txt in the workspace using the read tool, then reply with the exact marker text from that file.",
                    "228 toolloop", args.timeout)
                final = last_text_event(run_root / "logs" / "228_toolloop.out")
                state = safe_load_json(run_root / "run" / "state.json")
                if state is None or not isinstance(state, dict):
                    err_label = err_label or "state_missing_or_unparseable"
                    state = {}
                facts_state = state.get("toolloop_facts", {})
                if not isinstance(facts_state, dict):
                    facts_state = {}
                structural = per_request_structural(run_root)
                session = session_facts(structural)
                gates["toolloop"] = {
                    "exit_code": rc, "error": err_label, "elapsed_s": elapsed,
                    "toolloop_verified": state.get("toolloop_verified") is True,
                    "final_text_source": state.get("final_text_source"),
                    "final_text_equals_marker": final == marker,
                    "final_text_length": len(final) if isinstance(final, str) else None,
                    "marker_length": len(marker),
                    "toolloop_facts": facts_state,
                    "session": session,
                    "structural": structural,
                    "contract_facts": contract_facts(structural),
                    "pass": (rc == 0 and state.get("toolloop_verified") is True
                             and state.get("final_text_source")
                             == "correlated_tool_result"
                             and final == marker),
                }
                if session["session_value_sha256_8_first"]:
                    session_hashes.append(session["session_value_sha256_8_first"])
                clear_probe_journal()

            # ---- reasoning probe (fresh session, two main requests) -------
            if not args.skip_reasoning:
                write_private(run_root / "workspace" / "probe.txt",
                              b"reasoning-probe-material")
                (run_root / "run" / "scenario.json").write_text(json.dumps(
                    {"mode": "reasoning_continuation", "tool_file": "probe.txt",
                     "final_text": REASONING_SENTINEL}))
                (run_root / "run" / "scenario.json").chmod(0o600)
                rc, err_label, elapsed = run_client(
                    exe, run_root, config_path,
                    f"Read the file probe.txt in the workspace using the read tool, then reply with exactly {REASONING_SENTINEL}.",
                    "228 reasoning", args.timeout)
                final = last_text_event(run_root / "logs" / "228_reasoning.out")
                state = safe_load_json(run_root / "run" / "state.json")
                if state is None or not isinstance(state, dict):
                    err_label = err_label or "state_missing_or_unparseable"
                    state = {}
                rc_facts = state.get("reasoning_continuation", {})
                if not isinstance(rc_facts, dict):
                    rc_facts = {}
                structural = per_request_structural(run_root)
                session = session_facts(structural)
                gates["reasoning"] = {
                    "exit_code": rc, "error": err_label, "elapsed_s": elapsed,
                    "final_text_exact": final == REASONING_SENTINEL,
                    "reasoning_continuation": rc_facts,
                    "session": session,
                    "structural": structural,
                    "contract_facts": contract_facts(structural),
                    "pass": rc == 0 and final == REASONING_SENTINEL
                            and state.get("reasoning_continuation") is not None,
                }
                if session["session_value_sha256_8_first"]:
                    session_hashes.append(session["session_value_sha256_8_first"])
                clear_probe_journal()
    except Exception as exc:  # unexpected: report honestly, never crash silent
        global_errors.append(f"unexpected:{type(exc).__name__}")
    finally:
        fake_terminated = terminate_fake(fake_proc, fake_log)

    enabled = len(gates)
    session_distinct_across_probes = None
    if enabled >= 2:
        known = [h for h in session_hashes if h is not None]
        session_distinct_across_probes = len(set(known)) == len(known)

    if not pinned_identity:
        global_errors.append("pinned_identity_override")
    if not fake_terminated:
        global_errors.append("fake_process_not_terminated")
    if "toolloop" in gates:
        tl_stable = gates["toolloop"]["session"]["stable_across_requests"]
        if tl_stable is not True:
            global_errors.append("toolloop_session_not_stable_across_requests")
    if "reasoning" in gates:
        rz_stable = gates["reasoning"]["session"]["stable_across_requests"]
        if rz_stable is not True:
            global_errors.append("reasoning_session_not_stable_across_requests")
    observed_ua = None
    for g in gates.values():
        reqs = g.get("structural", {}).get("requests", [])
        if reqs and reqs[0].get("user_agent"):
            observed_ua = reqs[0]["user_agent"]
            break

    # SDK provenance read BEFORE cleanup (run-root npm check, then exe scan).
    sdk_prov = sdk_provenance(run_root, exe, observed_ua)

    if not args.keep_run_root:
        shutil.rmtree(run_root, ignore_errors=True)
        cleanup_ok = not run_root.exists()
        if not cleanup_ok:
            global_errors.append("run_root_cleanup_failed")
    else:
        cleanup_ok = True

    all_pass = (not global_errors and fake_ready
                and all(g.get("pass") is True for g in gates.values())
                and bool(gates)
                and (session_distinct_across_probes is None
                     or session_distinct_across_probes is True))

    report = {
        "verifier": "verify_opencode_responses_capture.py",
        "client": {
            "version": CLIENT_VERSION,
            "executable_sha256": got_sha,
            "observed_user_agent": observed_ua,
            "pinned_identity": "pinned" if pinned_identity
                               else "override_unqualified",
        },
        "config_variant": args.config,
        "sdk_provenance": sdk_prov,
        "fake_ready": fake_ready,
        "fake_ready_wait_s": fake_ready_s,
        "fake_process_terminated": fake_terminated,
        "gates": gates,
        "session_distinct_across_probes": session_distinct_across_probes,
        "errors": global_errors,
        "privacy": {
            "raw_content_retained": args.keep_run_root or (
                not args.keep_run_root and not cleanup_ok),
            "provider_call_performed": False,
            "user_profile_touched": False,
        },
        "artifacts": {
            "run_root_cleaned": (not args.keep_run_root) and cleanup_ok,
            "cleanup_verified": cleanup_ok,
            "retained_mode": "retained_by_flag" if args.keep_run_root
                             else "cleaned_default",
        },
        "all_pass": all_pass,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_private(Path(args.report), (json.dumps(report, indent=2) + "\n").encode())

    print(json.dumps({"all_pass": all_pass,
                      "gates": {k: {kk: vv for kk, vv in v.items()
                                    if kk not in ("structural", "session")}
                                for k, v in gates.items()},
                      "errors": global_errors,
                      "report": str(args.report)}, indent=2))
    raise SystemExit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
