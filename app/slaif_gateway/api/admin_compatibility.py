"""Focused admin router for reviewed Codex compatibility management (212-a).

Delivers G10: inspect registered Codex qualification and compatibility
data, identify a key's exact binding, download validated credential-free
presets, and perform the shared CLI's exact module upgrade/rollback or
data-profile migration through dry-run review -> signed review ->
confirmed atomic apply -> reload/repeat.

The controllers call the SAME shared functions the CLI uses
(``mutate_codex_client_module`` / ``migrate_codex_0162_key_profile``)
with ``apply=False`` for the review step and ``apply=True`` for the
apply step, inside the caller-owned transaction.  The shared Core
migration law is the sole operation authority: the reviewed signed
document binds operation, key UUID, exact source, selector, resolved
target tuple, and the ORIGINAL (never trimmed) bounded reason, and the
apply step re-validates everything - including the active profile
tuple against THIS worker's registry - before any mutation.

Form values name the operation and the exact Core DESTINATION selector
(the same vocabulary ``legal_module_operations`` derives); the expected
source is the frozen predecessor for upgrades and the key's current pin
selector for rollbacks, exactly as the CLI derives it.  A repeat of an
operation whose destination the key already carries is the Core's
accepted already_at_target no-op: the GUI never re-filters a signed
apply against current-page UI choices.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from types import MappingProxyType
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_attachment_context,
    _admin_error_page,
    _admin_key_dashboard_service_scope,
    _admin_not_found,
    _admin_page_context,
    _is_checked,
    _log_admin_action_failure,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_compatibility_review_token,
    verify_compatibility_review_token,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileDataError,
    list_codex_presets,
    read_codex_preset,
)
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.codex_module_upgrade import (
    CodexModuleUpgradeError,
    is_0162_profile_module,
    legal_module_operations,
    migrate_codex_0162_key_profile,
    module_selector,
    mutate_codex_client_module,
)
from slaif_gateway.services.codex_qualification import (
    CodexQualificationService,
    render_codex_profile,
)
from slaif_gateway.services.record_errors import RecordNotFoundError
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
)

router = APIRouter(prefix="/admin/operations/compatibility", include_in_schema=False)

# Finite operation vocabulary (form values "<operation>:<destination>").
# The destination is the EXACT Core target selector: upgrade values name
# the frozen destination of an upgrade edge; rollback values name the
# frozen predecessor the key returns to (0149-v4 for 0149-v5/0162-v1
# pins, 0162-v1 for a 0162-v2 pin).  "migrate" is the 0.162 data-profile
# migration with the CLI's active/frozen targets.
_OPERATION_LABELS = {
    "module_upgrade:0149-v5": "Upgrade to 0149-v5 (expected source 0149-v4)",
    "module_upgrade:0162-v1": "Upgrade to 0162-v1 (expected source 0149-v4)",
    "module_upgrade:0162-v2": "Upgrade to 0162-v2 (expected source 0162-v1)",
    "module_rollback:0149-v4": "Roll back to 0149-v4 (expected source: current pin)",
    "module_rollback:0162-v1": "Roll back to 0162-v1 (expected source: current pin)",
    "migrate:active": "Migrate pin -> active API data profile",
    "migrate:0162-v1": "Migrate pin -> frozen 0162-v1",
    "migrate:0162-v2": "Migrate pin -> frozen 0162-v2",
}
_TARGET_SELECTOR_TO_CORE = {
    "module_upgrade:0149-v5": ("module_upgrade", "0149-v5"),
    "module_upgrade:0162-v1": ("module_upgrade", "0162-v1"),
    "module_upgrade:0162-v2": ("module_upgrade", "0162-v2"),
    "module_rollback:0149-v4": ("module_rollback", "0149-v4"),
    "module_rollback:0162-v1": ("module_rollback", "0162-v1"),
    "migrate:active": ("migrate", "active"),
    "migrate:0162-v1": ("migrate", "0162-v1"),
    "migrate:0162-v2": ("migrate", "0162-v2"),
}
# The shared Core legal-fact helper names operations "upgrade"/"rollback";
# the form/review-document vocabulary uses the longer finite names.
_CORE_OPERATION_TO_FORM = {"upgrade": "module_upgrade", "rollback": "module_rollback"}
# The exact frozen predecessor of each upgrade destination (CLI law).
_UPGRADE_SOURCE_BY_TARGET = {
    "0149-v5": "0149-v4",
    "0162-v1": "0149-v4",
    "0162-v2": "0162-v1",
}
_MODULE_SELECTORS = frozenset({"0149-v4", "0149-v5", "0162-v1", "0162-v2"})


@asynccontextmanager
async def _compat_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Caller-owned transaction scope for one compatibility operation."""
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


def _review_doc_has_alias(request: Request, document: dict[str, Any]) -> bool:
    """True when ANY finite review fact is a known incoming authentication
    alias (fail closed).  Covers the free-text reason, the exact source
    version/digest pair, and EVERY value of the bound source/target
    tuples - a tuple equal to an incoming credential value is refused
    before signing/rendering and before apply persistence, never
    echoed."""
    facts: list[object] = [
        document.get("reason"),
        document.get("expected_source"),
        document.get("from_version"),
        document.get("from_digest"),
    ]
    for tuple_key in ("source_tuple", "target_tuple"):
        raw = document.get(tuple_key)
        if isinstance(raw, Mapping):
            facts.extend(str(value) for value in raw.values())
    return any(_is_known_alias(request, fact) for fact in facts)


def _client_module_pin(responses_policy: object) -> MappingProxyType[str, str] | None:
    """The exact stored (id, version, fixture_sha256) pin, or None.

    None means absent OR malformed; both render as an explicit
    "not readable / no legal operation" state (the shared Core remains
    the mutation authority and re-validates under the row lock).
    """
    if not isinstance(responses_policy, dict):
        return None
    raw = responses_policy.get("client_module")
    if (
        not isinstance(raw, dict)
        or set(raw) != {"id", "version", "fixture_sha256"}
        or not all(
            isinstance(raw.get(field), str) and raw.get(field)
            for field in ("id", "version", "fixture_sha256")
        )
    ):
        return None
    return MappingProxyType(
        {field: str(raw[field]) for field in ("id", "version", "fixture_sha256")}
    )


def _operation_options(pin: MappingProxyType[str, str] | None) -> list[tuple[str, str]]:
    """The finite (value, label) pairs legal for THIS exact pin.

    Presentation-only: derived from the shared Core read-only legal-fact
    helper, whose (operation, destination) pairs are exactly the frozen
    edges from this pin.  The signed review + shared Core remain the
    operation authority (a pin that moves between render and apply is
    handled by the Core's own already_at_target / identity-mismatch law).
    """
    options: list[tuple[str, str]] = []
    if pin is not None:
        for operation, target in legal_module_operations(pin):
            value = f"{_CORE_OPERATION_TO_FORM[operation]}:{target}"
            if value in _OPERATION_LABELS:
                options.append((value, _OPERATION_LABELS[value]))
        if is_0162_profile_module(pin):
            for target in ("active", "0162-v1", "0162-v2"):
                value = f"migrate:{target}"
                options.append((value, _OPERATION_LABELS[value]))
    return options


def _expected_source_for(value: str, pin_selector: str) -> str | None:
    """The exact Core expected source for one finite form value.

    Upgrades have a unique frozen predecessor per destination; rollbacks
    expect the key's CURRENT pin selector (the CLI's from-target), which
    the shared Core verifies under the row lock.  Profile migration
    carries no expected source: it binds the exact from-version/
    from-digest pair instead.
    """
    operation, target = _TARGET_SELECTOR_TO_CORE[value]
    if operation == "module_upgrade":
        return _UPGRADE_SOURCE_BY_TARGET.get(target)
    if operation == "module_rollback":
        return pin_selector if pin_selector in _MODULE_SELECTORS else None
    return None


def _action_name_for(value: str) -> str:
    operation, _target = _TARGET_SELECTOR_TO_CORE[value]
    if operation == "module_upgrade":
        return "codex_client_module_upgraded"
    if operation == "module_rollback":
        return "codex_client_module_rolled_back"
    return "codex_key_profile_migrated"


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def _qualification_service(session: AsyncSession) -> CodexQualificationService:
    return CodexQualificationService(
        provider_configs_repository=ProviderConfigsRepository(session),
        model_routes_repository=ModelRoutesRepository(session),
        pricing_rules_repository=PricingRulesRepository(session),
        fx_rates_repository=FxRatesRepository(session),
    )


@router.get("/", response_class=HTMLResponse)
async def compatibility_index(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    qualification_rows: list[dict[str, Any]] = []
    qualification_error = False
    try:
        async with _compat_session(request) as session:
            results = await _qualification_service(session).inspect()
        qualification_rows = []
        for result in results:
            # The canonical artifact handlers gate on the exact registered
            # profile render: reuse the SAME renderer for the link decision
            # so the index never offers an artifact the handler would 404.
            artifacts = None
            if result.ready and result.profile_id:
                try:
                    artifacts = render_codex_profile(
                        settings.PUBLIC_BASE_URL, result.profile_id
                    )
                except ValueError:
                    artifacts = None
            row_route_id = str(result.route_id)
            # Route hrefs (including the canonical artifact links) must
            # never carry a known incoming alias: withhold the display
            # value and drop the links, not just the text.
            route_alias = _is_known_alias(request, row_route_id)
            module_text = (
                f"{result.client_module_id} v{result.client_module_version}"
                if result.client_module_id
                else "—"
            )
            reasons_text = (
                ", ".join(result.reason_codes) if result.reason_codes else "None"
            )
            badge = _safe_display(request, result.badge)
            # State column: a short label for ready rows (the full
            # profile identifier is already in the Profile column);
            # not-ready badges keep their (withheld-safe) text.
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
                    "artifacts": (
                        {
                            "profile": True,
                            "base": not artifacts.profile_config_self_contained,
                            "catalog": artifacts.model_catalog_json is not None,
                        }
                        if artifacts is not None and not route_alias
                        else None
                    ),
                    "module": _safe_display(request, module_text),
                    "reasons": _safe_display(request, reasons_text),
                    "state_label": state_label,
                }
            )
    except Exception:  # noqa: BLE001 - inspection is read-only; safe fallback
        qualification_error = True

    startup_profile = getattr(request.app.state, "codex_0162_profile", None)
    if not isinstance(startup_profile, object) or not hasattr(
        startup_profile, "module_id"
    ):
        startup_profile = None

    presets: list[dict[str, Any]] = []
    presets_error = False
    try:
        for name, _path, profile in list_codex_presets():
            facts = profile.to_facts()
            # The same request-local alias withholding as the rest of the
            # index: a dynamic preset fact equal to a known incoming
            # credential value is displayed withheld, and a withheld
            # preset NAME is never re-exposed through the Inspect/
            # Download hrefs (no link at all).
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
                }
            )
    except CodexProfileDataError:
        presets_error = True

    return _no_store(
        templates.TemplateResponse(
            request,
            "compatibility/index.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "qualification_rows": qualification_rows,
                "qualification_error": qualification_error,
                "startup_profile": startup_profile,
                "startup_profile_facts": (
                    {
                        key: _safe_display(request, value)
                        for key, value in sorted(startup_profile.to_facts().items())
                    }
                    if startup_profile is not None
                    else None
                ),
                "presets": presets,
                "presets_error": presets_error,
            },
        )
    )


@router.get("/preset/{name}", response_class=HTMLResponse)
async def compatibility_preset_page(request: Request, name: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    try:
        document = read_codex_preset(name)
        facts = None
        for preset_name, _path, profile in list_codex_presets():
            if preset_name == name:
                facts = profile.to_facts()
                break
    except CodexProfileDataError:
        return _admin_error_page(
            request, status_code=404, message="Compatibility preset not found."
        )
    # Known-incoming-alias withholding for display facts and the raw
    # document (the export path refuses instead of rewriting bytes).
    safe_facts = (
        {key: _safe_display(request, value) for key, value in sorted(facts.items())}
        if facts is not None
        else None
    )
    document_withheld = _is_known_alias(request, document)
    return _no_store(
        templates.TemplateResponse(
            request,
            "compatibility/preset.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "name": name,
                "facts": safe_facts,
                "document": None if document_withheld else document,
                "document_withheld": document_withheld,
            },
        )
    )


@router.get("/preset/{name}/download")
async def compatibility_preset_download(request: Request, name: str) -> Response:
    """Authenticated private no-store download of ONE validated preset.

    The exact registered preset name is the only accepted input (the
    strict loader refuses everything else); the returned document is the
    exact credential-free bytes ``read_codex_preset`` returns - validated
    and bounded by the existing 65,536-byte profile limit, never
    re-serialized or modified (its identity is the loader's digest).
    Read authentication does NOT rotate the origin page's CSRF (the
    still-visible key-page form must keep working).  If the canonical
    bytes contained a known incoming credential value, the export is
    REFUSED with a fixed message - the digest-bound document is never
    rewritten.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    # Fully read-only: not even the session last-seen stamp is written.
    attachment_context = await _admin_attachment_context(request, touch=False)
    if isinstance(attachment_context, Response):
        return _no_store(attachment_context)
    try:
        document = read_codex_preset(name)
    except CodexProfileDataError:
        return _admin_error_page(
            request, status_code=404, message="Compatibility preset not found."
        )
    # Same pure presence/refusal policy as the preset display (accepted
    # gateway-key prefixes, credential shapes, and known incoming
    # authentication aliases; fail closed when discovery is incomplete).
    if _is_known_alias(request, document):
        return _admin_error_page(
            request,
            status_code=403,
            message=(
                "The compatibility preset export was refused because it "
                "contains a known credential value. The canonical preset "
                "is unchanged."
            ),
        )
    response = Response(
        document,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
    )
    return _no_store(response)


@router.get("/key/{key_id}", response_class=HTMLResponse)
async def compatibility_key_page(request: Request, key_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    try:
        parsed_key_id = uuid.UUID(key_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            key = await service.get_key_detail(parsed_key_id)
    except AdminKeyNotFoundError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    pin = _client_module_pin(key.responses_policy)
    selector = module_selector(pin) if pin is not None else None
    pin_readable = pin is not None and not any(
        _is_known_alias(request, pin[field])
        for field in ("id", "version", "fixture_sha256")
    )
    # A withheld binding is not re-exposed through hidden inputs or the
    # signed payload: no operation options and no raw pin values.
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

    return _no_store(
        templates.TemplateResponse(
            request,
            "compatibility/key.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "key": key,
                "pin": pin_display,
                "pin_readable": pin_readable,
                "pin_raw": pin_raw,
                "selector": selector if pin_readable else None,
                "options": options,
                "default_operation": options[0][0] if options else "",
            },
        )
    )


@router.post("/key/{key_id}/review", response_class=HTMLResponse)
async def compatibility_key_review(request: Request, key_id: str) -> Response:
    """Dry-run the SAME shared operation (apply=False) and sign the review.

    The review takes the existing key row lock briefly and performs NO
    domain or audit write.  The reason is validated by the shared Core
    law on the ORIGINAL string (8-200 printable ASCII, non-whitespace;
    never trimmed); a known incoming authentication alias is refused
    BEFORE the Core call with a fixed no-echo message.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    try:
        parsed_key_id = uuid.UUID(key_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    def _safe_400(message: str) -> Response:
        return _admin_error_page(request, status_code=400, message=message)

    value = str(form.get("operation_target") or "")
    if value not in _TARGET_SELECTOR_TO_CORE:
        return _safe_400("Choose a reviewed migration operation and target.")
    reason = str(form.get("reason") or "")
    if reason and _is_known_alias(request, reason):
        return _safe_400("Reason withheld: it matches a known incoming authentication value.")

    operation, target = _TARGET_SELECTOR_TO_CORE[value]
    action = _action_name_for(value)
    pin_version = str(form.get("from_version") or "")
    pin_digest = str(form.get("from_digest") or "")
    if operation == "migrate":
        # The posted source identity is a finite bounded review fact:
        # refuse a known incoming alias before the Core call (fixed,
        # no echo).  The Core re-checks it against the locked row.
        if _is_known_alias(request, pin_version) or _is_known_alias(
            request, pin_digest
        ):
            return _safe_400(
                "The reviewed source identity was withheld: it matches a "
                "known incoming authentication value. Open the key page "
                "again and review the migration."
            )
        expected_source = None
    else:
        pin_selector = str(form.get("pin_selector") or "")
        expected_source = _expected_source_for(value, pin_selector)
        if expected_source is None:
            return _safe_400("Choose a reviewed migration operation and target.")

    try:
        async with _compat_session(request) as session:
            if operation == "migrate":
                result = await migrate_codex_0162_key_profile(
                    session=session,
                    keys_repository=GatewayKeysRepository(session),
                    audit_repository=AuditRepository(session),
                    gateway_key_id=parsed_key_id,
                    from_version=pin_version,
                    from_digest=pin_digest,
                    target=target,
                    action=action,
                    actor_admin_id=action_context.admin_user.id,
                    reason=reason,
                    apply=False,
                )
            else:
                result = await mutate_codex_client_module(
                    session=session,
                    keys_repository=GatewayKeysRepository(session),
                    audit_repository=AuditRepository(session),
                    gateway_key_id=parsed_key_id,
                    expected_source=expected_source,
                    target=target,
                    action=action,
                    actor_admin_id=action_context.admin_user.id,
                    reason=reason,
                    apply=False,
                )
    except CodexModuleUpgradeError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(exc.safe_message)
    except RecordNotFoundError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    except Exception:  # noqa: BLE001 - read-only dry run; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("compatibility review failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400("The migration review could not be prepared right now; try again.")

    review_document: dict[str, Any]
    if operation == "migrate":
        review_document = {
            "operation": "profile_migrate",
            "gateway_key_id": str(parsed_key_id),
            "from_version": str(result.source_module["version"]),
            "from_digest": str(result.source_module["fixture_sha256"]),
            "target": target,
            "reason": reason,
            "source_tuple": dict(result.source_module),
            "target_tuple": dict(result.target_module),
        }
    else:
        review_document = {
            "operation": operation,
            "gateway_key_id": str(parsed_key_id),
            "expected_source": expected_source,
            "target": target,
            "reason": reason,
            "source_tuple": dict(result.source_module),
            "target_tuple": dict(result.target_module),
        }

    # Every finite review fact (reason, exact source pair, and BOTH bound
    # tuples) is a known-alias guard BEFORE signing or rendering: a value
    # that is an incoming credential for THIS request is refused with a
    # fixed no-echo message, never signed or re-displayed.
    if _review_doc_has_alias(request, review_document):
        return _safe_400(
            "The reviewed migration facts can no longer be shown: they match "
            "a known incoming authentication value. Open the key page again "
            "and review the migration."
        )
    try:
        token = build_compatibility_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            review_document=review_document,
        )
    except Exception:  # noqa: BLE001 - signing is pure; fixed safe fallback
        return _safe_400("The reviewed migration could not be signed; try again.")

    return _no_store(
        templates.TemplateResponse(
            request,
            "compatibility/migration_review.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "key_id": str(parsed_key_id),
                "review_document": review_document,
                "result": result,
                "review_token": token,
                "applied": None,
            },
        )
    )


@router.post("/key/{key_id}/apply", response_class=HTMLResponse)
async def compatibility_key_apply(request: Request, key_id: str) -> Response:
    """Verify the signed review, then execute the SAME operation (apply=True).

    The token is reviewed data, never authority: the apply URL's key must
    independently agree with the reviewed key UUID, and the shared Core
    re-validates the exact source/target law (including the active
    profile tuple against THIS worker's registry) before any mutation.
    Posted actor/source/target/reason confer no authority.  The reviewed
    reason is re-checked against THIS request's known incoming aliases
    before persistence.  The mutation and its one audit record commit
    together or roll back in the caller-owned transaction; a failure at
    an unconfirmed stage (for example a lost commit acknowledgement)
    must be reported as UNCONFIRMED, never as a guaranteed rollback.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    try:
        parsed_key_id = uuid.UUID(key_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    review_intent = str(form.get("review_token") or "")
    confirm_apply = str(form.get("confirm_apply") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    def _safe_400(message: str) -> Response:
        return _admin_error_page(request, status_code=400, message=message)

    # Everything below runs BEFORE any mutation.
    try:
        document = verify_compatibility_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_intent,
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
        return _safe_400(exc.message)
    if document["gateway_key_id"] != str(parsed_key_id):
        _log_admin_action_failure(
            request,
            exc=AdminReviewIntentError(
                "The compatibility review state is not valid for this signed-in admin."
            ),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(
            "The compatibility review state is not valid for this signed-in admin."
        )
    if not _is_checked(confirm_apply):
        return _safe_400("Confirm the reviewed migration before applying it.")

    operation_doc = document["operation"]
    target = str(document["target"])
    reason = str(document["reason"])
    expected_source = ""
    from_version = ""
    from_digest = ""
    if operation_doc == "profile_migrate":
        action = "codex_key_profile_migrated"
        from_version = str(document["from_version"])
        from_digest = str(document["from_digest"])
        # The active selector is symbolic: the apply worker must resolve
        # the SAME exact tuple the review bound (shared apply guard).
        expected_target_module = (
            dict(document["target_tuple"]) if target == "active" else None
        )
    else:
        action = (
            "codex_client_module_upgraded"
            if operation_doc == "module_upgrade"
            else "codex_client_module_rolled_back"
        )
        expected_source = str(document["expected_source"])
        expected_target_module = None

    # The SAME signed facts the review guarded (reason, exact source
    # pair, and BOTH bound tuples) are re-checked against THIS apply
    # request's known incoming aliases before any Core call or audit
    # write; the outcome page never renders a withheld fact.
    if _review_doc_has_alias(request, document):
        return _safe_400(
            "The reviewed migration can no longer be applied: a reviewed "
            "value matches a known incoming authentication value. Review "
            "the migration again."
        )

    try:
        async with _compat_session(request) as session:
            if operation_doc == "profile_migrate":
                result = await migrate_codex_0162_key_profile(
                    session=session,
                    keys_repository=GatewayKeysRepository(session),
                    audit_repository=AuditRepository(session),
                    gateway_key_id=parsed_key_id,
                    from_version=from_version,
                    from_digest=from_digest,
                    target=target,
                    action=action,
                    actor_admin_id=action_context.admin_user.id,
                    reason=reason,
                    apply=True,
                    expected_target_module=expected_target_module,
                )
            else:
                result = await mutate_codex_client_module(
                    session=session,
                    keys_repository=GatewayKeysRepository(session),
                    audit_repository=AuditRepository(session),
                    gateway_key_id=parsed_key_id,
                    expected_source=expected_source,
                    target=target,
                    action=action,
                    actor_admin_id=action_context.admin_user.id,
                    reason=reason,
                    apply=True,
                )
    except CodexModuleUpgradeError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(exc.safe_message)
    except RecordNotFoundError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    except Exception:  # noqa: BLE001 - outcome may be unconfirmed; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("compatibility apply failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(
            "The migration outcome is UNCONFIRMED. Check the key's current "
            "compatibility binding and the audit log before retrying or "
            "reviewing again."
        )

    # Honest outcome: applied writes one client_module tuple + one audit
    # entry; an already_at_target repeat is a no-write/no-audit no-op.
    return _no_store(
        templates.TemplateResponse(
            request,
            "compatibility/migration_review.html",
            {
                "admin": action_context.admin_user,
                "csrf_token": csrf_token,
                "key_id": str(parsed_key_id),
                "review_document": document,
                "result": result,
                "review_token": None,
                "applied": result,
            },
        )
    )
