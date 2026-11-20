"""Actual-client Hermes Chat capture/verification against the loopback fake.

Narrowly named Hermes verifier for OAP 227. Runs the task-owned Hermes
launcher (private HOME/HERMES_HOME/XDG, task venv python, synthetic bearer in
the private config) against the shared loopback_chat_fake.py in a fully
task-owned, isolated run root under the caller's task root. Only 127.0.0.1
traffic; no real provider, no user profile, no real key, no provider call.

Task-private environment requirement: this runner assumes a task-owned Hermes
environment (source tree, closure venv, launcher, private homes) supplied
through the CLI arguments. Each run gets a FRESH per-run HERMES_HOME inside
the run root, seeded only from the prepared config plus the public
dependency installs (the two known facts.json install paths are relocated to
the run home); the prepared seed home, source tree, and runtime assets are
treated as read-only. No snapshot or restore machinery exists.

Scenarios:
  text      ordinary single-turn streaming text, gated on the structured
            terminal result (type=result, exit_code 0, exact expected text)
  stall     synthetic upstream stall gated on the verified effective
            provider request timeout (closure-venv gate) plus a finite
            outer watchdog; distinguishes native SDK/provider timeout
            evidence from outer-watchdog cancellation in the outcome
  error     synthetic upstream HTTP error (default 500) observation
  toolloop  N read_file tool calls (default 2) with exact unpredictable
            per-call marker correlation, optional reasoning replay, final
            echo gated on the structured terminal result carrying the exact
            correlated tool result, with reasoning replay gated on the
            assistant replay fields in the request journal; this scenario
            never qualifies under outer-watchdog cancellation

Gates and honesty rules (mirror verify_opencode_chat_capture.py plus the
reviewed 227-a Hermes probe properties):
  - umask 077; run root 0700; every written file 0600.
  - The fake must pass a bounded TCP readiness wait (port open AND process
    alive) before the CLI starts.
  - The outer watchdog is a finite deadline; on expiry the owned CLI group
    is killed and the outcome is 'outer_watchdog_cancel' - never conflated
    with a native SDK/provider timeout.
  - Native-timeout qualification requires a strong current-run event line
    (sdk_timeout_exception or provider_unavailable_timeout) in run-appended
    home-log bytes only; a generic 'timed out' phrase is diagnostic only.
  - Monitored peer loss disqualifies the run (setup_failure_peer_lost).
  - Owned-runtime cleanup is identity-verified: the gateway pidfile is a
    JSON record and is signalled only when pid + start_time ticks +
    exact-NUL HERMES_HOME env entry + gateway argv tokens all match.
  - Current-run log evidence is read only from bytes APPENDED after native
    launch (per-file offsets captured before launch); the fresh per-run home
    has no pre-run state to restore, so cleanup is deletion of the whole run
    root plus verification that no owned processes or ports remain.
  - The private run root is deleted by default after the sanitized receipt
    is written; --keep-run-root retains it and the receipt labels the mode.
    A report path inside the run root is rejected under default cleanup.
  - The receipt never embeds raw markers, prompts, reasoning strings, log
    lines, or request bodies: secrets appear only as length + short SHA-256
    prefix plus presence booleans.

Stdlib only. Exit 0 only when the scenario gate passes AND cleanup is
verified.
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

TEXT_SENTINEL = "AGENT_CHAT_TEXT_OK"
ERROR_MESSAGE_TOKEN = "SYN-UP-FAIL-227"
FAKE_READY_TIMEOUT_S = 15.0
LOG_EVIDENCE_CAP = 4_000_000
HOME_BACKUP_MAX_BYTES = 1_000_000
HOME_SKIP_TOP_DIRS = ("installs",)
EVENT_PATTERNS = {
    "sdk_timeout_exception": re.compile(
        r"APITimeoutError|httpx\.\w*Timeout|ReadTimeout|ConnectTimeout"),
    "timed_out_phrase": re.compile(r"timed out", re.I),
    "provider_unavailable_timeout": re.compile(r"unavailable \(timeout\)", re.I),
    "error_500": re.compile(r"Error code: 500|SYN-UP-FAIL-227"),
}
STRONG_TIMEOUT_NAMES = ("sdk_timeout_exception", "provider_unavailable_timeout")
CLI_ENV_STRIP = ("PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "OPENAI_BASE_URL")


def die(msg: str) -> None:
    """Preflight failure before any run evidence exists (safe fixed text)."""
    print(f"FAIL {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def secret_ref(value: str) -> dict:
    """Receipt-safe reference to a secret string (never the string itself)."""
    enc = value.encode("utf-8")
    return {"length": len(enc), "sha256_12": sha256_bytes(enc)[:12]}


def write_private(path: str, data) -> None:
    if isinstance(data, str):
        data = data.encode("utf-8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def openlog(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    return os.fdopen(fd, "wb")


def free_loopback_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def proc_alive(pid) -> bool:
    return pid is not None and os.path.exists("/proc/%d" % pid)


def proc_environ_has(pid: int, keyval: str) -> bool:
    try:
        with open("/proc/%d/environ" % pid, "rb") as f:
            return keyval.encode() in f.read().split(b"\x00")
    except Exception:
        return False


def proc_start_ticks(pid: int):
    try:
        st = open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()
        return int(st[19])
    except Exception:
        return None


def killpg(proc) -> bool:
    """Deterministically terminate one owned process group (TERM then KILL)."""
    if proc.poll() is not None:
        return True
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return proc.poll() is not None
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    d = time.monotonic() + 5
    while time.monotonic() < d and proc.poll() is None:
        time.sleep(0.2)
    if proc.poll() is None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        d = time.monotonic() + 5
        while time.monotonic() < d and proc.poll() is None:
            time.sleep(0.2)
    return proc.poll() is not None


# ---------------------------------------------------------------------------
# Fresh per-run HERMES_HOME seeding (prepared template stays read-only)
# ---------------------------------------------------------------------------


class SetupFailure(Exception):
    """Setup failure after the run root exists; carries an honest outcome."""


def install_key(src: str) -> str:
    """Installer key for the shared read-only source path (sha256[:16])."""
    return hashlib.sha256(os.path.realpath(src).encode("utf-8")).hexdigest()[:16]


_SEED_URL_RE = re.compile(r"http://127\.0\.0\.1:(\d+)/v1")


def seed_run_home(seed_home: str, run_home: str, src: str, new_url: str) -> dict:
    """Seed a fresh run HERMES_HOME from the prepared template (read-only).

    Copies only the prepared config.yaml and the public dependency install
    tree (symlinks preserved; they point at the shared read-only runtime).
    Relocates the two known facts.json path fields
    (packages.venv.environment / .resolved_lock) from the seed-home prefix
    to the run-home prefix. No snapshot, no restore, no installer.
    """
    key = install_key(src)
    seed_cfg = os.path.join(seed_home, "config.yaml")
    with open(seed_cfg, "r", encoding="utf-8") as f:
        cfg_text = f.read()
    m = _SEED_URL_RE.search(cfg_text)
    if m is None:
        raise SetupFailure("seed config: loopback base_url pattern not found")
    old_url = "http://127.0.0.1:%s/v1" % m.group(1)
    if cfg_text.count(old_url) != 1:
        raise SetupFailure("seed config: loopback base_url not unique")
    new_cfg = cfg_text.replace(old_url, new_url)
    cfg_path = os.path.join(run_home, "config.yaml")
    write_private(cfg_path, new_cfg)
    with open(cfg_path, "r", encoding="utf-8") as f:
        if f.read() != new_cfg:
            raise SetupFailure("seed config: write-back verification failed")

    seed_inst = os.path.join(seed_home, "installs", key)
    run_inst = os.path.join(run_home, "installs", key)
    if not os.path.isfile(os.path.join(seed_inst, "facts.json")):
        raise SetupFailure("seed install: facts.json missing")
    shutil.copytree(seed_inst, run_inst, symlinks=True,
                    ignore_dangling_symlinks=True)

    facts_path = os.path.join(run_inst, "facts.json")
    with open(facts_path, "r", encoding="utf-8") as f:
        facts = json.load(f)
    venv = facts.get("packages", {}).get("venv", {})
    for field in ("environment", "resolved_lock"):
        val = venv.get(field)
        if not isinstance(val, str) or not val.startswith(seed_home + "/"):
            raise SetupFailure("facts.json: venv.%s missing or prefix mismatch"
                               % field)
        venv[field] = run_home + val[len(seed_home):]

    def _assert_no_seed_prefix(obj, where=""):
        if isinstance(obj, str):
            if seed_home in obj:
                raise SetupFailure(
                    "facts.json: stale seed-home path at %s" % where)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _assert_no_seed_prefix(v, where + "." + str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _assert_no_seed_prefix(v, "%s[%d]" % (where, i))

    _assert_no_seed_prefix(facts)
    write_private(facts_path, json.dumps(facts, indent=2, sort_keys=True) + "\n")
    return {
        "install_key": key,
        "base_url_relocated": True,
        "facts_environment_relocated": True,
        "facts_resolved_lock_relocated": True,
        "venv_environment": venv["environment"],
    }


# ---------------------------------------------------------------------------
# Effective provider request-timeout gate (closure venv, run-home config)
# ---------------------------------------------------------------------------

GATE_SCRIPT = r'''
import json, os, sys
home = %(home)r
src = %(src)r
named = %(named)r
model = %(model)r
timeout = %(timeout)r
os.environ["HERMES_HOME"] = home
os.environ.pop("PYTHONHOME", None)
sys._hermes_pin_default_home = True
sys.path.insert(0, src)
import hermes_bootstrap  # noqa: F401
from ruamel.yaml import YAML
y = YAML()
y.preserve_quotes = True
cfg = os.path.join(home, "config.yaml")
with open(cfg) as f:
    data = y.load(f)
prov = data.setdefault("providers", {})
c = prov.setdefault("custom", {})
if isinstance(c, dict):
    c["request_timeout_seconds"] = timeout
n = prov.setdefault(named, {})
if isinstance(n, dict):
    n["request_timeout_seconds"] = timeout
with open(cfg, "w") as f:
    y.dump(data, f)
from hermes_cli import timeouts
print(json.dumps({
    "custom": timeouts.get_provider_request_timeout("custom", model),
    "named": timeouts.get_provider_request_timeout(named, model),
    "named_base_url": (n.get("base_url") if isinstance(n, dict) else None),
}))
'''


def run_timeout_gate(closure_py: str, run_home: str, src: str, named: str,
                     model: str, timeout: float, new_url: str) -> dict:
    """Verify the effective provider request timeout through the real
    hermes_cli.timeouts module using the full run-home dependency closure."""
    script = GATE_SCRIPT % {"home": run_home, "src": src, "named": named,
                            "model": model, "timeout": timeout}
    gate = {"closure_venv": closure_py, "ok": False,
            "requested_timeout_seconds": timeout}
    try:
        r = subprocess.run([closure_py, "-c", script],
                           env={**os.environ, "PYTHONPATH": src},
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            gate["verified"] = out
            gate["named_base_url_match"] = (out.get("named_base_url") == new_url)
            gate["ok"] = (out.get("custom") == timeout
                          and out.get("named") == timeout
                          and gate["named_base_url_match"])
        else:
            gate["error"] = "gate_exit_%d" % r.returncode
            gate["error_tail_len"] = len(r.stderr)
    except Exception as e:
        gate["error"] = type(e).__name__
    return gate


# ---------------------------------------------------------------------------
# Scenario fixtures and prompts (no marker ever appears in a prompt)
# ---------------------------------------------------------------------------


def build_fixtures(mode: str, args, ws: str, run_dir: str):
    """Write run/scenario.json and workspace probe files.

    Returns (scenario, markers, reasoning_marker_or_None).
    """
    markers = []
    reasoning = None
    if mode == "text":
        scenario = {"mode": "text", "final_text": TEXT_SENTINEL}
    elif mode == "stall":
        scenario = {"mode": "text", "stall": True}
    elif mode == "error":
        scenario = {"mode": "text", "error_status": args.error_status,
                    "error_message": "%s synthetic upstream failure"
                                     % ERROR_MESSAGE_TOKEN}
    elif mode == "toolloop":
        files = []
        for i in range(args.tool_calls):
            marker = ("SLAIF227-HERMES-MARK" + (str(i) if i else "") + "-"
                      + secrets.token_hex(4))
            markers.append(marker)
            fn = "probe%d.txt" % (i + 1)
            write_private(os.path.join(ws, fn), marker)
            write_private(os.path.join(run_dir, "expected_marker_%d.bin" % i),
                          marker)
            files.append(fn)
        scenario = {"mode": "toolloop", "tool_files": files,
                    "tool_name": "read_file", "arg_key": "path",
                    "tool_turn_at": 1, "tool_usage": [56000, 200],
                    "aux_final_text": "{\"title\": \"Synthetic Multi Read\"}"}
        if args.reasoning_replay:
            reasoning = "SYN-REASONING-227-" + secrets.token_hex(4)
            scenario["first_reasoning_content"] = reasoning
    else:
        raise SetupFailure("unknown scenario mode: %s" % mode)
    write_private(os.path.join(run_dir, "scenario.json"),
                  json.dumps(scenario) + "\n")
    return scenario, markers, reasoning


def build_prompt(mode: str, scenario: dict) -> str:
    if mode == "text":
        return ("Reply with exactly %s. Do not use tools, inspect files, "
                "or run commands." % TEXT_SENTINEL)
    if mode in ("stall", "error"):
        return ("SYNTHETIC 227 loopback probe. Reply with the single word OK. "
                "Do not use tools. No external calls.")
    files = ", ".join(scenario["tool_files"])
    return ("SYNTHETIC 227 multi-read loopback probe. Use the file tool to "
            "read %s in the working directory (issue all %d reads). Then "
            "reply with the exact full contents of the first file you read. "
            "Do not use the terminal or any other tool."
            % (files, len(scenario["tool_files"])))


# ---------------------------------------------------------------------------
# Peer fake + native CLI launch (both Popen handles retained in one wrapper)
# ---------------------------------------------------------------------------

FAKE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "loopback_chat_fake.py")


def start_fake(vpy: str, port: int, run_root: str, logs_dir: str,
               task_root: str) -> subprocess.Popen:
    fake_log = openlog(os.path.join(logs_dir, "fake.log"))
    return subprocess.Popen([vpy, FAKE_PATH, str(port)],
                            env={**os.environ,
                                 "AGENT_CHAT_FAKE_RUN": run_root},
                            cwd=task_root, stdout=fake_log,
                            stderr=subprocess.STDOUT, start_new_session=True)


def wait_fake_ready(fake: subprocess.Popen, port: int) -> tuple:
    """Bounded readiness: port open AND owned fake still alive."""
    t0 = time.monotonic()
    d = t0 + FAKE_READY_TIMEOUT_S
    while time.monotonic() < d:
        if port_open(port) and fake.poll() is None:
            return True, round(time.monotonic() - t0, 2)
        if fake.poll() is not None:
            break
        time.sleep(0.2)
    return False, round(time.monotonic() - t0, 2)


def start_cli(vpy: str, launcher: str, prompt: str, ws: str, run_root: str,
              run_home: str, logs_dir: str) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if k not in CLI_ENV_STRIP}
    home_dir = os.path.join(run_root, "home")
    env.update(HOME=home_dir, HERMES_HOME=run_home,
               XDG_CONFIG_HOME=os.path.join(home_dir, ".config"),
               XDG_CACHE_HOME=os.path.join(home_dir, ".cache"),
               XDG_DATA_HOME=os.path.join(home_dir, ".local/state"),
               XDG_STATE_HOME=os.path.join(home_dir, ".local/state"))
    cli_log = openlog(os.path.join(logs_dir, "cli.log"))
    return subprocess.Popen([vpy, launcher, "chat", "--oneshot",
                             "--format", "stream-json", "--in", ws,
                             "--max-turns", "3", "-q", prompt],
                            env=env, cwd=ws, stdout=cli_log,
                            stderr=subprocess.STDOUT, start_new_session=True)


def run_watchdog(cli: subprocess.Popen, fake: subprocess.Popen,
                 watchdog_s: float) -> tuple:
    """Finite outer watchdog. Returns (outer_cancel, peer_died_during_cli)."""
    outer_cancel = False
    peer_died = False
    deadline = time.monotonic() + watchdog_s
    while True:
        if cli.poll() is not None:
            d2 = time.monotonic() + 5
            while time.monotonic() < d2 and fake.poll() is None:
                time.sleep(0.2)
            break
        if fake.poll() is not None:
            peer_died = True
        if time.monotonic() > deadline:
            outer_cancel = True
            killpg(cli)
            break
        time.sleep(0.5)
    return outer_cancel, peer_died


def capture_home_log_offsets(run_home: str) -> dict:
    """Per-file byte offsets of run-home logs BEFORE the native launch."""
    offsets = {}
    logs_dir = os.path.join(run_home, "logs")
    if os.path.isdir(logs_dir):
        for fn in sorted(os.listdir(logs_dir)):
            p = os.path.join(logs_dir, fn)
            if os.path.isfile(p):
                offsets["logs/" + fn] = os.path.getsize(p)
    return offsets


# ---------------------------------------------------------------------------
# Owned-runtime cleanup (identity-verified; receipt-safe booleans only)
# ---------------------------------------------------------------------------


def cleanup_gateway(run_home: str) -> dict:
    """Signal the run-home gateway only after JSON pidfile identity matches.

    Identity = pid + start_time ticks + exact-NUL HERMES_HOME env entry +
    gateway argv tokens present in cmdline. The receipt records match
    booleans and state labels only (never the raw cmdline).
    """
    pidfile = os.path.join(run_home, "gateway.pid")
    gw = {"pidfile": pidfile, "observed": None, "killed": False,
          "absent_after": None, "iterations": 0}
    pid = None
    for _ in range(2):
        gw["iterations"] += 1
        rec = None
        try:
            with open(pidfile) as f:
                rec = json.load(f)
        except Exception:
            rec = None
        pid = rec.get("pid") if isinstance(rec, dict) else None
        if not proc_alive(pid):
            gw["observed"] = "already_absent" if pid else "no_record"
            gw["absent_after"] = True
            break
        smatch = proc_start_ticks(pid) == rec.get("start_time")
        hmatch = proc_environ_has(pid, "HERMES_HOME=%s" % run_home)
        amatch = False
        try:
            cmd = (open("/proc/%d/cmdline" % pid, "rb").read()
                   .decode("utf-8", "replace"))
            amatch = ("gateway" in cmd and all(
                tok in cmd for tok in (rec.get("argv") or [])
                if " " not in tok and tok != "run"
                and not tok.startswith("/")))
        except Exception:
            pass
        gw["observed"] = {"pid": pid, "start_time_match": smatch,
                          "hermes_home_match": hmatch,
                          "argv_tokens_match": amatch}
        if smatch and hmatch and amatch:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            d = time.monotonic() + 5
            while time.monotonic() < d and proc_alive(pid):
                time.sleep(0.2)
            if proc_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                d = time.monotonic() + 5
                while time.monotonic() < d and proc_alive(pid):
                    time.sleep(0.2)
            gw["killed"] = True
        if not proc_alive(pid):
            gw["absent_after"] = True
            break
        time.sleep(1)
    if gw["absent_after"] is None:
        gw["absent_after"] = not proc_alive(pid)
    return gw


def stray_home_processes(run_home: str) -> list:
    """Live PIDs whose environ contains exactly our private HERMES_HOME."""
    out = []
    for e in os.listdir("/proc"):
        if e.isdigit() and proc_environ_has(int(e), "HERMES_HOME=%s" % run_home):
            out.append(int(e))
    return sorted(out)


# ---------------------------------------------------------------------------
# Sanitized evidence facts (structural only; no raw content in the receipt)
# ---------------------------------------------------------------------------


def read_journal(run_dir: str) -> tuple:
    """Returns (journal_facts, first_request_user_messages)."""
    posts = gets = 0
    models = set()
    first_user = None
    try:
        with open(os.path.join(run_dir, "requests.jsonl")) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                m, p = e.get("method"), e.get("path")
                if m == "POST" and p == "/v1/chat/completions":
                    posts += 1
                    try:
                        b = json.loads(e.get("body") or "{}")
                    except Exception:
                        b = {}
                    if isinstance(b.get("model"), str):
                        models.add(b["model"])
                    if first_user is None:
                        first_user = b.get("messages")
                elif m == "GET" and p == "/v1/models":
                    gets += 1
    except FileNotFoundError:
        pass
    return ({"chat_completions_posts": posts, "models_gets": gets,
             "post_models": sorted(models)}, first_user)


def prompt_clean_fact(first_user, secret_strings) -> dict:
    """Generated secrets (markers/reasoning) must be absent from the
    first-request user messages. Counts user messages checked only."""
    checked = 0
    clean = True

    def scan(v):
        nonlocal clean
        if isinstance(v, str):
            for s in secret_strings:
                if s and s in v:
                    clean = False
        elif isinstance(v, dict):
            for x in v.values():
                scan(x)
        elif isinstance(v, list):
            for x in v:
                scan(x)

    if isinstance(first_user, list):
        for msg in first_user:
            if isinstance(msg, dict) and msg.get("role") == "user":
                checked += 1
                scan(msg.get("content"))
    return {"prompt_clean": clean, "prompt_user_messages_checked": checked}


def peer_state_fact(run_dir: str, n_calls: int):
    try:
        with open(os.path.join(run_dir, "state.json")) as f:
            st = json.load(f)
    except Exception:
        return None
    per_call = st.get("toolloop_facts", {}).get("per_call") or []
    facts = st.get("toolloop_facts", {})
    return {
        "toolloop_verified": st.get("toolloop_verified") is True,
        "final_text_source": st.get("final_text_source"),
        "calls_issued": facts.get("calls_issued"),
        "correlated_calls": facts.get("correlated_calls"),
        "all_calls_correlated_with_marker": (
            len(per_call) == n_calls and all(
                c.get("correlated_tool_message") and c.get("marker_present")
                for c in per_call)),
        "title_requests": st.get("title_requests"),
        "summary_issued": st.get("summary_issued"),
    }


def cli_log_facts(cli_log_path: str, mode: str, markers: list,
                  reasoning) -> dict:
    """Structured CLI stream-json facts.

    Only a terminal {"type":"result","exit_code":0,"text":<expected>} event
    whose text EXACTLY equals the expected value (TEXT_SENTINEL for text,
    markers[0] for toolloop) qualifies a successful run. Marker/sentinel
    occurrences anywhere else (tool results, banners, echoed prompts) are
    recorded as diagnostics and never gate qualification."""
    try:
        with open(cli_log_path, "rb") as f:
            data = f.read(8 << 20).decode("utf-8", "replace")
    except FileNotFoundError:
        return {"present": False}
    out = {"present": True, "log_bytes": len(data),
           "stream_json_lines": 0, "terminal_result_present": False,
           "terminal_exit_code": None, "terminal_text_exact": False}
    expected = None
    if mode == "text":
        expected = TEXT_SENTINEL
    elif mode == "toolloop" and markers:
        expected = markers[0]
    for ln in data.splitlines():
        s = ln.strip()
        if not s.startswith("{"):
            continue
        try:
            e = json.loads(s)
        except Exception:
            continue
        if not isinstance(e, dict):
            continue
        out["stream_json_lines"] += 1
        if e.get("type") == "result":
            out["terminal_result_present"] = True
            ec = e.get("exit_code")
            out["terminal_exit_code"] = ec if type(ec) is int else None
            t = e.get("text")
            out["terminal_text_exact"] = bool(expected) \
                and isinstance(t, str) and t == expected
    # Diagnostic presence facts only (never gate qualification on these).
    out["sentinel_present"] = TEXT_SENTINEL in data
    out["marker_anywhere_in_log"] = bool(markers) \
        and any(m in data for m in markers)
    out["reasoning_marker_present"] = bool(reasoning) and reasoning in data
    return out


def reasoning_replay_fact(run_dir: str, reasoning) -> dict:
    """Gate reasoning replay on the actual assistant replay fields in the
    request journal, not on CLI-log presence.

    From the 2nd Chat POST onward, an assistant message must carry the exact
    synthetic reasoning value in 'reasoning' or 'reasoning_content'. The
    first request never counts (nothing has been replayed yet)."""
    replayed = False
    checked = 0
    if reasoning:
        try:
            with open(os.path.join(run_dir, "requests.jsonl")) as f:
                idx = 0
                for line in f:
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("method") != "POST" or \
                            e.get("path") != "/v1/chat/completions":
                        continue
                    idx += 1
                    if idx == 1:
                        continue
                    checked += 1
                    try:
                        b = json.loads(e.get("body") or "{}")
                    except Exception:
                        continue
                    for msg in b.get("messages") or []:
                        if not isinstance(msg, dict) \
                                or msg.get("role") != "assistant":
                            continue
                        if msg.get("reasoning") == reasoning or \
                                msg.get("reasoning_content") == reasoning:
                            replayed = True
        except FileNotFoundError:
            pass
    return {"reasoning_requested": bool(reasoning),
            "replayed_in_journal": replayed,
            "requests_checked": checked}


def current_run_log_evidence(run_home: str, offsets: dict) -> dict:
    """Event-line counts from bytes APPENDED to run-home logs after launch.

    Enumerates the CURRENT log files (a fresh per-run home starts with no
    logs, so newly created files must be discovered here); each file is read
    from its pre-launch byte offset (0 for files that did not exist yet).
    The byte count uses the raw read length before decoding."""
    ev = {}
    logs_dir = os.path.join(run_home, "logs")
    try:
        names = sorted(os.listdir(logs_dir))
    except OSError:
        return ev
    for fn in names:
        p = os.path.join(logs_dir, fn)
        if not os.path.isfile(p):
            continue
        off = offsets.get("logs/" + fn, 0)
        try:
            with open(p, "rb") as f:
                f.seek(off)
                raw = f.read(LOG_EVIDENCE_CAP)
        except Exception:
            continue
        appended_bytes = len(raw)
        data = raw.decode("utf-8", "replace")
        hit = {name: sum(1 for ln in data.splitlines() if rx.search(ln))
               for name, rx in EVENT_PATTERNS.items()}
        if any(hit.values()) or appended_bytes:
            ev[fn] = {"appended_bytes": appended_bytes,
                                         "event_lines": hit}
    return ev


def strong_timeout_event(ev: dict) -> bool:
    return any(h["event_lines"].get("sdk_timeout_exception", 0) > 0
               or h["event_lines"].get("provider_unavailable_timeout", 0) > 0
               for h in ev.values())


def error_500_event(ev: dict) -> bool:
    return any(h["event_lines"].get("error_500", 0) > 0
               for h in ev.values())


# ---------------------------------------------------------------------------
# Outcome classification, qualification, and receipt finalization
# ---------------------------------------------------------------------------


def classify_outcome(posts: int, peer_died: bool, outer_cancel: bool,
                     cli_rc, strong_timeout: bool, err500: bool,
                     error_status: int) -> str:
    if posts == 0:
        return "setup_failure_no_post"
    if peer_died:
        return "setup_failure_peer_lost"
    if outer_cancel:
        return "outer_watchdog_cancel"
    if cli_rc == 0:
        return "native_exit_zero"
    if strong_timeout:
        return "native_provider_timeout_observed"
    if error_status and err500:
        return "native_error_500_observed"
    return "native_nonzero_unclassified"


def _terminal_gate(cli: dict) -> bool:
    """Successful runs require a structured terminal result: present,
    exit_code 0, and text exactly equal to the scenario expected value."""
    return (cli.get("terminal_result_present") is True
            and cli.get("terminal_exit_code") == 0
            and cli.get("terminal_text_exact") is True)


def qualified_for(mode: str, cleanup_verified: bool, posts: int,
                  peer_died: bool, outcome: str, err500: bool,
                  cli: dict, clean: bool, peer: dict,
                  replay: dict) -> bool:
    if not (cleanup_verified and clean):
        return False
    if mode == "text":
        return (posts >= 1 and outcome == "native_exit_zero"
                and _terminal_gate(cli))
    if mode == "stall":
        return (posts > 0 and not peer_died
                and outcome in ("native_provider_timeout_observed",
                                "outer_watchdog_cancel"))
    if mode == "error":
        return (posts > 0 and not peer_died and err500
                and outcome in ("native_error_500_observed",
                                "outer_watchdog_cancel"))
    if mode == "toolloop":
        if outcome != "native_exit_zero":
            return False
        return (posts >= 2 and peer is not None
                and peer["toolloop_verified"]
                and peer["all_calls_correlated_with_marker"]
                and peer["final_text_source"] == "correlated_tool_result"
                and _terminal_gate(cli)
                and (not replay["reasoning_requested"]
                     or replay["replayed_in_journal"]))
    return False


def finish(result: dict, run_root: str, report: str, scenario_qualified: bool,
           cleanup: dict, outcome: str, keep: bool) -> None:
    """Finalize the receipt in a safe order.

    Core owned-runtime cleanup is verified FIRST. The private run root is
    never deleted while any core cleanup fact is unverified (it is retained
    with an explicit reason instead). Only after the core-cleanup decision
    is default deletion attempted; removal success/failure then feeds
    final_cleanup_verified, and final qualified is the scenario gate AND
    final cleanup verification."""
    result.update(outcome=outcome, cleanup=cleanup,
                  finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()))
    core = (cleanup.get("cli_stopped") is True
            and cleanup.get("fake_terminated") is True
            and cleanup.get("port_closed") is True
            and cleanup.get("owned_runtime_absent") is True)
    if not keep:
        if not core:
            # Never delete HOME while owned runtime cleanup is unverified;
            # retain the private root for inspection instead.
            cleanup["run_root_retained"] = True
            cleanup["run_root_retained_reason"] = "core_cleanup_unverified"
            result.setdefault("errors", []).append(
                "run_root_retained_core_cleanup_unverified")
            run_root_removed = None
        else:
            try:
                shutil.rmtree(run_root)
                cleanup["run_root_removed"] = True
                run_root_removed = True
            except OSError as e:
                cleanup["run_root_removed"] = False
                cleanup["run_root_retained"] = True
                cleanup["run_root_retained_reason"] = "remove_failed"
                result.setdefault("errors", []).append(
                    "run_root_remove_failed:%s" % type(e).__name__)
                run_root_removed = False
    else:
        cleanup["run_root_retained"] = True
        cleanup["run_root_retained_reason"] = "keep_run_root_requested"
        run_root_removed = None
    final_cleanup_verified = core and (keep or run_root_removed is True)
    qualified = scenario_qualified and final_cleanup_verified
    result.update(qualified=qualified, cleanup_verified=final_cleanup_verified)
    if os.path.isdir(run_root):
        # Retained root: persist the run receipt inside the retained root.
        write_private(os.path.join(run_root, "result.json"),
                      json.dumps(result, indent=2))
    write_private(report, json.dumps(result, indent=2))
    print(json.dumps({"run": result.get("run"), "outcome": outcome,
                      "qualified": qualified,
                      "cleanup_verified": final_cleanup_verified,
                      "report": report}, sort_keys=True))
    raise SystemExit(0 if (qualified and final_cleanup_verified) else 1)


# ---------------------------------------------------------------------------
# Command-line driver
# ---------------------------------------------------------------------------


def _reap(proc: subprocess.Popen, limit: float = 6.0) -> bool:
    """Wait briefly for a killed owned process to be reaped. True if dead."""
    if proc.poll() is not None:
        return True
    d = time.monotonic() + limit
    while time.monotonic() < d and proc.poll() is None:
        time.sleep(0.2)
    return proc.poll() is not None


def main() -> None:
    ap = argparse.ArgumentParser(
        description="OAP 227-a Hermes loopback capture verifier")
    ap.add_argument("--task-root", required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--home-seed", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--launcher", required=True)
    ap.add_argument("--venv-python", required=True)
    ap.add_argument("--scenario", required=True,
                    choices=("text", "stall", "error", "toolloop"))
    ap.add_argument("--watchdog", type=float, default=240.0)
    ap.add_argument("--prefer-port", type=int, default=0)
    ap.add_argument("--tool-calls", type=int, default=2)
    ap.add_argument("--reasoning-replay", action="store_true")
    ap.add_argument("--error-status", type=int, default=500)
    ap.add_argument("--timeout-seconds", type=float, default=3.0)
    ap.add_argument("--timeout-model", default="qwen38-27b")
    ap.add_argument("--named-provider", default="slaif227fake")
    ap.add_argument("--closure-python", default="")
    ap.add_argument("--keep-run-root", action="store_true")
    args = ap.parse_args()

    os.umask(0o077)
    task_root = os.path.realpath(args.task_root)
    seed_home = os.path.realpath(args.home_seed)
    src = os.path.realpath(args.src)
    launcher = os.path.realpath(args.launcher)
    vpy = os.path.realpath(args.venv_python)
    report = os.path.realpath(args.report)
    keep = args.keep_run_root
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.run_name):
        die("bad_run_name")
    run_root = os.path.join(task_root, "runs", args.run_name)
    if os.path.exists(run_root):
        die("run_root_exists")
    if not keep and report.startswith(run_root + os.sep):
        die("report_inside_run_root")

    key = install_key(src)
    for label, p in (("launcher", launcher), ("venv_python", vpy),
                     ("seed_config", os.path.join(seed_home, "config.yaml")),
                     ("seed_installs", os.path.join(seed_home, "installs")),
                     ("src", src)):
        if not os.path.exists(p):
            die("missing_%s" % label)
    if not os.path.isdir(os.path.join(seed_home, "installs", key)):
        die("missing_seed_install")
    if args.closure_python and not os.path.isfile(
            os.path.realpath(args.closure_python)):
        die("missing_closure_python")
    try:
        rv = subprocess.run([vpy, "-c", "import sys; print(sys.version)"],
                            capture_output=True, text=True, timeout=30)
        pyver = (rv.stdout.strip().splitlines()[0]
                 if rv.returncode == 0 and rv.stdout else "")
    except Exception:
        pyver = ""
    if not pyver:
        die("venv_python_preflight_failed")

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = {
        "runner": os.path.basename(os.path.abspath(__file__)),
        "oap": "227-a",
        "run": args.run_name,
        "scenario_mode": args.scenario,
        "started_utc": started,
        "source": {"src": src, "install_key": key,
                   "python_version": pyver},
        "watchdog_s": args.watchdog,
        "errors": [],
    }

    run_home = os.path.join(run_root, "hermes-home")
    run_dir = os.path.join(run_root, "run")
    logs_dir = os.path.join(run_root, "logs")
    ws = os.path.join(run_root, "workspace")
    home_dir = os.path.join(run_root, "home")
    for d in (run_root, run_home, run_dir, logs_dir, ws, home_dir):
        os.makedirs(d, mode=0o700, exist_ok=True)
        os.chmod(d, 0o700)

    def early_finish(cleanup: dict, outcome: str) -> None:
        finish(result, run_root, report, False, cleanup, outcome, keep)

    port = (args.prefer_port
            if (args.prefer_port and not port_open(args.prefer_port))
            else free_loopback_port())
    new_url = "http://127.0.0.1:%d/v1" % port
    result["port"] = port
    result["preflight"] = {
        "preferred_port": args.prefer_port or None,
        "port_allocated": port,
        "port_free_before_fake": not port_open(port),
    }

    try:
        seed_facts = seed_run_home(seed_home, run_home, src, new_url)
    except (SetupFailure, OSError) as e:
        result["seed"] = {"ok": False, "error": type(e).__name__}
        result["errors"].append("seed_failed:%s" % type(e).__name__)
        early_finish({"cli_stopped": False, "fake_terminated": False,
                      "port_closed": not port_open(port),
                      "owned_runtime_absent": False},
                     "setup_failure_seed")
    result["seed"] = {"ok": True, **seed_facts}

    if args.scenario == "stall":
        closure_py = (args.closure_python
                      or seed_facts["venv_environment"] + "/bin/python")
        if not os.path.isfile(closure_py):
            gate = {"closure_venv": closure_py, "ok": False,
                    "error": "closure_venv_missing"}
        else:
            gate = run_timeout_gate(closure_py, run_home, src,
                                    args.named_provider, args.timeout_model,
                                    args.timeout_seconds, new_url)
        result["timeout_gate"] = gate
        if not gate.get("ok"):
            result["errors"].append("timeout_gate_not_verified")
            early_finish({"cli_stopped": False, "fake_terminated": False,
                          "port_closed": not port_open(port),
                          "owned_runtime_absent": False},
                         "setup_failure_effective_timeout_unverified")

    scenario, markers, reasoning = build_fixtures(
        args.scenario, args, ws, run_dir)
    result["scenario"] = {
        "mode": args.scenario,
        "tool_files_count": len(scenario.get("tool_files") or []),
        "error_status": (args.error_status
                         if args.scenario == "error" else None),
    }
    prompt = build_prompt(args.scenario, scenario)

    fake = start_fake(vpy, port, run_root, logs_dir, task_root)
    write_private(os.path.join(run_dir, "fake.pid"), str(fake.pid) + "\n")
    fake_ready, fake_wait = wait_fake_ready(fake, port)
    fake_receipt = {"pid": fake.pid, "ready": fake_ready,
                    "ready_wait_s": fake_wait, "terminated": None,
                    "exit": None}
    if not fake_ready:
        killpg(fake)
        _reap(fake)
        fake_receipt.update(terminated=fake.poll() is not None,
                            exit=fake.poll())
        result["fake"] = fake_receipt
        result["errors"].append("fake_not_ready")
        early_finish({"cli_stopped": False,
                      "fake_terminated": fake_receipt["terminated"] is True,
                      "port_closed": not port_open(port),
                      "owned_runtime_absent":
                          fake_receipt["terminated"] is True},
                     "setup_failure_fake_not_ready")
    result["fake"] = fake_receipt

    offsets = capture_home_log_offsets(run_home)
    t_cli = time.monotonic()
    cli = start_cli(vpy, launcher, prompt, ws, run_root, run_home, logs_dir)
    write_private(os.path.join(run_dir, "cli.pid"), str(cli.pid) + "\n")
    outer_cancel, peer_died = run_watchdog(cli, fake, args.watchdog)
    cli_rc = cli.wait()
    wall_s = round(time.monotonic() - t_cli, 2)

    if fake.poll() is None:
        killpg(fake)
        _reap(fake)
    fake_terminated = fake.poll() is not None
    fake_receipt.update(terminated=fake_terminated, exit=fake.poll())
    gw = cleanup_gateway(run_home)
    time.sleep(1)
    port_closed = not port_open(port)
    stray = stray_home_processes(run_home)
    owned_runtime_absent = (
        not proc_alive(fake.pid) and not proc_alive(cli.pid)
        and gw.get("absent_after") is True and not stray)
    cleanup = {"cli_stopped": cli_rc is not None,
               "fake_terminated": fake_terminated,
               "port_closed": port_closed,
               "owned_runtime_absent": owned_runtime_absent}

    jf, first_user = read_journal(run_dir)
    posts = jf.get("chat_completions_posts", 0)
    pc = prompt_clean_fact(first_user,
                           markers + ([reasoning] if reasoning else []))
    peer = (peer_state_fact(run_dir, args.tool_calls)
            if args.scenario == "toolloop" else None)
    clif = cli_log_facts(os.path.join(logs_dir, "cli.log"),
                         args.scenario, markers, reasoning)
    ev = (current_run_log_evidence(run_home, offsets)
          if args.scenario in ("stall", "error") else {})
    strong = strong_timeout_event(ev)
    err500 = error_500_event(ev)

    outcome = classify_outcome(posts, peer_died, outer_cancel, cli_rc,
                               strong, err500,
                               args.error_status
                               if args.scenario == "error" else 0)
    replay = reasoning_replay_fact(run_dir, reasoning)
    core = (cleanup["cli_stopped"] is True
            and cleanup["fake_terminated"] is True
            and cleanup["port_closed"] is True
            and cleanup["owned_runtime_absent"] is True)
    qualified = qualified_for(args.scenario, core, posts, peer_died,
                              outcome, err500, clif,
                              pc.get("prompt_clean", False), peer,
                              replay)

    result.update({
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cli": {"pid": cli.pid, "exit": cli_rc, "wall_s": wall_s,
                "stopped": cli_rc is not None,
                "outer_watchdog_cancel": outer_cancel,
                "launcher_sha256": sha256_file(launcher)},
        "prompt": secret_ref(prompt),
        "secrets": {"markers": [secret_ref(m) for m in markers],
                    "reasoning": (secret_ref(reasoning)
                                  if reasoning else None)},
        "journal": jf,
        "prompt_clean": pc,
        "peer_state": peer,
        "reasoning_replay": replay,
        "cli_log_facts": clif,
        "current_run_log_evidence": ev,
        "native_timeout_evidence_current_run": strong,
        "current_run_error_500_evidence": err500,
        "peer_died": peer_died,
        "gateway_cleanup": gw,
        "stray_private_home_processes": stray,
        "cleanup": cleanup,
        "privacy": {"raw_content_retained": keep,
                    "provider_call_performed": False,
                    "user_profile_touched": False},
        "artifacts": {"run_root": run_root, "retained": keep},
    })
    finish(result, run_root, report, qualified, cleanup, outcome, keep)


if __name__ == "__main__":
    main()
