"""Focused admin router for reviewed Codex replay-reference maintenance (213-a).

Delivers G09: authenticated, usable GUI inspection of retained Codex
replay references and the reviewed monotonic extension of their expiry,
reusing the SAME shared service the CLI uses
(``CodexReplayMaintenanceService.inspect_replay_references`` /
``preview_replay_extend`` / ``apply_replay_extend``) inside the
caller-owned transaction.  The shared service remains the sole
authority for locking, scope-membership revalidation, eligibility
classification, fingerprints, monotonic expiry law, and the accepted
already-applied repeat; the controllers only bind the reviewed plan to
the signed-in actor/session through the existing HMAC review-intent
pattern and enforce the GUI's known-incoming-alias withholding.

Scope is always explicit (one existing key, one cohort, or explicitly
every active key - never an implicit default); inspection is read-only
with NO domain/audit write; preview renders the strict bounded plan
(read-only) and signs it with a 15-minute bound; apply re-verifies the
token, re-checks this request's known incoming aliases, and calls the
shared apply in ONE caller-owned transaction.  Expiry target is ALWAYS
the original stored creation time plus the selected lifetime; nothing is
ever shortened, recreated, or transferred.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _is_checked,
    _log_admin_action_failure,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_replay_review_token,
    verify_replay_review_token,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferencesRepository,
)
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.key_configuration import (
    MAX_KEY_CONFIGURATION_REASON_LENGTH,
)
from slaif_gateway.schemas.codex_replay_maintenance import (
    EXCLUSION_REASON_CODES,
    REPLAY_PLAN_MAX_BYTES,
    ReplayMaintenanceError,
    ReplayMaintenanceStaleError,
    parse_replay_scope,
    parse_scope_uuid,
    parse_replay_extend_plan_document,
    parse_utc_datetime,
    render_replay_extend_plan,
    validate_utc_bounds,
)
from slaif_gateway.services.codex_replay_maintenance import (
    MAX_REFERENCE_TTL_SECONDS,
    MIN_REFERENCE_TTL_SECONDS,
    CodexReplayMaintenanceService,
    ReplayInspectionSummary,
)
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
)

router = APIRouter(
    prefix="/admin/operations/replay-maintenance", include_in_schema=False
)

# The finite explicit scope options shown on the index page (never an
# implicit default; the third is a deliberate operator choice).
INDEX_SCOPE_OPTIONS = (
    {
        "label": "One existing key",
        "href": "/admin/keys",
        "link_text": "Open the searchable key list",
        "note": "open the key detail and use its Replay maintenance link.",
    },
    {
        "label": "One cohort",
        "href": "/admin/cohorts",
        "link_text": "Open the searchable cohort list",
        "note": "open the cohort detail and use its Replay maintenance link.",
    },
    {
        "label": "Every active key (explicit)",
        "href": "/admin/operations/replay-maintenance/all-active",
        "link_text": "Open the explicit every-active-key scope",
        "note": "",
    },
)

# Finite scope vocabulary (form values).  There is NO implicit
# all-active default: every scope is an explicit operator choice.
_SCOPE_KINDS = frozenset({"key", "cohort", "all_active"})
# Normal GUI convention for the bounded safe audit reason: bounded
# nonblank Unicode (at most MAX_KEY_CONFIGURATION_REASON_LENGTH
# characters).  The string is NEVER trimmed; the shared Core
# re-validates nonblank content and credential shapes on the ORIGINAL
# string at apply, and the reviewed string is preserved through apply.
_TTL_RE = re.compile(r"^[0-9]{1,9}$")

EXCLUSION_LABELS = {
    "key_not_active_or_valid": "Key not active or outside its validity window",
    "ledger_not_finalized": "Usage ledger row not finalized",
    "unsupported_kind": "Item kind outside the maintained set",
    "hmac_version_unavailable": "Stored HMAC version has no configured secret",
    "outside_lifetime": "Original creation already beyond the selected lifetime",
    "expired_not_included": "Already expired and not explicitly included",
}


@asynccontextmanager
async def _replay_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Caller-owned transaction scope for one replay-maintenance operation."""
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield session


def _accepted_prefixes(request: Request) -> tuple[str, ...]:
    return _settings(request).get_gateway_key_accepted_prefixes()


def _is_known_alias(request: Request, value: object) -> bool:
    """True when a display/submitted value is a known incoming
    authentication alias (pure fail-closed discovery; never echoes)."""
    return is_known_incoming_secret_alias(
        value, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    )


def _safe_display(request: Request, value: object) -> str:
    """One display string with known-incoming-alias withholding."""
    text = value if isinstance(value, str) else ""
    if not text:
        return "—"
    if _is_known_alias(request, text):
        return "Withheld: matches a known credential value"
    return text


def _walk_strings(value: Any) -> Any:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _review_doc_has_alias(request: Request, document: dict[str, Any]) -> bool:
    """True when ANY signed/displayed fact is a known incoming
    authentication alias (fail closed).  The plan is a closed shallow
    structure (scope UUIDs, bounded timestamps, counts, fingerprints),
    so the walk is finite; the free-text reason is included."""
    return any(_is_known_alias(request, item) for item in _walk_strings(document))


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def _dashboard_gate(request: Request) -> Response | None:
    """The normal fixed-404 guard for every replay-maintenance handler."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    return None


def _recovery_scope(request: Request, scope: Any) -> Any:
    """The verified canonical scope for a recovery link, or None.

    A scope whose canonical code is itself a known incoming
    authentication alias is never re-exposed through a URL, so those
    errors fall back to the fixed replay entry.
    """
    if scope is None:
        return None
    scope_code = str(scope.key_id or scope.cohort_id or "")
    if scope_code and _is_known_alias(request, scope_code):
        return None
    return scope


def _replay_error_page(
    request: Request,
    *,
    status_code: int,
    message: str,
    scope: Any = None,
) -> Response:
    """Replay-owned error page: the fixed safe message plus a useful
    recovery link (verified canonical scope when safe, otherwise the
    fixed replay entry).  No raw input or token is ever rendered."""
    status_text = {
        400: "Bad request",
        404: "Not found",
    }
    safe_scope = _recovery_scope(request, scope)
    return templates.TemplateResponse(
        request,
        "replay_maintenance/error.html",
        {
            "error_status": status_code,
            "error_status_text": status_text.get(status_code, "Error"),
            "error_message": message,
            "scope_href": _scope_href(safe_scope) if safe_scope is not None else None,
        },
        status_code=status_code,
    )


def _iso(value: Any) -> str:
    if value is None:
        return "—"
    return value.isoformat().replace("+00:00", "Z")


def _replay_service(request: Request, session: AsyncSession) -> CodexReplayMaintenanceService:
    return CodexReplayMaintenanceService(
        repository=CodexReplayReferencesRepository(session),
        audit_repository=AuditRepository(session),
        settings=_settings(request),
    )


# ---------------------------------------------------------------------------
# Scope pages
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def replay_maintenance_index(request: Request) -> Response:
    """Scope entry: three EXPLICIT scopes, never an implicit all-active default."""
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    return _no_store(
        templates.TemplateResponse(
            request,
            "replay_maintenance/index.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "scope_options": INDEX_SCOPE_OPTIONS,
                "configured_ttl_seconds": _settings(request).CODEX_REPLAY_REFERENCE_TTL_SECONDS,
            },
        )
    )


def _parse_scope_path_uuid(request: Request, value: str, *, field: str):
    """Shared canonical UUID grammar for scope paths (no permissive
    shorthand); anything non-canonical is a fixed 404, never echoed."""
    try:
        return parse_scope_uuid(value, field=field), None
    except ReplayMaintenanceError:
        return None, _admin_error_page(
            request,
            status_code=404,
            message="Gateway key not found." if field == "key" else "Cohort not found.",
        )


async def _key_scope_detail(request: Request, key_id: str):
    """Parse a canonical key UUID and prove the actual record exists."""
    parsed_key_id, error = _parse_scope_path_uuid(request, key_id, field="key")
    if error is not None:
        return None, error
    try:
        async with _replay_session(request) as session:
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(parsed_key_id)
    except Exception:  # noqa: BLE001 - read-only; fixed safe fallback
        key = None
    if key is None:
        return None, _replay_error_page(
            request,
            status_code=404,
            message="Gateway key not found.",
        )
    return key, None


async def _cohort_scope_detail(request: Request, cohort_id: str):
    """Parse a canonical cohort UUID and prove the actual record exists."""
    parsed_cohort_id, error = _parse_scope_path_uuid(request, cohort_id, field="cohort")
    if error is not None:
        return None, error
    try:
        async with _replay_session(request) as session:
            cohort = await CohortsRepository(session).get_cohort_by_id(parsed_cohort_id)
    except Exception:  # noqa: BLE001 - read-only; fixed safe fallback
        cohort = None
    if cohort is None:
        return None, _replay_error_page(
            request,
            status_code=404,
            message="Cohort not found.",
        )
    return cohort, None


def _render_scope_page(
    request: Request,
    *,
    context: Any,
    csrf_token: str,
    scope_kind: str,
    scope_code: str,
    scope_label: str,
    key_status: str | None = None,
    cohort_name: str | None = None,
) -> Response:
    return _no_store(
        templates.TemplateResponse(
            request,
            "replay_maintenance/scope.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "scope_kind": scope_kind,
                "scope_label": scope_label,
                "scope_code": scope_code,
                "key_status": key_status,
                # Absent facet stays None (the template omits it); the
                # safe-display fallback "—" must not fabricate a value.
                "cohort_name": _safe_display(request, cohort_name) if cohort_name else None,
                "configured_ttl_seconds": _settings(request).CODEX_REPLAY_REFERENCE_TTL_SECONDS,
                "ttl_min": MIN_REFERENCE_TTL_SECONDS,
                "ttl_max": MAX_REFERENCE_TTL_SECONDS,
            },
        )
    )


@router.get("/key/{key_id}", response_class=HTMLResponse)
async def replay_maintenance_key_scope(request: Request, key_id: str) -> Response:
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    key, error = await _key_scope_detail(request, key_id)
    if error is not None:
        return error
    # The scope code is a finite review fact that also travels into the
    # hidden form inputs and reload URLs below: a known incoming
    # authentication alias is refused BEFORE any template context is
    # built, not merely withheld in visible text.
    key_scope_code = str(key.id)
    if _is_known_alias(request, key_scope_code):
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay maintenance scope cannot be shown: it matches a "
                "known incoming authentication value."
            ),
        )
    return _render_scope_page(
        request,
        context=context,
        csrf_token=csrf_token,
        scope_kind="key",
        scope_code=key_scope_code,
        scope_label="One gateway key",
        key_status=key.status,
    )


@router.get("/cohort/{cohort_id}", response_class=HTMLResponse)
async def replay_maintenance_cohort_scope(request: Request, cohort_id: str) -> Response:
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    cohort, error = await _cohort_scope_detail(request, cohort_id)
    if error is not None:
        return error
    if _is_known_alias(request, str(cohort.id)):
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay maintenance scope cannot be shown: it matches a "
                "known incoming authentication value."
            ),
        )
    return _render_scope_page(
        request,
        context=context,
        csrf_token=csrf_token,
        scope_kind="cohort",
        scope_code=str(cohort.id),
        scope_label="One cohort",
        cohort_name=cohort.name,
    )


@router.get("/all-active", response_class=HTMLResponse)
async def replay_maintenance_all_active(request: Request) -> Response:
    """The explicit every-active-key scope (a deliberate operator choice)."""
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    return _render_scope_page(
        request,
        context=context,
        csrf_token=csrf_token,
        scope_kind="all_active",
        scope_code="",
        scope_label="Every active key (explicit scope)",
    )


# ---------------------------------------------------------------------------
# Scope form parsing (shared by inspect and preview)
# ---------------------------------------------------------------------------


def _parse_scope_form(form: Any) -> tuple[str, Any]:
    """Exactly one explicit scope from finite form fields (fixed safe errors).

    Every populated scope member is passed to the shared exactly-one
    parser, so a conflicting submission (for example kind=key with a
    cohort_id also present) is refused by the Core scope law rather
    than silently dropped; the chosen kind's own ID is still required.
    """
    kind = str(form.get("scope") or "")
    if kind not in _SCOPE_KINDS:
        raise ReplayMaintenanceError(
            "Choose exactly one replay maintenance scope: one key, one "
            "cohort, or every active key.",
            error_code="replay_maintenance_scope",
        )
    key_id = str(form.get("key_id") or "") or None
    cohort_id = str(form.get("cohort_id") or "") or None
    if kind == "key" and key_id is None:
        raise ReplayMaintenanceError(
            "Choose exactly one replay maintenance scope: one key, one "
            "cohort, or every active key.",
            error_code="replay_maintenance_scope",
        )
    if kind == "cohort" and cohort_id is None:
        raise ReplayMaintenanceError(
            "Choose exactly one replay maintenance scope: one key, one "
            "cohort, or every active key.",
            error_code="replay_maintenance_scope",
        )
    scope = parse_replay_scope(
        key_id=key_id,
        cohort_id=cohort_id,
        all_active=(kind == "all_active"),
    )
    return kind, scope


def _parse_bound_fields(form: Any) -> tuple[Any, Any]:
    """Explicit UTC creation bounds; blanks mean no bound (fixed safe errors)."""
    created_from_raw = str(form.get("created_from") or "").strip()
    created_until_raw = str(form.get("created_until") or "").strip()
    created_from = (
        parse_utc_datetime(created_from_raw, field="created-from")
        if created_from_raw
        else None
    )
    created_until = (
        parse_utc_datetime(created_until_raw, field="created-until")
        if created_until_raw
        else None
    )
    validate_utc_bounds(created_from, created_until)
    return created_from, created_until


def _scope_label(scope: Any) -> str:
    if scope.key_id is not None:
        return "One gateway key"
    if scope.cohort_id is not None:
        return "One cohort"
    return "Every active key (explicit scope)"


def _scope_href(scope: Any) -> str:
    if scope.key_id is not None:
        return f"/admin/operations/replay-maintenance/key/{scope.key_id}"
    if scope.cohort_id is not None:
        return f"/admin/operations/replay-maintenance/cohort/{scope.cohort_id}"
    return "/admin/operations/replay-maintenance/all-active"


def _plan_context(request: Request, plan: Any) -> dict[str, Any]:
    """Finite reviewed-plan facts for the review/result template."""
    reasons = [
        {
            "code": code,
            "label": EXCLUSION_LABELS[code],
            "count": plan.exclusion_counts.get(code, 0),
        }
        for code in sorted(EXCLUSION_REASON_CODES)
    ]
    return {
        "scope_text": _safe_display(request, plan.scope.scope_text),
        "created_from": _iso(plan.created_from),
        "created_until": _iso(plan.created_until),
        "ttl_seconds": plan.ttl_seconds,
        "configured_ttl_seconds": plan.configured_ttl_seconds,
        "ttl_is_configured_default": plan.ttl_seconds == plan.configured_ttl_seconds,
        "include_expired": plan.include_expired,
        "previewed_at": _iso(plan.previewed_at),
        "selected_keys": plan.selected_keys,
        "eligible_references": plan.eligible_references,
        "exclusion_reasons": reasons,
        "old_expiry_min": _iso(plan.old_expiry_min),
        "old_expiry_max": _iso(plan.old_expiry_max),
        "new_expiry_min": _iso(plan.new_expiry_min),
        "new_expiry_max": _iso(plan.new_expiry_max),
        # Truthful label input: eligible>0 means the reviewed RANGES exist
        # (old and expected post-state under the max(old, created + TTL)
        # formula).  It does NOT mean every eligible row changes: rows
        # whose stored expiry is already at or beyond the target are not
        # shortened, so the applied page reports the ACTUAL
        # result.updated_references count instead.
        "has_eligible_range": plan.eligible_references > 0,
    }


def _inspection_context(request: Request, summary: ReplayInspectionSummary) -> dict[str, Any]:
    """Finite read-only inspection facts (alias-guarded dynamic labels)."""
    per_key = []
    for item in summary.per_key:
        key_code = str(item.key_id)
        # The sort attribute must carry the SAME safe display text: a
        # known incoming alias is never re-exposed through data-sort
        # values or hrefs.
        key_display = _safe_display(request, key_code)
        key_alias = _is_known_alias(request, key_code)
        per_key.append(
            {
                "key_id": key_display,
                "key_href": None if key_alias else f"/admin/keys/{key_code}",
                "key_status": _safe_display(request, item.key_status),
                "references": item.references,
                "active_references": item.active_references,
                "expired_references": item.expired_references,
                "created_min": _iso(item.created_min),
                "created_max": _iso(item.created_max),
                "expiry_min": _iso(item.expiry_min),
                "expiry_max": _iso(item.expiry_max),
            }
        )
    groups = []
    for item in summary.route_model_groups:
        route_code = str(item.route_id)
        route_display = _safe_display(request, route_code)
        route_alias = _is_known_alias(request, route_code)
        model_display = _safe_display(request, item.requested_model)
        groups.append(
            {
                "route_id": route_display,
                "route_href": None if route_alias else f"/admin/routes/{route_code}",
                "requested_model": model_display,
                "references": item.references,
            }
        )
    reasons = [
        {
            "code": code,
            "label": EXCLUSION_LABELS[code],
            "count": getattr(summary.reasons, code),
        }
        for code in sorted(EXCLUSION_REASON_CODES)
    ]
    return {
        "scope_text": _safe_display(request, summary.scope_text),
        "now": _iso(summary.now),
        "configured_ttl_seconds": summary.configured_ttl_seconds,
        # "keys" would collide with dict.keys in the Jinja projection.
        "keys_count": summary.keys,
        "keys_active_or_valid": summary.keys_active_or_valid,
        "references": summary.references,
        "active_references": summary.active_references,
        "expired_references": summary.expired_references,
        "created_min": _iso(summary.created_min),
        "created_max": _iso(summary.created_max),
        "expiry_min": _iso(summary.expiry_min),
        "expiry_max": _iso(summary.expiry_max),
        "per_key": per_key,
        "route_model_groups": groups,
        "route_model_groups_total": summary.route_model_groups_total,
        "route_model_groups_truncated": summary.route_model_groups_truncated,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Private POST operations
# ---------------------------------------------------------------------------


@router.post("/inspect", response_class=HTMLResponse)
async def replay_maintenance_inspect(request: Request) -> Response:
    """Read-only inspection: NO domain/audit write, shared service law."""
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    scope = None
    try:
        _kind, scope = _parse_scope_form(form)
        created_from, created_until = _parse_bound_fields(form)
    except ReplayMaintenanceError as exc:
        return _replay_error_page(
            request, status_code=400, message=exc.safe_message, scope=scope
        )

    # A submitted scope UUID is a finite fact of this request: a known
    # incoming authentication alias is refused before the service call
    # with a fixed no-echo message (and never re-exposed via a link).
    scope_code = str(scope.key_id or scope.cohort_id or "")
    if scope_code and _is_known_alias(request, scope_code):
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay maintenance scope cannot be inspected: it matches a "
                "known incoming authentication value."
            ),
        )

    try:
        async with _replay_session(request) as session:
            summary = await _replay_service(request, session).inspect_replay_references(
                scope=scope,
                created_from=created_from,
                created_until=created_until,
            )
    except ReplayMaintenanceError as exc:
        return _replay_error_page(
            request, status_code=400, message=exc.safe_message, scope=scope
        )
    except Exception:  # noqa: BLE001 - read-only inspection; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("replay maintenance inspection failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay maintenance inspection could not be completed right now; "
                "try again."
            ),
            scope=scope,
        )

    return _no_store(
        templates.TemplateResponse(
            request,
            "replay_maintenance/inspection.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "summary": _inspection_context(request, summary),
                "scope_label": _scope_label(scope),
                "scope_href": _scope_href(scope),
            },
        )
    )


@router.post("/preview", response_class=HTMLResponse)
async def replay_maintenance_preview(request: Request) -> Response:
    """Deliberate preview: shared service preview in a caller-owned
    transaction (NO domain/audit write), strict plan rendering and
    signing bound to the signed-in actor/session with a 15-minute bound.
    """
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    scope = None
    try:
        _kind, scope = _parse_scope_form(form)
        created_from, created_until = _parse_bound_fields(form)
    except ReplayMaintenanceError as exc:
        return _replay_error_page(
            request, status_code=400, message=exc.safe_message, scope=scope
        )

    scope_code = str(scope.key_id or scope.cohort_id or "")
    if scope_code and _is_known_alias(request, scope_code):
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay maintenance scope cannot be previewed: it matches a "
                "known incoming authentication value."
            ),
        )

    ttl_raw = str(form.get("ttl_seconds") or "").strip()
    if ttl_raw:
        if not _TTL_RE.fullmatch(ttl_raw):
            return _replay_error_page(
                request,
                status_code=400,
                message=(
                    "TTL must be a whole number of seconds (1..31536000), or blank "
                    "for the configured default."
                ),
                scope=scope,
            )
        ttl_seconds: int | None = int(ttl_raw)
    else:
        ttl_seconds = None

    include_expired = _is_checked(str(form.get("include_expired") or ""))
    reason = str(form.get("reason") or "")
    if not reason.strip():
        return _replay_error_page(
            request,
            status_code=400,
            message="Enter a nonblank audit reason for the reviewed replay extension.",
            scope=scope,
        )
    if len(reason) > MAX_KEY_CONFIGURATION_REASON_LENGTH:
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "Audit reason is too long. Keep it to at most "
                f"{MAX_KEY_CONFIGURATION_REASON_LENGTH} characters."
            ),
            scope=scope,
        )
    # The normal GUI reason convention does not trim: the ORIGINAL string
    # (leading/trailing spaces included) is the reviewed string, and the
    # shared Core re-validates nonblank content and credential shapes on
    # it at apply.  A known incoming alias is refused before signing.
    if _is_known_alias(request, reason):
        return _replay_error_page(
            request,
            status_code=400,
            message="Reason withheld: it matches a known incoming authentication value.",
            scope=scope,
        )

    try:
        async with _replay_session(request) as session:
            plan = await _replay_service(request, session).preview_replay_extend(
                scope=scope,
                ttl_seconds=ttl_seconds,
                include_expired=include_expired,
                created_from=created_from,
                created_until=created_until,
            )
    except ReplayMaintenanceError as exc:
        return _replay_error_page(
            request, status_code=400, message=exc.safe_message, scope=scope
        )
    except Exception:  # noqa: BLE001 - read-only preview; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("replay maintenance preview failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _replay_error_page(
            request,
            status_code=400,
            message="The replay extension preview could not be prepared right now; try again.",
            scope=scope,
        )

    plan_document = render_replay_extend_plan(plan)
    # The strict 32KiB aggregate bound on the RENDERED plan is enforced
    # BEFORE any allocation or signing (the CLI applies the same bound
    # to its plan files); the review-intent wrapper budgets the envelope.
    rendered = json.dumps(plan_document, indent=2, sort_keys=True).encode("utf-8")
    if len(rendered) > REPLAY_PLAN_MAX_BYTES:
        return _replay_error_page(
            request,
            status_code=400,
            message="The reviewed replay plan exceeds the bounded size.",
            scope=scope,
        )

    review_document: dict[str, Any] = {"plan": plan_document, "reason": reason}
    # Every signed/displayed fact (scope UUIDs, bounds, counts,
    # fingerprints, and the free-text reason) is a known-alias guard
    # BEFORE signing or rendering: refused with a fixed no-echo message,
    # never signed or re-displayed.
    if _review_doc_has_alias(request, review_document):
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The reviewed replay facts can no longer be shown: they match a "
                "known incoming authentication value. Preview the scope again."
            ),
            scope=scope,
        )
    try:
        token = build_replay_review_token(
            admin_session_secret=_settings(request).ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            review_document=review_document,
        )
    except Exception:  # noqa: BLE001 - signing is pure; fixed safe fallback
        return _replay_error_page(
            request,
            status_code=400,
            message="The reviewed replay extension could not be signed; try again.",
            scope=scope,
        )

    return _no_store(
        templates.TemplateResponse(
            request,
            "replay_maintenance/review.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "plan_document": plan_document,
                "reason": reason,
                "plan_context": _plan_context(request, plan),
                "scope_label": _scope_label(plan.scope),
                "scope_href": _scope_href(plan.scope),
                "review_token": token,
                "result": None,
            },
        )
    )


@router.post("/apply", response_class=HTMLResponse)
async def replay_maintenance_apply(request: Request) -> Response:
    """Verify the signed review, then apply in ONE caller transaction.

    The token is reviewed data, never authority: posted plan/count/TTL/
    reason/actor overrides confer no authority.  The signed facts are
    re-checked against THIS request's known incoming aliases before any
    service call or audit write.  The shared service determines stale
    scope/state/eligibility, HMAC availability, and the accepted repeat
    under its lock law; the extension and its one audit record commit
    together or roll back in the caller-owned transaction.
    """
    if (gate := _dashboard_gate(request)) is not None:
        return gate
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    review_token = str(form.get("review_token") or "")
    confirm_apply = str(form.get("confirm_apply") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    # Everything below runs BEFORE any mutation.
    try:
        document = verify_replay_review_token(
            admin_session_secret=_settings(request).ADMIN_SESSION_SECRET,
            token=review_token,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
    except AdminReviewIntentError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        # The reviewed scope cannot be trusted from an invalid token, so
        # recovery falls back to the fixed replay entry.
        return _replay_error_page(request, status_code=400, message=exc.message)
    if not _is_checked(confirm_apply):
        return _replay_error_page(
            request,
            status_code=400,
            message="Confirm the reviewed replay extension before applying it.",
            scope=parse_replay_extend_plan_document(document["plan"]).scope,
        )

    # The SAME signed facts the preview guarded (scope UUIDs, bounds,
    # counts, fingerprints, and the free-text reason) are re-checked
    # against THIS apply request's known incoming aliases before any
    # service call or audit write; a withheld fact is never applied or
    # re-rendered.
    plan_doc = document["plan"]
    if _review_doc_has_alias(request, document):
        try:
            alias_scope = parse_replay_extend_plan_document(plan_doc).scope
        except ReplayMaintenanceError:
            alias_scope = None
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The reviewed replay extension can no longer be applied: a "
                "reviewed value matches a known incoming authentication value. "
                "Preview the scope again."
            ),
            scope=alias_scope,
        )

    plan: Any = None
    reason = ""
    try:
        plan = parse_replay_extend_plan_document(document["plan"])
        reason = str(document["reason"])
        async with _replay_session(request) as session:
            result = await _replay_service(request, session).apply_replay_extend(
                plan=plan,
                reason=reason,
                actor_admin_id=action_context.admin_user.id,
            )
    except ReplayMaintenanceStaleError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                exc.safe_message + " Preview the scope again to review the current state."
            ),
            scope=plan.scope if plan is not None else None,
        )
    except ReplayMaintenanceError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _replay_error_page(
            request,
            status_code=400,
            message=exc.safe_message,
            scope=plan.scope if plan is not None else None,
        )
    except Exception:  # noqa: BLE001 - outcome may be unconfirmed; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("replay maintenance apply failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _replay_error_page(
            request,
            status_code=400,
            message=(
                "The replay extension outcome is UNCONFIRMED. Check the replay "
                "reference state and the audit log before retrying or previewing "
                "again; a lost commit acknowledgement cannot prove a rollback."
            ),
            scope=plan.scope if plan is not None else None,
        )

    return _no_store(
        templates.TemplateResponse(
            request,
            "replay_maintenance/review.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "plan_document": document["plan"],
                "reason": reason,
                "plan_context": _plan_context(request, plan),
                "scope_label": _scope_label(plan.scope),
                "scope_href": _scope_href(plan.scope),
                "review_token": None,
                "result": result,
            },
        )
    )
