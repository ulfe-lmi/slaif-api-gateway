"""Operations GUI (objective 211-a): content-free request diagnostics and
safe process-configuration inspection.

Surfaces under ``/admin/operations``:

- ``GET  /admin/operations/``                landing (two operation cards)
- ``GET  /admin/operations/diagnostics``     status panel, lookup form,
  recent-ID picker, and result area (content-free records only)
- ``POST /admin/operations/diagnostics/lookup``   resolve one submitted ID
  (safe ID grammar plus known-incoming-alias withholding; fixed typed
  outcomes; unsafe values are never redisplayed or echoed)
- ``POST /admin/operations/diagnostics/choices``  the ONE kind-specific
  picker POST lookup (CSRF-verified non-mutating session, fixed endpoint,
  the query is never echoed, store-unavailable is a distinct outcome)
- ``POST /admin/operations/diagnostics/cleanup``  one bounded expired
  records prune plus its one actor/reason audit in ONE transaction
  (explicit confirmation checkbox, bounded nonblank reason)
- ``GET  /admin/operations/process-configuration``  the finite 45-setting
  API-process snapshot, operator-declared revision, upstream LLM profile
  identities, and the Codex client identity (startup snapshots only)

The diagnostics module only maps form state to the shared typed
service and renders safe projections: content-free projection, the ID
grammar, alias discovery, bounded reads, and the audited-cleanup
transaction all live in :mod:`slaif_gateway.services.request_diagnostics`
and the repositories.  The configuration page renders the finite
allowlist only — no environment dump, no ``model_dump`` enumeration, no
database/Redis/connectivity claims, and no capture arming.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from slaif_gateway import __version__
from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_bounded_reason,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_service_scope,
    _clear_session_cookie,
    _set_no_store_headers,
    _is_checked,
    _settings,
    templates,
)
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.request_diagnostics import (
    DIAGNOSTIC_LOOKUP_BOUND,
    DiagnosticsCleanupResult,
    DiagnosticsNamespace,
    DiagnosticLookupOutcome,
    DiagnosticLookupResult,
)
from slaif_gateway.services.admin_session_service import AdminSessionError
from slaif_gateway.services.configuration_inspection import (
    API_PROCESS_RESTART_SCOPE,
    CONFIG_INSPECTION_ALLOWLIST,
    inspect_process_configuration,
    setting_meaning,
)
from slaif_gateway.services.request_diagnostics import (
    DIAGNOSTIC_CHOICE_QUERY_MAX_LENGTH,
    DIAGNOSTIC_CHOICE_SELECTED_MAX,
    RequestDiagnosticsService,
    is_known_incoming_secret_alias,
    is_safe_diagnostic_id,
    safe_deployment_revision,
)
from slaif_gateway.web.formatting import format_number, format_tokens_m

router = APIRouter(prefix="/admin", include_in_schema=False)

# Finite namespace vocabulary for lookup and picker scope.
_NAMESPACE_VALUES: dict[str, DiagnosticsNamespace] = {
    "any": DiagnosticsNamespace.ANY,
    "gateway": DiagnosticsNamespace.GATEWAY,
    "client": DiagnosticsNamespace.CLIENT,
}

# The ONE kind served by the picker POST lookup (matches the record-choice
# control kind and the JS constant; every other kind stays on the shared
# GET /admin/record-choices endpoint).
_DIAGNOSTIC_PICKER_KIND = "diagnostic_request_id"

# One bounded cleanup batch removes at most this many expired records.
_CLEANUP_BATCH_LIMIT = 1000


def _diagnostics_service(request: Request) -> RequestDiagnosticsService:
    """Module seam for the typed diagnostics service (unit-test fake)."""
    return RequestDiagnosticsService(
        settings=_settings(request),
        session_factory=get_sessionmaker_from_app(request),
    )


def _accepted_prefixes(request: Request) -> tuple[str, ...]:
    return _settings(request).get_gateway_key_accepted_prefixes()


def _is_unsafe_lookup_value(request: Request, value: str) -> bool:
    """True when a submitted lookup value must be withheld.

    Refuses both values outside the safe ID grammar and values that are
    or embed a KNOWN incoming authentication alias (accepted gateway
    prefixes, credential shapes, and incoming bearer/cookie/session/proxy/
    query credentials via the shared pure discovery helpers).  A regex
    alone is deliberately not sufficient: opaque values such as the
    current admin session cookie can fit the grammar.
    """
    if not is_safe_diagnostic_id(value):
        return True
    return is_known_incoming_secret_alias(
        value, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    )


def _is_incoming_alias(request: Request, value: object) -> bool:
    """Output-side check: is this stored/display value a known incoming
    authentication alias for THIS request?

    Input-only checks are insufficient: a safe ID written under one
    request's credentials can equal an opaque credential value (e.g. a
    cookie) of a LATER request.  Display projections withhold such
    values without mutating stored facts, canonical profile identities,
    or any review state; the existing pure discovery helpers are reused
    (no generic sanitizer framework).
    """
    if not isinstance(value, str) or not value:
        return False
    return is_known_incoming_secret_alias(
        value, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    )


def _choice_options_for_request(
    request: Request, result: Any
) -> list[dict[str, str]]:
    """Picker option rows with output-side alias withholding applied.

    The sub line carries only the namespace and the real write time
    (never free-form content); a choice whose ID is a known incoming
    alias for this request is withheld from the rendered set.
    """
    return [
        {
            "id": choice.id,
            "label": choice.id,
            "sub": f"{choice.namespace} · {choice.recorded_at:%Y-%m-%d %H:%M UTC}",
        }
        for choice in result.choices
        if not _is_incoming_alias(request, choice.id)
    ]


# String fields of a found record whose stored values must pass the
# output-side alias check before HTML rendering (the finite grammar
# bounds stay authoritative; this only withholds known aliases).
_RECORD_DISPLAY_FIELDS: tuple[str, ...] = (
    "gateway_request_id",
    "client_request_id",
    "client_id_unavailable_reason",
    "endpoint_template",
    "source",
    "reason_code",
    "error_code",
    "error_param",
    "route_pattern",
    "deployment_revision",
    "replay_error_code",
)


def _withheld_record_fields(
    request: Request, record: Any
) -> set[str]:
    """Names of found-record string fields withheld from display."""
    withheld: set[str] = set()
    for name in _RECORD_DISPLAY_FIELDS:
        if _is_incoming_alias(request, getattr(record, name, None)):
            withheld.add(name)
    return withheld


def _human_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} day(s)"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} hour(s)"
    if seconds % 60 == 0:
        return f"{seconds // 60} minute(s)"
    return f"{seconds} second(s)"


# Token-named keys inside the counts/limits fact maps (the closed
# vocabulary from the record projection).
_TOKEN_FACT_KEYS = frozenset(
    {
        "absolute_max_output_tokens",
        "max_output_tokens",
        "max_input_tokens",
        "context_window_tokens",
    }
)


def _format_fact_map(value: Any) -> str:
    """Readable labelled numeric facts for a positions/counts/limits map.

    Shared formatters: grouped ``num`` for ordinary counts and M tokens
    (plus the exact raw count) for token-named keys; never a Python dict
    repr. The exact raw record stays authoritative in the database.
    """
    if not value:
        return "—"
    parts: list[str] = []
    for key in sorted(value):
        number = format_number(value[key])
        if key in _TOKEN_FACT_KEYS:
            parts.append(
                f"{key}: {format_tokens_m(value[key])}M tokens ({number})"
            )
        else:
            parts.append(f"{key}: {number}")
    return " · ".join(parts)


def _json_error(message: str, status_code: int) -> JSONResponse:
    """Fixed-message JSON refusal for the private picker endpoint.

    The message is derived only from finite constants (never from the
    submitted input), and every private lookup response — including
    errors — carries no-store cache headers.
    """
    response = JSONResponse({"detail": message}, status_code=status_code)
    _set_no_store_headers(response)
    return response


def _render_diagnostics_page(
    request: Request,
    *,
    context: Any,
    csrf_token: str,
    status: Any,
    lookup_value: str = "",
    lookup_namespace: str = "any",
    lookup_result: DiagnosticLookupResult | None = None,
    picker_options: list[dict[str, str]] | None = None,
    cleanup_result: DiagnosticsCleanupResult | None = None,
    error_message: str = "",
) -> Response:
    if picker_options is None:
        picker_options = []
    withheld: set[str] = set()
    facts: dict[str, str] = {}
    if lookup_result is not None and lookup_result.record is not None:
        withheld = _withheld_record_fields(request, lookup_result.record)
        record = lookup_result.record
        facts = {
            "positions": _format_fact_map(record.positions),
            "counts": _format_fact_map(record.counts),
            "limits": _format_fact_map(record.limits),
        }
    response = templates.TemplateResponse(
        request,
        "operations/diagnostics.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "status": status,
            "human_retention": _human_duration(status.retention_seconds),
            "lookup_value": lookup_value,
            "lookup_namespace": lookup_namespace,
            "lookup_result": lookup_result,
            "withheld_fields": withheld,
            "facts": facts,
            "picker_options": picker_options,
            "cleanup_result": cleanup_result,
            "cleanup_batch_limit": _CLEANUP_BATCH_LIMIT,
            "error_message": error_message,
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


async def _admin_choices_context(
    request: Request, csrf_token: str
) -> tuple[Any, None] | Response:
    """Non-mutating auth for the picker POST lookup.

    Same session validation law as the pages, but with ``touch=False``
    and CSRF verification WITHOUT a refresh (mirrors the shared
    record-choices lookup posture): repeated picker searches never
    invalidate the rendered form's token and never mutate session rows.
    Returns a fixed JSON 400 for an invalid CSRF token (AJAX surface).
    """
    settings = _settings(request)
    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        response = RedirectResponse("/admin/login", status_code=303)
        _set_no_store_headers(response)
        return response
    try:
        async with _admin_service_scope(request) as service:
            context = await service.validate_admin_session(
                session_token=session_token,
                touch=False,
            )
            if not service.verify_session_csrf_token(context.admin_session, csrf_token):
                return _json_error("Invalid CSRF token.", 400)
            return context, None
    except (AdminSessionError, RuntimeError):
        response = RedirectResponse("/admin/login", status_code=303)
        _clear_session_cookie(response, settings)
        _set_no_store_headers(response)
        return response


@router.get("/operations/")
async def operations_index(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    response = templates.TemplateResponse(
        request,
        "operations/index.html",
        {"admin": context.admin_user, "csrf_token": csrf_token},
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@router.get("/operations/diagnostics")
async def operations_diagnostics_page(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    service = _diagnostics_service(request)
    status = await service.status()

    # GET convenience prefill: validated with the safe-ID grammar plus the
    # known-incoming-alias check and the finite namespace vocabulary;
    # unsafe values are ignored (safe projected identifiers only).
    namespace_param = (request.query_params.get("namespace") or "any").strip().lower()
    namespace = _NAMESPACE_VALUES.get(namespace_param, DiagnosticsNamespace.ANY)
    lookup_param = (request.query_params.get("lookup") or "").strip()
    prefill = ""
    if lookup_param and not _is_unsafe_lookup_value(request, lookup_param):
        prefill = lookup_param

    try:
        choices = await service.lookup_choices(
            namespace=namespace, selected=()
        )
        picker_options = _choice_options_for_request(request, choices)
    except Exception:  # noqa: BLE001 - picker degrades to an empty batch
        picker_options = []

    return _render_diagnostics_page(
        request,
        context=context,
        csrf_token=csrf_token,
        status=status,
        lookup_value=prefill,
        lookup_namespace=namespace_param if namespace_param in _NAMESPACE_VALUES else "any",
        picker_options=picker_options,
    )


@router.post("/operations/diagnostics/lookup")
async def operations_diagnostics_lookup(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    context_or_response = await _admin_action_context(
        request, csrf_token=str(form.get("csrf_token") or "")
    )
    if isinstance(context_or_response, Response):
        return context_or_response
    context = context_or_response

    namespace_param = str(form.get("lookup_namespace") or "").strip().lower()
    namespace = _NAMESPACE_VALUES.get(namespace_param)
    if namespace is None:
        return _admin_error_page(request, status_code=400, message="Invalid namespace.")

    # ONE integrated control: the record-choice named lookup_id carries
    # either a selected retained ID (managed hidden field) or the typed
    # value (allow_new); there is no second entry/selection field whose
    # stale text could override the selection.
    value = str(form.get("lookup_id") or "").strip()

    service = _diagnostics_service(request)
    if not value:
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=await service.status(),
            lookup_namespace=namespace_param,
            error_message="Enter a diagnostic request ID.",
        )
    if _is_unsafe_lookup_value(request, value):
        # Unsafe values and known incoming aliases are withheld: a typed
        # not-found with the field CLEARED; the value never reaches HTML,
        # a redirect, or the logs.
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=await service.status(),
            lookup_value="",
            lookup_namespace=namespace_param,
            lookup_result=DiagnosticLookupResult(
                outcome=DiagnosticLookupOutcome.NOT_FOUND, namespace=namespace
            ),
        )
    result = await service.resolve(value, namespace=namespace)
    return _render_diagnostics_page(
        request,
        context=context,
        csrf_token=str(form.get("csrf_token") or ""),
        status=await service.status(),
        lookup_value=value,
        lookup_namespace=namespace_param,
        lookup_result=result,
    )


@router.post("/operations/diagnostics/choices")
async def operations_diagnostics_choices(request: Request) -> Response:
    """The ONE kind-specific picker POST lookup (211-a).

    Body: ``kind`` (must be the diagnostics picker kind), ``namespace``
    (finite), optional ``q`` (bounded substring, never echoed), repeated
    ``selected`` (safe IDs that reserve their slots), and the page's
    ``csrf_token``.  JSON response has the same shape as the shared GET
    record-choices endpoint; an unavailable store is a distinct marker,
    never an empty match set.
    """
    # An unavailable store is a distinct NON-SUCCESS status (503) with
    # safe JSON so the picker widget shows "unavailable" instead of
    # treating it as success with zero matches; retained values are
    # still withheld output-side against this request's credentials.
    if not _settings(request).ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    auth = await _admin_choices_context(
        request, csrf_token=str(form.get("csrf_token") or "")
    )
    if isinstance(auth, Response):
        return auth  # 303 login redirect (unauthenticated)

    if str(form.get("kind") or "") != _DIAGNOSTIC_PICKER_KIND:
        return _json_error("Unknown picker kind.", 400)
    namespace_param = str(form.get("namespace") or "").strip().lower()
    namespace = _NAMESPACE_VALUES.get(namespace_param)
    if namespace is None:
        return _json_error("Invalid namespace.", 400)

    query = str(form.get("q") or "").strip()
    if len(query) > DIAGNOSTIC_CHOICE_QUERY_MAX_LENGTH:
        return _json_error(
            f"At most {DIAGNOSTIC_CHOICE_QUERY_MAX_LENGTH} "
            "characters are accepted for the search.",
            400,
        )
    if query and is_known_incoming_secret_alias(
        query, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    ):
        # A known incoming authentication alias is never used as search
        # data and never echoed; the fixed message carries no input.
        return _json_error("Search value withheld.", 400)

    selected_values: list[str] = []
    # Raw repeat-count bound BEFORE cleaning/deduplication: 101 identical
    # submitted values must not slip past the count bound (the service
    # bound applies AFTER dedup) and must not re-run secret discovery.
    selected_raw = form.getlist("selected")
    if len(selected_raw) > DIAGNOSTIC_CHOICE_SELECTED_MAX:
        return _json_error("Too many selected values.", 400)
    for raw in selected_raw:
        stem = str(raw).strip()
        if not stem:
            continue
        if (
            not is_safe_diagnostic_id(stem)
            or is_known_incoming_secret_alias(
                stem,
                scope=request.scope,
                accepted_prefixes=_accepted_prefixes(request),
            )
        ):
            return _json_error("Invalid selected value.", 400)
        selected_values.append(stem)

    service = _diagnostics_service(request)
    try:
        result = await service.lookup_choices(
            namespace=namespace, query=query or None, selected=tuple(selected_values)
        )
    except ValueError:
        # Excess selected inputs (service-side explicit bound): fixed safe
        # message derived only from the constant, no input echo.
        return _json_error("Too many selected values.", 400)

    if not result.store_available:
        # Distinct safe unavailable outcome (never an empty match set):
        # non-success status, no choice values, no details.
        return _json_error("Diagnostics store unavailable.", 503)

    payload = {
        "kind": _DIAGNOSTIC_PICKER_KIND,
        "limit": DIAGNOSTIC_LOOKUP_BOUND,
        "choices": _choice_options_for_request(request, result),
        "cutoff": result.cutoff.isoformat(),
        "store_available": bool(result.store_available),
    }
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@router.post("/operations/diagnostics/cleanup")
async def operations_diagnostics_cleanup(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    context_or_response = await _admin_action_context(
        request, csrf_token=str(form.get("csrf_token") or "")
    )
    if isinstance(context_or_response, Response):
        return context_or_response
    context = context_or_response

    service = _diagnostics_service(request)
    status = await service.status()

    if not _is_checked(str(form.get("confirm") or "")):
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=status,
            error_message="Confirm the cleanup before it runs.",
        )
    reason, reason_error = _admin_bounded_reason(str(form.get("reason") or ""))
    if reason_error:
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=status,
            error_message=reason_error,
        )
    if reason is None:
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=status,
            error_message="A reason is required for the audit log.",
        )
    if _is_incoming_alias(request, reason):
        # The generic reason redactor cannot recognize opaque values
        # (e.g. the current incoming cookie): the request-aware
        # incoming-alias guard applies BEFORE the cleanup service/audit
        # call.  Fixed safe error, blank recovery field, no service call.
        return _render_diagnostics_page(
            request,
            context=context,
            csrf_token=str(form.get("csrf_token") or ""),
            status=status,
            error_message=(
                "Reason withheld: it matches a known incoming "
                "authentication value."
            ),
        )

    result = await service.cleanup_audited(
        actor_admin_user_id=context.admin_user.id,
        reason=reason,
    )
    return _render_diagnostics_page(
        request,
        context=context,
        csrf_token=str(form.get("csrf_token") or ""),
        status=await service.status(),
        cleanup_result=result,
    )


@router.get("/operations/process-configuration")
async def operations_process_configuration_page(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    payload = inspect_process_configuration(settings, process_scope="api")
    config = payload["config"]
    settings_rows = []
    for name in CONFIG_INSPECTION_ALLOWLIST:
        entry = config["settings"][name]
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

    profiles = getattr(request.app.state, "upstream_llm_profiles", None)
    profile_rows = []
    if profiles:
        for profile_id in sorted(profiles):
            profile = profiles[profile_id]
            # Output-side withholding for the displayed identity strings
            # (canonical snapshot data is never mutated): a profile id or
            # sha256 that is a known incoming alias for THIS request is
            # withheld, and the selector is only rendered when BOTH
            # identity strings are shown (no partial selector echo).
            pid_display = (
                profile.profile_id
                if not _is_incoming_alias(request, profile.profile_id)
                else None
            )
            sha_display = (
                profile.sha256
                if not _is_incoming_alias(request, profile.sha256)
                else None
            )
            selector = (
                {
                    "version": 1,
                    "profile": pid_display,
                    "revision": profile.revision,
                    "sha256": sha_display,
                }
                if pid_display is not None and sha_display is not None
                else None
            )
            profile_rows.append(
                {
                    "profile_id": pid_display,
                    "revision": profile.revision,
                    "instruction_placement": profile.instruction_placement,
                    "tool_encoding": profile.tool_encoding,
                    "sha256": sha_display,
                    "selector": selector,
                }
            )

    codex_profile = getattr(request.app.state, "codex_0162_profile", None)
    codex_facts = None
    if codex_profile is not None:
        # Display projection of the identity/provenance facts: the SAME
        # targeted output withholding applies to every displayed value
        # (a stored fact that is a known incoming alias for THIS request
        # renders as not recorded); the canonical snapshot is untouched.
        codex_facts = {
            key: (value if not _is_incoming_alias(request, value) else None)
            for key, value in codex_profile.to_facts().items()
        }

    # Operator-declared identity text passes the same output-side check
    # as record fields: a safe-charset value that is a known incoming
    # alias for THIS request is shown as unavailable (stored settings
    # and canonical profile identities are never mutated).
    deployed_revision = safe_deployment_revision(
        settings.REQUEST_CAPTURE_DEPLOYED_REVISION
    )
    if deployed_revision is not None and _is_incoming_alias(request, deployed_revision):
        deployed_revision = None
    revision_provenance = safe_deployment_revision(
        settings.REQUEST_CAPTURE_REVISION_PROVENANCE
    )
    if revision_provenance is not None and _is_incoming_alias(request, revision_provenance):
        revision_provenance = None

    response = templates.TemplateResponse(
        request,
        "operations/process_configuration.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "package_version": __version__,
            "snapshot_scope": str(config["snapshot_scope"]),
            "restart_scope": API_PROCESS_RESTART_SCOPE,
            "limitations": list(config["limitations"]),
            "settings_rows": settings_rows,
            "profile_rows": profile_rows,
            "codex_facts": codex_facts,
            "deployed_revision": deployed_revision,
            "revision_provenance": revision_provenance,
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response
