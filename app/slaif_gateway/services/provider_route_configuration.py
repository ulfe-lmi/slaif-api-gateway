"""Shared typed partial operations for provider/route configuration (199-a).

The CLI uses these operations so reviewed partial provider updates and
stable-ID route updates go through the existing field services:

* ``partial_update_provider_config`` locks the provider row, assembles the
  COMPLETE state (omitted fields preserved from the fresh locked row), and
  delegates to ``ProviderConfigService.update_provider_config`` — one audit
  record and one mutation inside the caller's transaction.
* ``preview_route_update_for_route`` resolves exactly one route READ-ONLY,
  merges the typed edits, validates the complete merged candidate, and
  renders a reviewed NON-secret plan (with an expected configuration
  fingerprint) without writing or auditing anything.
* ``execute_route_update_plan`` locks the exact route (and its provider),
  revalidates the fresh expected pre-state and dependencies, and calls
  ``ModelRouteService.update_model_route`` in one caller transaction.

The configuration fingerprint is a public digest over the reviewed
configuration fields (identity and timestamps excluded): it is staleness
data, not a credential and not replay authority. Every error uses fixed,
safe vocabulary and never echoes file bodies, paths, or secret-looking
values. Configuration validation here is NOT credential/model/SMTP
qualification.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute, ProviderConfig
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.modules.servers.completion_service.profiles import (
    PROFILE_KEY,
    load_profile,
    profile_id_from_capabilities,
)
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
)
from slaif_gateway.services.provider_config_service import ProviderConfigService
from slaif_gateway.services.record_errors import RecordNotFoundError

_MODULE_PROVIDER_KIND = "module"
_COMPATIBLE_PROVIDER_KIND = "openai_compatible"

_PREVIEW_NOTE = (
    "Configuration review only. The gateway Codex context/admission ceiling, "
    "the configured default/max output reservation, the physical model "
    "capacity, and the client-advertised context are distinct values; "
    "unknown physical or client values remain unknown. No credential, model, "
    "or SMTP qualification is performed by this plan."
)


def compute_route_configuration_fingerprint(
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
    """Public digest over the reviewed configuration fields of one route.

    Includes capabilities, notes, and enabled; excludes identity
    (route id) and timestamps. Used only as expected-pre-state staleness
    data for reviewed plans — never as a credential or replay authority.
    """
    canonical = json.dumps(
        {
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


def _route_fingerprint(row: ModelRoute) -> str:
    return compute_route_configuration_fingerprint(
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


def validate_merged_route_candidate(
    capabilities: dict[str, Any] | None,
    *,
    endpoint: str,
    provider: str,
    provider_kind: str,
    requested_model: str,
    upstream_model: str,
    external_tool_ceilings: ExternalToolOperatorCeilings = (
        DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
    ),
) -> dict[str, Any]:
    """Complete configuration-time validation of one merged route candidate.

    Reuses the strict capability-group contract and mirrors the server
    module-resolution rules (provider kind, exclusive transport selectors,
    profile availability, and the adapter's public/upstream model
    identity) with the existing pure parsers/loaders. No credentials are
    loaded, no adapter is constructed, and no network call is made. This
    validates CONFIGURATION, not credential/model readiness.
    """
    document = dict(capabilities or {})
    validate_capabilities_document(
        document, external_tool_ceilings=external_tool_ceilings
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
    if PROFILE_KEY in document:
        if provider_kind != _MODULE_PROVIDER_KIND:
            raise ProviderRouteConfigError(
                "completion_service: A profile selector requires a module provider kind."
            )
        if endpoint != CHAT_COMPLETIONS_ENDPOINT:
            raise ProviderRouteConfigError(
                "completion_service: A profile selector requires the chat completions endpoint."
            )
        profile = load_profile(profile_id_from_capabilities(document))
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

    The row is locked (``FOR UPDATE``) before any complete service input is
    assembled, so omitted fields preserve the fresh current values and zero
    retries survive. Exactly one audited mutation runs in the caller
    transaction. ``enabled`` is preserved; use the enable/disable commands.
    """
    if notes is not None and clear_notes:
        raise ProviderRouteConfigError(
            "notes: Choose either --notes or --clear-notes, not both."
        )
    providers = ProviderConfigsRepository(session)
    row = await providers.get_provider_config_for_update(provider_or_id)
    if row is None:
        raise RecordNotFoundError("Provider config")

    if clear_notes and row.notes is not None:
        # The shared service deliberately preserves omitted/None notes
        # (existing callers rely on that), so the explicit CLI clear is a
        # single-column assignment in the SAME locked transaction, covered
        # by the service's one audit record.
        row.notes = None
        await session.flush()

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
        actor_admin_id=actor_admin_id,
        reason=reason,
        confirm_insecure_http=confirm_insecure_http,
    )


def _resolve_route_id(route_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(route_id))
    except ValueError as exc:
        raise RecordNotFoundError("Model route") from exc


async def _load_route_and_provider_kind(
    session: AsyncSession, route_id: str
) -> tuple[ModelRoute, str]:
    routes = ModelRoutesRepository(session)
    providers = ProviderConfigsRepository(session)
    row = await routes.get_model_route_by_id(_resolve_route_id(route_id))
    if row is None:
        raise RecordNotFoundError("Model route")
    provider_row = await providers.get_provider_config_by_provider(row.provider)
    if provider_row is None:
        raise ProviderRouteConfigError("Route provider configuration is missing.")
    return row, provider_row.kind


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
    provider_kind: str,
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
) -> RouteUpdatePlan:
    """Pure: render one reviewed route update plan (no writes, no audit).

    Omitted typed fields preserve the current stored values in the plan;
    ``clear_notes`` is the reviewed clear form for notes. Raises
    ``ProviderRouteConfigError`` for invalid candidates. The caller has
    already resolved the route read-only and must not write on failure.
    """
    if notes is not None and clear_notes:
        raise ProviderRouteConfigError(
            "notes: Choose either --notes or --clear-notes, not both."
        )
    try:
        proposed_endpoint = normalize_endpoint(
            endpoint if endpoint is not None else route.endpoint
        )
    except ValueError as exc:
        raise ProviderRouteConfigError(str(exc)) from exc
    proposed = {
        "requested_model": (
            requested_model if requested_model is not None else route.requested_model
        ),
        "match_type": match_type if match_type is not None else route.match_type,
        "endpoint": proposed_endpoint,
        "provider": provider if provider is not None else route.provider,
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
    validate_merged_route_candidate(
        merged,
        endpoint=proposed_endpoint,
        provider=proposed["provider"],
        provider_kind=provider_kind,
        requested_model=proposed["requested_model"],
        upstream_model=proposed["upstream_model"],
        external_tool_ceilings=external_tool_ceilings,
    )

    current = {
        "requested_model": route.requested_model,
        "match_type": route.match_type,
        "endpoint": route.endpoint,
        "provider": route.provider,
        "upstream_model": route.upstream_model,
        "priority": route.priority,
        "visible_in_models": route.visible_in_models,
        "supports_streaming": route.supports_streaming,
        "notes": route.notes,
    }
    changed = sorted(name for name in current if current[name] != proposed[name])
    if mode != "unchanged":
        changed.append("capabilities")
    plan = RouteUpdatePlan(
        route_id=str(route.id),
        requested_model=proposed["requested_model"],
        match_type=proposed["match_type"],
        endpoint=proposed_endpoint,
        provider=proposed["provider"],
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
        preview={"note": _PREVIEW_NOTE, "changed_fields": changed},
    )
    # Strict round-trip gate BEFORE any file write (rendered document must
    # re-parse under the same strict contract).
    render_route_update_plan(plan)
    return plan


async def preview_route_update_for_route(
    session: AsyncSession,
    route_id: str,
    **edits: Any,
) -> RouteUpdatePlan:
    """READ-ONLY preview: resolve one route + provider kind, render a plan."""
    route, provider_kind = await _load_route_and_provider_kind(session, route_id)
    return preview_route_update(route, provider_kind, **edits)


async def execute_route_update_plan(
    session: AsyncSession,
    plan: RouteUpdatePlan,
    *,
    reason: str,
    actor_admin_id: uuid.UUID | None = None,
) -> ModelRoute:
    """Apply one reviewed route plan: lock, revalidate, one audited update.

    The exact route row is locked with ``FOR UPDATE``; the fresh
    configuration fingerprint and enabled state must still match the plan
    (and the route's provider must still exist), otherwise
    ``ProviderRouteStaleError`` is raised with zero writes and zero
    audits. A repeated apply of an already-applied plan is therefore
    refused as stale — never re-mutated. The merged candidate is
    revalidated against the fresh provider kind before the single
    ``ModelRouteService.update_model_route`` call in the caller
    transaction.

    Documented no-op law: if the reviewed plan's complete proposed state
    already equals the fresh locked row (possible only for a plan that
    changed nothing), the row is returned as-is with ZERO writes and ZERO
    audits. Any real change is applied exactly once; a second apply of the
    same plan is refused stale because the fresh fingerprint no longer
    matches the reviewed expected pre-state.
    """
    routes = ModelRoutesRepository(session)
    providers = ProviderConfigsRepository(session)
    row = await routes.get_model_route_for_update(plan.route_id)
    if row is None:
        raise RecordNotFoundError("Model route")
    if row.enabled != plan.enabled:
        raise ProviderRouteStaleError(
            "The route enabled state no longer matches the reviewed plan."
        )
    if _route_fingerprint(row) != plan.expected_configuration_fingerprint:
        raise ProviderRouteStaleError(
            "The route configuration no longer matches the reviewed plan."
        )
    provider_row = await providers.get_provider_config_for_update(row.provider)
    if provider_row is None:
        raise ProviderRouteStaleError(
            "The route provider configuration no longer matches the reviewed plan."
        )
    merged = _capabilities_for_mode(
        row.capabilities, plan.capabilities_mode, plan.capabilities, plan.capability_patch
    )
    validate_merged_route_candidate(
        merged,
        endpoint=plan.endpoint,
        provider=plan.provider,
        provider_kind=provider_row.kind,
        requested_model=plan.requested_model,
        upstream_model=plan.upstream_model or plan.requested_model,
    )
    if (
        merged == (row.capabilities or {})
        and row.requested_model == plan.requested_model
        and row.match_type == plan.match_type
        and row.endpoint == plan.endpoint
        and row.provider == plan.provider
        and row.upstream_model == (plan.upstream_model or plan.requested_model)
        and row.priority == plan.priority
        and row.visible_in_models == plan.visible_in_models
        and row.supports_streaming == plan.supports_streaming
        and row.notes == plan.notes
    ):
        return row
    return await ModelRouteService(
        model_routes_repository=routes,
        audit_repository=AuditRepository(session),
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
