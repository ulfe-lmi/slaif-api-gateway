"""183-a focused orchestration/grounding tests for the isolated Codex
research fallback (no Docker, no network: the execution adapter is
replaced by parent-owned stand-ins; the grounding and planning layers are
the real product code)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from slaif_gateway.schemas.catalog_refresh import (
    RESEARCH_EXTRACTOR_ID,
    RESEARCH_OUTPUT_SCHEMA_VERSION,
    ResearchGroundedFact,
    ResearchIdentity,
)
from slaif_gateway.services.catalog_refresh import collection as catalog_collection
from slaif_gateway.services.catalog_refresh import research as r
from slaif_gateway.services.catalog_refresh import research_grounding as rg
from slaif_gateway.services.catalog_refresh import research_isolation as iso
from slaif_gateway.services.catalog_refresh import sources as src
from slaif_gateway.services.catalog_refresh import source_evidence as se
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError


# --- synthetic OpenRouter snapshot -------------------------------------------


def _or_snapshot_bytes(rows: list[dict]) -> bytes:
    return (json.dumps({"data": rows}, sort_keys=True) + "\n").encode("utf-8")


def _row(
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


# --- output contract -----------------------------------------------------------


def test_load_research_output_accepts_valid_router() -> None:
    raw = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [
                {
                    "model": "syn-1",
                    "index": 0,
                    "context_length": {
                        "locator": "data[0].context_length",
                        "quote": "128K",
                    },
                }
            ],
        }
    ).encode("utf-8")
    output = r.load_research_output(raw)
    assert output.task == "openrouter_models_api"
    assert len(output.models) == 1


def _base_output() -> dict:
    return {
        "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
        "task": "openrouter_models_api",
        "models": [
            {
                "model": "syn-1",
                "index": 0,
                "context_length": {"locator": "data[0].context_length", "quote": "128K"},
            }
        ],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema="slaif-research-output/2"),
        lambda d: d.update(task="openai"),
        lambda d: d.update(extra=1),
        lambda d: d["models"][0].update(extra=1),
        lambda d: d["models"][0].pop("index"),
        lambda d: d["models"][0].update(index=-1),
        lambda d: d["models"][0].update(context_length={"locator": "x", "quote": ""}),
    ],
)
def test_load_research_output_rejects_invalid(mutate) -> None:
    import copy

    data = copy.deepcopy(_base_output())
    mutate(data)
    with pytest.raises(ValueError):
        r.load_research_output(json.dumps(data).encode("utf-8"))


def test_load_research_output_rejects_non_json_and_oversize() -> None:
    with pytest.raises(ValueError):
        r.load_research_output(b"not json at all")
    with pytest.raises(ValueError):
        r.load_research_output(b"x" * (r.MAX_TASK_JSON_BYTES + 1))


# --- planning -------------------------------------------------------------------


def _cfg(tmp_path: Path, **overrides) -> r.ResearchConfig:
    # mock_model=True keeps the phase tests on the qualification mock
    # transport: no operator endpoint is configured, and the (stand-in)
    # execute_task never touches the network.
    values = dict(
        enabled=True,
        cli_bin=str(tmp_path / "codex"),
        model_name="syn-model",
        workspace_root=str(tmp_path),
        mock_model=True,
        mock_result_json="{}",
    )
    values.update(overrides)
    return r.ResearchConfig(**values)


def test_plan_snapshot_plans_only_unresolved_eligible() -> None:
    raw = _or_snapshot_bytes([_row("syn-1", context_length="128K"), _row("syn-2")])
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
    assert parsed.ok
    by_model = {m.model: m for m in parsed.models}
    assert by_model["syn-1"].context_length is None  # deterministic pass unresolved
    assert by_model["syn-2"].context_length == 128000
    plan = r.plan_snapshot_tasks(
        openrouter_bytes=raw,
        openrouter_parse=parsed,
        openai_pricing_bytes=None,
        openai_pricing_parse=None,
    )
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.task == r.TASK_OPENROUTER
    assert task.models == ("syn-1",)
    assert task.content_sha256 == hashlib.sha256(raw).hexdigest()
    assert "model:context_length" in task.requested_fields
    assert plan.remaining == ()


def test_plan_snapshot_complete_rows_are_not_candidates() -> None:
    raw = _or_snapshot_bytes([_row("syn-1")])
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
    plan = r.plan_snapshot_tasks(
        openrouter_bytes=raw,
        openrouter_parse=parsed,
        openai_pricing_bytes=None,
        openai_pricing_parse=None,
    )
    assert plan.tasks == ()
    assert plan.remaining == ()


def test_plan_snapshot_task_bound_reports_remaining() -> None:
    rows = [_row(f"syn-{i:03d}", context_length="128K") for i in range(r.MAX_RESEARCH_TASKS * r.MAX_RESEARCH_MODELS_PER_TASK + 1)]
    raw = _or_snapshot_bytes(rows)
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
    plan = r.plan_snapshot_tasks(
        openrouter_bytes=raw,
        openrouter_parse=parsed,
        openai_pricing_bytes=None,
        openai_pricing_parse=None,
    )
    assert len(plan.tasks) == r.MAX_RESEARCH_TASKS
    assert len(plan.remaining) == 1
    source_key, provider, leftover = plan.remaining[0]
    assert provider == "openrouter"
    assert len(leftover) == 1
    assert source_key.startswith("openrouter|")


def test_plan_docs_page_feasibility_skips_resolved_limits() -> None:
    # A page that states a limit the deterministic pass ALREADY resolved is
    # not an eligible unresolved fact: the complete-row contract would make
    # the task unsatisfiable, so it must not be planned.
    page_md = (
        "Model ID: `syn-page`\n"
        "\n"
        "Context window (tokens): 131072\n"
        "Max output (tokens): 16K\n"
        "\n"
    ).encode("utf-8")
    page = se.ParsedModel(
        provider="openai",
        model="syn-page",
        context_length=131072,  # already resolved deterministically
        max_output_tokens=None,
    )
    plan = r.plan_docs_page_tasks([("syn-page", page_md, page)])
    assert plan.tasks == ()
    # Both unresolved and both resolvable on the page: feasible.
    page2 = se.ParsedModel(
        provider="openai",
        model="syn-page",
        context_length=None,
        max_output_tokens=None,
    )
    plan2 = r.plan_docs_page_tasks([("syn-page", page_md, page2)])
    assert len(plan2.tasks) == 1
    assert plan2.tasks[0].requested_fields == ("model:context_length", "model:max_output_tokens")


# --- run_research_phase (execution adapter stand-in) ------------------------------


def _fake_cli(path: Path) -> None:
    """A bounded executable stand-in that reports a version (help/version
    only; it is never the object under qualification)."""
    path.write_text("#!/bin/sh\necho 'codex-cli 0.162.1-qualification'\n", encoding="utf-8")
    path.chmod(0o755)


def _plan_one(models=("syn-1",), evidence: bytes = b"{}") -> r.ResearchPlan:
    return r.ResearchPlan(
        tasks=(
            r.ResearchTask(
                task=r.TASK_OPENROUTER,
                source_key="openrouter|catalog|openrouter_models_api",
                provider="openrouter",
                models=models,
                evidence=evidence,
                content_sha256=hashlib.sha256(evidence).hexdigest(),
                requested_fields=("pricing", "model:context_length", "model:max_output_tokens"),
            ),
        ),
        remaining=(),
    )


def _completed(output: bytes, **kw) -> iso.TaskExecution:
    return iso.TaskExecution(
        status="completed",
        exit_code=0,
        output_bytes=output,
        output_sha256=hashlib.sha256(output).hexdigest(),
        probe={"relay_reachable": True, "host_canary_reachable": False, "external_reachable": False},
        relay_requests=2,
        **kw,
    )


def test_phase_not_run_when_disabled_or_empty(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, enabled=False)
    assert r.run_research_phase(cfg, _plan_one()).identity.status == "NOT_RUN"
    cfg2 = _cfg(tmp_path)
    assert r.run_research_phase(cfg2, r.ResearchPlan(tasks=())).identity.status == "NOT_RUN"


def test_forward_mode_refuses_unconfigured_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        iso,
        "execute_task",
        lambda *a, **k: pytest.fail("execute_task must not run without a configured endpoint"),
    )
    _fake_cli(tmp_path / "codex")
    cfg = _cfg(tmp_path, mock_model=False, mock_result_json=None)
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "research_endpoint_unconfigured"


def test_phase_refuses_incomplete_configuration(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, cli_bin="")
    assert r.run_research_phase(cfg, _plan_one()).identity.status == "UNAVAILABLE"
    assert r.run_research_phase(cfg, _plan_one()).identity.failure_code == "research_configuration_incomplete"
    cfg = _cfg(tmp_path, model_name="")
    assert r.run_research_phase(cfg, _plan_one()).identity.failure_code == "research_configuration_incomplete"


def test_phase_refuses_missing_template_or_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(r, "_template_path", lambda: tmp_path / "absent-template.md")
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "research_template_missing"
    monkeypatch.undo()
    monkeypatch.setattr(r, "_schema_path", lambda: tmp_path / "absent-schema.json")
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.failure_code == "research_schema_missing"


ASSET_TEMPLATE_SHA256 = (
    "5ba7ff44d58fa21f7d020fbb793e5611bfb416b0475e5d92e23d566a45081d18"
)
ASSET_SCHEMA_SHA256 = (
    "89c57bd740aca25a60e90f304cd70b657993910d9555ac289adc875cf9564a87"
)


def test_packaged_assets_resolve_with_canonical_bytes() -> None:
    """184 R2: the research template/schema are canonical PACKAGED assets
    resolved through importlib.resources (identical in a source checkout
    and a wheel install). The exact bytes are digest-pinned; the identity
    binding (template_sha256) measures these same bytes per phase."""
    template = r._template_path()
    schema = r._schema_path()
    assert hashlib.sha256(template.read_bytes()).hexdigest() == ASSET_TEMPLATE_SHA256
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == ASSET_SCHEMA_SHA256
    # resolved inside the installed package, not a repository-relative path
    assert "slaif_gateway" in template.parts and "resources" in template.parts


def test_phase_refuses_missing_asset_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """184 R2: a broken installation can lack the packaged asset package
    itself; importlib.resources.files then raises ModuleNotFoundError
    (not OSError). Resolution errors must normalize to the same safe
    UNAVAILABLE refusals instead of escaping run_research_phase."""
    cfg = _cfg(tmp_path)
    missing = ModuleNotFoundError("No module named 'slaif_gateway.resources.catalog_refresh'")
    monkeypatch.setattr(r, "_template_path", lambda: (_ for _ in ()).throw(missing))
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "research_template_missing"
    monkeypatch.undo()
    monkeypatch.setattr(r, "_schema_path", lambda: (_ for _ in ()).throw(missing))
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "research_schema_missing"


def test_phase_refuses_workspace_inside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = _cfg(tmp_path, workspace_root=str(repo), repo_root=str(repo))
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "workspace_in_repo"


def test_phase_refuses_preexisting_workspace_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(r.secrets, "token_hex", lambda _n: "fixedtoken")
    base = tmp_path / "slaif-research" / "run-fixedtoken"
    base.mkdir(parents=True, mode=0o700)
    cfg = _cfg(tmp_path)
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "workspace_collision"


def test_phase_ordinary_exception_is_measured_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(r, "_run_phase_tasks", _boom)
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    identity = outcome.identity
    # A crash AFTER the verified CLI identity was measured is a measured
    # FAILED (identity, plan-derived scope, measured wall time preserved),
    # never a pre-invocation UNAVAILABLE.
    assert identity.status == "FAILED"
    assert identity.failure_code == "execution_error:RuntimeError"
    assert identity.codex_version and identity.cli_sha256
    assert identity.template_sha256
    assert identity.elapsed_ms is not None
    assert identity.child_exit_code == -1
    assert identity.facts_requested == 3
    assert identity.tasks_planned == 1
    assert identity.tasks_unattempted == 1
    assert outcome.facts == []


def test_phase_cleanup_failure_discards_all_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [],
        }
    ).encode("utf-8")
    monkeypatch.setattr(
        iso, "execute_task", lambda *a, **k: _completed(canned)
    )

    def _refuse(*args, **kwargs):
        raise PermissionError("injected")

    monkeypatch.setattr(r.shutil, "rmtree", _refuse)
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    identity = outcome.identity
    # Post-execution cleanup failure: the measured execution history
    # (verified CLI identity, timing, exit record, scope) is preserved as a
    # FAILED post-execution outcome; ALL research output is discarded.
    assert identity.status == "FAILED"
    assert identity.failure_code == "cleanup_incomplete"
    assert identity.codex_version and identity.cli_sha256
    assert identity.template_sha256
    assert identity.elapsed_ms is not None
    assert identity.child_exit_code == 0
    assert identity.facts_requested == 3
    assert outcome.cleanup_errors
    assert outcome.facts == []


def test_phase_later_task_refusal_preserves_execution_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [],
        }
    ).encode("utf-8")
    calls = {"n": 0}

    def _second_refused(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _completed(canned, elapsed_ms=500)
        return iso.TaskExecution(
            status="unavailable",
            failure_code="internal_network_unavailable",
            elapsed_ms=5,
        )

    monkeypatch.setattr(iso, "execute_task", _second_refused)
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    plan = r.ResearchPlan(
        tasks=(_plan_one().tasks[0], _plan_one(models=("syn-2",)).tasks[0]),
        remaining=(),
    )
    outcome = r.run_research_phase(cfg, plan)
    identity = outcome.identity
    assert identity.status == "FAILED"
    assert identity.failure_code == "internal_network_unavailable"
    # the earlier executed task's measured history is NOT erased
    assert identity.tasks_planned == 2
    assert identity.tasks_unattempted == 1
    assert identity.child_exit_code == 0
    assert identity.elapsed_ms == 505
    assert identity.codex_version and identity.cli_sha256
    # all research output is still discarded
    assert outcome.facts == []
    assert outcome.grounded_rows == {}


def test_phase_later_task_workspace_failure_preserves_execution_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # task 0 completes; task 1 workspace creation then fails (owned
    # injected filesystem failure): a measured FAILED with the completed
    # task's history preserved, never a blank pre-invocation UNAVAILABLE
    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [],
        }
    ).encode("utf-8")
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(canned, elapsed_ms=500))

    real_mkdir = Path.mkdir

    def _fail_second_task_dir(self, *args, **kwargs):
        if "/task-01-" in str(self):
            raise OSError(28, "No space left on device")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _fail_second_task_dir)
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    plan = r.ResearchPlan(
        tasks=(_plan_one().tasks[0], _plan_one(models=("syn-2",)).tasks[0]),
        remaining=(),
    )
    outcome = r.run_research_phase(cfg, plan)
    identity = outcome.identity
    assert identity.status == "FAILED"
    assert identity.failure_code == "workspace_unavailable"
    # the earlier executed task's measured history is NOT erased
    assert identity.tasks_planned == 2
    assert identity.tasks_unattempted == 1
    assert identity.child_exit_code == 0
    assert identity.elapsed_ms == 500
    assert identity.codex_version and identity.cli_sha256
    assert identity.template_sha256
    # all research output is still discarded
    assert outcome.facts == []
    assert outcome.grounded_rows == {}


def test_phase_child_failure_fails_whole_phase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        iso,
        "execute_task",
        lambda *a, **k: iso.TaskExecution(
            status="child_failure",
            failure_code="child_timeout",
            exit_code=137,
            elapsed_ms=1500,
        ),
    )
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    plan = _plan_one(models=("syn-1", "syn-2"))
    outcome = r.run_research_phase(cfg, plan)
    assert outcome.identity.status == "FAILED"
    assert outcome.identity.failure_code == "child_timeout"
    assert outcome.identity.child_exit_code == 137
    assert outcome.identity.tasks_planned == 1
    assert outcome.identity.tasks_unattempted == 1
    # requested scope is plan-derived BEFORE execution
    assert outcome.identity.facts_requested == 2 * 3
    assert outcome.facts == []


def test_phase_unavailable_boundary_propagates_safe_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        iso,
        "execute_task",
        lambda *a, **k: iso.TaskExecution(
            status="unavailable",
            failure_code="internal_network_unavailable",
            elapsed_ms=5,
        ),
    )
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "UNAVAILABLE"
    assert outcome.identity.failure_code == "internal_network_unavailable"


def test_phase_malformed_output_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(b"definitely not json"))
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "FAILED"
    assert outcome.identity.failure_code == "malformed_output"
    assert outcome.facts == []


def test_phase_out_of_scope_claim_is_dropped_not_grounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [{"model": "intruder-model", "index": 0}],
        }
    ).encode("utf-8")
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(canned))
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    assert outcome.identity.status == "SUCCEEDED"
    assert outcome.identity.facts_accepted == 0
    assert outcome.identity.facts_returned == 0
    assert outcome.scope_violations == 1
    assert outcome.facts == []


def test_phase_facts_bound_exhaustion_refuses_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cell = rg.GroundedCell(
        field="model:context_length",
        locator="data[0].context_length",
        quote="128K",
        value="128000",
        unit="none",
        currency=None,
    )
    fact = ResearchGroundedFact(
        source_key="openrouter|catalog|openrouter_models_api",
        provider="openrouter",
        model="syn-1",
        field=cell.field,
        locator=cell.locator,
        quote=cell.quote,
        value=cell.value,
        unit=cell.unit,
        currency=None,
    )

    def _ground(task, output):
        return r._TaskGrounded(
            rows={},
            facts=[fact, fact],
            rejected={},
            docs_resolved={},
            scope_violations=0,
            returned_cells=2,
            accepted_cells=2,
        )

    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [],
        }
    ).encode("utf-8")
    monkeypatch.setattr(r, "_ground_task", _ground)
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(canned))
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one(), facts_bound=1)
    assert outcome.identity.status == "FAILED"
    assert outcome.identity.failure_code == "facts_bound_exhausted"
    assert outcome.facts == []


def test_phase_success_identity_is_complete_and_measured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canned = json.dumps(
        {
            "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "task": "openrouter_models_api",
            "models": [{"model": "syn-1", "index": 0}],
        }
    ).encode("utf-8")
    monkeypatch.setattr(
        iso, "execute_task", lambda *a, **k: _completed(canned, elapsed_ms=1234)
    )
    cfg = _cfg(tmp_path)
    _fake_cli(tmp_path / "codex")
    outcome = r.run_research_phase(cfg, _plan_one())
    identity = outcome.identity
    assert identity.status == "SUCCEEDED"
    assert identity.codex_version  # measured from the (fake) binary
    assert identity.cli_sha256
    assert identity.result_sha256
    assert identity.elapsed_ms == 1234
    assert identity.child_exit_code == 0
    assert identity.mock_model is True
    assert identity.tasks_planned == 1
    assert identity.tasks_unattempted == 0
    assert identity.facts_requested == 1 * 3
    assert identity.extractor_version == RESEARCH_EXTRACTOR_ID


def test_merge_phase_identities() -> None:
    not_run = ResearchIdentity(status="NOT_RUN", extractor_version="e", tool_version="t")
    succeeded = ResearchIdentity(
        status="SUCCEEDED",
        codex_version="0.162.1",
        cli_sha256="0" * 64,
        prompt_version="p",
        template_sha256="1" * 64,
        output_schema_version="s",
        extractor_version="e",
        tool_version="t",
        facts_requested=3,
        facts_returned=2,
        facts_accepted=2,
        facts_rejected=0,
        elapsed_ms=10,
        child_exit_code=0,
        result_sha256="2" * 64,
        tasks_planned=1,
        tasks_unattempted=0,
    )
    failed = ResearchIdentity(
        status="FAILED",
        codex_version="0.162.1",
        cli_sha256="0" * 64,
        prompt_version="p",
        template_sha256="1" * 64,
        output_schema_version="s",
        extractor_version="e",
        tool_version="t",
        facts_requested=3,
        elapsed_ms=5,
        child_exit_code=137,
        failure_code="child_timeout",
        tasks_planned=1,
        tasks_unattempted=1,
    )
    assert r.merge_phase_identities(not_run, succeeded) is succeeded
    assert r.merge_phase_identities(succeeded, not_run) is succeeded
    assert r.merge_phase_identities(failed, succeeded).status == "FAILED"
    merged = r.merge_phase_identities(succeeded, succeeded)
    assert merged.status == "SUCCEEDED"
    assert merged.facts_accepted == 4
    assert merged.facts_requested == 6
    assert merged.tasks_planned == 2


# --- deterministic-first + full pipeline (mocked transport, no Docker) -----------


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
    def fetch(specs, *, client, context, resolve):
        results = []
        for spec in specs:
            content = provider_bytes.get(spec.url)
            if content is None:
                results.append(
                    src.RetrievalResult(
                        spec=spec,
                        ok=False,
                        final_url=spec.url,
                        retrieved_at=datetime.now(UTC),
                        status=None,
                        content_type=None,
                        content=None,
                        attempts=1,
                        redirects=0,
                        failure_code="http_404",
                    )
                )
            else:
                results.append(
                    src.RetrievalResult(
                        spec=spec,
                        ok=True,
                        final_url=spec.url,
                        retrieved_at=datetime.now(UTC),
                        status=200,
                        content_type="application/json",
                        content=content,
                        attempts=1,
                        redirects=0,
                    )
                )
        return results

    return fetch


def test_deterministic_first_suppresses_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _or_snapshot_bytes([_row("syn-1")])  # fully resolvable
    monkeypatch.setattr(
        iso,
        "execute_task",
        lambda *a, **k: pytest.fail("research must not run when deterministic parse is complete"),
    )
    client = httpx.Client()
    bundle = catalog_collection.collect_bundle(
        providers=("openrouter",),
        model_include=(),
        baseline_mode="first_install",
        baseline=None,
        client=client,
        fetch=_fake_fetch({src.OPENROUTER_MODELS_URL: raw}),
        research=_cfg(tmp_path),
    )
    assert bundle.research.status == "NOT_RUN"
    assert bundle.research_facts == ()
    model = next(m for m in bundle.models if m.model == "syn-1")
    assert model.provenance.extraction == "deterministic"


def _pipeline_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """One openrouter first-install collect whose only unresolved limit is
    completed by the (stand-in) mock research transport; the returned
    bundle carries the sealed, parent-grounded research facts."""
    raw = _or_snapshot_bytes([_row("syn-1", context_length="128K")])
    parsed = se.parse_snapshot("openrouter", "openrouter_models_api", raw)
    assert parsed.ok
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
    canned_bytes = json.dumps(canned).encode("utf-8")
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(canned_bytes))
    _fake_cli(tmp_path / "codex")
    cfg = _cfg(tmp_path, mock_model=True, mock_result_json=canned_bytes.decode("utf-8"))
    client = httpx.Client()
    # the fixture row is USD-priced, so a real live collection also carries
    # the required USD->EUR reference quote (ECB daily, yesterday's date);
    # without it the honest state is BLOCKED fx_evidence_unbound
    from datetime import timedelta

    ecb_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    return catalog_collection.collect_bundle(
        providers=("openrouter",),
        model_include=(),
        baseline_mode="first_install",
        baseline=None,
        client=client,
        fetch=_fake_fetch(
            {
                src.OPENROUTER_MODELS_URL: raw,
                src.ECB_DAILY_XML_URL: _ecb_xml_bytes(ecb_date, "1.08"),
            }
        ),
        research=cfg,
    )


# --- 183-b B3: captured official docs-page layout derivative --------------------

DOCS_PAGE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "catalog_refresh" / "research-openai-page-variant.md"
)
DOCS_PAGE_VARIANT_SHA256 = (
    "1167433c22fc055af0dbd2480afeff869107cf53969dbb9b7fe76478070b3f0c"
)


def _openai_pricing_md_bytes() -> bytes:
    """Standard-v1 eligible row (short-context input+output only, no cache
    writes, no long-context tier)."""
    return (
        "# Pricing\n\n"
        "### Standard pricing data\n\n"
        "| Model | Short context input | Short context cached input | Short context output | Long context input | Long context output |\n"
        "|---|---|---|---|---|---|\n"
        "| gpt-3.5-turbo | $0.50 | - | $1.50 | - | - |\n\n"
    ).encode("utf-8")


def _models_index_md_bytes() -> bytes:
    return (
        "# Models\n\n"
        "## Featured models\n\n"
        "- [GPT-3.5 Turbo](/api/docs/models/gpt-3.5-turbo.md): Legacy GPT model.\n"
    ).encode("utf-8")


def _docs_page_canned() -> dict:
    """The captured page's exact limit lines (0-based line numbers of the
    pinned fixture bytes)."""
    return {
        "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
        "task": "openai_docs_page",
        "models": [
            {
                "model": "gpt-3.5-turbo",
                "context_length": {
                    "locator": "line[15]",
                    "quote": "Context window (tokens): 16,385",
                },
                "max_output_tokens": {
                    "locator": "line[16]",
                    "quote": "Maximum output (tokens): 4,096",
                },
            }
        ],
    }


def _docs_page_pipeline_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    page_bytes: bytes | None = None,
    canned: dict | None = None,
):
    """183-b B3: a first-install OpenAI collect over the captured official
    docs-page LAYOUT DERIVATIVE (provenance:
    research-openai-page-variant-provenance.json). The deterministic parser
    succeeds on prices/modalities/endpoints but leaves BOTH limits
    unresolved in the prose layout; the (stand-in) mock research transport
    completes them from the SAME captured page bytes. No physical network:
    every URL is served by the fixture fetcher."""
    page = (
        page_bytes
        if page_bytes is not None
        else DOCS_PAGE_FIXTURE.read_bytes()
    )
    if canned is None:
        canned = _docs_page_canned()
    canned_bytes = json.dumps(canned, separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(iso, "execute_task", lambda *a, **k: _completed(canned_bytes))
    _fake_cli(tmp_path / "codex")
    cfg = _cfg(tmp_path, mock_model=True, mock_result_json=canned_bytes.decode("utf-8"))
    from datetime import timedelta

    ecb_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    return catalog_collection.collect_bundle(
        providers=("openai",),
        model_include=(),
        baseline_mode="first_install",
        baseline=None,
        client=httpx.Client(),
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


def test_full_pipeline_mock_research_seals_grounded_facts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from slaif_gateway.services.catalog_refresh.policy import policy_from_document
    from slaif_gateway.services.catalog_refresh.validation import (
        sql_capture_for_mode,
        validate_bundle,
    )

    bundle = _pipeline_bundle(tmp_path, monkeypatch)
    assert bundle.research.status == "SUCCEEDED"
    assert bundle.research.mock_model is True
    facts = bundle.research_facts
    assert len(facts) == 5  # 3 pricing cells + 2 limits
    fields = {f.field for f in facts}
    assert "model:context_length" in fields and "model:max_output_tokens" in fields
    model = next(m for m in bundle.models if m.model == "syn-1")
    assert model.provenance.extraction == "semantic"
    assert model.provenance.extractor == RESEARCH_EXTRACTOR_ID
    # context_length was completed by the grounded research row
    assert model.context_length == 128000
    # the ACTUAL validation report re-grounds every sealed fact and keeps the
    # declaration/review split honest
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
    )
    research = report.to_dict()["research"]
    assert research["review"] == {"facts_sealed": 5, "facts_regrounded": 5}
    assert research["declared"]["status"] == "SUCCEEDED"
    assert research["declared"]["mock_model"] is True
    assert any(w.code == "research_semantic_method" for w in report.warnings)


def test_regrounding_refuses_tampered_fact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from slaif_gateway.services.catalog_refresh.policy import policy_from_document
    from slaif_gateway.services.catalog_refresh.validation import (
        sql_capture_for_mode,
        validate_bundle,
    )

    bundle = _pipeline_bundle(tmp_path, monkeypatch)
    tampered = bundle.research_facts[0].model_copy(update={"quote": "999K"})
    facts = (tampered, *bundle.research_facts[1:])
    bundle = bundle.model_copy(update={"research_facts": facts})
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        validate_bundle(
            bundle,
            None,
            policy_from_document(bundle.policy),
            sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        )
    assert excinfo.value.code == "research_fact_ungroundable"


def test_regrounded_research_facts_conflict_block() -> None:
    from slaif_gateway.services.catalog_refresh import validation as v

    grounded: dict = {}

    def _fact(value: str, quote: str = "128K") -> ResearchGroundedFact:
        return ResearchGroundedFact(
            source_key="openrouter|catalog|openrouter_models_api",
            provider="openrouter",
            model="syn-1",
            field="model:context_length",
            locator="data[0].context_length",
            quote=quote,
            value=value,
            unit="none",
            currency=None,
        )

    v._record_regrounded_research(
        grounded, provider="openrouter", model="syn-1",
        field="model:context_length", fact=_fact("128000"),
    )
    # an identical duplicate (different quote, same grounded value) is
    # deduplicated, not a conflict
    v._record_regrounded_research(
        grounded, provider="openrouter", model="syn-1",
        field="model:context_length", fact=_fact("128000", quote="128000"),
    )
    assert len(grounded) == 1
    # conflicting grounded observations for the same context block instead
    # of silently selecting the last entry
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        v._record_regrounded_research(
            grounded, provider="openrouter", model="syn-1",
            field="model:context_length", fact=_fact("131072"),
        )
    assert excinfo.value.code == "research_facts_conflict"


def test_regrounding_refuses_facts_without_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from slaif_gateway.services.catalog_refresh.policy import policy_from_document
    from slaif_gateway.services.catalog_refresh.validation import (
        sql_capture_for_mode,
        validate_bundle,
    )

    bundle = _pipeline_bundle(tmp_path, monkeypatch)
    not_run = ResearchIdentity(
        status="NOT_RUN", extractor_version=RESEARCH_EXTRACTOR_ID, tool_version="183.1"
    )
    bundle = bundle.model_copy(update={"research": not_run})
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        validate_bundle(
            bundle,
            None,
            policy_from_document(bundle.policy),
            sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        )
    assert excinfo.value.code == "research_facts_without_success"

# --- 183-b B3: captured official docs-page layout derivative --------------------


def test_docs_page_captured_variant_plans_single_task() -> None:
    # The pinned captured-page derivative: deterministic parse succeeds
    # (prices/modalities/endpoints) but leaves both limits unresolved in the
    # prose layout; the parent page scan resolves BOTH uniquely, so the page
    # is exactly one eligible docs_page task.
    page = DOCS_PAGE_FIXTURE.read_bytes()
    assert hashlib.sha256(page).hexdigest() == DOCS_PAGE_VARIANT_SHA256
    parsed = se.parse_snapshot("openai", "docs_page", page)
    assert parsed.ok
    assert len(parsed.models) == 1
    model = parsed.models[0]
    assert model.model == "gpt-3.5-turbo"
    assert model.context_length is None  # deterministic pass unresolved
    assert model.max_output_tokens is None
    assert model.prices is not None  # pricing still parsed
    plan = r.plan_docs_page_tasks([("gpt-3.5-turbo", page, model)])
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.task == r.TASK_DOCS_PAGE
    assert task.source_key == "openai|gpt-3.5-turbo|docs_page"
    assert task.requested_fields == ("model:context_length", "model:max_output_tokens")
    assert task.content_sha256 == hashlib.sha256(page).hexdigest()
    assert plan.remaining == ()


def test_full_docs_page_pipeline_mock_research_seals_limit_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from slaif_gateway.services.catalog_refresh.policy import policy_from_document
    from slaif_gateway.services.catalog_refresh.validation import (
        ACQUISITION_LIVE,
        sql_capture_for_mode,
        validate_bundle,
    )

    bundle = _docs_page_pipeline_bundle(tmp_path, monkeypatch)
    assert bundle.research.status == "SUCCEEDED"
    assert bundle.research.mock_model is True
    facts = bundle.research_facts
    assert len(facts) == 2  # exactly the two unresolved limits, nothing else
    assert {
        (f.provider, f.model, f.field) for f in facts
    } == {
        ("openai", "gpt-3.5-turbo", "model:context_length"),
        ("openai", "gpt-3.5-turbo", "model:max_output_tokens"),
    }
    model = next(m for m in bundle.models if m.model == "gpt-3.5-turbo")
    assert model.context_length == 16385
    assert model.max_output_tokens == 4096
    # semantic provenance for the researched limits, deterministic for the rest
    assert model.provenance.extraction == "semantic"
    report, _ = validate_bundle(
        bundle,
        None,
        policy_from_document(bundle.policy),
        sql_capture=sql_capture_for_mode(bundle.baseline.mode),
        acquisition=ACQUISITION_LIVE,
    )
    assert report.state == "READY_WITH_WARNINGS"
    assert sorted(w.code for w in report.warnings) == [
        "new_model_exposure",
        "research_semantic_method",
    ]
    research = report.to_dict()["research"]
    assert research["review"] == {"facts_sealed": 2, "facts_regrounded": 2}
    assert research["declared"]["status"] == "SUCCEEDED"
    assert research["declared"]["mock_model"] is True


def test_docs_page_without_readable_limits_is_never_researched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A page that states NO limit the parent can ground is never a research
    # candidate: research stays NOT_RUN (nothing was invoked), the
    # deterministic disposition (incomplete/missing_limits) stands, and no
    # model is proposed.
    page = DOCS_PAGE_FIXTURE.read_bytes().replace(
        b"Context window (tokens): 16,385\nMaximum output (tokens): 4,096\n", b""
    )
    bundle = _docs_page_pipeline_bundle(tmp_path, monkeypatch, page_bytes=page)
    assert bundle.research.status == "NOT_RUN"
    assert bundle.research_facts == ()
    assert bundle.models == ()
    entries = {
        (e.provider, e.model): (e.disposition, e.reason_code) for e in bundle.collection.inventory
    }
    assert entries[("openai", "gpt-3.5-turbo")] == ("incomplete", "missing_limits")


def test_docs_page_fabricated_quote_is_rejected_not_grounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A transcription whose quote is NOT a line of the captured page bytes
    # is rejected by the parent grounding: zero sealed facts, the measured
    # phase identity (SUCCEEDED exit, 2 rejected) is retained, and the
    # deterministic disposition stands.
    canned = _docs_page_canned()
    canned["models"][0]["context_length"]["quote"] = "Context window (tokens): 999,999"
    bundle = _docs_page_pipeline_bundle(tmp_path, monkeypatch, canned=canned)
    assert bundle.research.status == "SUCCEEDED"
    assert bundle.research.child_exit_code == 0
    assert bundle.research_facts == ()
    assert bundle.research.facts_rejected == 2
    assert bundle.models == ()
    entries = {
        (e.provider, e.model): (e.disposition, e.reason_code) for e in bundle.collection.inventory
    }
    assert entries[("openai", "gpt-3.5-turbo")] == ("incomplete", "missing_limits")
