"""Objective 183 (R1/R3): isolated Codex research fallback orchestration.

Deterministic official-source collection/parsing stays FIRST. Only when
eligible required facts remain unresolved from the captured official bytes
does the parent plan a bounded research task; the REAL Codex CLI runs
inside the enforced outer boundary (``research_isolation``) against a
narrow relay-only model connection; and the PARENT re-resolves every
returned locator against the captured bytes (``research_grounding``)
before any fact can enter the bundle.

Honesty rules enforced here:

- the parent sets the research status; a model or a supplied bundle can
  never certify an execution (supplied identities are declarations);
- a phase is SUCCEEDED only when EVERY planned task child completed with a
  schema-conformant result; any child failure fails the whole phase and no
  partial research data is used (the deterministic dispositions stand);
- an unavailable enforcement boundary refuses research (UNAVAILABLE);
  there is never an unsandboxed fallback;
- every grounded cell is sealed verbatim (quote + locator + parent value)
  so an offline verify re-grounds it against the sealed evidence bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from slaif_gateway.schemas.catalog_refresh import (
    RESEARCH_EXTRACTOR_ID,
    RESEARCH_OUTPUT_SCHEMA_VERSION,
    RESEARCH_TEMPLATE_VERSION,
    ResearchGroundedFact,
    ResearchIdentity,
)
from slaif_gateway.services.catalog_refresh import research_grounding as rg
from slaif_gateway.services.catalog_refresh import research_isolation as iso
from slaif_gateway.services.catalog_refresh import source_evidence as se

__all__ = [
    "MAX_RESEARCH_FACTS",
    "MAX_RESEARCH_MODELS_PER_TASK",
    "MAX_RESEARCH_TASKS",
    "ResearchConfig",
    "ResearchOutput",
    "ResearchPhaseOutcome",
    "ResearchTask",
    "load_research_output",
    "merge_phase_identities",
    "plan_docs_page_tasks",
    "plan_snapshot_tasks",
    "run_research_phase",
]

TASK_OPENROUTER = "openrouter_models_api"
TASK_OPENAI_PRICING = "openai_pricing_docs"
TASK_DOCS_PAGE = "openai_docs_page"
_TASK_KINDS = (TASK_OPENROUTER, TASK_OPENAI_PRICING, TASK_DOCS_PAGE)

MAX_RESEARCH_MODELS_PER_TASK = rg.MAX_RESEARCH_MODELS
MAX_RESEARCH_TASKS = 8
# Bundle-wide sealed-cell bound (schema max_length of research_facts).
MAX_RESEARCH_FACTS = 640
MAX_TASK_JSON_BYTES = 256 * 1024
# Source-record model part for the whole-catalog snapshot records (sources.py).
_CATALOG_MODEL = "catalog"


# --- configuration (trusted operator input; never bundle authority) --------


@dataclass(frozen=True)
class ResearchConfig:
    """Operator-trusted research configuration for ONE collect invocation.

    ``model_endpoint``/``model_name``/``model_auth_env`` select the research
    inference path (relay forward mode); the key VALUE is read from the
    named environment variable by the PARENT and handed only to the relay
    container - the researcher sees only the synthetic task credential.
    """

    enabled: bool = True
    cli_bin: str = ""
    model_endpoint: str = ""
    model_name: str = ""
    model_auth_env: str = ""
    timeout_seconds: int = 120
    mock_model: bool = False
    mock_result_json: str | None = None
    # Qualification-only mock-model tool loop (mock mode): prepared
    # intermediate function-call turns (the real CLI executes the LOCAL
    # tools inside the enforced worker; the relay only serves the prepared
    # replies). Never used by a forward/operator-configured endpoint.
    mock_tool_sequence_sse: str | None = None
    # Qualification-only safe body-marker observation (mock mode):
    # name -> synthetic marker value; the mock relay logs, per request,
    # which marker NAMES appear in the request body (values never logged).
    mock_body_markers: dict[str, str] | None = None
    workspace_root: str = "/tmp"
    repo_root: str | None = None
    tool_version: str = "183.1"
    # Verified HTTPS is required for real external endpoints; True marks an
    # explicit owned synthetic test upstream (HTTP) for qualification only.
    upstream_http_allowed: bool = False


# --- tasks -------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchTask:
    """One bounded research task: one captured source scope for one run."""

    task: str  # TASK_OPENROUTER | TASK_OPENAI_PRICING | TASK_DOCS_PAGE
    source_key: str  # the source record key the sealed facts will bind
    provider: str
    models: tuple[str, ...]  # bounded model scope (never empty)
    evidence: bytes  # captured official bytes (digest-bound by the record)
    content_sha256: str
    requested_fields: tuple[str, ...]  # unresolved fields that motivated it


@dataclass(frozen=True)
class ResearchPlan:
    """Parent-owned research plan for one phase.

    ``tasks`` is the bounded executable scope; ``remaining`` lists the
    eligible work that could NOT be planned into a task (the bundle-wide
    task bound) as (source_key, provider, models) chunks. Remaining work is
    reported explicitly (inventory + identity counts); it is never silently
    dropped, and a phase with remaining work never claims complete research.
    """

    tasks: tuple[ResearchTask, ...]
    remaining: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


# --- output contract (pydantic twin of the checked-in JSON schema) -----------


class _ResearchCell(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    locator: str = Field(min_length=1, max_length=256)
    quote: str = Field(min_length=1, max_length=512)


class RouterModelTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=200)
    index: int = Field(ge=0, le=100000)
    pricing: dict[str, _ResearchCell] = Field(default_factory=dict, max_length=32)
    context_length: _ResearchCell | None = None
    max_output_tokens: _ResearchCell | None = None


class OpenAiTierTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    line: int = Field(ge=0, le=1000000)
    cells: dict[str, _ResearchCell] = Field(default_factory=dict, max_length=32)


class OpenAiPricingModelTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=200)
    tiers: dict[str, OpenAiTierTranscription] = Field(default_factory=dict, max_length=4)


class DocsPageModelTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=200)
    context_length: _ResearchCell | None = None
    max_output_tokens: _ResearchCell | None = None


class ResearchOutput(BaseModel):
    """Strict typed twin of the packaged research-output.schema.json
    (draft 2020-12). ``task`` selects the per-model shape; unknown extras,
    extra models, or out-of-bounds cells are validation errors."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_id: str = Field(alias="schema", min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=64)
    models: list[Any] = Field(default_factory=list, max_length=MAX_RESEARCH_MODELS_PER_TASK)

    @classmethod
    def parse_task(cls, raw: Mapping[str, Any] | bytes | str) -> "ResearchOutput":
        if isinstance(raw, (bytes, str)):
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            try:
                data: Any = json.loads(text)
            except (ValueError, UnicodeDecodeError):
                raise ValueError("research output is not valid JSON") from None
        else:
            data = dict(raw)
        if not isinstance(data, dict):
            raise ValueError("research output must be a JSON object")
        output = cls.model_validate(data)
        kind = output.task
        if kind not in _TASK_KINDS:
            raise ValueError(f"unknown research task kind {kind!r}")
        if output.schema_id != RESEARCH_OUTPUT_SCHEMA_VERSION:
            raise ValueError(f"unsupported research output schema {output.schema_id!r}")
        model_cls = {
            TASK_OPENROUTER: RouterModelTranscription,
            TASK_OPENAI_PRICING: OpenAiPricingModelTranscription,
            TASK_DOCS_PAGE: DocsPageModelTranscription,
        }[kind]
        for item in output.models:
            try:
                model_cls.model_validate(item)
            except ValidationError as exc:
                raise ValueError(
                    f"research model transcription invalid: {exc.error_count()} error(s)"
                ) from None
        return output


def load_research_output(raw: bytes) -> ResearchOutput:
    """Validate the bounded single result file (never prose, never SQL)."""
    if len(raw) > MAX_TASK_JSON_BYTES:
        raise ValueError("research output exceeds the byte bound")
    return ResearchOutput.parse_task(raw)


# --- planning (parent-owned eligibility scope) -------------------------------


def _bounded_candidate_chunks(models: Sequence[str]) -> list[tuple[str, ...]]:
    models = tuple(models)
    return [
        models[i : i + MAX_RESEARCH_MODELS_PER_TASK]
        for i in range(0, len(models), MAX_RESEARCH_MODELS_PER_TASK)
    ]


def plan_snapshot_tasks(
    *,
    openrouter_bytes: bytes | None,
    openrouter_parse: se.SnapshotParse | None,
    openai_pricing_bytes: bytes | None,
    openai_pricing_parse: se.SnapshotParse | None,
    model_include: frozenset[str] = frozenset(),
) -> ResearchPlan:
    """Plan the snapshot-phase research tasks from the captured bytes.

    Candidates are ONLY unresolved eligible standard-v1 facts: a row the
    deterministic parse left without a limit whose raw bytes DO carry it, or
    a model in a snapshot whose deterministic parse failed (the raw bytes
    are still the only evidence). Index-only IDs, fetch failures, policy
    denials and explicit selections are never widened here. Eligible
    candidates beyond the bundle task bound are returned in
    :attr:`ResearchPlan.remaining` (explicit inventory), never dropped.
    """
    tasks: list[ResearchTask] = []
    remaining: list[tuple[str, str, tuple[str, ...]]] = []
    # --- OpenRouter ---------------------------------------------------------
    if openrouter_bytes is not None and openrouter_parse is not None:
        candidates: list[str] = []
        if openrouter_parse.ok:
            # parsed-but-incomplete: deterministic row missing a limit that
            # the raw bytes actually carry (a grammar the parent can ground).
            for row in sorted(openrouter_parse.models, key=lambda m: m.model):
                if model_include and row.model not in model_include:
                    continue
                missing = [
                    name
                    for name, value in (
                        ("model:context_length", row.context_length),
                        ("model:max_output_tokens", row.max_output_tokens),
                    )
                    if value is None
                ]
                if not missing:
                    continue
                try:
                    context = rg.resolve_router_row(openrouter_bytes, row.model)
                except rg.GroundingError:
                    continue  # raw bytes do not resolve: nothing to ground
                has_raw = (
                    ("model:context_length" in missing and context.context_length is not None)
                    or ("model:max_output_tokens" in missing and context.max_output_tokens is not None)
                )
                if has_raw:
                    candidates.append(row.model)
        else:
            # deterministic parse failed: enumerate raw model IDs (bounded,
            # parent-side) and pre-filter to plausible eligible rows.
            try:
                payload = se.loads_raw_snapshot_json(openrouter_bytes, kind="openrouter_models_api")
            except Exception:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                for row in payload["data"]:
                    if not isinstance(row, dict):
                        continue
                    model_id = row.get("id")
                    if not isinstance(model_id, str) or not model_id:
                        continue
                    if model_include and model_id not in model_include:
                        continue
                    architecture = row.get("architecture")
                    if not (
                        isinstance(architecture, Mapping)
                        and "text" in tuple(architecture.get("input_modalities") or ())
                        and "text" in tuple(architecture.get("output_modalities") or ())
                    ):
                        continue
                    pricing = row.get("pricing")
                    if not (
                        isinstance(pricing, Mapping)
                        and isinstance(pricing.get("prompt"), str)
                        and isinstance(pricing.get("completion"), str)
                    ):
                        continue
                    deprecation = row.get("deprecation")
                    if isinstance(deprecation, Mapping) and deprecation.get("is_deprecated") is True:
                        continue
                    candidates.append(model_id)
        chunks = _bounded_candidate_chunks(candidates)
        budget = MAX_RESEARCH_TASKS - len(tasks)
        for chunk in chunks[:budget]:
            tasks.append(
                ResearchTask(
                    task=TASK_OPENROUTER,
                    source_key=f"openrouter|{_CATALOG_MODEL}|{TASK_OPENROUTER}",
                    provider="openrouter",
                    models=chunk,
                    evidence=openrouter_bytes,
                    content_sha256=hashlib.sha256(openrouter_bytes).hexdigest(),
                    requested_fields=("pricing", "model:context_length", "model:max_output_tokens"),
                )
            )
        leftover = tuple(m for chunk in chunks[budget:] for m in chunk)
        if leftover:
            remaining.append(
                (f"openrouter|{_CATALOG_MODEL}|{TASK_OPENROUTER}", "openrouter", leftover)
            )
    # --- OpenAI pricing docs --------------------------------------------------
    if (
        openai_pricing_bytes is not None
        and openai_pricing_parse is not None
        and not openai_pricing_parse.ok
    ):
        try:
            context = rg.resolve_openai_pricing_snapshot(openai_pricing_bytes)
        except rg.GroundingError:
            context = None
        if context is not None:
            candidates = sorted(
                {
                    model
                    for (tier, model) in context.rows
                    if tier == "standard" and model not in context.conflicting_models
                }
            )
            if model_include:
                candidates = [m for m in candidates if m in model_include]
            chunks = _bounded_candidate_chunks(candidates)
            budget = MAX_RESEARCH_TASKS - len(tasks)
            for chunk in chunks[:budget]:
                tasks.append(
                    ResearchTask(
                        task=TASK_OPENAI_PRICING,
                        source_key=f"openai|{_CATALOG_MODEL}|{TASK_OPENAI_PRICING}",
                        provider="openai",
                        models=chunk,
                        evidence=openai_pricing_bytes,
                        content_sha256=hashlib.sha256(openai_pricing_bytes).hexdigest(),
                        requested_fields=("pricing:",),
                    )
                )
            leftover = tuple(m for chunk in chunks[budget:] for m in chunk)
            if leftover:
                remaining.append(
                    (f"openai|{_CATALOG_MODEL}|{TASK_OPENAI_PRICING}", "openai", leftover)
                )
    return ResearchPlan(tasks=tuple(tasks), remaining=tuple(remaining))


def plan_docs_page_tasks(
    pages: Sequence[tuple[str, bytes, se.ParsedModel]],
    *,
    model_include: frozenset[str] = frozenset(),
) -> ResearchPlan:
    """Plan per-model model-doc-page tasks for pages that parsed but left a
    limit unresolved although the page bytes state it in a readable layout.
    A page that was never fetched or that failed deterministic parsing is
    never a candidate (its other gates are unknown).

    Feasibility: the complete-row grounding contract requires a claim for
    EVERY limit the page states, so a page is a candidate only when every
    limit the parent can resolve on the page is one of its UNRESOLVED
    fields. Pages whose remaining eligible models exceed the task bound are
    returned in :attr:`ResearchPlan.remaining`, never dropped."""
    tasks: list[ResearchTask] = []
    remaining: list[tuple[str, str, tuple[str, ...]]] = []
    for model_id, evidence, page in pages:
        if model_include and model_id not in model_include:
            continue
        missing = [
            name
            for name, value in (
                ("model:context_length", page.context_length),
                ("model:max_output_tokens", page.max_output_tokens),
            )
            if value is None
        ]
        if not missing:
            continue
        try:
            context = rg.resolve_doc_page(evidence)
        except rg.GroundingError:
            continue
        if context.model_id != model_id:
            continue  # page identity mismatch: never ground under another model
        resolvable: set[str] = set()
        for name, candidates in (
            ("model:context_length", context.context_candidates),
            ("model:max_output_tokens", context.maxout_candidates),
        ):
            if len({value for _line, value in candidates}) == 1:
                resolvable.add(name)
        if not resolvable:
            continue  # the page bytes state no resolvable limit: nothing to ground
        if not resolvable <= set(missing):
            continue  # the page states a limit the deterministic pass already
            # resolved: re-transcribing it is not an eligible unresolved fact,
            # and the complete-row contract would make the task unsatisfiable
        if len(tasks) >= MAX_RESEARCH_TASKS:
            remaining.append((f"openai|{model_id}|docs_page", "openai", (model_id,)))
            continue
        tasks.append(
            ResearchTask(
                task=TASK_DOCS_PAGE,
                source_key=f"openai|{model_id}|docs_page",
                provider="openai",
                models=(model_id,),
                evidence=evidence,
                content_sha256=hashlib.sha256(evidence).hexdigest(),
                requested_fields=tuple(missing),
            )
        )
    return ResearchPlan(tasks=tuple(tasks), remaining=tuple(remaining))


# --- per-model grounding into sealed facts -----------------------------------


@dataclass
class _TaskGrounded:
    rows: dict[tuple[str, str], list[se.ParsedModel]]
    facts: list[ResearchGroundedFact]
    rejected: dict[tuple[str, str], str]
    docs_resolved: dict[str, dict[str, int]]
    scope_violations: int
    returned_cells: int  # claimed transcription cells (accepted + rejected)
    accepted_cells: int  # cells of grounded models (all-or-none per model)


def _fact(task: ResearchTask, model_id: str, cell: rg.GroundedCell) -> ResearchGroundedFact:
    return ResearchGroundedFact(
        source_key=task.source_key,
        provider=task.provider,
        model=model_id,
        field=cell.field,
        locator=cell.locator,
        quote=cell.quote,
        value=cell.value,
        unit=cell.unit,
        currency=cell.currency,
    )


def _claimed_cell_count(task: ResearchTask, trans_model: Any) -> int:
    """Number of transcription cells ONE model claims (counting unit)."""
    if task.task == TASK_OPENROUTER:
        return (
            len(trans_model.pricing)
            + (1 if trans_model.context_length is not None else 0)
            + (1 if trans_model.max_output_tokens is not None else 0)
        )
    if task.task == TASK_OPENAI_PRICING:
        return sum(len(t.cells) for t in trans_model.tiers.values())
    return (
        (1 if trans_model.context_length is not None else 0)
        + (1 if trans_model.max_output_tokens is not None else 0)
    )


def _ground_task(task: ResearchTask, output: ResearchOutput) -> _TaskGrounded:
    """Parent-ground every claimed model of ONE task (per-model honesty).

    Out-of-scope claims are counted and dropped (never grounded); one bad
    transcription rejects only its own model (all its claimed cells)."""
    scoped = set(task.models)
    rows: dict[tuple[str, str], list[se.ParsedModel]] = {}
    facts: list[ResearchGroundedFact] = []
    rejected: dict[tuple[str, str], str] = {}
    docs_resolved: dict[str, dict[str, int]] = {}
    scope_violations = 0
    returned_cells = 0
    accepted_cells = 0
    seen: set[str] = set()
    for item in output.models:
        if task.task == TASK_OPENROUTER:
            trans_model = RouterModelTranscription.model_validate(item)
            model_id = trans_model.model
        elif task.task == TASK_OPENAI_PRICING:
            trans_model = OpenAiPricingModelTranscription.model_validate(item)
            model_id = trans_model.model
        else:
            trans_model = DocsPageModelTranscription.model_validate(item)
            model_id = trans_model.model
        if model_id not in scoped:
            scope_violations += 1
            continue
        claimed = _claimed_cell_count(task, trans_model)
        if model_id in seen:
            rejected[(task.provider, model_id)] = "model_duplicate"
            returned_cells += claimed
            continue
        seen.add(model_id)
        returned_cells += claimed
        try:
            if task.task == TASK_OPENROUTER:
                trans = rg.RouterTranscription(
                    model=model_id,
                    claimed_index=trans_model.index,
                    pricing_cells={k: (c.locator, c.quote) for k, c in trans_model.pricing.items()},
                    context_length=(
                        (trans_model.context_length.locator, trans_model.context_length.quote)
                        if trans_model.context_length is not None
                        else None
                    ),
                    max_output_tokens=(
                        (trans_model.max_output_tokens.locator, trans_model.max_output_tokens.quote)
                        if trans_model.max_output_tokens is not None
                        else None
                    ),
                )
                row, cells = rg.ground_router_row(task.evidence, trans)
                rows[(task.provider, model_id)] = [row]
            elif task.task == TASK_OPENAI_PRICING:
                tier_trans = {
                    tier: rg.OpenAiTierTranscription(
                        line=t.line,
                        cells={h: (c.locator, c.quote) for h, c in t.cells.items()},
                    )
                    for tier, t in trans_model.tiers.items()
                }
                tier_rows, cells = rg.ground_openai_pricing_row(task.evidence, model_id, tier_trans)
                rows[(task.provider, model_id)] = list(tier_rows)
            else:
                context_trans = (
                    (trans_model.context_length.locator, trans_model.context_length.quote)
                    if trans_model.context_length is not None
                    else None
                )
                maxout_trans = (
                    (trans_model.max_output_tokens.locator, trans_model.max_output_tokens.quote)
                    if trans_model.max_output_tokens is not None
                    else None
                )
                for name, trans in (
                    ("model:context_length", context_trans),
                    ("model:max_output_tokens", maxout_trans),
                ):
                    if trans is not None and name not in task.requested_fields:
                        scope_violations += 1
                        rejected[(task.provider, model_id)] = f"scope_violation:{name}"
                        break
                else:
                    resolved, cells = rg.ground_doc_page(
                        task.evidence, model_id, context_trans, maxout_trans
                    )
                    docs_resolved[model_id] = resolved
                    rows[(task.provider, model_id)] = []
        except rg.GroundingError as exc:
            rejected[(task.provider, model_id)] = exc.code
            continue
        facts.extend(_fact(task, model_id, cell) for cell in cells)
        accepted_cells += len(cells)
    return _TaskGrounded(
        rows=rows,
        facts=facts,
        rejected=rejected,
        docs_resolved=docs_resolved,
        scope_violations=scope_violations,
        returned_cells=returned_cells,
        accepted_cells=accepted_cells,
    )


# --- execution phase ----------------------------------------------------------


@dataclass
class ResearchPhaseOutcome:
    """One research phase (snapshot tasks or page tasks) measured result."""

    identity: ResearchIdentity
    grounded_rows: dict[tuple[str, str], list[se.ParsedModel]] = field(default_factory=dict)
    facts: list[ResearchGroundedFact] = field(default_factory=list)
    docs_resolved: dict[str, dict[str, int]] = field(default_factory=dict)
    rejected: dict[tuple[str, str], str] = field(default_factory=dict)
    task_count: int = 0
    scope_violations: int = 0
    cleanup_errors: tuple[str, ...] = ()


def _cli_identity(cfg: ResearchConfig) -> tuple[str, str]:
    """Measured CLI version + verified binary hash (parent-side; help/version
    only - never a model probe).

    Measured FRESH for every phase: there is no path-keyed cache, because a
    binary installed at the same path can change between invocations and a
    stale identity would mislabel the executed binary."""
    sha = iso.verify_cli_binary(cfg.cli_bin)
    version = "N/A"
    try:
        proc = subprocess.run(
            [cfg.cli_bin, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
        first = (proc.stdout or proc.stderr or "").strip().splitlines()
        if first:
            version = first[0].strip()[:32] or "N/A"
    except (OSError, subprocess.TimeoutExpired):
        version = "N/A"
    return version, sha


def _asset_file(name: str) -> Path:
    # 184 (R2): canonical packaged asset resolved through
    # importlib.resources, so it works identically in a source checkout
    # and in a wheel installation outside the checkout. Resolved lazily
    # at use time; a missing asset refuses the phase (UNAVAILABLE) and is
    # never replaced by a repository-relative fallback or invented
    # constant.
    from importlib.resources import files

    return Path(files("slaif_gateway.resources.catalog_refresh").joinpath(name))


def _template_path() -> Path:
    return _asset_file("research-instructions.md")


def _schema_path() -> Path:
    return _asset_file("research-output.schema.json")


def _identity_base(cfg: ResearchConfig, template_bytes: bytes) -> dict[str, Any]:
    cli_version, cli_sha = _cli_identity(cfg)
    return {
        "codex_version": cli_version,
        "cli_sha256": cli_sha,
        "prompt_version": RESEARCH_TEMPLATE_VERSION,
        # bound to the EXACT template bytes copied as the task-local AGENTS.md
        "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
        "output_schema_version": RESEARCH_OUTPUT_SCHEMA_VERSION,
        "extractor_version": RESEARCH_EXTRACTOR_ID,
        "tool_version": cfg.tool_version,
        "mock_model": cfg.mock_model,
    }


def _not_run(cfg: ResearchConfig) -> ResearchPhaseOutcome:
    return ResearchPhaseOutcome(
        identity=ResearchIdentity(
            status="NOT_RUN", extractor_version=RESEARCH_EXTRACTOR_ID, tool_version=cfg.tool_version
        )
    )


def _unavailable(cfg: ResearchConfig, code: str) -> ResearchPhaseOutcome:
    return ResearchPhaseOutcome(
        identity=ResearchIdentity(
            status="UNAVAILABLE",
            failure_code=code,
            extractor_version=RESEARCH_EXTRACTOR_ID,
            tool_version=cfg.tool_version,
        )
    )


def run_research_phase(
    cfg: ResearchConfig,
    plan: ResearchPlan,
    facts_bound: int = MAX_RESEARCH_FACTS,
) -> ResearchPhaseOutcome:
    """Execute the planned tasks in the enforced boundary and parent-ground
    every result.

    Honesty/bound rules (existing R1/R2/R3 requirements):

    - every phase uses a NEW private owned workspace under the configured
      root; pre-existing task state is never accepted (a collision refuses
      the phase) and only the tree this invocation created is removed;
    - the checked-in template/schema bytes are read once and the identity
      is bound to those EXACT bytes; a missing asset refuses the phase
      (UNAVAILABLE) - never an invented version-constant identity;
    - ``facts_requested`` is derived from the PARENT PLAN before execution
      (requested model/field groups per planned model); returned/accepted/
      rejected are measured from the actual results;
    - when the complete accepted result would exceed the remaining bundle
      bound (``facts_bound``), the phase FAILS with ``facts_bound_exhausted``
      instead of silently truncating;
    - any child failure fails the WHOLE phase (no partial research data);
      a boundary refusal BEFORE any invocation is UNAVAILABLE, while a
      refusal AFTER earlier tasks executed is a measured FAILED that
      preserves the execution history (version, timing, exit record,
      scope) with all research output discarded;
    - a post-execution cleanup failure is likewise FAILED with the
      measured execution history preserved; only a pre-invocation phase
      keeps a UNAVAILABLE identity.
    """
    if not cfg.enabled or not plan.tasks:
        return _not_run(cfg)
    if not cfg.cli_bin or not cfg.model_name:
        return _unavailable(cfg, "research_configuration_incomplete")

    # Exact packaged asset bytes (importlib.resources resolution); a
    # missing asset - file absent OR asset package missing (broken
    # install) - refuses the phase as UNAVAILABLE; the identity may never
    # be an invented constant and resolution errors never escape the
    # phase.
    try:
        template_bytes = _template_path().read_bytes()
    except (OSError, ModuleNotFoundError):
        return _unavailable(cfg, "research_template_missing")
    try:
        schema_bytes = _schema_path().read_bytes()
    except (OSError, ModuleNotFoundError):
        return _unavailable(cfg, "research_schema_missing")

    # New private owned per-invocation workspace; placement checked BEFORE
    # any writes, ownership verified after creation, pre-existing state is
    # never accepted.
    base_dir = Path(cfg.workspace_root) / "slaif-research" / f"run-{secrets.token_hex(8)}"
    try:
        if cfg.repo_root:
            if base_dir.resolve().is_relative_to(Path(cfg.repo_root).resolve()):
                return _unavailable(cfg, "workspace_in_repo")
        base_dir.parent.mkdir(parents=True, exist_ok=True)
        base_dir.mkdir(mode=0o700, exist_ok=False)
        st = base_dir.stat()
        if (
            st.st_uid != os.getuid()
            or st.st_gid != os.getgid()
            or (st.st_mode & 0o777) != 0o700
        ):
            return _unavailable(cfg, "workspace_ownership")
    except FileExistsError:
        return _unavailable(cfg, "workspace_collision")
    except OSError:
        return _unavailable(cfg, "workspace_unavailable")

    # Measured identity BEFORE the task loop so an ordinary execution
    # exception can never be presented with a missing/partial identity.
    try:
        base = _identity_base(cfg, template_bytes)
    except iso._BoundaryUnavailable:
        return _unavailable(cfg, "cli_unavailable")

    facts_requested = sum(len(t.models) * len(t.requested_fields) for t in plan.tasks)
    phase_start = time.monotonic()
    cleanup_errors: tuple[str, ...] = ()
    try:
        try:
            if base.get("codex_version") == "N/A":
                # The binary was hashed but could not report its own
                # version (for example it is not executable): the
                # qualified CLI boundary is not proven, so the phase
                # refuses BEFORE any invocation with the safe refusal
                # code. A FAILED identity for an unversioned CLI is
                # impossible by the identity contract (SUCCEEDED/FAILED
                # require the actual measured version), so this refusal
                # must not fall through to the measured-failure path.
                outcome = _unavailable(cfg, "cli_unversioned")
            else:
                outcome = _run_phase_tasks(
                    cfg, plan, base_dir, template_bytes, schema_bytes,
                    facts_bound, base,
                )
        except Exception as exc:
            # Last resort (an identity-construction defect or a replaced
            # loop): the CLI WAS verified and the phase was attempted, so
            # this is a measured FAILED - not a pre-invocation refusal -
            # preserving the measured identity, plan-derived requested
            # scope, and measured phase wall time; no research output.
            outcome = ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=facts_requested,
                    elapsed_ms=int((time.monotonic() - phase_start) * 1000),
                    child_exit_code=-1,  # no child exit was captured
                    failure_code=f"execution_error:{type(exc).__name__}",
                    tasks_planned=len(plan.tasks),
                    tasks_unattempted=len(plan.tasks),
                )
            )
    finally:
        # Remove ONLY the workspace tree this invocation created; a failure
        # to do so is observable, never silently marked removed.
        try:
            shutil.rmtree(base_dir)
        except OSError as exc:
            cleanup_errors = (f"workspace:{type(exc).__name__}",)
    if cleanup_errors:
        # Required owned-resource cleanup failed. A POST-execution failure
        # is FAILED with the measured execution history preserved (the
        # identity is exactly what ran: version, binary hash, template,
        # timing, exit record, scope); ALL research output is discarded.
        # Only a phase that never invoked the CLI keeps its pre-invocation
        # UNAVAILABLE refusal, with the cleanup failure recorded.
        ident = outcome.identity
        if ident.status in ("SUCCEEDED", "FAILED"):
            failure_code = "cleanup_incomplete"
            if ident.failure_code:
                failure_code = f"cleanup_incomplete+{ident.failure_code}"
            outcome = ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=ident.facts_requested,
                    elapsed_ms=ident.elapsed_ms,
                    child_exit_code=ident.child_exit_code,
                    failure_code=failure_code,
                    tasks_planned=ident.tasks_planned,
                    tasks_unattempted=ident.tasks_unattempted,
                ),
                cleanup_errors=cleanup_errors,
            )
        else:
            outcome = ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    status="UNAVAILABLE",
                    failure_code="cleanup_incomplete",
                    extractor_version=RESEARCH_EXTRACTOR_ID,
                    tool_version=cfg.tool_version,
                ),
                cleanup_errors=cleanup_errors,
            )
    elif outcome.cleanup_errors:
        outcome = ResearchPhaseOutcome(
            identity=outcome.identity,
            cleanup_errors=cleanup_errors,
        )
    return outcome


def _run_phase_tasks(
    cfg: ResearchConfig,
    plan: ResearchPlan,
    base_dir: Path,
    template_bytes: bytes,
    schema_bytes: bytes,
    facts_bound: int,
    base: dict[str, Any],
) -> ResearchPhaseOutcome:
    """The task loop of :func:`run_research_phase` (always returns)."""
    # Parent-planned requested scope, measured BEFORE any execution: the
    # requested model/field groups of every planned model (a failed first
    # child therefore still reports the full planned scope).
    facts_requested = sum(len(t.models) * len(t.requested_fields) for t in plan.tasks)
    exit_codes: list[int] = []
    result_shas: list[str] = []
    elapsed_total = 0
    facts_returned = 0
    facts_accepted = 0
    facts_rejected = 0
    grounded: dict[tuple[str, str], list[se.ParsedModel]] = {}
    all_facts: list[ResearchGroundedFact] = []
    rejected: dict[tuple[str, str], str] = {}
    docs_resolved: dict[str, dict[str, int]] = {}
    scope_violations = 0
    executed = 0

    def _post_exec_failure(failure_code: str) -> ResearchPhaseOutcome:
        """A failure AFTER at least one task executed: a measured FAILED
        that preserves the known execution history (measured identity,
        cumulative timing, last exit record, planned scope) while ALL
        research output is discarded. Only a phase that never invoked the
        CLI keeps the plain pre-invocation refusal."""
        return ResearchPhaseOutcome(
            identity=ResearchIdentity(
                **base,
                status="FAILED",
                facts_requested=facts_requested,
                elapsed_ms=elapsed_total,
                child_exit_code=exit_codes[-1] if exit_codes else 0,
                failure_code=failure_code,
                tasks_planned=len(plan.tasks),
                tasks_unattempted=len(plan.tasks) - executed,
            ),
            task_count=len(plan.tasks),
            scope_violations=scope_violations,
        )

    for index, task in enumerate(plan.tasks):
        task_dir = base_dir / f"task-{index:02d}-{hashlib.sha256(task.source_key.encode()).hexdigest()[:12]}"
        mkdir_code = None
        try:
            task_dir.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError:
            mkdir_code = "workspace_collision"
        except OSError:
            mkdir_code = "workspace_unavailable"
        if mkdir_code is not None:
            # a workspace failure AFTER earlier tasks executed is a
            # measured FAILED that preserves their history, never a blank
            # pre-invocation UNAVAILABLE
            if executed == 0:
                return _unavailable(cfg, mkdir_code)
            return _post_exec_failure(mkdir_code)
        for sub in ("inputs", "outputs", "config", "home"):
            (task_dir / sub).mkdir(exist_ok=True)
        evidence_ext = {TASK_OPENROUTER: ".json", TASK_OPENAI_PRICING: ".md", TASK_DOCS_PAGE: ".md"}[task.task]
        evidence_path = task_dir / "inputs" / f"evidence{evidence_ext}"
        try:
            evidence_path.write_bytes(task.evidence)
            task_json = task_dir / "inputs" / "task.json"
            task_json.write_text(
                json.dumps(
                    {
                        "schema": RESEARCH_OUTPUT_SCHEMA_VERSION,
                        "task": task.task,
                        "models": list(task.models),
                        "requested_fields": list(task.requested_fields),
                        "instructions_version": RESEARCH_TEMPLATE_VERSION,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            agent_md = task_dir / "AGENTS.md"
            agent_md.write_bytes(template_bytes)
            schema_path = task_dir / "inputs" / "output-schema.json"
            schema_path.write_bytes(schema_bytes)
        except OSError:
            if executed == 0:
                return _unavailable(cfg, "workspace_write_failed")
            return _post_exec_failure("workspace_write_failed")

        upstream_key = ""
        if not cfg.mock_model:
            upstream_key = os.environ.get(cfg.model_auth_env, "") if cfg.model_auth_env else ""
            if not cfg.model_endpoint or not upstream_key:
                if executed == 0:
                    return _unavailable(cfg, "research_endpoint_unconfigured")
                return _post_exec_failure("research_endpoint_unconfigured")
        execution = iso.execute_task(
            task_dir,
            task_name=task.task,
            models_json=json.dumps(list(task.models)),
            evidence_path=evidence_path,
            agent_md=agent_md,
            output_schema=schema_path,
            cli_bin=cfg.cli_bin,
            cli_sha256=base["cli_sha256"],
            model_name=cfg.model_name,
            mode="mock" if cfg.mock_model else "forward",
            canned_result_json=cfg.mock_result_json if cfg.mock_model else None,
            upstream_base=cfg.model_endpoint if not cfg.mock_model else "",
            upstream_key=upstream_key,
            upstream_http_allowed=cfg.upstream_http_allowed,
            mock_tool_sequence_sse=(
                cfg.mock_tool_sequence_sse.encode("utf-8")
                if cfg.mock_model and cfg.mock_tool_sequence_sse is not None
                else None
            ),
            mock_body_markers=cfg.mock_body_markers if cfg.mock_model else None,
            # Qualify the real CLI to the minimal reviewed local tool
            # catalog (each override verified against the actual synthetic
            # request): hosted web-search (provider authority), multi-agent
            # delegation, goal APIs, and the image tool are disabled; the
            # relay gate independently refuses anything outside the catalog
            extra_cli_args=(
                "-c", 'web_search="disabled"',
                "-c", "features.multi_agent=false",
                "-c", "features.goals=false",
                "--disable", "view_image",
            ),
            timeout_seconds=cfg.timeout_seconds,
            repo_root=Path(cfg.repo_root) if cfg.repo_root else None,
        )
        elapsed_total += execution.elapsed_ms
        if execution.status == "unavailable":
            refusal = execution.failure_code or "boundary_unavailable"
            if executed == 0:
                # No CLI invocation occurred in this phase: the enforcement
                # boundary was refused BEFORE any invocation, so nothing was
                # measured and the safe refusal code stands alone.
                return _unavailable(cfg, refusal)
            # A LATER-task boundary refusal must not erase the earlier
            # executed-task history (shared post-execution failure return).
            return _post_exec_failure(refusal)
        if execution.status == "child_failure":
            failure_code = execution.failure_code or "child_failure"
            exit_codes.append(execution.exit_code if execution.exit_code is not None else -1)
            # a failed child fails the whole phase: no partial research
            # data, and the full planned scope is still reported
            return ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=facts_requested,
                    elapsed_ms=elapsed_total,
                    child_exit_code=exit_codes[0],
                    failure_code=failure_code,
                    tasks_planned=len(plan.tasks),
                    tasks_unattempted=len(plan.tasks) - executed,
                ),
                task_count=len(plan.tasks),
                scope_violations=scope_violations,
            )
        try:
            output = load_research_output(execution.output_bytes or b"")
        except ValueError:
            return ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=facts_requested,
                    elapsed_ms=elapsed_total,
                    child_exit_code=0,
                    failure_code="malformed_output",
                    tasks_planned=len(plan.tasks),
                    tasks_unattempted=len(plan.tasks) - executed,
                ),
                task_count=len(plan.tasks),
                scope_violations=scope_violations,
            )
        try:
            grounded_task = _ground_task(task, output)
        except Exception as exc:  # defensive: a crash is never a success
            return ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=facts_requested,
                    elapsed_ms=elapsed_total,
                    child_exit_code=0,
                    failure_code=f"grounding_error:{type(exc).__name__}",
                    tasks_planned=len(plan.tasks),
                    tasks_unattempted=len(plan.tasks) - executed,
                ),
                task_count=len(plan.tasks),
                scope_violations=scope_violations,
            )
        executed += 1
        scope_violations += grounded_task.scope_violations
        facts_returned += grounded_task.returned_cells
        facts_accepted += grounded_task.accepted_cells
        facts_rejected += grounded_task.returned_cells - grounded_task.accepted_cells
        result_shas.append(execution.output_sha256 or "")
        exit_codes.append(0)
        for key, value in grounded_task.rows.items():
            if value:
                grounded.setdefault(key, []).extend(value)
        all_facts.extend(grounded_task.facts)
        rejected.update(grounded_task.rejected)
        docs_resolved.update(grounded_task.docs_resolved)
        # No silent truncation: the complete accepted result must fit the
        # remaining bundle bound or the phase fails honestly.
        if len(all_facts) > facts_bound:
            return ResearchPhaseOutcome(
                identity=ResearchIdentity(
                    **base,
                    status="FAILED",
                    facts_requested=facts_requested,
                    elapsed_ms=elapsed_total,
                    child_exit_code=0,
                    failure_code="facts_bound_exhausted",
                    tasks_planned=len(plan.tasks),
                    tasks_unattempted=len(plan.tasks) - executed,
                ),
                task_count=len(plan.tasks),
                scope_violations=scope_violations,
            )
    return ResearchPhaseOutcome(
        identity=ResearchIdentity(
            **base,
            status="SUCCEEDED",
            facts_requested=facts_requested,
            facts_returned=facts_returned,
            facts_accepted=facts_accepted,
            facts_rejected=facts_rejected,
            elapsed_ms=elapsed_total,
            child_exit_code=exit_codes[0] if exit_codes else 0,
            result_sha256=hashlib.sha256(";".join(sorted(set(result_shas))).encode()).hexdigest(),
            tasks_planned=len(plan.tasks),
            tasks_unattempted=0,
        ),
        grounded_rows=grounded,
        facts=all_facts,
        rejected=rejected,
        docs_resolved=docs_resolved,
        task_count=len(plan.tasks),
        scope_violations=scope_violations,
    )


def merge_phase_identities(first: ResearchIdentity, second: ResearchIdentity) -> ResearchIdentity:
    """Aggregate two phases (snapshot + pages) into the bundle identity."""
    if first.status == "NOT_RUN":
        return second
    if second.status == "NOT_RUN":
        return first
    if first.status != "SUCCEEDED" or second.status != "SUCCEEDED":
        return first if first.status != "SUCCEEDED" else second
    return ResearchIdentity(
        status="SUCCEEDED",
        codex_version=first.codex_version,
        cli_sha256=first.cli_sha256,
        prompt_version=first.prompt_version,
        template_sha256=first.template_sha256,
        output_schema_version=first.output_schema_version,
        extractor_version=first.extractor_version,
        tool_version=first.tool_version,
        facts_requested=first.facts_requested + second.facts_requested,
        facts_returned=first.facts_returned + second.facts_returned,
        facts_accepted=first.facts_accepted + second.facts_accepted,
        facts_rejected=first.facts_rejected + second.facts_rejected,
        elapsed_ms=(first.elapsed_ms or 0) + (second.elapsed_ms or 0),
        child_exit_code=first.child_exit_code,
        result_sha256=hashlib.sha256(
            f"{first.result_sha256 or ''};{second.result_sha256 or ''}".encode()
        ).hexdigest(),
        mock_model=first.mock_model and second.mock_model,
        tasks_planned=first.tasks_planned + second.tasks_planned,
        tasks_unattempted=first.tasks_unattempted + second.tasks_unattempted,
    )
