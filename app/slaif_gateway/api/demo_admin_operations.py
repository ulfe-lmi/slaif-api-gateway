"""Objective 224-t: demo-only Operations index and captured
process-configuration page, from one verified copy.

A small, purpose-built router mounted by ``create_demo_app`` ONLY,
BEFORE the normal operations router, so the two exact paths
``GET /admin/operations/`` and
``GET /admin/operations/process-configuration`` are served by these
demo handlers in the demo process while the normal handlers (which
read live API-process ``Settings`` and app-global loaded profiles)
are never reached for those paths there. Every other operations path
(diagnostics, compatibility, replay-maintenance, subpaths) stays
mounted as before and remains default-denied by the central demo
gate; every unsafe method on ``/admin`` remains the unchanged uniform
204 cut before body parsing and dispatch.

The process-configuration page reads ONLY the worker-captured,
sanitized process-configuration projection leaf
(``configuration/process-configuration.json``, kind
``process_configuration``) from this visitor's exact verified copy.
The read uses the gate's SAME request-local copy engine
(``get_sessionmaker_from_app`` on ``request.state.demo_admin``) in
one SELECT-only transaction that re-verifies
``current_database()`` and ``transaction_read_only`` before the
metadata lookup. The closed metadata law (exact kind, nonnegative
size under the 1 MiB cap, canonical SHA256, database-computed
``octet_length`` equal to the claimed byte count, finite
representable capture time) runs BEFORE any body fetch; the bounded
body fetch re-asserts every condition as BOUND parameters, and the
fetched bytes are re-verified (exact length + SHA256) and re-proven
against the 223 typed verifier law before projection. Any missing
leaf, invalid metadata, bound violation, digest/size mismatch,
verification failure or driver error is one fixed safe 503 with no
input echo. This handler NEVER falls back to ``_settings(request)``,
live ``request.app.state.upstream_llm_profiles``, the live
environment, the app filesystem, the provider network or the source
database for displayed values: the worker process that built the
copy may hold different cached settings than the live API process,
so the page is labeled the worker-observed deployment configuration
captured at copy time (with its own capture time), never the live
API-process cached settings. The package version row is explicitly
labeled the demo web process's LIVE build identity (not a captured
value). The deployed revision and revision provenance were not
captured in this round and render as "not recorded in this demo
snapshot"; the 223-captured upstream LLM profile identities and the
worker-pinned Codex client reference are NOT displayed on this page
yet - never fabricated, never read live. No credential-shaped value, original operator
identity, path, copy name or DSN fragment ever appears in the
response, logs or errors; every demo response stays private
no-store.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from sqlalchemy import select, text

from slaif_gateway import __version__
from slaif_gateway.api.admin import templates
from slaif_gateway.api.admin_operations import (
    _CLEANUP_BATCH_LIMIT,
    _format_fact_map,
    _is_incoming_alias,
    _is_unsafe_lookup_value,
    _withheld_record_fields,
)
from slaif_gateway.db.models import RequestDiagnostic
from slaif_gateway.db.repositories.request_diagnostics import (
    RequestDiagnosticsRepository,
)
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.request_diagnostics import (
    DIAGNOSTIC_LOOKUP_BOUND,
    DiagnosticDisambiguationCandidate,
    DiagnosticLookupOutcome,
    DiagnosticLookupResult,
    DiagnosticsNamespace,
)
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services.configuration_inspection import (
    API_PROCESS_RESTART_SCOPE,
    CONFIG_INSPECTION_ALLOWLIST,
    setting_meaning,
)

router = APIRouter(prefix="/admin/operations", include_in_schema=False)

# The ONE closed worker-published logical name of the
# process-configuration projection (fixed vocabulary, no per-copy
# component) and its closed display cap: the canonical document for
# the finite 45-setting allowlist is a few KiB, so 1 MiB is a tight
# bound enforced BEFORE any body fetch (the worker's own per-file cap
# is looser, so a healthy leaf always fits).
_PROCESS_CONFIG_NAME = dsf._PROC_CONFIG_LOGICAL_NAME
_MAX_PROCESS_CONFIG_BYTES = 1024 * 1024
_MAX_CAPTURE_AT = 253_402_300_800.0  # Worker-published ceiling.
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

_SAFE_INDEX_UNAVAILABLE = (
    "The operations page is unavailable for this demo session."
)
_SAFE_PROCESS_CONFIG_UNAVAILABLE = (
    "The process configuration is unavailable for this demo session."
)

# Truthful demo scope/limitations (224-t): the displayed values are
# the WORKER process's cached Settings at copy time - a different
# process than the live API process, which may hold different cached
# settings - and they are frozen at capture time (changing ambient
# demo-web settings after the copy was built cannot change the page).
_DEMO_SNAPSHOT_SCOPE = (
    "worker-observed deployment configuration captured at copy time - "
    "a finite reviewed allowlist of numeric/boolean settings; not the "
    "live API process's cached settings, not per-key policy, and not "
    "the limits of every worker or the reverse proxy"
)
_DEMO_LIMITATIONS: tuple[str, ...] = (
    "snapshot is the SNAPSHOT WORKER process's cached Settings at copy "
    "time, not the live API process's cached settings; the two "
    "processes may differ",
    "configured/default source comes from the worker process's "
    "model_fields_set at capture time",
    "values are frozen at capture time: changing demo-web or deployment "
    "settings after the copy was built does not change this page",
    "no database, network, broker, or provider access was performed "
    "while displaying this page",
    "no credential values, hosts, source paths or secret file contents "
    "are exposed",
    "the package version row is the demo web process's live build "
    "identity, not a worker-captured value",
    "deployed revision and revision provenance were not captured in "
    "this demo snapshot",
    "the captured upstream LLM profile identities and the worker-pinned "
    "Codex client reference are not displayed on this page yet",
    "a configured database URL is not connectivity or authentication "
    "proof",
    "external reverse-proxy request-size limits are NOT observed by "
    "this page",
)


def _index_not_found() -> Response:
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _index_unavailable() -> Response:
    return HTMLResponse(
        _SAFE_INDEX_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


def _process_config_not_found() -> Response:
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _process_config_unavailable() -> Response:
    return HTMLResponse(
        _SAFE_PROCESS_CONFIG_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


async def _demo_copy_recheck(session_factory: Any, target_db: str) -> bool:
    """One SELECT-only/read-only transaction on the gate's SAME
    request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck (the
    224-p form pages share this law)."""
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            return current == target_db and read_only == "on"
    except Exception:
        return False


@router.get("/", response_class=HTMLResponse)
async def demo_operations_index(request: Request) -> Response:
    """224-t: the demo Operations index (exact path with its REQUIRED
    trailing slash, gate-admitted).

    The static index renders the FAMILIAR operations page with a
    narrow demo branch: it describes the FROZEN copied data of this
    session, links only the pages this demo host already admits, and
    visibly marks the not-yet-admitted operations read pages as
    unavailable (no broken-feature usability is implied; later
    suffixes restore them). Every operational action has no effect
    (the gate's quiet 204 cut ends every unsafe method before any
    body is parsed). One SELECT-only/read-only copy transaction
    performs the independent binding recheck; any query string
    refuses with fixed 404 BEFORE copy access.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _index_not_found()
    # Query law: NO query parameters are defined for the demo
    # operations index; ANY parameter refuses safely (fixed 404, no
    # echo) - the gate already enforces this for the exact path.
    if request.query_params.multi_items():
        return _index_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _index_unavailable()
    if not await _demo_copy_recheck(session_factory, demo.target_db):
        return _index_unavailable()
    response = templates.TemplateResponse(
        request,
        "operations/index.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "demo_admin": True,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/process-configuration", response_class=HTMLResponse)
async def demo_operations_process_configuration(request: Request) -> Response:
    """224-t: the captured worker-observed process-configuration page
    (exact path, NO trailing slash, gate-admitted).

    The page renders the 45 finite allowlist values + configured/
    default provenance from the verified per-login display copy ONLY
    (see the module docstring for the full read law). Any query
    string refuses with fixed 404 BEFORE copy access; every failure
    after copy access is the fixed safe 503.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _process_config_not_found()
    # Query law: NO query parameters are defined for the demo
    # process-configuration page; ANY parameter refuses safely (fixed
    # 404, no echo) - the gate already enforces this for the exact
    # path.
    if request.query_params.multi_items():
        return _process_config_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _process_config_unavailable()
    body: bytes | None = None
    captured: float | None = None
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _process_config_unavailable()
            # Metadata FIRST (parameterized exact logical-name lookup;
            # no SQL identifier interpolation, no pathname). The
            # database computes ``octet_length(body)`` so a corrupt
            # row that CLAIMS a small byte_count while storing an
            # oversized body is refused here, before ANY body bytes
            # are transferred.
            meta = (
                await session.execute(
                    text(
                        "SELECT kind, byte_count, sha256, captured_at, "
                        "octet_length(body) AS actual_bytes "
                        "FROM demo_display.leaves "
                        "WHERE logical_name = :name"
                    ),
                    {"name": _PROCESS_CONFIG_NAME},
                )
            ).first()
            if meta is None:
                # Every worker-built healthy copy carries this
                # REQUIRED leaf; absence means a corrupt or foreign
                # copy -> one fixed safe 503 (never a fabricated page).
                return _process_config_unavailable()
            kind, byte_count, stored_sha, captured_at, actual_bytes = meta
            # Invalid closed metadata: fixed 503. The 1 MiB cap is
            # enforced BEFORE any body fetch.
            if (
                kind != dsf.KIND_PROCESS_CONFIG
                or isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or not 0 <= byte_count <= _MAX_PROCESS_CONFIG_BYTES
                or not isinstance(stored_sha, str)
                or _SHA256_HEX.fullmatch(stored_sha) is None
                or isinstance(actual_bytes, bool)
                or not isinstance(actual_bytes, int)
                or not 0 <= actual_bytes <= _MAX_PROCESS_CONFIG_BYTES
                # A corrupt/incomplete row whose stored body length
                # disagrees with its claimed byte_count is refused
                # here, before any body fetch.
                or actual_bytes != byte_count
                or isinstance(captured_at, bool)
                or not isinstance(captured_at, (int, float))
                or not math.isfinite(float(captured_at))
                or not 0 <= float(captured_at) < _MAX_CAPTURE_AT
            ):
                return _process_config_unavailable()
            # Body ONLY after the bound: the bounded fetch re-asserts
            # kind, size, SHA256 and the cap as BOUND parameters (no
            # identifier interpolation), so a concurrently modified
            # or corrupt row can never transfer unbounded bytes.
            body_row = (
                await session.execute(
                    text(
                        "SELECT body FROM demo_display.leaves "
                        "WHERE logical_name = :name "
                        "AND octet_length(body) <= :cap "
                        "AND byte_count = :size "
                        "AND sha256 = :digest "
                        "AND kind = :kind"
                    ),
                    {
                        "name": _PROCESS_CONFIG_NAME,
                        "cap": _MAX_PROCESS_CONFIG_BYTES,
                        "size": byte_count,
                        "digest": stored_sha,
                        "kind": dsf.KIND_PROCESS_CONFIG,
                    },
                )
            ).first()
            if body_row is None:
                return _process_config_unavailable()
            fetched = bytes(body_row[0])
            if len(fetched) != byte_count or (
                hashlib.sha256(fetched).hexdigest() != stored_sha
            ):
                return _process_config_unavailable()
            body = fetched
            captured = float(captured_at)
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not
        # swallowed.
        return _process_config_unavailable()
    # Typed re-proof from BYTES (the 223 verifier law): a stored body
    # that passes size/digest but breaks the closed shape law is
    # refused before projection.
    try:
        dsf._verify_json_policy(dsf.KIND_PROCESS_CONFIG, body)
        document = json.loads(body.decode("utf-8"))
        entries = document["settings"]
        settings_rows: list[dict[str, object]] = []
        for name in CONFIG_INSPECTION_ALLOWLIST:
            entry = entries[name]
            units, meaning = setting_meaning(name) or ("", "")
            value = entry["value"]
            settings_rows.append(
                {
                    "name": name,
                    "units": units,
                    "value": "(none)" if value is None else value,
                    "source": str(entry["source"]),
                    "meaning": meaning,
                }
            )
        captured_dt = datetime.fromtimestamp(captured, tz=UTC)
        captured_utc = captured_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return _process_config_unavailable()
    response = templates.TemplateResponse(
        request,
        "operations/process_configuration.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "package_version": __version__,
            "snapshot_scope": _DEMO_SNAPSHOT_SCOPE,
            "restart_scope": API_PROCESS_RESTART_SCOPE,
            "limitations": list(_DEMO_LIMITATIONS),
            "settings_rows": settings_rows,
            # The 223-captured profile identities and the worker-pinned
            # Codex reference are NOT displayed on this page yet (the
            # template renders the honest not-displayed notes); the
            # live app-global profiles and the live API-process Codex
            # identity are NEVER read here.
            "profile_rows": [],
            "codex_facts": None,
            "deployed_revision": None,
            "revision_provenance": None,
            "demo_admin": True,
            "demo_captured_utc": captured_utc,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response

# ---------------------------------------------------------------------------
# 224-v: the demo copy-backed request-diagnostics read page
# ---------------------------------------------------------------------------

# The bounded recent list and the exact safe-ID lookup share ONE
# request-local SELECT-only transaction on the verified copy. The
# recent list is capped at this many newest rows; the lookup reuses
# the normal service's bounded candidate law (one row past the bound)
# with NO retention cutoff: the demo projection does not capture the
# source deployment's retention settings, so the demo never applies
# (or displays) a retention window.
_DIAGNOSTICS_RECENT_LIMIT = 100
_DIAGNOSTICS_NAMESPACE_VALUES = {
    "any": DiagnosticsNamespace.ANY,
    "gateway": DiagnosticsNamespace.GATEWAY,
    "client": DiagnosticsNamespace.CLIENT,
}
# No retention cutoff: every copied row is inspectable. The floor is
# far below any representable capture time.
_DIAGNOSTICS_NO_CUTOFF = datetime(1, 1, 1, tzinfo=UTC)

_SAFE_DIAGNOSTICS_UNAVAILABLE = (
    "The diagnostics page is unavailable for this demo session."
)


def _diagnostics_not_found() -> Response:
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _diagnostics_unavailable() -> Response:
    return HTMLResponse(
        _SAFE_DIAGNOSTICS_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


def _demo_lookup_result(
    rows: tuple, total: int, lookup: str, namespace: DiagnosticsNamespace
) -> DiagnosticLookupResult:
    """The normal service's exact typed outcome law, minus the live
    retention cutoff (the copy is the bounded universe)."""
    if not rows:
        return DiagnosticLookupResult(
            outcome=DiagnosticLookupOutcome.NOT_FOUND, namespace=namespace
        )
    if len(rows) == 1:
        return DiagnosticLookupResult(
            outcome=DiagnosticLookupOutcome.FOUND,
            namespace=namespace,
            record=rows[0],
            match_count=total,
        )
    candidates = tuple(
        DiagnosticDisambiguationCandidate(
            gateway_request_id=row.gateway_request_id,
            occurred_at=row.occurred_at,
            matched_namespace="gateway"
            if row.gateway_request_id == lookup
            else "client",
        )
        for row in rows[:DIAGNOSTIC_LOOKUP_BOUND]
    )
    return DiagnosticLookupResult(
        outcome=DiagnosticLookupOutcome.AMBIGUOUS,
        namespace=namespace,
        match_count=total,
        candidates=candidates,
        overflow=total > DIAGNOSTIC_LOOKUP_BOUND,
    )


@router.get("/diagnostics", response_class=HTMLResponse)
async def demo_operations_diagnostics(request: Request) -> Response:
    """224-v: the demo copy-backed request-diagnostics page (exact
    path, gate-admitted with its bounded optional read-only selector
    ``lookup=<safe ID>&namespace=<any|gateway|client>``).

    The page reads ONLY content-free diagnostic rows from the
    visitor's request-local verified copy, in ONE SELECT-only
    transaction with the independent ``current_database()`` /
    ``transaction_read_only`` recheck: a bounded newest-first recent
    list plus (when the selector is present) the exact safe-ID
    lookup with the normal typed outcome law. The gate already
    enforced the raw query law, including the pre-copy known-
    incoming-alias refusal; the adapter re-proves the value before
    use (a value that cannot be re-proven renders the cleared
    not-found, never the value). Retention/recording settings are
    NOT displayed (they were not captured in the demo projection);
    the data is labeled frozen at copy time. Corrupt or absent copy
    data is the fixed safe 503 - never an ambient fallback. No raw
    capture artifact, prompt, credential or source-DB access occurs.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _diagnostics_not_found()
    # The gate enforced the closed raw query law (at most one of each
    # exact parameter); the adapter re-proves the values before use.
    query = dict(request.query_params.multi_items())
    namespace_raw = query.get("namespace", "any")
    if namespace_raw not in _DIAGNOSTICS_NAMESPACE_VALUES:
        return _diagnostics_not_found()
    lookup_raw = query.get("lookup", "")
    # Unsafe grammar or a known incoming alias: the value is withheld
    # with the field CLEARED (the normal POST's exact not-found
    # semantics); the value never reaches HTML, a redirect or logs.
    lookup = ""
    if lookup_raw and not _is_unsafe_lookup_value(request, lookup_raw):
        lookup = lookup_raw
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _diagnostics_unavailable()
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _diagnostics_unavailable()
            # Frozen copy summary: the copied rows are the bounded
            # universe (NO retention cutoff - the source deployment's
            # retention settings were not captured in the demo
            # projection and are never displayed as if live).
            count, oldest, newest = (
                await session.execute(
                    text(
                        "SELECT COUNT(*), MIN(occurred_at), MAX(occurred_at) "
                        "FROM request_diagnostics"
                    )
                )
            ).one()
            recent = (
                (
                    await session.execute(
                        select(RequestDiagnostic)
                        .order_by(
                            RequestDiagnostic.occurred_at.desc(),
                            RequestDiagnostic.id.desc(),
                        )
                        .limit(_DIAGNOSTICS_RECENT_LIMIT)
                    )
                )
                .scalars()
                .all()
            )
            lookup_result: DiagnosticLookupResult | None = None
            if lookup:
                rows, total = await RequestDiagnosticsRepository(
                    session
                ).lookup_retained(
                    lookup_id=lookup,
                    namespace=_DIAGNOSTICS_NAMESPACE_VALUES[namespace_raw],
                    not_before=_DIAGNOSTICS_NO_CUTOFF,
                    limit=DIAGNOSTIC_LOOKUP_BOUND + 1,
                )
                lookup_result = _demo_lookup_result(
                    rows, total, lookup, _DIAGNOSTICS_NAMESPACE_VALUES[namespace_raw]
                )
    except Exception:  # noqa: BLE001 - corrupt/absent copy data refuses
        return _diagnostics_unavailable()

    withheld: set[str] = set()
    facts: dict[str, str] = {}
    if lookup_result is not None and lookup_result.record is not None:
        # The normal page's exact output-side alias withholding.
        withheld = _withheld_record_fields(request, lookup_result.record)
        record = lookup_result.record
        facts = {
            "positions": _format_fact_map(record.positions),
            "counts": _format_fact_map(record.counts),
            "limits": _format_fact_map(record.limits),
        }
    recent_rows = []
    for row in recent:
        recent_rows.append(
            {
                "record": row,
                "withheld": _withheld_record_fields(request, row),
            }
        )
    # Ambiguous candidates: withhold any candidate whose stored
    # gateway ID is or embeds a known incoming authentication alias
    # BEFORE it is rendered or linked (the found/recent projections
    # are covered by _withheld_record_fields; the typed candidate
    # tuples are not). A withheld candidate keeps its row (the count
    # stays honest) but shows no ID and no resolve link.
    demo_candidates: list[dict[str, object]] = []
    if (
        lookup_result is not None
        and lookup_result.outcome is DiagnosticLookupOutcome.AMBIGUOUS
    ):
        for candidate in lookup_result.candidates:
            alias = _is_incoming_alias(request, candidate.gateway_request_id)
            demo_candidates.append(
                {
                    "gateway_display": None
                    if alias
                    else candidate.gateway_request_id,
                    "matched_namespace": candidate.matched_namespace,
                    "occurred_at": candidate.occurred_at,
                    "resolve_href": None
                    if alias
                    else (
                        "/admin/operations/diagnostics?lookup="
                        f"{candidate.gateway_request_id}&namespace=gateway"
                    ),
                }
            )
    response = templates.TemplateResponse(
        request,
        "operations/diagnostics.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "demo_admin": True,
            "demo_copy": SimpleNamespace(
                copied_records=int(count),
                oldest_occurred_at=oldest,
                newest_occurred_at=newest,
            ),
            "status": None,
            "human_retention": "",
            "lookup_value": lookup,
            "lookup_namespace": namespace_raw,
            "lookup_result": lookup_result,
            "withheld_fields": withheld,
            "facts": facts,
            "picker_options": [],
            "recent_rows": recent_rows,
            "recent_limit": _DIAGNOSTICS_RECENT_LIMIT,
            "demo_candidates": demo_candidates,
            "cleanup_result": None,
            "cleanup_batch_limit": _CLEANUP_BATCH_LIMIT,
            "error_message": "",
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
