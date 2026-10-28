"""Shared typed partial operations for provider/route configuration (199).

The CLI uses these operations so reviewed provider/route configuration
changes go through the existing field services with bounded context:

* ``partial_update_provider_config`` locks the provider row, assembles the
  COMPLETE state (omitted fields preserved from the fresh locked row), and
  delegates to ``ProviderConfigService.update_provider_config`` — one audit
  record and one mutation inside the caller's transaction.
* ``preview_route_update_for_route`` resolves exactly one route READ-ONLY,
  resolves the PROPOSED destination provider READ-ONLY, merges the typed
  edits into the canonical configuration the service will actually store,
  validates the complete merged candidate against that provider's real
  kind/configuration (including pure server-module resolution, the
  zero-retry rule, and the no-streaming limit for configured-completion
  routes), and renders a reviewed NON-secret plan bound to the route
  UUID, the destination provider UUID, and the provider context digest —
  without writing or auditing anything.
* ``execute_route_update_plan`` locks the exact route and the destination
  provider (deterministic order: route, then provider), revalidates the
  fresh expected route pre-state and provider identity/context, and calls
  ``ModelRouteService.update_model_route`` in one caller transaction with
  the installation ceilings.
* ``validate_route_creation_candidate`` is the READ-ONLY configuration
  validation applied before a NEW route is stored (provider must exist;
  canonical merged candidate validated against the provider).

The route configuration fingerprint is a ROUTE-BOUND public digest over
the reviewed configuration pre-state (only timestamps excluded); the
provider context digest covers the provider fields that route validation
depends on (kind, base URL, credential env-var NAME, timeout, retries —
enabled/display deliberately excluded: preparation stays separate from
readiness). Both are public staleness/optimistic-guard data, never a
credential or replay authority. Every error uses fixed, safe vocabulary
and never echoes file bodies, paths, or secret-looking values; known
credential SHAPES in new free-form input are refused before mutation
(known-shape protection, not universal content sanitization).
Configuration validation here is NOT credential/model/SMTP qualification.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute, ProviderConfig
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.servers.completion_service.profiles import (
    PROFILE_KEY,
    load_bindings,
    load_profile,
    profile_id_from_capabilities,
)
from slaif_gateway.modules.servers.registry import (
    COMPLETION_SERVICE_MODULE_ID,
    resolve_server_module,
)
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_ROUTE_CAPABILITY_KEY,
)
from slaif_gateway.modules.servers.local_coding_vllm.contract import (
    VLLM_ROUTE_CAPABILITY_KEY,
)
from slaif_gateway.modules.servers.upstream_llm.profiles import (
    CAPABILITY_KEY as UPSTREAM_LLM_CAPABILITY_KEY,
)
from slaif_gateway.schemas.provider_route_configuration import (
    CapabilityPatch,
    ProviderRouteConfigError,
    ProviderRouteStaleError,
    RouteUpdatePlan,
    merge_capability_patch,
    render_route_update_plan,
    validate_capabilities_document,
)
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    ExternalToolOperatorCeilings,
)
from slaif_gateway.services.model_route_service import (
    CHAT_COMPLETIONS_ENDPOINT,
    ModelRouteService,
    normalize_endpoint,
    normalize_route_configuration,
)
from slaif_gateway.services.provider_config_service import ProviderConfigService
from slaif_gateway.services.record_errors import RecordNotFoundError
from slaif_gateway.utils.redaction import redact_text

_MODULE_PROVIDER_KIND = "module"
_COMPATIBLE_PROVIDER_KIND = "openai_compatible"

# Canonical review fields: exactly the stored-shape fields a reviewed plan
# renders for current/proposed comparison (see
# schemas.provider_route_configuration._CANONICAL_CONFIGURATION_KEYS).
_CANONICAL_FIELDS = (
    "requested_model",
    "match_type",
    "endpoint",
    "provider",
    "upstream_model",
    "priority",
    "enabled",
    "visible_in_models",
    "supports_streaming",
    "capabilities",
    "notes",
)

_PREVIEW_NOTE = (
    "Configuration review only. The gateway Codex context/admission ceiling, "
    "the configured default/max output reservation, the physical model "
    "capacity, and the client-advertised context are distinct values; "
    "unknown physical or client values remain unknown. No credential, model, "
    "or SMTP qualification is performed by this plan."
)


def compute_route_configuration_fingerprint(
    route_id: str,
    *,
    requested_model: str,
    match_type: str,
    endpoint: str,
    provider: str,
    upstream_model: str | None,
    priority: int,
    visible_in_models: bool,
    supports_streaming: bool,
    enabled: bool,
    capabilities: dict[str, Any] | None,
    notes: str | None,
) -> str:
    """Route-bound public digest over the reviewed configuration pre-state.

    Binds the stable route UUID to the reviewed configuration fields
    (capabilities, notes, enabled, endpoint, match type, provider, upstream
    model, priority, visibility, streaming, requested model) so an
    unchanged expected pre-state can never validate against a DIFFERENT
    route that happens to carry identical configuration. Excludes only
    timestamps. Used solely as expected-pre-state staleness data for
    reviewed plans — never as a credential or replay authority. Public
    configuration digest / optimistic guard, not a signed plan.
    """
    canonical = json.dumps(
        {
            "route_id": route_id,
            "capabilities": capabilities,
            "enabled": enabled,
            "endpoint": endpoint,
            "match_type": match_type,
            "notes": notes,
            "priority": priority,
            "provider": provider,
            "requested_model": requested_model,
            "supports_streaming": supports_streaming,
            "upstream_model": upstream_model,
            "visible_in_models": visible_in_models,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_provider_context_fingerprint(row: ProviderConfig) -> str:
    """Public digest over the provider configuration fields relevant to
    route validation.

    Covers kind, base URL, credential ENV-var NAME, timeout, and retry
    count — the dependency context a reviewed route plan was validated
    against. Display fields and the enabled flag are excluded on purpose:
    preparation stays separate from enabled/readiness (a disabled provider
    can still back a route preparation). Staleness data only, never a
    credential or replay authority.
    """
    canonical = json.dumps(
        {
            "api_key_env_var": row.api_key_env_var,
            "base_url": row.base_url,
            "kind": row.kind,
            "max_retries": row.max_retries,
            "timeout_seconds": row.timeout_seconds,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _route_fingerprint(row: ModelRoute) -> str:
    return compute_route_configuration_fingerprint(
        str(row.id),
        requested_model=row.requested_model,
        match_type=row.match_type,
        endpoint=row.endpoint,
        provider=row.provider,
        upstream_model=row.upstream_model,
        priority=row.priority,
        visible_in_models=row.visible_in_models,
        supports_streaming=row.supports_streaming,
        enabled=row.enabled,
        capabilities=row.capabilities,
        notes=row.notes,
    )


def contains_known_secret_shape(value: str | None) -> bool:
    """True when free-form text matches a RECOGNIZED credential shape.

    Reuses the existing redaction patterns (gateway key text, bearer
    tokens, provider keys, sensitive assignments). Detection only: it
    never returns or logs the matched value. Known-shape protection, not
    universal content sanitization.
    """
    if value is None:
        return False
    return redact_text(value) != value


def _reject_known_secret_shape(value: str | None, *, field: str) -> None:
    """Refuse new free-form input carrying a known credential shape.

    Fixed safe vocabulary only: the field name is named, the value is
    never echoed. Called BEFORE any mutation.
    """
    if contains_known_secret_shape(value):
        raise ProviderRouteConfigError(
            f"{field}: Value must not contain recognized credential patterns."
        )


def _canonical_route_state(
    *,
    requested_model: str,
    match_type: str,
    endpoint: str,
    provider: str,
    upstream_model: str | None,
    priority: int,
    visible_in_models: bool,
    supports_streaming: bool,
    enabled: bool,
    capabilities: dict[str, Any] | None,
    notes: str | None,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
) -> dict[str, Any]:
    """Canonical form of one complete route state, exactly as the CRUD
    service would store it (pure normalizer composition, 11 fields).

    This is the single preview/storage parity point: the reviewed plan
    renders this canonical form, and execution compares fresh state
    against the same canonical form, so no default capability block or
    field canonicalization is added after review. Raises ValueError for
    invalid field shapes (callers convert to fixed safe errors).
    """
    core = normalize_route_configuration(
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider,
        upstream_model=upstream_model,
        priority=priority,
        supports_streaming=supports_streaming,
        capabilities=capabilities,
        notes=notes,
        external_tool_ceilings=external_tool_ceilings,
    )
    return {
        "requested_model": core["requested_model"],
        "match_type": core["match_type"],
        "endpoint": core["endpoint"],
        "provider": core["provider"],
        "upstream_model": core["upstream_model"],
        "priority": core["priority"],
        "enabled": enabled,
        "visible_in_models": visible_in_models,
        "supports_streaming": core["supports_streaming"],
        "capabilities": core["capabilities"],
        "notes": core["notes"],
    }


def validate_merged_route_candidate(
    capabilities: dict[str, Any] | None,
    *,
    endpoint: str,
    provider: str,
    provider_row: ProviderConfig,
    requested_model: str,
    upstream_model: str,
    supports_streaming: bool,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
    profile_dir: str = "",
) -> dict[str, Any]:
    """Complete configuration-time validation of one merged route candidate.

    Reuses the strict capability-group contract and the EXISTING pure
    server-module resolution (provider kind, exclusive transport
    selectors, registered module, legacy profile bindings) plus the
    profile/binding parsers and loaders: a candidate is valid only when
    the provider's actual kind/slug/capabilities resolve to a supported
    server module, in the SAME configured profile directory the runtime
    uses. Configured-completion candidates — explicit selector OR
    implicit legacy binding — additionally require the chat completions
    endpoint, zero provider retries, the configured profile's
    public/upstream model identity, and NO advertised streaming (the
    completion adapter refuses stream values other than False). No
    credentials are loaded, no adapter is constructed, and no network
    call is made. This validates CONFIGURATION, not credential/model
    readiness.
    """
    provider_kind = provider_row.kind
    document = dict(capabilities or {})
    validate_capabilities_document(
        document,
        external_tool_ceilings=external_tool_ceilings,
        profile_dir=profile_dir,
    )
    if (
        UPSTREAM_LLM_CAPABILITY_KEY in document
        or LOCAL_CODING_ROUTE_CAPABILITY_KEY in document
        or VLLM_ROUTE_CAPABILITY_KEY in document
        or "vllm_chat_video" in document
    ) and provider_kind != _COMPATIBLE_PROVIDER_KIND:
        raise ProviderRouteConfigError(
            "candidate: The selected transport requires an openai_compatible provider kind."
        )
    if PROFILE_KEY in document and provider_kind != _MODULE_PROVIDER_KIND:
        # Explicit selector: fixed safe vocabulary (the registry would
        # reject this too, but this message names the selector).
        raise ProviderRouteConfigError(
            "completion_service: A profile selector requires a module provider kind."
        )
    try:
        module = resolve_server_module(provider, provider_kind, document)
    except ProviderConfigurationError as exc:
        raise ProviderRouteConfigError(
            "candidate: The selected provider does not resolve to a supported server module."
        ) from exc
    if module.module_id == COMPLETION_SERVICE_MODULE_ID:
        if endpoint != CHAT_COMPLETIONS_ENDPOINT:
            raise ProviderRouteConfigError(
                "completion_service: A profile selector requires the chat completions endpoint."
            )
        if provider_row.max_retries != 0:
            raise ProviderRouteConfigError(
                "completion_service: The selected provider must not retry "
                "(max_retries must be 0)."
            )
        # The completion adapter refuses every stream value other than
        # False, so a reviewed configuration must not advertise streaming
        # on the route flag or the chat capability (no silent strip).
        if supports_streaming:
            raise ProviderRouteConfigError(
                "completion_service: The completion service does not support "
                "streaming on this route."
            )
        chat_block = document.get("chat_completions")
        if isinstance(chat_block, Mapping) and chat_block.get("chat_streaming") is True:
            raise ProviderRouteConfigError(
                "completion_service: The chat completions capability must not "
                "advertise streaming."
            )
        profile_id = profile_id_from_capabilities(document) or load_bindings().providers.get(
            str(provider).strip().lower()
        )
        if profile_id is None:
            raise ProviderRouteConfigError(
                "completion_service: Value must be a valid available profile selector."
            )
        try:
            profile = load_profile(profile_id, profile_dir)
        except ProviderConfigurationError as exc:
            raise ProviderRouteConfigError(
                "completion_service: Value must be a valid available profile selector."
            ) from exc
        if profile.public_model != requested_model:
            raise ProviderRouteConfigError(
                "completion_service: The profile public model differs from the route requested model."
            )
        if profile.upstream_model != upstream_model:
            raise ProviderRouteConfigError(
                "completion_service: The profile upstream model differs from the route upstream model."
            )
    return document


async def partial_update_provider_config(
    session: AsyncSession,
    provider_or_id: str,
    *,
    display_name: str | None = None,
    base_url: str | None = None,
    kind: str | None = None,
    api_key_env_var: str | None = None,
    timeout_seconds: int | None = None,
    max_retries: int | None = None,
    notes: str | None = None,
    clear_notes: bool = False,
    confirm_insecure_http: bool = False,
    reason: str,
    actor_admin_id: uuid.UUID | None = None,
) -> ProviderConfig:
    """Partially update one provider through the shared field service.

    New free-form input (display name, base URL, notes, reason) is refused
    BEFORE any mutation when it carries a known credential shape, and the
    audit reason must be nonblank (the 199-b law; the pre-existing
    creation/HTTP reason law is preserved untouched). The row is then
    locked (``FOR UPDATE``) before the COMPLETE intended state is
    assembled, so omitted fields preserve the fresh current values, zero
    retries survive, and the service captures the REAL prior values for
    its one audit record in the caller transaction. ``enabled`` is
    preserved; use the enable/disable commands.

    Clearing notes uses the explicit ``clear_notes`` intent (199-c): the
    shared service captures the REAL prior values before mutation, the
    metadata repository stores NULL within that same operation, and the
    service's ONE audit records real old notes -> null. Existing shared
    callers keep the pre-existing default (``clear_notes=False``;
    ``notes=None`` means preserve), so admin-form and other behavior is
    unchanged.
    """
    if notes is not None and clear_notes:
        raise ProviderRouteConfigError(
            "notes: Choose either --notes or --clear-notes, not both."
        )
    if not (reason or "").strip():
        raise ProviderRouteConfigError(
            "reason: A nonblank audit reason is required."
        )
    _reject_known_secret_shape(display_name, field="display_name")
    _reject_known_secret_shape(base_url, field="base_url")
    _reject_known_secret_shape(notes, field="notes")
    _reject_known_secret_shape(reason, field="reason")

    providers = ProviderConfigsRepository(session)
    row = await providers.get_provider_config_for_update(provider_or_id)
    if row is None:
        raise RecordNotFoundError("Provider config")

    return await ProviderConfigService(
        provider_configs_repository=providers,
        audit_repository=AuditRepository(session),
    ).update_provider_config(
        str(row.id),
        provider=row.provider,
        display_name=display_name if display_name is not None else row.display_name,
        kind=kind if kind is not None else row.kind,
        base_url=base_url if base_url is not None else row.base_url,
        api_key_env_var=(
            api_key_env_var if api_key_env_var is not None else row.api_key_env_var
        ),
        enabled=row.enabled,
        timeout_seconds=timeout_seconds
        if timeout_seconds is not None
        else row.timeout_seconds,
        max_retries=max_retries if max_retries is not None else row.max_retries,
        notes=None if clear_notes else (notes if notes is not None else row.notes),
        clear_notes=clear_notes,
        actor_admin_id=actor_admin_id,
        reason=reason,
        confirm_insecure_http=confirm_insecure_http,
    )


def _resolve_route_id(route_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(route_id))
    except ValueError as exc:
        raise RecordNotFoundError("Model route") from exc


async def _load_route_readonly(session: AsyncSession, route_id: str) -> ModelRoute:
    """Resolve exactly one route READ-ONLY (missing is a record error)."""
    routes = ModelRoutesRepository(session)
    row = await routes.get_model_route_by_id(_resolve_route_id(route_id))
    if row is None:
        raise RecordNotFoundError("Model route")
    return row


async def _resolve_destination_provider(
    session: AsyncSession,
    provider: str,
    *,
    for_update: bool,
    missing_error: type[ProviderRouteConfigError] | type[ProviderRouteStaleError],
) -> ProviderConfig:
    """Resolve the PROPOSED destination provider (not the route's old one).

    Preview resolves READ-ONLY and reports a missing destination as a
    fixed candidate error; execution locks it (after the route lock,
    deterministic order: route, then provider) and reports a missing
    destination as STALE — the reviewed provider context is gone.
    """
    providers = ProviderConfigsRepository(session)
    if for_update:
        row = await providers.get_provider_config_for_update(provider)
    else:
        row = await providers.get_provider_config_by_provider(provider)
    if row is None:
        raise missing_error(
            "The destination provider configuration no longer matches the reviewed plan."
            if for_update
            else "The selected provider configuration is missing."
        )
    return row


def _capabilities_for_mode(
    current: dict[str, Any] | None,
    mode: str,
    capabilities: dict[str, Any] | None,
    patch: CapabilityPatch,
) -> dict[str, Any]:
    """Rebuild the merged capabilities for one plan mode from fresh state."""
    if mode == "full-replacement":
        assert capabilities is not None
        return dict(capabilities)
    if mode == "partial":
        return merge_capability_patch(current, patch)
    return dict(current or {})


def preview_route_update(
    route: ModelRoute,
    provider_row: ProviderConfig,
    *,
    requested_model: str | None = None,
    match_type: str | None = None,
    endpoint: str | None = None,
    provider: str | None = None,
    upstream_model: str | None = None,
    priority: int | None = None,
    visible_in_models: bool | None = None,
    supports_streaming: bool | None = None,
    notes: str | None = None,
    clear_notes: bool = False,
    capabilities_document: dict[str, Any] | None = None,
    capability_patch: CapabilityPatch | None = None,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
    profile_dir: str = "",
) -> RouteUpdatePlan:
    """Pure: render one reviewed route update plan (no writes, no audit).

    ``provider_row`` is the PROPOSED destination provider (resolved by the
    caller from the plan's provider selection, not from the route's old
    provider): the candidate is validated against its actual kind and
    configuration, and the plan BINDS its UUID plus context digest so an
    unrelated or later-modified provider cannot satisfy execution.

    Omitted typed fields preserve the current stored values; the preview
    block renders the CANONICAL current and proposed configurations (the
    exact stored shape the service will write, defaults included) and the
    changed canonical field names. Raises ``ProviderRouteConfigError`` for
    invalid candidates. The caller has already resolved the route
    read-only and must not write on failure.
    """
    if notes is not None and clear_notes:
        raise ProviderRouteConfigError(
            "notes: Choose either --notes or --clear-notes, not both."
        )
    _reject_known_secret_shape(notes, field="notes")
    try:
        proposed_endpoint = normalize_endpoint(
            endpoint if endpoint is not None else route.endpoint
        )
    except ValueError as exc:
        raise ProviderRouteConfigError(str(exc)) from exc
    proposed_provider = provider if provider is not None else route.provider
    proposed = {
        "requested_model": (
            requested_model if requested_model is not None else route.requested_model
        ),
        "match_type": match_type if match_type is not None else route.match_type,
        "endpoint": proposed_endpoint,
        "provider": proposed_provider,
        "upstream_model": (
            upstream_model if upstream_model is not None else route.upstream_model
        ),
        "priority": priority if priority is not None else route.priority,
        "visible_in_models": (
            route.visible_in_models if visible_in_models is None else visible_in_models
        ),
        "supports_streaming": (
            route.supports_streaming
            if supports_streaming is None
            else supports_streaming
        ),
        "notes": (
            None if clear_notes else (notes if notes is not None else route.notes)
        ),
    }
    if capabilities_document is not None:
        mode = "full-replacement"
        capabilities: dict[str, Any] | None = capabilities_document
        patch = CapabilityPatch()
    elif capability_patch is not None and not capability_patch.is_empty():
        mode = "partial"
        capabilities = None
        patch = capability_patch
    else:
        mode = "unchanged"
        capabilities = None
        patch = CapabilityPatch()

    fingerprint = _route_fingerprint(route)
    merged = _capabilities_for_mode(route.capabilities, mode, capabilities, patch)
    try:
        proposed_canonical = _canonical_route_state(
            requested_model=proposed["requested_model"],
            match_type=proposed["match_type"],
            endpoint=proposed_endpoint,
            provider=proposed_provider,
            upstream_model=proposed["upstream_model"],
            priority=proposed["priority"],
            visible_in_models=proposed["visible_in_models"],
            supports_streaming=proposed["supports_streaming"],
            enabled=route.enabled,
            capabilities=merged,
            notes=proposed["notes"],
            external_tool_ceilings=external_tool_ceilings,
        )
        current_canonical = _canonical_route_state(
            requested_model=route.requested_model,
            match_type=route.match_type,
            endpoint=route.endpoint,
            provider=route.provider,
            upstream_model=route.upstream_model,
            priority=route.priority,
            visible_in_models=route.visible_in_models,
            supports_streaming=route.supports_streaming,
            enabled=route.enabled,
            capabilities=route.capabilities,
            notes=route.notes,
            external_tool_ceilings=external_tool_ceilings,
        )
    except ValueError as exc:
        raise ProviderRouteConfigError(str(exc)) from exc
    validate_merged_route_candidate(
        proposed_canonical["capabilities"],
        endpoint=proposed_canonical["endpoint"],
        provider=proposed_provider,
        provider_row=provider_row,
        requested_model=proposed_canonical["requested_model"],
        upstream_model=proposed_canonical["upstream_model"],
        supports_streaming=proposed_canonical["supports_streaming"],
        external_tool_ceilings=external_tool_ceilings,
        profile_dir=profile_dir,
    )
    changed = sorted(
        name
        for name in _CANONICAL_FIELDS
        if current_canonical[name] != proposed_canonical[name]
    )
    plan = RouteUpdatePlan(
        route_id=str(route.id),
        expected_route_id=str(route.id),
        expected_provider_id=str(provider_row.id),
        expected_provider_context_fingerprint=(
            compute_provider_context_fingerprint(provider_row)
        ),
        requested_model=proposed["requested_model"],
        match_type=proposed["match_type"],
        endpoint=proposed_endpoint,
        provider=proposed_provider,
        upstream_model=proposed["upstream_model"],
        priority=proposed["priority"],
        visible_in_models=proposed["visible_in_models"],
        supports_streaming=proposed["supports_streaming"],
        enabled=route.enabled,
        notes=proposed["notes"],
        capabilities_mode=mode,
        capabilities=capabilities,
        capability_patch=patch,
        expected_configuration_fingerprint=fingerprint,
        preview={
            "note": _PREVIEW_NOTE,
            "changed_fields": changed,
            "current_configuration": current_canonical,
            "proposed_configuration": proposed_canonical,
        },
    )
    # Strict round-trip gate BEFORE any file write (the rendered document
    # must carry the exact reviewed bindings).
    render_route_update_plan(plan)
    return plan


async def preview_route_update_for_route(
    session: AsyncSession,
    route_id: str,
    *,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
    profile_dir: str = "",
    **edits: Any,
) -> RouteUpdatePlan:
    """READ-ONLY preview: resolve one route and its PROPOSED destination
    provider, then render the reviewed plan (zero writes, zero audits)."""
    route = await _load_route_readonly(session, route_id)
    proposed_provider = edits.get("provider")
    if proposed_provider is None or not str(proposed_provider).strip():
        proposed_provider = route.provider
    provider_row = await _resolve_destination_provider(
        session,
        proposed_provider,
        for_update=False,
        missing_error=ProviderRouteConfigError,
    )
    return preview_route_update(
        route,
        provider_row,
        external_tool_ceilings=external_tool_ceilings,
        profile_dir=profile_dir,
        **edits,
    )


async def execute_route_update_plan(
    session: AsyncSession,
    plan: RouteUpdatePlan,
    *,
    reason: str,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
    profile_dir: str = "",
    actor_admin_id: uuid.UUID | None = None,
) -> ModelRoute:
    """Apply one reviewed route plan: lock, revalidate, one audited update.

    Deterministic lock order: the exact route row (``FOR UPDATE``) first,
    then the PROPOSED destination provider. The fresh route must still
    carry the plan's bound identity (``expected_route_id`` — an unchanged
    expected pre-state can never apply to a different route), enabled
    state, and route-bound configuration fingerprint; the destination
    provider must still exist, carry the plan's bound provider identity
    (``expected_provider_id``), and match the reviewed context digest
    (``expected_provider_context_fingerprint`` — kind, base URL,
    credential env-var NAME, timeout, retries). Any mismatch raises
    ``ProviderRouteStaleError`` with zero writes and zero audits.

    The merged candidate is canonicalized with the SAME pure normalizer
    the service uses (installation ceilings included) and revalidated
    against the FRESH provider row (kind, zero-retry rule, configured
    profile directory) before the single
    ``ModelRouteService.update_model_route`` call in the caller
    transaction. A repeated apply of an already-applied plan is refused
    stale because the fresh fingerprint no longer matches the reviewed
    expected pre-state.

    Documented no-op law: if the reviewed plan's complete CANONICAL
    proposed state already equals the fresh locked row's canonical state,
    the row is returned as-is with ZERO writes and ZERO audits. Any real
    change is applied exactly once.
    """
    if not (reason or "").strip():
        raise ProviderRouteConfigError(
            "reason: A nonblank audit reason is required."
        )
    _reject_known_secret_shape(reason, field="reason")

    routes = ModelRoutesRepository(session)
    row = await routes.get_model_route_for_update(_resolve_route_id(plan.route_id))
    if row is None:
        raise RecordNotFoundError("Model route")
    if str(row.id) != plan.expected_route_id:
        raise ProviderRouteStaleError(
            "The route identity no longer matches the reviewed plan."
        )
    if row.enabled != plan.enabled:
        raise ProviderRouteStaleError(
            "The route enabled state no longer matches the reviewed plan."
        )
    if _route_fingerprint(row) != plan.expected_configuration_fingerprint:
        raise ProviderRouteStaleError(
            "The route configuration no longer matches the reviewed plan."
        )
    provider_row = await _resolve_destination_provider(
        session,
        plan.provider,
        for_update=True,
        missing_error=ProviderRouteStaleError,
    )
    if str(provider_row.id) != plan.expected_provider_id:
        raise ProviderRouteStaleError(
            "The destination provider identity no longer matches the reviewed plan."
        )
    if (
        compute_provider_context_fingerprint(provider_row)
        != plan.expected_provider_context_fingerprint
    ):
        raise ProviderRouteStaleError(
            "The destination provider context no longer matches the reviewed plan."
        )

    merged = _capabilities_for_mode(
        row.capabilities, plan.capabilities_mode, plan.capabilities, plan.capability_patch
    )
    try:
        proposed_canonical = _canonical_route_state(
            requested_model=plan.requested_model,
            match_type=plan.match_type,
            endpoint=plan.endpoint,
            provider=plan.provider,
            upstream_model=plan.upstream_model,
            priority=plan.priority,
            visible_in_models=plan.visible_in_models,
            supports_streaming=plan.supports_streaming,
            enabled=row.enabled,
            capabilities=merged,
            notes=plan.notes,
            external_tool_ceilings=external_tool_ceilings,
        )
        fresh_canonical = _canonical_route_state(
            requested_model=row.requested_model,
            match_type=row.match_type,
            endpoint=row.endpoint,
            provider=row.provider,
            upstream_model=row.upstream_model,
            priority=row.priority,
            visible_in_models=row.visible_in_models,
            supports_streaming=row.supports_streaming,
            enabled=row.enabled,
            capabilities=row.capabilities,
            notes=row.notes,
            external_tool_ceilings=external_tool_ceilings,
        )
    except ValueError as exc:
        raise ProviderRouteConfigError(str(exc)) from exc
    validate_merged_route_candidate(
        proposed_canonical["capabilities"],
        endpoint=proposed_canonical["endpoint"],
        provider=plan.provider,
        provider_row=provider_row,
        requested_model=proposed_canonical["requested_model"],
        upstream_model=proposed_canonical["upstream_model"],
        supports_streaming=proposed_canonical["supports_streaming"],
        external_tool_ceilings=external_tool_ceilings,
        profile_dir=profile_dir,
    )
    if proposed_canonical == fresh_canonical:
        return row
    return await ModelRouteService(
        model_routes_repository=routes,
        audit_repository=AuditRepository(session),
        external_tool_ceilings=external_tool_ceilings,
    ).update_model_route(
        row.id,
        requested_model=plan.requested_model,
        match_type=plan.match_type,
        endpoint=plan.endpoint,
        provider=plan.provider,
        upstream_model=plan.upstream_model,
        priority=plan.priority,
        visible_in_models=plan.visible_in_models,
        enabled=row.enabled,
        supports_streaming=plan.supports_streaming,
        capabilities=merged,
        notes=plan.notes,
        actor_admin_id=actor_admin_id,
        reason=reason,
    )


async def validate_route_creation_candidate(
    session: AsyncSession,
    *,
    requested_model: str,
    match_type: str,
    provider: str,
    upstream_model: str | None,
    priority: int,
    visible_in_models: bool,
    enabled: bool,
    supports_streaming: bool,
    notes: str | None,
    endpoint: str,
    capabilities: dict[str, object] | None,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
    profile_dir: str = "",
) -> None:
    """READ-ONLY configuration validation before a NEW route is stored.

    The selected provider must already exist; the complete candidate is
    canonicalized with the SAME pure normalizer the CRUD service applies
    (installation ceilings included) and the merged candidate is
    validated against the provider's actual kind and configuration
    (endpoint, module/profile/upstream mapping, zero retries for
    configured-completion routes). No writes, no audit, no credentials,
    no network: this validates CONFIGURATION, not readiness.
    """
    _reject_known_secret_shape(notes, field="notes")
    provider_row = await _resolve_destination_provider(
        session,
        provider,
        for_update=False,
        missing_error=ProviderRouteConfigError,
    )
    try:
        canonical = _canonical_route_state(
            requested_model=requested_model,
            match_type=match_type,
            endpoint=endpoint,
            provider=provider,
            upstream_model=upstream_model,
            priority=priority,
            visible_in_models=visible_in_models,
            supports_streaming=supports_streaming,
            enabled=enabled,
            capabilities=capabilities,
            notes=notes,
            external_tool_ceilings=external_tool_ceilings,
        )
    except ValueError as exc:
        raise ProviderRouteConfigError(str(exc)) from exc
    validate_merged_route_candidate(
        canonical["capabilities"],
        endpoint=canonical["endpoint"],
        provider=provider,
        provider_row=provider_row,
        requested_model=canonical["requested_model"],
        upstream_model=canonical["upstream_model"],
        supports_streaming=canonical["supports_streaming"],
        external_tool_ceilings=external_tool_ceilings,
        profile_dir=profile_dir,
    )
