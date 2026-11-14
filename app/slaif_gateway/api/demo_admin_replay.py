"""Demo-host read-only Codex replay-maintenance views (224-v).

The standalone demo process admits the exact replay-maintenance GET
family over the visitor's verified per-login SELECT-only copy:

* ``GET /admin/operations/replay-maintenance/``            (index,
  REQUIRED trailing slash);
* ``GET /admin/operations/replay-maintenance/all-active``;
* ``GET /admin/operations/replay-maintenance/key/{uuid}``;
* ``GET /admin/operations/replay-maintenance/cohort/{uuid}``.

The central demo gate admits ONLY these exact shapes (canonical
lowercase dashed UUIDs, no query, near misses default-denied) and
keeps every unsafe method - including the normal inspect/preview/
apply POSTs - the pre-body quiet 204 cut.

Read law: ONE request-local SELECT-only transaction on the gate-bound
engine with the independent ``current_database()`` /
``transaction_read_only`` recheck. The summary reuses ONLY the
pure-read, copy-bound repository aggregate statements (key states,
reference aggregates, per-key aggregates, route/model groups) plus
two small bounded SELECTs (kind counts; up to 100 newest SAFE
metadata rows - no HMAC digests, no opaque tokens, no
source_request_id, no usage-ledger IDs). The worker-captured
``CODEX_REPLAY_REFERENCE_TTL_SECONDS`` comes from the verified
process-configuration display leaf (224-t capture law); when the
leaf is absent or corrupt it is labeled unavailable. The demo
process's HMAC keys are NEVER read: no HMAC eligibility, no
preview/apply authority, no signed plan is implied, and the active/
expired split is a plain comparison of the copied expiry timestamps
against view time. Corrupt or absent copy data is the fixed safe 503
- never an ambient fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid as _uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.api.admin_compatibility import (
    _is_known_alias,
    _safe_display,
)
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferencesRepository,
)
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services.codex_replay_maintenance import (
    MAX_SELECTED_KEYS,
    MAX_REFERENCE_TTL_SECONDS,
    MIN_REFERENCE_TTL_SECONDS,
)

router = APIRouter(
    prefix="/admin/operations/replay-maintenance", include_in_schema=False
)

# The process-configuration leaf (224-t capture law) carries the
# worker-observed TTL; its closed display cap is the same 1 MiB bound
# the 224-t page enforces before any body fetch.
_PROCESS_CONFIG_NAME = dsf._PROC_CONFIG_LOGICAL_NAME
_MAX_PROCESS_CONFIG_BYTES = 1024 * 1024
_MAX_CAPTURE_AT = 253_402_300_800.0
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TTL_SETTING_NAME = "CODEX_REPLAY_REFERENCE_TTL_SECONDS"

# Bounded recent-row and group display limits (the normal UI's
# inspection bounds: 100 groups, and the newest 100 safe metadata
# rows per scope).
_RECENT_ROW_LIMIT = 100
_ROUTE_GROUP_LIMIT = 100

_SAFE_NOT_FOUND = "Not Found"
_SAFE_UNAVAILABLE = (
    "The replay maintenance page is unavailable for this demo session."
)
_SAFE_ALIAS_REFUSAL = (
    "The replay maintenance scope cannot be shown: it matches a known "
    "incoming authentication value."
)


def _not_found() -> Response:
    return HTMLResponse(
        _SAFE_NOT_FOUND, status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_UNAVAILABLE, status_code=503, headers={"Cache-Control": "private, no-store"}
    )


def _alias_refusal() -> Response:
    return HTMLResponse(
        _SAFE_ALIAS_REFUSAL, status_code=400,
        headers={"Cache-Control": "private, no-store"},
    )


def _no_query(request: Request) -> bool:
    return not request.query_params.multi_items()


async def _copy_recheck(session: Any, target_db: str) -> bool:
    current = await session.scalar(text("SELECT current_database()"))
    read_only = await session.scalar(text("SHOW transaction_read_only"))
    return current == target_db and read_only == "on"


async def _worker_ttl_seconds(session: Any) -> int | None:
    """The worker-captured TTL from the verified process-configuration
    leaf (224-t capture law: metadata first with the database-computed
    length, the 1 MiB bound BEFORE any body fetch, the bounded fetch
    re-asserting every condition as bound parameters, exact length +
    SHA256, and the typed verifier law). ``None`` = unavailable
    (absent or corrupt leaf; the page labels it, it never falls back
    to the demo process's own settings)."""
    try:
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
            return None
        kind, byte_count, stored_sha, captured_at, actual_bytes = meta
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
            or actual_bytes != byte_count
            or isinstance(captured_at, bool)
            or not isinstance(captured_at, (int, float))
            or not math.isfinite(float(captured_at))
            or not 0 <= float(captured_at) < _MAX_CAPTURE_AT
        ):
            return None
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
            return None
        body = bytes(body_row[0])
        if len(body) != byte_count or (
            hashlib.sha256(body).hexdigest() != stored_sha
        ):
            return None
        dsf._verify_json_policy(dsf.KIND_PROCESS_CONFIG, body)
        document = json.loads(body.decode("utf-8"))
        value = document["settings"][_TTL_SETTING_NAME]["value"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None
        return value
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return None


async def _demo_summary(
    session: Any,
    *,
    key_id: _uuid.UUID | None,
    cohort_id: _uuid.UUID | None,
    all_active: bool,
) -> SimpleNamespace:
    """The bounded copy-backed retained-reference summary (pure-read,
    copy-bound repository aggregates + two small bounded SELECTs).
    Raises on driver/shape failure so the caller returns the fixed
    safe 503."""
    repo = CodexReplayReferencesRepository(session)
    keys = await repo.list_maintenance_key_states(
        key_id=key_id,
        cohort_id=cohort_id,
        all_active=all_active,
        limit=MAX_SELECTED_KEYS + 1,
    )
    if len(keys) > MAX_SELECTED_KEYS:
        # The normal service refuses an oversize scope instead of
        # truncating; the demo says exactly that and reads nothing
        # more.
        return SimpleNamespace(
            oversize=True,
            keys_count=len(keys),
            now=datetime.now(UTC),
            totals=None,
            per_key=(),
            groups=(),
            groups_total=0,
            kind_counts=(),
            recent=(),
        )
    key_ids = [key.id for key in keys]
    now = datetime.now(UTC)
    totals = await repo.inspect_reference_aggregates(
        key_ids=key_ids, created_from=None, created_until=None, now=now
    )
    per_key_rows = await repo.inspect_reference_per_key(
        key_ids=key_ids, created_from=None, created_until=None, now=now
    )
    groups, groups_total = await repo.inspect_reference_route_groups(
        key_ids=key_ids,
        created_from=None,
        created_until=None,
        limit=_ROUTE_GROUP_LIMIT,
    )
    if key_ids:
        kind_rows = (
            await session.execute(
                text(
                    "SELECT item_kind, COUNT(*) AS n "
                    "FROM codex_replay_references "
                    "WHERE gateway_key_id = ANY(:ids) "
                    "GROUP BY item_kind ORDER BY item_kind"
                ),
                {"ids": key_ids},
            )
        ).all()
        kind_counts = tuple(
            (str(kind), int(count)) for kind, count in kind_rows
        )
        recent_rows = (
            await session.execute(
                text(
                    "SELECT gateway_key_id, item_kind, provider, "
                    "upstream_model, tool_namespace, tool_name, "
                    "created_at, expires_at "
                    "FROM codex_replay_references "
                    "WHERE gateway_key_id = ANY(:ids) "
                    "ORDER BY created_at DESC, id DESC "
                    "LIMIT :limit"
                ),
                {"ids": key_ids, "limit": _RECENT_ROW_LIMIT},
            )
        ).all()
        recent = tuple(dict(row._mapping) for row in recent_rows)
    else:
        kind_counts = ()
        recent = ()
    return SimpleNamespace(
        oversize=False,
        keys_count=len(keys),
        key_statuses=tuple((key.id, key.status) for key in keys),
        now=now,
        totals=totals,
        per_key=tuple(per_key_rows),
        groups=tuple(groups),
        groups_total=groups_total,
        kind_counts=kind_counts,
        recent=recent,
    )


def _scope_context(
    request: Request,
    *,
    scope_kind: str,
    scope_label: str,
    scope_code: str,
    key_status: str | None,
    cohort_name: str | None,
    summary: SimpleNamespace,
    ttl_seconds: int | None,
) -> dict[str, Any]:
    now = summary.now
    def _iso(value: Any) -> str:
        return value.isoformat() if isinstance(value, datetime) else "—"

    key_status_by_id = dict(
        summary.key_statuses if not summary.oversize else ()
    )
    per_key = []
    for row in summary.per_key:
        (
            key_uuid,
            references,
            active_references,
            created_min,
            created_max,
            expiry_min,
            expiry_max,
        ) = row
        key_code = str(key_uuid)
        key_alias = _is_known_alias(request, key_code)
        per_key.append(
            {
                "key_id": _safe_display(request, key_code),
                "key_href": None if key_alias else f"/admin/keys/{key_code}",
                "key_status": _safe_display(
                    request, key_status_by_id.get(key_uuid)
                ),
                "references": references,
                "active_references": active_references,
                "expired_references": references - active_references,
                "created_min": _iso(created_min),
                "created_max": _iso(created_max),
                "expiry_min": _iso(expiry_min),
                "expiry_max": _iso(expiry_max),
            }
        )
    groups = []
    for route_uuid, model, count in summary.groups:
        route_code = str(route_uuid)
        route_alias = _is_known_alias(request, route_code)
        groups.append(
            {
                "route_id": _safe_display(request, route_code),
                "route_href": None if route_alias else f"/admin/routes/{route_code}",
                "requested_model": _safe_display(request, model),
                "references": count,
            }
        )
    recent = []
    for row in summary.recent:
        key_code = str(row["gateway_key_id"])
        key_alias = _is_known_alias(request, key_code)
        recent.append(
            {
                "key_id": _safe_display(request, key_code),
                "key_href": None if key_alias else f"/admin/keys/{key_code}",
                "item_kind": _safe_display(request, row["item_kind"]),
                "provider": _safe_display(request, row["provider"]),
                "upstream_model": _safe_display(request, row["upstream_model"]),
                "tool_namespace": _safe_display(request, row["tool_namespace"]),
                "tool_name": _safe_display(request, row["tool_name"]),
                "created_at": _iso(row["created_at"]),
                "expires_at": _iso(row["expires_at"]),
                "expired": (
                    row["expires_at"] < now
                    if isinstance(row["expires_at"], datetime)
                    else None
                ),
            }
        )
    return {
        "scope_kind": scope_kind,
        "scope_label": scope_label,
        "scope_code": _safe_display(request, scope_code) if scope_code else "",
        "key_status": _safe_display(request, key_status) if key_status else None,
        "cohort_name": (
            _safe_display(request, cohort_name) if cohort_name else None
        ),
        "demo_admin": True,
        "demo_now": _iso(now),
        "demo_ttl_seconds": ttl_seconds,
        "demo_ttl_available": ttl_seconds is not None,
        "demo_oversize": summary.oversize,
        "demo_keys_count": summary.keys_count,
        "demo_max_keys": MAX_SELECTED_KEYS,
        "demo_references": summary.totals.references if summary.totals else 0,
        "demo_active": summary.totals.active_references if summary.totals else 0,
        "demo_expired": (
            (summary.totals.references - summary.totals.active_references)
            if summary.totals
            else 0
        ),
        "demo_created_min": _iso(summary.totals.created_min) if summary.totals else "—",
        "demo_created_max": _iso(summary.totals.created_max) if summary.totals else "—",
        "demo_expiry_min": _iso(summary.totals.expiry_min) if summary.totals else "—",
        "demo_expiry_max": _iso(summary.totals.expiry_max) if summary.totals else "—",
        "demo_per_key": per_key,
        "demo_groups": groups,
        "demo_groups_total": summary.groups_total,
        "demo_groups_truncated": summary.groups_total > len(summary.groups),
        "demo_kind_counts": summary.kind_counts,
        "demo_recent": recent,
        "demo_recent_limit": _RECENT_ROW_LIMIT,
    }


def _base_context(request: Request, demo: Any) -> dict[str, Any]:
    return {
        "admin": demo.session_context.admin_user,
        "csrf_token": demo.csrf_token,
        "demo_admin": True,
        "demo_ttl_seconds": None,
        "demo_ttl_available": False,
        # Normal-branch variables: the illustrative form controls stay
        # visible in demo (their submission is the gate's quiet pre-
        # body 204 no-op), so the form's finite TTL bounds are supplied
        # as illustrative context only (no authority).
        "scope_options": (),
        "configured_ttl_seconds": 0,
        "ttl_min": MIN_REFERENCE_TTL_SECONDS,
        "ttl_max": MAX_REFERENCE_TTL_SECONDS,
    }


async def _index_body(request: Request, demo: Any) -> Response:
    ttl: int | None = None
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            ttl = await _worker_ttl_seconds(session)
    except Exception:  # noqa: BLE001
        return _unavailable()
    context = _base_context(request, demo)
    context["demo_ttl_seconds"] = ttl
    context["demo_ttl_available"] = ttl is not None
    response = templates.TemplateResponse(
        request,
        "replay_maintenance/index.html",
        context,
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def _scope_body(
    request: Request,
    demo: Any,
    *,
    scope_kind: str,
    scope_label: str,
    scope_code: str,
    key_id: _uuid.UUID | None,
    cohort_id: _uuid.UUID | None,
    all_active: bool,
) -> Response:
    key_status: str | None = None
    cohort_name: str | None = None
    summary: SimpleNamespace | None = None
    ttl: int | None = None
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            if key_id is not None:
                key = await GatewayKeysRepository(session).get_gateway_key_by_id(
                    key_id
                )
                if key is None:
                    return _not_found()
                key_status = key.status
            if cohort_id is not None:
                cohort = await CohortsRepository(session).get_cohort_by_id(
                    cohort_id
                )
                if cohort is None:
                    return _not_found()
                cohort_name = cohort.name
            summary = await _demo_summary(
                session,
                key_id=key_id,
                cohort_id=cohort_id,
                all_active=all_active,
            )
            ttl = await _worker_ttl_seconds(session)
    except Exception:  # noqa: BLE001
        return _unavailable()
    context = _base_context(request, demo)
    context.update(
        _scope_context(
            request,
            scope_kind=scope_kind,
            scope_label=scope_label,
            scope_code=scope_code,
            key_status=key_status,
            cohort_name=cohort_name,
            summary=summary,
            ttl_seconds=ttl,
        )
    )
    response = templates.TemplateResponse(
        request,
        "replay_maintenance/scope.html",
        context,
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/", response_class=HTMLResponse)
async def demo_replay_index(request: Request) -> Response:
    """224-v: the demo replay-maintenance index (REQUIRED trailing
    slash, query-free, gate-admitted)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    return await _index_body(request, demo)


@router.get("/all-active", response_class=HTMLResponse)
async def demo_replay_all_active(request: Request) -> Response:
    """224-v: the explicit every-active-key scope (copied rows)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    return await _scope_body(
        request,
        demo,
        scope_kind="all_active",
        scope_label="Every active key (explicit scope)",
        scope_code="",
        key_id=None,
        cohort_id=None,
        all_active=True,
    )


@router.get("/key/{key_id}", response_class=HTMLResponse)
async def demo_replay_key_scope(request: Request, key_id: str) -> Response:
    """224-v: the one-existing-key scope; the key must exist in the
    visitor's copy (the gate already enforced the canonical UUID)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    try:
        parsed = _uuid.UUID(key_id)
    except ValueError:
        return _not_found()
    if _is_known_alias(request, key_id):
        return _alias_refusal()
    return await _scope_body(
        request,
        demo,
        scope_kind="key",
        scope_label="One gateway key",
        scope_code=str(parsed),
        key_id=parsed,
        cohort_id=None,
        all_active=False,
    )


@router.get("/cohort/{cohort_id}", response_class=HTMLResponse)
async def demo_replay_cohort_scope(request: Request, cohort_id: str) -> Response:
    """224-v: the one-cohort scope; the cohort must exist in the
    visitor's copy (the gate already enforced the canonical UUID)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    try:
        parsed = _uuid.UUID(cohort_id)
    except ValueError:
        return _not_found()
    if _is_known_alias(request, cohort_id):
        return _alias_refusal()
    return await _scope_body(
        request,
        demo,
        scope_kind="cohort",
        scope_label="One cohort",
        scope_code=str(parsed),
        key_id=None,
        cohort_id=parsed,
        all_active=False,
    )
