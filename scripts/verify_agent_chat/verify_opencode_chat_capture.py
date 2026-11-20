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

Emission: a sanitized structural JSON report (field names/types/counts,
predicate booleans, public hashes). Never prints markers, prompts, tool
arguments/results, raw IDs, or raw bodies.

Stdlib only. Exit 0 only when every enabled probe's gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def die(msg: str) -> None:
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
               title: str, timeout: int, extra_args=()) -> tuple[int, Path, Path]:
    out = run_root / "logs" / f"{title.replace(' ', '_')}.out"
    err = run_root / "logs" / f"{title.replace(' ', '_')}.err"
    cmd = [exe, "--pure", "run", "--dir", str(run_root / "workspace"),
           "--format", "json", "--title", title,
           "--model", f"{PROVIDER}/{MODEL}", *extra_args, prompt]
    with open(out, "wb") as fo, open(err, "wb") as fe:
        proc = subprocess.run(cmd, env=client_env(run_root, config_path),
                              stdout=fo, stderr=fe, timeout=timeout)
    return proc.returncode, out, err


def last_text_event(out_path: Path) -> str | None:
    text = None
    for line in out_path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        part = e.get("part") or {}
        if e.get("type") == "text" and part.get("type") == "text":
            text = part.get("text")
    return text


def structural_facts(run_root: Path) -> dict:
    """Sanitized structural facts from the private journal (never raw bodies)."""
    journal = run_root / "run" / "requests.jsonl"
    requests = []
    for line in journal.read_text(errors="replace").splitlines():
        e = json.loads(line)
        if e["method"] != "POST" or e["path"] != "/v1/chat/completions":
            continue
        b = json.loads(e["body"])
        tools = b.get("tools", [])
        requests.append({
            "top_level_fields": sorted(b.keys()),
            "top_level_field_count": len(b),
            "reasoning_effort": b.get("reasoning_effort"),
            "max_tokens": b.get("max_tokens"),
            "store": b.get("store"),
            "tool_choice": b.get("tool_choice"),
            "stream": b.get("stream"),
            "stream_options": b.get("stream_options"),
            "tool_names": [t.get("function", {}).get("name") for t in tools
                           if isinstance(t, dict) and t.get("type") == "function"],
            "tool_declaration_form": "nested" if tools and isinstance(tools[0], dict)
                and isinstance(tools[0].get("function"), dict) else None,
            "message_roles": [m.get("role") for m in b.get("messages", [])
                              if isinstance(m, dict)],
            "user_agent": e["headers"].get("User-Agent"),
            "session_header_names": sorted(k for k in e["headers"]
                                           if k.lower().startswith("x-session")
                                           or k.lower() == "x-opencode-session-id"),
            "session_headers_equal": len({e["headers"][k] for k in e["headers"]
                                          if k.lower().startswith("x-session")
                                          or k.lower() == "x-opencode-session-id"}) <= 1,
        })
    return {"requests": requests}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--executable", default=PINNED_EXECUTABLE)
    ap.add_argument("--expect-sha256", default=PINNED_EXECUTABLE_SHA256)
    ap.add_argument("--config", choices=["default", "denyweb"], default="denyweb")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--skip-toolloop", action="store_true")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    exe = args.executable
    if not os.path.isfile(exe):
        die(f"executable missing: {exe}")
    got_sha = sha256_file(exe)
    if got_sha != args.expect_sha256:
        die(f"executable sha256 mismatch: {got_sha}")

    run_root = Path(args.run_root)
    build_run_root(run_root)
    port = free_loopback_port()
    config_path = write_config(run_root, port, deny_webfetch=(args.config == "denyweb"))

    fake = Path(__file__).with_name("loopback_chat_fake.py")
    fake_env = dict(os.environ, AGENT_CHAT_FAKE_RUN=str(run_root),
                    AGENT_CHAT_FAKE_WORKSPACE=str(run_root / "workspace"))
    fake_log = open(run_root / "logs" / "fake.log", "wb")
    fake_proc = subprocess.Popen([sys.executable, str(fake), str(port)],
                                 env=fake_env, stdout=fake_log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    gates: dict = {}
    try:
        # text probe
        (run_root / "run" / "scenario.json").write_text(json.dumps(
            {"mode": "text", "final_text": TEXT_SENTINEL}))
        (run_root / "run" / "scenario.json").chmod(0o600)
        rc, out, _ = run_client(exe, run_root, config_path,
                                f"Reply with exactly {TEXT_SENTINEL}. Do not use tools, inspect files, or run commands.",
                                "227 text", args.timeout)
        final = last_text_event(out)
        gates["text"] = {
            "exit_code": rc,
            "final_text_exact": final == TEXT_SENTINEL,
            "pass": rc == 0 and final == TEXT_SENTINEL,
        }
        (run_root / "run" / "requests.jsonl").unlink(missing_ok=True)
        (run_root / "run" / "state.json").unlink(missing_ok=True)

        if not args.skip_toolloop:
            marker = f"SLAIF227-MARK-{secrets.token_hex(16)}"
            write_private(run_root / "workspace" / "probe.txt", marker.encode())
            write_private(run_root / "run" / "expected_marker.bin", marker.encode())
            (run_root / "run" / "scenario.json").write_text(json.dumps(
                {"mode": "toolloop", "tool_file": "probe.txt"}))
            (run_root / "run" / "scenario.json").chmod(0o600)
            rc, out, _ = run_client(exe, run_root, config_path,
                                    "Read the file probe.txt in the workspace using the read tool, then reply with the exact marker text from that file.",
                                    "227 toolloop", args.timeout)
            final = last_text_event(out)
            state = json.loads((run_root / "run" / "state.json").read_text())
            gates["toolloop"] = {
                "exit_code": rc,
                "toolloop_verified": state.get("toolloop_verified") is True,
                "final_text_source": state.get("final_text_source"),
                "final_text_equals_marker": final == marker,
                "final_text_length": len(final) if isinstance(final, str) else None,
                "marker_length": len(marker),
                "correlated_calls": state.get("toolloop_facts", {}).get("correlated_calls"),
                "unverified_calls": state.get("toolloop_facts", {}).get("unverified_calls"),
                "pass": (rc == 0 and state.get("toolloop_verified") is True
                         and state.get("final_text_source") == "correlated_tool_result"
                         and final == marker),
            }
    finally:
        # cleanup: owned fake process only (new session => kill its group)
        try:
            os.killpg(os.getpgid(fake_proc.pid), signal.SIGTERM)
            fake_proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(fake_proc.pid), signal.SIGKILL)
            except Exception:
                pass
        fake_log.close()

    facts = structural_facts(run_root)
    report = {
        "verifier": "verify_opencode_chat_capture.py",
        "client": {
            "version": CLIENT_VERSION,
            "executable_sha256": got_sha,
            "observed_user_agent": (facts["requests"][0]["user_agent"]
                                    if facts["requests"] else None),
        },
        "config_variant": args.config,
        "gates": gates,
        "structural": facts,
        "privacy": {"raw_content_retained": False, "provider_call_performed": False,
                    "user_profile_touched": False},
        "all_pass": all(g.get("pass") is True for g in gates.values()) and bool(gates),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_private(Path(args.report), (json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps({"all_pass": report["all_pass"], "gates": gates,
                      "report": str(args.report)}, indent=2))
    raise SystemExit(0 if report["all_pass"] else 1)


if __name__ == "__main__":
    main()
