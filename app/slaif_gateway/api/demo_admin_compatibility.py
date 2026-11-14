"""Objective 224-u: demo-only read-only Codex compatibility views.

A small, purpose-built router mounted by ``create_demo_app`` ONLY,
BEFORE the normal compatibility router, so the exact paths
``GET /admin/operations/compatibility/``,
``GET /admin/operations/compatibility/preset/{shipped-name}``, its
``GET .../download`` child and
``GET /admin/operations/compatibility/key/{canonical-uuid}`` are
served by these demo handlers in the demo process while the normal
handlers are never reached for those paths there. Every other
compatibility shape (unknown preset names, subpaths, near misses)
stays default-denied by the central demo gate; every unsafe method
(including the review/apply POSTs) remains the unchanged uniform 204
cut before body parsing and dispatch - no key pin, quota, usage,
replay, audit or permission mutation is possible.

Installation facts (the qualification rows, the per-key binding) are
computed ONLY from this request's local verified SELECT-only copy:
the handlers first re-verify ``current_database()`` and
``transaction_read_only`` on the gate's SAME request-local copy
engine, and every repository read goes through the copy-bound
``get_sessionmaker_from_app`` seam. The demo process's dummy
Settings, any current app-global Codex profile, a live public base
URL, the environment or the network are NEVER used as installation
facts: the demo web process adopts no API startup profile (the
page says so), and no runnable profile artifact is offered - the
qualification rows carry a fixed demo note instead of artifact
links. The shipped preset documents are package-owned
credential-free reference material (validated by the existing
finite preset loader), not a per-login operator file; the download
serves only the bounded, exact canonical bytes after the existing
known-incoming-secret-alias check (refusal, never a rewrite). The
known-incoming-secret-alias withholding applies to every rendered
fact. No raw key, provider credential, operator source path/host,
signed review payload or writable action endpoint appears in any
demo response; links stay copy-backed.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from sqlalchemy import text

from slaif_gateway.api.admin import _admin_key_dashboard_service_scope
from slaif_gateway.api.admin import templates
from slaif_gateway.api.admin_compatibility import (
    _client_module_pin,
    _compat_session,
    _is_known_alias,
    _no_store,
    _operation_options,
    _qualification_service,
    _safe_display,
)
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileDataError,
    list_codex_presets,
    read_codex_preset,
)
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.codex_module_upgrade import (
    module_selector,
)

router = APIRouter(
    prefix="/admin/operations/compatibility", include_in_schema=False
)

# Truthful demo scope for the qualification table (224-u): the rows
# are this visitor's frozen copy - and no runnable profile artifact
# is offered from it.
_DEMO_ARTIFACTS_NOTE = (
    "Not offered in the demo snapshot (no runnable profile export)."
)
_DEMO_WITHHELD_ROUTE_NOTE = (
    "Withheld: route ID matches a known credential value."
)

_SAFE_UNAVAILABLE = (
    "The Codex compatibility is unavailable for this demo session."
)


def _not_found() -> Response:
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


def _refused_export() -> Response:
    return HTMLResponse(
        "The compatibility preset export was refused because it "
        "contains a known credential value. The canonical preset "
        "is unchanged.",
        status_code=403,
        headers={"Cache-Control": "private, no-store"},
    )


def _demo_state(request: Request):
    return getattr(request.state, "demo_admin", None)


def _has_query(request: Request) -> bool:
    # NO query parameter is defined on ANY demo compatibility GET;
    # the gate already enforces this for the exact paths.
    return request.query_params.multi_items() != []


async def _copy_recheck(request: Request) -> bool:
    """One SELECT-only/read-only transaction on the gate's SAME
    request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck."""
    demo = request.state.demo_admin
    try:
        session_factory = get_sessionmaker_from_app(request)
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            return current == demo.target_db and read_only == "on"
    except Exception:
        return False


def _preset_facts(name: str) -> dict[str, Any] | None:
    for preset_name, _path, profile in list_codex_presets():
        if preset_name == name:
            return profile.to_facts()
    return None


@router.get("/", response_class=HTMLResponse)
async def demo_compatibility_index(request: Request) -> Response:
    """The demo compatibility index (exact path with its REQUIRED
    trailing slash, gate-admitted).

    The qualification rows are computed from this visitor's exact
    verified copy (the qualification service on the copy-bound
    sessionmaker); the presets are the package-owned shipped
    reference set. No runnable profile artifact is offered and the
    demo web process adopts no API startup profile - the template's
    demo branches say exactly that.
    """
    demo = _demo_state(request)
    if demo is None or _has_query(request):
        return _not_found()
    try:
        get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    if not await _copy_recheck(request):
        return _unavailable()

    qualification_rows: list[dict[str, Any]] = []
    qualification_error = False
    try:
        async with _compat_session(request) as session:
            results = await _qualification_service(session).inspect()
        for result in results:
            row_route_id = str(result.route_id)
            route_alias = _is_known_alias(request, row_route_id)
            if route_alias:
                artifacts_note = _DEMO_WITHHELD_ROUTE_NOTE
            elif result.ready and result.profile_id:
                artifacts_note = _DEMO_ARTIFACTS_NOTE
            else:
                artifacts_note = "Unavailable until the route is ready (see Reasons)."
            module_text = (
                f"{result.client_module_id} v{result.client_module_version}"
                if result.client_module_id
                else "—"
            )
            reasons_text = (
                ", ".join(result.reason_codes)
                if result.reason_codes
                else "No blocking reasons"
            )
            badge = _safe_display(request, result.badge)
            state_label = (
                "Protocol-qualified"
                if result.ready and badge.startswith("Protocol-qualified")
                else badge
            )
            qualification_rows.append(
                {
                    "badge": badge,
                    "ready": result.ready,
                    "requested_model": _safe_display(request, result.requested_model),
                    "provider": _safe_display(request, result.provider),
                    "endpoint": _safe_display(request, result.endpoint),
                    "route_id": _safe_display(request, row_route_id),
                    "route_href": (
                        None if route_alias else f"/admin/routes/{row_route_id}"
                    ),
                    "profile": _safe_display(request, result.profile_id or "—"),
                    "metadata_version": result.metadata_version,
                    # The demo NEVER offers a runnable profile
                    # artifact: the link decision is fixed False.
                    "artifacts": None,
                    "artifacts_note": _safe_display(request, artifacts_note),
                    "module": _safe_display(request, module_text),
                    "reasons": _safe_display(request, reasons_text),
                    "state_label": state_label,
                }
            )
    except Exception:  # noqa: BLE001 - inspection is read-only; safe fallback
        qualification_error = True

    presets: list[dict[str, Any]] = []
    presets_error = False
    try:
        for name, _path, profile in list_codex_presets():
            facts = profile.to_facts()
            name_alias = _is_known_alias(request, name)
            presets.append(
                {
                    "name": _safe_display(request, name),
                    "revision": _safe_display(request, facts.get("revision", "—")),
                    "digest": _safe_display(request, facts.get("digest", "—")),
                    "cli_version": _safe_display(request, facts.get("cli_version", "—")),
                    "inspect_href": (
                        None
                        if name_alias
                        else f"/admin/operations/compatibility/preset/{name}"
                    ),
                    "download_href": (
                        None
                        if name_alias
                        else f"/admin/operations/compatibility/preset/{name}/download"
                    ),
                    "actions_note": (
                        "Withheld: preset name matches a known credential value."
                        if name_alias
                        else ""
                    ),
                }
            )
    except CodexProfileDataError:
        presets_error = True

    response = templates.TemplateResponse(
        request,
        "compatibility/index.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "qualification_rows": qualification_rows,
            "qualification_error": qualification_error,
            "startup_profile": None,
            "startup_profile_facts": None,
            "presets": presets,
            "presets_error": presets_error,
            "demo_admin": True,
        },
        status_code=200,
    )
    return _no_store(response)


@router.get("/preset/{name}", response_class=HTMLResponse)
async def demo_compatibility_preset_page(
    request: Request, name: str
) -> Response:
    """One shipped preset page (the gate admits ONLY the exact
    validated shipped names; the strict loader is the final
    authority)."""
    demo = _demo_state(request)
    if demo is None or _has_query(request):
        return _not_found()
    try:
        get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    if not await _copy_recheck(request):
        return _unavailable()
    try:
        document = read_codex_preset(name)
        facts = _preset_facts(name)
    except CodexProfileDataError:
        return _not_found()
    safe_facts = (
        {key: _safe_display(request, value) for key, value in sorted(facts.items())}
        if facts is not None
        else None
    )
    document_withheld = _is_known_alias(request, document)
    response = templates.TemplateResponse(
        request,
        "compatibility/preset.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "name": name,
            "facts": safe_facts,
            "document": None if document_withheld else document,
            "document_withheld": document_withheld,
            "demo_admin": True,
        },
        status_code=200,
    )
    return _no_store(response)


@router.get("/preset/{name}/download")
async def demo_compatibility_preset_download(
    request: Request, name: str
) -> Response:
    """The demo preset export: the bounded, exact canonical
    credential-free bytes after the existing secret check (refusal,
    never a rewrite)."""
    demo = _demo_state(request)
    if demo is None or _has_query(request):
        return _not_found()
    try:
        get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    if not await _copy_recheck(request):
        return _unavailable()
    try:
        document = read_codex_preset(name)
    except CodexProfileDataError:
        return _not_found()
    if _is_known_alias(request, document):
        return _refused_export()
    response = Response(
        document,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
    return _no_store(response)


@router.get("/key/{key_id}", response_class=HTMLResponse)
async def demo_compatibility_key_page(
    request: Request, key_id: str
) -> Response:
    """One key's compatibility binding from this visitor's exact
    verified copy (canonical lowercase UUID only - the gate admits
    no other shape). The review form is rendered as in the normal
    page but has NO effect: every unsafe method is the gate's quiet
    204 cut (no review is signed, nothing is applied)."""
    demo = _demo_state(request)
    if demo is None or _has_query(request):
        return _not_found()
    try:
        parsed_key_id = uuid.UUID(key_id)
    except ValueError:
        return _not_found()
    try:
        get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    if not await _copy_recheck(request):
        return _unavailable()
    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            key = await service.get_key_detail(parsed_key_id)
    except AdminKeyNotFoundError:
        return _not_found()
    except Exception:
        return _unavailable()

    pin = _client_module_pin(key.responses_policy)
    selector = module_selector(pin) if pin is not None else None
    pin_readable = pin is not None and not any(
        _is_known_alias(request, pin[field])
        for field in ("id", "version", "fixture_sha256")
    )
    options = _operation_options(pin) if pin_readable else []
    pin_display = (
        {
            "id": _safe_display(request, pin["id"]),
            "version": _safe_display(request, pin["version"]),
            "fixture_sha256": _safe_display(request, pin["fixture_sha256"]),
        }
        if pin is not None
        else None
    )
    pin_raw = (
        {
            "from_version": pin["version"],
            "from_digest": pin["fixture_sha256"],
            "pin_selector": selector,
        }
        if pin_readable
        else {"from_version": "", "from_digest": "", "pin_selector": ""}
    )

    response = templates.TemplateResponse(
        request,
        "compatibility/key.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "key": key,
            "pin": pin_display,
            "pin_readable": pin_readable,
            "pin_raw": pin_raw,
            "selector": selector if pin_readable else None,
            "options": options,
            "default_operation": options[0][0] if options else "",
            "demo_admin": True,
        },
        status_code=200,
    )
    return _no_store(response)
