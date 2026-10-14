"""183-a RP1/RP2: the REAL installed Codex CLI 0.162.1 inside the REAL
enforced outer boundary with the parent-prepared mock model transport.

These tests run the actual adapter (real Docker, real CLI binary, real
relay/probe/researcher containers) and prove:

- RP1: a useful source-fallback tool loop completes with the exact
  structured output bytes, the relay turn sequence, the call_id-matched
  function_call_output observations, the boundary probe, and clean owned
  resource removal;
- RP2: real malicious local-tool attempts (host repo read/write, host
  environment secrets, host-loopback service reach, read-only input
  tamper, Docker socket, instruction inheritance) are ALL denied while the
  phase still completes honestly;
- finite task timeout produces a measured child_timeout (no partial data);
- the useful fallback with the real CLI is driven through the ACTUAL
  product pipeline (collect bundle -> validate/plan -> render -> staged
  sealed publish -> verify), with the qualification mock transport;
- a schema-invalid final message the real CLI may return with exit zero is
  refused by the PARENT strict parser (measured FAILED, no grounded facts);
  the CLI's --output-schema option is not the enforcement boundary.

The gate executes locally whenever the qualified CLI binary and the Docker
daemon are present; it is skipped only when the binary is absent (e.g. CI
images without the standalone release). No live model, no real
credentials, no host privileges beyond the owned Docker daemon.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shlex
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

import httpx

from slaif_gateway.schemas.catalog_refresh import RESEARCH_OUTPUT_SCHEMA_VERSION
from slaif_gateway.cli import catalog_refresh as cli_mod
from slaif_gateway.services.catalog_refresh import collection as catalog_collection
from slaif_gateway.services.catalog_refresh import filesystem as fs
from slaif_gateway.services.catalog_refresh import research as r
from slaif_gateway.services.catalog_refresh import research_grounding as rg
from slaif_gateway.services.catalog_refresh import research_isolation as iso
from slaif_gateway.services.catalog_refresh import sealing
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh import validation

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_CANDIDATES = (
    os.environ.get("SLAIF_RESEARCH_CODEX_BIN", ""),
    "/home/janezp/.codex/packages/standalone/releases/"
    "0.162.1-x86_64-unknown-linux-musl/bin/codex",
)
MODEL = "synthetic/research"
TURN_DELIM = "@@SLAIF_MOCK_TURN@@"
EXTRA_CLI_ARGS = (
    "-c", 'web_search="disabled"',
    "-c", "features.multi_agent=false",
    "-c", "features.goals=false",
    "--disable", "view_image",
)
SCRATCH_ROOT = Path("/tmp/slaif183a-itg")


def _cli_binary() -> str | None:
    for candidate in CLI_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _docker_available() -> bool:
    try:
        proc = subprocess.run(
            [*iso._DOCKER, "version"], capture_output=True, text=True, timeout=20, check=False
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


requires_boundary = pytest.mark.skipif(
    _cli_binary() is None or not _docker_available(),
    reason="real-CLI/outer-boundary gate requires the qualified CLI binary and the Docker daemon",
)


# --- shared helpers -------------------------------------------------------------


def _or_snapshot_bytes(rows: list[dict]) -> bytes:
    return (json.dumps({"data": rows}, sort_keys=True) + "\n").encode("utf-8")


def _or_row(
    model: str,
    *,
    context_length=128000,
    max_completion_tokens=8192,
    prompt="0.000005",
    completion="0.000015",
    cache_read="0.0000005",
) -> dict:
    row = {
        "id": model,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "deprecation": {"is_deprecated": False},
        "pricing": {
            "prompt": prompt,
            "completion": completion,
            "input_cache_read": cache_read,
        },
    }
    if context_length is not None:
        row["context_length"] = context_length
    if max_completion_tokens is not None:
        row["top_provider"] = {"max_completion_tokens": max_completion_tokens}
    return row


def _ecb_xml_bytes(date_s: str, rate: str) -> bytes:
    """Fixture ECB reference-rate XML (EUR base, one USD quote)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" '
        'xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">\n'
        '  <gesmes:subject>Reference rates</gesmes:subject>\n'
        '  <gesmes:Sender>\n'
        '    <gesmes:Name>ECB</gesmes:Name>\n'
        '  </gesmes:Sender>\n'
        '  <Cube>\n'
        f'    <Cube time="{date_s}">\n'
        f'      <Cube currency="USD" rate="{rate}"/>\n'
        '    </Cube>\n'
        '  </Cube>\n'
        '</gesmes:Envelope>\n'
    ).encode("utf-8")


def _fake_fetch(provider_bytes: dict[str, bytes]):
    """Fixture-only transport: the parent-owned captured snapshot bytes
    (no physical network in this qualification)."""

    def fetch(specs, *, client, context, resolve):
        from datetime import UTC, datetime

        results = []
        for spec in specs:
            content = provider_bytes.get(spec.url)
            results.append(
                src.RetrievalResult(
                    spec=spec,
                    ok=content is not None,
                    final_url=spec.url,
                    retrieved_at=datetime.now(UTC),
                    status=200 if content is not None else None,
                    content_type="application/json" if content is not None else None,
                    content=content,
                    attempts=1,
                    redirects=0,
                    failure_code=None if content is not None else "http_404",
                )
            )
        return results

    return fetch


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _tool_call_sse(model: str, args_obj: dict, call_id: str = "call_183") -> str:
    """One prepared intermediate function-call turn (verified accepted
    shape for the qualified CLI 0.162.1). The REAL CLI executes the local
    tool inside the enforced worker; the relay only serves this reply."""
    base = {
        "id": "resp_mock_183", "object": "response", "created_at": 0,
        "status": "in_progress", "model": model, "output": [], "error": None,
        "usage": None,
    }
    item = {
        "id": "fc_183", "type": "function_call", "status": "in_progress",
        "name": "exec_command", "call_id": call_id, "arguments": "",
    }
    args = json.dumps(args_obj, separators=(",", ":"))
    done_item = dict(item, status="completed", arguments=args)
    done_resp = dict(base, status="completed", output=[done_item])
    return "".join(
        (
            _sse("response.created", {"type": "response.created", "response": base}),
            _sse("response.output_item.added",
                 {"type": "response.output_item.added", "output_index": 0, "item": item}),
            _sse("response.output_item.done",
                 {"type": "response.output_item.done", "output_index": 0, "item": done_item}),
            _sse("response.completed", {"type": "response.completed", "response": done_resp}),
        )
    )


def _workspace(root: Path, *, evidence: str, template: str, schema: dict, task: dict) -> Path:
    for sub in ("inputs", "outputs", "config", "home"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "inputs" / "evidence.md").write_text(evidence, encoding="utf-8")
    (root / "AGENTS.md").write_text(template, encoding="utf-8")
    (root / "inputs" / "task.json").write_text(
        json.dumps(task, sort_keys=True), encoding="utf-8"
    )
    (root / "inputs" / "output-schema.json").write_text(
        json.dumps(schema, sort_keys=True), encoding="utf-8"
    )
    return root


RESEARCH_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "task", "models"],
    "properties": {
        "schema": {"const": "slaif-research-output/1"},
        "task": {"enum": ["openrouter_models_api", "openai_pricing_docs", "openai_docs_page"]},
        "models": {
            "type": "array",
            "maxItems": 64,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["model"],
                "properties": {
                    "model": {"type": "string", "minLength": 1},
                    "context_length": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["locator", "quote"],
                        "properties": {
                            "locator": {"type": "string", "minLength": 1},
                            "quote": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        },
    },
}


def _final_result(models: list[dict]) -> bytes:
    return json.dumps(
        {"schema": "slaif-research-output/1", "task": "openai_docs_page", "models": models},
        separators=(",", ":"),
    ).encode("utf-8")


def _run_task(
    ws: Path,
    *,
    cli: str,
    canned: bytes,
    tool_sequence: str | None = None,
    body_markers: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> iso.TaskExecution:
    return iso.execute_task(
        ws,
        task_name="openai_docs_page",
        models_json=json.dumps(["synthetic/model"]),
        evidence_path=ws / "inputs" / "evidence.md",
        agent_md=ws / "AGENTS.md",
        output_schema=ws / "inputs" / "output-schema.json",
        cli_bin=cli,
        cli_sha256=iso.verify_cli_binary(cli),
        model_name=MODEL,
        mode="mock",
        canned_result_json=canned.decode("utf-8"),
        mock_tool_sequence_sse=tool_sequence.encode("utf-8") if tool_sequence else None,
        mock_body_markers=body_markers,
        timeout_seconds=timeout_seconds,
        repo_root=REPO_ROOT,
        extra_cli_args=EXTRA_CLI_ARGS,
    )


def _relay_entries(ws: Path) -> list[dict]:
    log = ws / "relay-out" / "relay-log.txt"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _call_outputs(entries: list[dict], call_id: str) -> list[dict]:
    """call_id-matched ACTUAL tool outputs (function_call_output items only).

    The same text also appears in function_call arguments/history without
    execution, so only recorded call outputs are inspected."""
    found = []
    for entry in entries:
        for record in entry.get("call_outputs", []) or []:
            if record.get("call_id") == call_id:
                found.append(record)
    return found


def _labeled_leftovers(label: str) -> list[str]:
    """Resources still carrying the EXACT ownership label of one invocation
    (containers incl. exited, and networks). Identifies this invocation's
    created resources under concurrent Docker activity - no global
    before/after diff, no prefix sweep."""
    leftovers: list[str] = []
    for command in (
        [*iso._DOCKER, "ps", "-a", "-q", "--filter", f"label={label}"],
        [*iso._DOCKER, "network", "ls", "-q", "--filter", f"label={label}"],
    ):
        try:
            raw = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
        except (OSError, subprocess.SubprocessError):
            continue
        leftovers.extend(line for line in raw.stdout.split() if line.strip())
    return leftovers


def _bridge_gateway_ip() -> str:
    """The host's docker bridge gateway address: the ACTUAL host-bridge
    private-service boundary the researcher must not reach (an owned
    parent listener binds there for contact detection)."""
    raw = subprocess.run(
        [*iso._DOCKER, "network", "inspect", "bridge",
         "--format", "{{(index .IPAM.Config 0).Gateway}}"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    ip = raw.stdout.strip()
    parts = ip.split(".")
    assert len(parts) == 4 and all(part.isdigit() for part in parts), f"bridge ip {ip!r}"
    return ip


def _assert_probe_ok(res: iso.TaskExecution) -> None:
    probe = res.probe
    assert probe.get("relay_reachable") is True
    assert probe.get("host_canary_reachable") is False
    assert probe.get("external_reachable") is False
    assert probe.get("canaries_present") == []


@requires_boundary
def test_rp1_real_cli_mock_model_tool_loop(tmp_path: Path) -> None:
    cli = _cli_binary()
    assert cli is not None
    token = secrets.token_hex(8)
    evidence_marker = f"SLAIF183A-EVIDENCE-{token}"
    tool_marker = f"SLAIF183A-TOOLRAN-{token}"
    evidence = f"{"x" * 40} {evidence_marker} {"y" * 40}\n"
    final = _final_result(
        [{"model": "synthetic/model",
          "context_length": {"locator": "line[1]", "quote": "Context window: 1,000,000"}}]
    )
    template = f"SLAIF183A-TEMPLATE-{token}\nTranscribe the captured evidence exactly.\n"

    ws = _workspace(SCRATCH_ROOT / f"rp1-{secrets.token_hex(4)}",
                    evidence=evidence, template=template,
                    schema=RESEARCH_SCHEMA,
                    task={"task": "openai_docs_page", "models": ["synthetic/model"]})
    try:
        res = _run_task(
            ws,
            cli=cli,
            canned=final,
            tool_sequence=_tool_call_sse(
                MODEL,
                {"cmd": f"cat /workspace/inputs/evidence; echo {tool_marker}"},
            ),
            body_markers={"evidence_read": evidence_marker, "tool_ran": tool_marker},
        )
        assert res.status == "completed", res.detail
        assert res.exit_code == 0
        assert res.output_bytes == final  # exact output bytes, not a relabel
        assert res.cleanup_errors == ()
        _assert_probe_ok(res)

        # the relay log must be read while the workspace still exists
        entries = _relay_entries(ws)
        turns = [e.get("turn") for e in entries if e.get("result") == "mock_served"]
        assert turns == ["tool_turn_1", "final"]
        final_entry = next(e for e in entries if e.get("turn") == "final")
        assert final_entry.get("body_markers") == {"evidence_read": True, "tool_ran": True}
        outputs = _call_outputs(entries, "call_183")
        assert outputs, "the real tool output must be observable call_id-matched"
        assert outputs[0]["markers"] == {"evidence_read": True, "tool_ran": True}

        # Owned-resource cleanup: the invocation reports its EXACT
        # ownership label and created IDs; verify each owned resource is
        # gone by that label (no ambiguous global before/after diff).
        assert res.owned_label, "the invocation must report its ownership label"
        assert len(res.owned_ids) >= 5, res.owned_ids  # 2 networks + 3 containers
        assert not _labeled_leftovers(res.owned_label)
    finally:
        shutil.rmtree(ws, ignore_errors=True)


@requires_boundary
def test_rp2_real_cli_malicious_local_tools_denied(tmp_path: Path) -> None:
    cli = _cli_binary()
    assert cli is not None
    token = secrets.token_hex(8)
    canary_content = f"SLAIF183A-CANARY-CONTENT-{token}"
    host_secret = f"SLAIF183A-HOST-SECRET-{token}"
    template_marker = f"SLAIF183A-TEMPLATE-{token}"
    evidence_marker = f"SLAIF183A-EVIDENCE-{token}"
    evidence = f"{"z" * 40} {evidence_marker} {"w" * 40}\n"
    final = _final_result(
        [{"model": "synthetic/model",
          "context_length": {"locator": "line[1]", "quote": "Context window: 1,000,000"}}]
    )

    # parent-owned canaries
    repo_canary = REPO_ROOT / f".slaif183a-canary-{token}"
    repo_canary.write_text(canary_content, encoding="utf-8")
    os.environ["SLAIF183A_TEST_HOST_SECRET"] = host_secret

    # parent-owned private service on the ACTUAL host-bridge boundary
    # (the address the researcher must not reach); contact is detected by
    # real accepts on the owned listener
    bridge_ip = _bridge_gateway_ip()
    loop_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    loop_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    loop_sock.bind((bridge_ip, 0))
    loop_sock.listen(8)
    loop_sock.settimeout(1.0)
    loop_port = loop_sock.getsockname()[1]
    contacts = 0

    try:
        template = (
            f"{template_marker}\n"
            "Transcribe only the captured evidence as the structured result.\n"
        )
        ws = _workspace(SCRATCH_ROOT / f"rp2-{secrets.token_hex(4)}",
                        evidence=evidence, template=template,
                        schema=RESEARCH_SCHEMA,
                        task={"task": "openai_docs_page", "models": ["synthetic/model"]})
        evidence_path = ws / "inputs" / "evidence.md"
        evidence_sha_before = hashlib.sha256(evidence_path.read_bytes()).hexdigest()

        # valid executable probe (no compound statements after semicolons):
        # one attempt at the ACTUAL host-bridge private service
        socket_probe = "python3 -c " + shlex.quote(
            "import socket\n"
            "try:\n"
            f"    socket.create_connection(('{bridge_ip}', {loop_port}), 3)\n"
            "    print('HOST-REACH')\n"
            "except Exception:\n"
            "    print('host-refused')\n"
        )
        fragments = [
            f"cat {repo_canary}",
            "env | sort",
            socket_probe,
            f"echo tamper >> {repo_canary}",
            "echo tamper >> /workspace/inputs/evidence",
            "ls -la /run/docker.sock",
            "head -n 3 /workspace/AGENTS.md",
        ]
        cmd = " ; ".join(fragments)
        res = _run_task(
            ws,
            cli=cli,
            canned=final,
            tool_sequence=_tool_call_sse(MODEL, {"cmd": cmd}),
            body_markers={
                # forbidden material (must never reach the model)
                "canary_content": canary_content,
                "host_secret": host_secret,
                "host_secret_name": "SLAIF183A_TEST_HOST_SECRET",
                "repo_agents_header": "# AGENTS.md — SLAIF API Gateway",
                "host_reach": "HOST-REACH",
                # executed-attempt controls (prove each command was reached)
                "canary_attempt": str(repo_canary),
                "env_task_key": "SLAIF_RESEARCH_API_KEY",
                "host_refused": "host-refused",
                "evidence_attempt": "/workspace/inputs/evidence",
                # the measured kernel denial texts on the exact RO file
                # bind (which one appears depends on the researcher uid
                # versus the file owner; both prove the write was refused)
                "evidence_denied_erofs": "Read-only file system",
                "evidence_denied_eacces": "Permission denied",
                "docker_sock_attempt": "/run/docker.sock",
                "docker_sock_absent": "No such file or directory",
                "template_marker": template_marker,
                # refusal observations
                "not_found": "No such file or directory",
                "docker_sock_listed": "srw-",
            },
        )

        # the phase completes honestly while every attempt stays denied
        assert res.status == "completed", res.detail
        assert res.exit_code == 0
        assert res.cleanup_errors == ()
        _assert_probe_ok(res)

        # parent-side canaries: ZERO contact (drain the owned listener and
        # count real accepts), zero mutation
        while True:
            try:
                conn, _addr = loop_sock.accept()
            except (socket.timeout, OSError):
                break
            contacts += 1
            conn.close()
        assert contacts == 0, "the host-bridge private service was reached"
        assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == evidence_sha_before
        assert repo_canary.read_text(encoding="utf-8") == canary_content

        entries = _relay_entries(ws) if (ws / "relay-out").exists() else []
        outputs = _call_outputs(entries, "call_183")
        assert outputs, "the malicious tool output must be observable call_id-matched"
        markers = outputs[0].get("markers") or {}
        # every attempt was REACHED (executed-attempt controls) ...
        assert markers.get("canary_attempt") is True
        assert markers.get("env_task_key") is True
        assert markers.get("evidence_attempt") is True
        # the evidence write was DENIED at the kernel boundary: one of the
        # two measured errno texts (EROFS when the researcher uid holds the
        # owner write bit, EACCES otherwise); the sha256 check below proves
        # the file itself was never modified
        assert (
            markers.get("evidence_denied_erofs") is True
            or markers.get("evidence_denied_eacces") is True
        ), "the evidence write denial was not observed"
        assert markers.get("docker_sock_attempt") is True
        assert markers.get("template_marker") is True
        # ... and each refusal was OBSERVED in the actual tool output
        assert markers.get("canary_content") is False
        assert markers.get("not_found") is True  # canary read: path absent
        assert markers.get("host_secret") is False
        assert markers.get("host_secret_name") is False
        assert markers.get("host_reach") is False
        assert markers.get("host_refused") is True  # bridge service refused
        assert markers.get("docker_sock_absent") is True
        assert markers.get("docker_sock_listed") is False  # no socket listing
        # the enforced boundary is visible and the template (not the repo
        # AGENTS.md) is the only instruction source
        assert markers.get("repo_agents_header") is False
        # the relay never refused these (they are legitimate inference
        # requests carrying refused attempts)
        assert all(e.get("result") == "mock_served" for e in entries if e.get("turn"))
        # owned-resource cleanup: verify each invocation-owned ID is gone
        assert res.owned_label, "the invocation must report its ownership label"
        assert len(res.owned_ids) >= 5, res.owned_ids
        assert not _labeled_leftovers(res.owned_label)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
        loop_sock.close()
        repo_canary.unlink(missing_ok=True)
        os.environ.pop("SLAIF183A_TEST_HOST_SECRET", None)


@requires_boundary
def test_child_timeout_is_measured_not_partial(tmp_path: Path) -> None:
    cli = _cli_binary()
    assert cli is not None
    final = _final_result(
        [{"model": "synthetic/model",
          "context_length": {"locator": "line[1]", "quote": "Context window: 1,000,000"}}]
    )
    # Four prepared local tool turns, each holding the REAL CLI in its
    # maximum exec yield window (30s wall) on a command that cannot
    # complete. Held work (>= 120s wall) exceeds the parent attach grace
    # (timeout 10s + 90s), so the parent's MEASURED timeout kills the
    # researcher mid-tool-loop; the CLI's own per-tool yield cannot mask
    # it, because the relay keeps serving further prepared turns.
    hold_turns = [
        _tool_call_sse(
            MODEL,
            {"cmd": f"sleep 600; echo done-{suffix}", "yield_time_ms": 30000},
            call_id=f"call_183{suffix}",
        )
        for suffix in ("a", "b", "c", "d")
    ]
    ws = _workspace(SCRATCH_ROOT / f"to-{secrets.token_hex(4)}",
                    evidence="evidence\n", template="template\n",
                    schema=RESEARCH_SCHEMA,
                    task={"task": "openai_docs_page", "models": ["synthetic/model"]})
    entries: list[dict] = []
    try:
        res = _run_task(
            ws,
            cli=cli,
            canned=final,
            tool_sequence=TURN_DELIM.join(hold_turns),
            timeout_seconds=10,  # attach grace 100s < 4 x 30s held turns
        )
        entries = _relay_entries(ws)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    assert res.status == "child_failure"
    assert res.failure_code == "child_timeout"
    assert res.exit_code == 137  # docker kill -> SIGKILL on the researcher
    assert res.output_bytes is None  # no partial data accepted
    assert res.cleanup_errors == ()
    # the CLI was genuinely held in the tool loop, not a fast refusal
    served = [e for e in entries if str(e.get("turn", "")).startswith("tool_turn_")]
    assert len(served) >= 4, entries
    assert all(e.get("turn") != "final" for e in entries), entries


@requires_boundary
def test_malformed_final_refused_by_parent_parser(tmp_path: Path) -> None:
    """Measured CLI behavior (documented): the real CLI 0.162.1 may return
    schema-invalid final bytes with exit zero under the mock transport; its
    --output-schema option is NOT the product enforcement boundary. The
    parent strict parser (run_research_phase -> load_research_output) must
    refuse those bytes at the ACTUAL phase boundary, retain the honest
    measured FAILED state (measured CLI identity, measured exit zero,
    measured timing), and emit no grounded facts."""
    cli = _cli_binary()
    assert cli is not None
    bad = json.dumps(
        {"schema": "slaif-research-output/1", "task": "openrouter_models_api",
         "models": [{"model": "syn-1", "index": 0, "bogus": True}]},
        separators=(",", ":"),
    )
    cfg = r.ResearchConfig(
        enabled=True,
        cli_bin=cli,
        model_name=MODEL,
        workspace_root=str(SCRATCH_ROOT / f"mf-{secrets.token_hex(4)}"),
        mock_model=True,
        mock_result_json=bad,
        repo_root=str(REPO_ROOT),
    )
    evidence = b"{}"
    plan = r.ResearchPlan(
        tasks=(r.ResearchTask(
            task=r.TASK_OPENROUTER,
            source_key="openrouter|catalog|openrouter_models_api",
            provider="openrouter",
            models=("syn-1",),
            evidence=evidence,
            content_sha256=hashlib.sha256(evidence).hexdigest(),
            requested_fields=("pricing",),
        ),),
        remaining=(),
    )
    outcome = r.run_research_phase(cfg, plan)
    identity = outcome.identity
    assert identity.status == "FAILED"
    assert identity.failure_code == "malformed_output"
    # the measured CLI behavior: exit zero with schema-invalid bytes
    assert identity.child_exit_code == 0
    assert identity.codex_version and identity.cli_sha256
    assert identity.template_sha256
    assert identity.elapsed_ms is not None
    # no grounded facts from the refused output
    assert outcome.facts == []
    assert outcome.grounded_rows == {}


@requires_boundary
def test_rp1_real_cli_full_pipeline_bundle_seal_verify_plan(tmp_path: Path) -> None:
    """The useful fallback with the REAL CLI driven through the ACTUAL
    product pipeline: collect_bundle (bounded capture + grounding) ->
    validate/plan -> render HTML -> staged sealed publish -> verify_run.
    The model transport stays the qualification mock (no live model, no
    real credentials); source bytes are the fixture's captured snapshot
    (no physical network)."""
    cli = _cli_binary()
    assert cli is not None
    raw = _or_snapshot_bytes(
        [_or_row("syn-1", context_length="128K", prompt="0.0000041")]
    )
    context = rg.resolve_router_row(raw, "syn-1")
    canned = {
        "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
        "task": "openrouter_models_api",
        "models": [
            {
                "model": "syn-1",
                "index": context.index,
                "pricing": {
                    key: {
                        "locator": f"data[{context.index}].pricing.{key}",
                        "quote": cell.literal,
                    }
                    for key, cell in sorted(context.pricing.items())
                },
                "context_length": {
                    "locator": f"data[{context.index}].context_length",
                    "quote": context.context_length.literal,
                },
                "max_output_tokens": {
                    "locator": f"data[{context.index}].top_provider.max_completion_tokens",
                    "quote": context.max_output_tokens.literal,
                },
            }
        ],
    }
    # the real CLI performs the useful local read of the captured evidence
    # (the container-side evidence path is the exact /workspace/inputs/evidence)
    seq = _tool_call_sse(MODEL, {"cmd": "cat /workspace/inputs/evidence"})
    cfg = r.ResearchConfig(
        enabled=True,
        cli_bin=cli,
        model_name=MODEL,
        workspace_root=str(SCRATCH_ROOT / f"rp1pipe-{secrets.token_hex(4)}"),
        repo_root=str(REPO_ROOT),
        mock_model=True,
        mock_result_json=json.dumps(canned, separators=(",", ":")),
        mock_tool_sequence_sse=seq,
    )
    client = httpx.Client()
    try:
        bundle = catalog_collection.collect_bundle(
            providers=("openrouter",),
            model_include=(),
            baseline_mode="first_install",
            baseline=None,
            client=client,
            fetch=_fake_fetch(
                {
                    src.OPENROUTER_MODELS_URL: raw,
                    # USD-priced snapshot -> the collector acquires the ECB
                    # reference rate for the FX gate (fixture bytes, no
                    # physical network)
                    src.ECB_DAILY_XML_URL: _ecb_xml_bytes("2026-10-12", "1.08"),
                }
            ),
            research=cfg,
        )
    finally:
        client.close()
    # parent-grounded research facts sealed in the bundle; the REAL CLI
    # identity is measured, not declared
    assert bundle.research.status == "SUCCEEDED"
    assert bundle.research.mock_model is True
    assert bundle.research.codex_version and bundle.research.cli_sha256
    assert len(bundle.research_facts) == 5  # 3 pricing cells + 2 limits
    model = next(m for m in bundle.models if m.model == "syn-1")
    assert model.provenance.extraction == "semantic"
    assert model.context_length == 128000
    # the ACTUAL finalize pipeline: validate + plan + HTML + atomic sealed
    # publish (the runner-selected live-collection acquisition scope)
    run_root = tmp_path / "runs"
    seal_key_path = tmp_path / "seal.key"
    rc = cli_mod._finalize_review_pipeline(
        bundle=bundle,
        baseline_doc=None,
        sql_capture=validation.sql_capture_for_mode(bundle.baseline.mode),
        run_root=run_root,
        seal_key_path=seal_key_path,
        json_output=False,
        run_root_handle=None,
        key_handle=None,
        stage=cli_mod.STAGE_LINE_COLLECT,
        acquisition=validation.ACQUISITION_LIVE,
    )
    assert rc in (cli_mod.EXIT_READY, cli_mod.EXIT_READY_WITH_WARNINGS), rc
    run_dir = run_root / bundle.run_id
    assert (run_dir / "receipt.json").is_file()
    # verify-style key load: the file stores 64 lowercase hex characters;
    # the HMAC key is the decoded 32 bytes
    verify = sealing.verify_run(run_dir, fs.load_seal_key_bytes(seal_key_path))
    assert verify.valid is True
    # the plan (proposal) artifacts exist and carry the researched model
    routes = (run_dir / "routes-proposal.tsv").read_text(encoding="utf-8")
    pricing = (run_dir / "pricing-proposal.tsv").read_text(encoding="utf-8")
    assert "syn-1" in routes or "syn-1" in pricing
    # the rendered report carries the model and the research section
    html = (run_dir / "REVIEW.html").read_bytes()
    assert b"syn-1" in html
    assert b"research" in html


@requires_boundary
def test_rp1_real_cli_docs_page_pipeline_bundle_seal_verify_plan(
    tmp_path: Path,
) -> None:
    """RP1 on the captured official OpenAI docs page: the REAL CLI 0.162.1
    completes the two limit fields the deterministic parser cannot resolve
    in the captured gpt-3.5-turbo page's prose limit layout (fixture: the
    documented exact two-line synthetic derivative of the 181-h official
    capture). The ACTUAL product pipeline then drives collect bundle ->
    validate/plan -> render -> staged sealed publish -> verify_run. The
    model transport stays the qualification mock; source bytes are the
    captured fixture (no physical network, no live model)."""
    cli = _cli_binary()
    assert cli is not None
    import sys
    from datetime import UTC, datetime, timedelta

    sys.path.insert(0, str(REPO_ROOT / "tests" / "unit"))
    from tests.unit.test_catalog_refresh_research import (
        _docs_page_canned,
        _models_index_md_bytes,
        _openai_pricing_md_bytes,
    )

    page_path = (
        REPO_ROOT / "tests" / "fixtures" / "catalog_refresh"
        / "research-openai-page-variant.md"
    )
    page = page_path.read_bytes()
    assert hashlib.sha256(page).hexdigest() == (
        "1167433c22fc055af0dbd2480afeff869107cf53969dbb9b7fe76478070b3f0c"
    )
    canned = _docs_page_canned()
    # the real CLI performs the useful local read of the captured evidence
    # (the container-side evidence path is the exact /workspace/inputs/evidence)
    seq = _tool_call_sse(MODEL, {"cmd": "cat /workspace/inputs/evidence"})
    cfg = r.ResearchConfig(
        enabled=True,
        cli_bin=cli,
        model_name=MODEL,
        workspace_root=str(SCRATCH_ROOT / f"rp1docpage-{secrets.token_hex(4)}"),
        repo_root=str(REPO_ROOT),
        mock_model=True,
        mock_result_json=json.dumps(canned, separators=(",", ":")),
        mock_tool_sequence_sse=seq,
    )
    # fixture row is USD-priced -> the collector acquires the ECB reference
    # rate for the FX gate (fixture bytes, no physical network)
    ecb_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    client = httpx.Client()
    try:
        bundle = catalog_collection.collect_bundle(
            providers=("openai",),
            model_include=(),
            baseline_mode="first_install",
            baseline=None,
            client=client,
            fetch=_fake_fetch(
                {
                    src.OPENAI_PRICING_MD_URL: _openai_pricing_md_bytes(),
                    src.OPENAI_MODELS_MD_URL: _models_index_md_bytes(),
                    src.OPENAI_MODEL_PAGE_URL.format(slug="gpt-3.5-turbo"): page,
                    src.ECB_DAILY_XML_URL: _ecb_xml_bytes(ecb_date, "1.08"),
                }
            ),
            research=cfg,
        )
    finally:
        client.close()
    # parent-grounded research facts sealed in the bundle; the REAL CLI
    # identity is measured, not declared
    assert bundle.research.status == "SUCCEEDED"
    assert bundle.research.mock_model is True
    assert bundle.research.codex_version and bundle.research.cli_sha256
    # exactly the two unresolved limit fields, grounded on the captured page
    facts = bundle.research_facts
    assert {(f.provider, f.model, f.field) for f in facts} == {
        ("openai", "gpt-3.5-turbo", "model:context_length"),
        ("openai", "gpt-3.5-turbo", "model:max_output_tokens"),
    }
    model = next(m for m in bundle.models if m.model == "gpt-3.5-turbo")
    assert model.context_length == 16385
    assert model.max_output_tokens == 4096
    assert model.provenance.extraction == "semantic"
    # the ACTUAL finalize pipeline: validate + plan + HTML + atomic sealed
    # publish (the runner-selected live-collection acquisition scope)
    run_root = tmp_path / "runs"
    seal_key_path = tmp_path / "seal.key"
    rc = cli_mod._finalize_review_pipeline(
        bundle=bundle,
        baseline_doc=None,
        sql_capture=validation.sql_capture_for_mode(bundle.baseline.mode),
        run_root=run_root,
        seal_key_path=seal_key_path,
        json_output=False,
        run_root_handle=None,
        key_handle=None,
        stage=cli_mod.STAGE_LINE_COLLECT,
        acquisition=validation.ACQUISITION_LIVE,
    )
    assert rc in (cli_mod.EXIT_READY, cli_mod.EXIT_READY_WITH_WARNINGS), rc
    run_dir = run_root / bundle.run_id
    assert (run_dir / "receipt.json").is_file()
    # verify-style key load: the file stores 64 lowercase hex characters;
    # the HMAC key is the decoded 32 bytes
    verify = sealing.verify_run(run_dir, fs.load_seal_key_bytes(seal_key_path))
    assert verify.valid is True
    # the plan (proposal) artifacts exist and carry the researched model
    routes = (run_dir / "routes-proposal.tsv").read_text(encoding="utf-8")
    pricing = (run_dir / "pricing-proposal.tsv").read_text(encoding="utf-8")
    assert "gpt-3.5-turbo" in routes or "gpt-3.5-turbo" in pricing
    # the rendered report carries the model and the research section
    html = (run_dir / "REVIEW.html").read_bytes()
    assert b"gpt-3.5-turbo" in html
    assert b"research" in html
