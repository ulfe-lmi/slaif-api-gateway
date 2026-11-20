"""Actual-client OpenCode Chat capture/verification against the loopback fake.

Narrowly named OpenCode verifier for OAP 227. Runs the pinned OpenCode
executable against the shared loopback_chat_fake.py in a fully task-owned,
isolated run root (private HOME/XDG, synthetic bearer, --pure, bounded
timeout). Only 127.0.0.1 traffic; no provider, no user profile, no real key.

Probes:
  text      ordinary single-turn streaming text (sentinel exact match)
  toolloop  natural two-turn read-tool continuation gated on the exact
            unpredictable marker extracted from the correlated native tool
            result (never an unconditional file read)

Gates and honesty rules:
  - The pinned binary identity (SHA-256) is checked before anything runs.
  - The fake must pass a bounded TCP readiness wait before any probe.
  - Per-probe structural facts are captured BEFORE the probe journal is
    deleted, so a failed later probe cannot erase earlier evidence.
  - The report is written even on probe timeout, missing/corrupt state, or
    parse failure: the affected gate records an explicit error label and
    fails honestly instead of raising.
  - Session evidence is a real cross-request predicate: the two toolloop
    main requests of one session must carry the same session hint value,
    and a fresh run (text probe) must differ from it. Only short SHA-256
    prefixes of hint values are recorded, never raw IDs.
  - Private run-root artifacts (raw journal, config with dummy bearer,
    logs, markers) are deleted by default BEFORE the report is written and
    the deletion is verified; a failed required cleanup fails the run and
    the report labels it. --keep-run-root retains them and the report
    labels the retained mode. A report path inside the run root is rejected
    when default cleanup applies.
  - Owned processes only: the client child (its own process group) and the
    fake (its own process group) are terminated deterministically; nothing
    global is ever signalled. Non-termination fails the run.
  - A qualification run requires the exact pinned binary identity; any
    --executable/--expect-sha256 override is labelled override_unqualified
    and cannot produce all_pass, so an unqualified probe can never be
    reported as qualification success.

Emission: a sanitized structural JSON report (field names/types/counts,
predicate booleans, short public hashes). Never prints markers, prompts,
tool arguments/results, raw IDs, or raw bodies.

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
import socket
import subprocess
import sys
import time
from pathlib import Path

PINNED_EXECUTABLE = "/home/janezp/.local/share/opencode-bin/releases/v1.19.3/opencode"
PINNED_EXECUTABLE_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
CLIENT_VERSION = "1.19.3"
PROVIDER = "agent-chat-fake"
MODEL = "agent-chat-fake-model"
DUMMY_KEY_PREFIX = "sk-slaif-dummy"
TEXT_SENTINEL = "AGENT_CHAT_TEXT_OK"
FAKE_READY_TIMEOUT_S = 20.0
SESSION_HEADER_NAMES = ("x-opencode-session-id", "x-session-affinity", "x-session-id")


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
                "npm": "@ai-sdk/openai-compatible",
                "name": "SLAIF 227 Loopback",
                "options": {
                    "baseURL": f"http://127.0.0.1:{port}/v1",
                    "apiKey": f"{DUMMY_KEY_PREFIX}-{secrets.token_hex(4)}-loopback",
                },
                "models": {
                    MODEL: {
                        "name": "SLAIF 227 Test Model",
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
    path = run_root / "config" / "opencode-227.json"
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
               title: str, timeout: int, extra_args=()) -> tuple[int | None, str | None]:
    """Run one bounded client invocation in its own process group.

    Returns (return_code, error_label). On timeout the owned child group is
    killed deterministically and the probe records 'client_timeout'.
    """
    out = run_root / "logs" / f"{title.replace(' ', '_')}.out"
    err = run_root / "logs" / f"{title.replace(' ', '_')}.err"
    cmd = [exe, "--pure", "run", "--dir", str(run_root / "workspace"),
           "--format", "json", "--title", title,
           "--model", f"{PROVIDER}/{MODEL}", *extra_args, prompt]
    with open(out, "wb") as fo, open(err, "wb") as fe:
        proc = subprocess.Popen(cmd, env=client_env(run_root, config_path),
                                stdout=fo, stderr=fe, start_new_session=True)
        try:
            return proc.wait(timeout=timeout), None
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            return None, "client_timeout"


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
                or e.get("path") != "/v1/chat/completions":
            continue
        try:
            b = json.loads(e["body"])
        except Exception:
            b = None
        if not isinstance(b, dict):
            b = {}
        tools = b.get("tools") if isinstance(b.get("tools"), list) else []
        session_value = _session_hint_value(e)
        requests.append({
            "top_level_fields": sorted(k for k in b.keys() if isinstance(k, str)),
            "top_level_field_count": len(b),
            "reasoning_effort": b.get("reasoning_effort"),
            "max_tokens": b.get("max_tokens"),
            "store": b.get("store"),
            "tool_choice": b.get("tool_choice"),
            "stream": b.get("stream"),
            "stream_options": b.get("stream_options"),
            "tool_names": [t.get("function", {}).get("name") for t in tools
                           if isinstance(t, dict) and t.get("type") == "function"
                           and isinstance(t.get("function"), dict)],
            "tool_declaration_form": "nested" if tools and isinstance(tools[0], dict)
                and isinstance(tools[0].get("function"), dict) else None,
            "message_roles": [m.get("role") for m in b.get("messages", [])
                              if isinstance(m, dict)],
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--executable", default=PINNED_EXECUTABLE)
    ap.add_argument("--expect-sha256", default=PINNED_EXECUTABLE_SHA256)
    ap.add_argument("--config", choices=["default", "denyweb"], default="denyweb")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--skip-toolloop", action="store_true")
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

    fake = Path(__file__).with_name("loopback_chat_fake.py")
    fake_env = dict(os.environ, AGENT_CHAT_FAKE_RUN=str(run_root),
                    AGENT_CHAT_FAKE_WORKSPACE=str(run_root / "workspace"))
    fake_log = open(run_root / "logs" / "fake.log", "wb")
    fake_proc = subprocess.Popen([sys.executable, str(fake), str(port)],
                                 env=fake_env, stdout=fake_log,
                                 stderr=subprocess.STDOUT, start_new_session=True)

    gates: dict = {}
    global_errors: list[str] = []
    fake_ready = False
    fake_ready_s = None
    try:
        fake_ready, fake_ready_s = wait_fake_ready(port)
        if not fake_ready:
            global_errors.append("fake_not_ready_within_deadline")

        if fake_ready:
            # ---- text probe (its own session) -----------------------------
            (run_root / "run" / "scenario.json").write_text(json.dumps(
                {"mode": "text", "final_text": TEXT_SENTINEL}))
            (run_root / "run" / "scenario.json").chmod(0o600)
            rc, err_label = run_client(
                exe, run_root, config_path,
                f"Reply with exactly {TEXT_SENTINEL}. Do not use tools, inspect files, or run commands.",
                "227 text", args.timeout)
            gates["text"] = {"exit_code": rc, "error": err_label}
            final = last_text_event(run_root / "logs" / "227_text.out")
            text_structural = per_request_structural(run_root)
            gates["text"].update({
                "final_text_exact": final == TEXT_SENTINEL,
                "pass": rc == 0 and final == TEXT_SENTINEL,
                "session": session_facts(text_structural),
                "structural": text_structural,
            })
            # facts captured; now the probe journal may be cleared
            (run_root / "run" / "requests.jsonl").unlink(missing_ok=True)
            (run_root / "run" / "state.json").unlink(missing_ok=True)

            # ---- toolloop probe (a fresh session, two main requests) ------
            if not args.skip_toolloop:
                marker = f"SLAIF227-MARK-{secrets.token_hex(16)}"
                write_private(run_root / "workspace" / "probe.txt", marker.encode())
                write_private(run_root / "run" / "expected_marker.bin", marker.encode())
                (run_root / "run" / "scenario.json").write_text(json.dumps(
                    {"mode": "toolloop", "tool_file": "probe.txt"}))
                (run_root / "run" / "scenario.json").chmod(0o600)
                rc, err_label = run_client(
                    exe, run_root, config_path,
                    "Read the file probe.txt in the workspace using the read tool, then reply with the exact marker text from that file.",
                    "227 toolloop", args.timeout)
                gates["toolloop"] = {"exit_code": rc, "error": err_label}
                final = last_text_event(run_root / "logs" / "227_toolloop.out")
                state = safe_load_json(run_root / "run" / "state.json")
                if state is None:
                    err_label = err_label or "state_missing_or_unparseable"
                    state = {}
                if not isinstance(state, dict):
                    err_label = err_label or "state_missing_or_unparseable"
                    state = {}
                facts_state = state.get("toolloop_facts", {})
                if not isinstance(facts_state, dict):
                    facts_state = {}
                tl_structural = per_request_structural(run_root)
                gates["toolloop"].update({
                    "error": err_label,
                    "toolloop_verified": state.get("toolloop_verified") is True,
                    "final_text_source": state.get("final_text_source"),
                    "final_text_equals_marker": final == marker,
                    "final_text_length": len(final) if isinstance(final, str) else None,
                    "marker_length": len(marker),
                    "correlated_calls": facts_state.get("correlated_calls"),
                    "unverified_calls": facts_state.get("unverified_calls"),
                    "session": session_facts(tl_structural),
                    "structural": tl_structural,
                    "pass": (rc == 0 and state.get("toolloop_verified") is True
                             and state.get("final_text_source") == "correlated_tool_result"
                             and final == marker),
                })
    except Exception as exc:  # unexpected: report honestly, never crash silent
        global_errors.append(f"unexpected:{type(exc).__name__}")
    finally:
        fake_terminated = terminate_fake(fake_proc, fake_log)

    # Cross-probe session distinctness: fresh opencode runs must differ.
    session_distinct_across_probes = None
    if "text" in gates and "toolloop" in gates:
        a = gates["text"]["session"]["session_value_sha256_8_first"]
        b = gates["toolloop"]["session"]["session_value_sha256_8_first"]
        session_distinct_across_probes = (
            a is not None and b is not None and a != b)

    if not pinned_identity:
        global_errors.append("pinned_identity_override")
    if not fake_terminated:
        global_errors.append("fake_process_not_terminated")
    if "toolloop" in gates:
        tl_stable = gates["toolloop"]["session"]["stable_across_requests"]
        if tl_stable is not True:
            global_errors.append("toolloop_session_not_stable_across_requests")
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

    observed_ua = None
    for g in gates.values():
        reqs = g.get("structural", {}).get("requests", [])
        if reqs and reqs[0].get("user_agent"):
            observed_ua = reqs[0]["user_agent"]
            break

    report = {
        "verifier": "verify_opencode_chat_capture.py",
        "client": {
            "version": CLIENT_VERSION,
            "executable_sha256": got_sha,
            "observed_user_agent": observed_ua,
            "pinned_identity": "pinned" if pinned_identity
                               else "override_unqualified",
        },
        "config_variant": args.config,
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

    print(json.dumps({"all_pass": all_pass, "gates": {k: {kk: vv for kk, vv in v.items()
                              if kk not in ("structural", "session")}
                              for k, v in gates.items()},
                      "errors": global_errors,
                      "report": str(args.report)}, indent=2))
    raise SystemExit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
