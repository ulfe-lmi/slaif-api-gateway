"""Read-only, configuration-only inspection of effective gateway-key policy.

This module projects SAFE, explicitly selected values from a persisted
``GatewayKey`` row and the deployment ``Settings`` into CLI/reportable
structures. It NEVER authenticates: no HMAC verification, status, fence, or
time-window checks are performed or implied, and its output must not be read
as proof that a request would be admitted. Provider configuration references
(base URLs, API-key environment variables, raw capabilities/metadata) are
never projected; unknown or malformed stored policy surfaces as a fixed safe
marker instead of copied private values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.rate_limits import (
    LazyThrottlingPolicy,
    parse_lazy_throttling_policy_metadata,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    ChatCompletionRouteCapabilityError,
    enforce_chat_completion_route_capabilities,
)
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnPolicyError,
    chat_streaming_live_burn_policy_from_metadata,
    default_chat_streaming_live_burn_policy,
)
from slaif_gateway.services.endpoint_policy import (
    CHAT_COMPLETIONS,
    MODELS_LIST,
    RESPONSES,
    EndpointPolicyService,
    canonical_endpoint_id,
)
from slaif_gateway.services.endpoint_policy_errors import EndpointNotAllowedError
from slaif_gateway.services.external_tool_policy_contract import (
    parse_key_external_tool_policy,
    strict_key_policy,
)
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.key_modes import is_trusted_calibration_key
from slaif_gateway.services.rate_limit_policy import (
    build_rate_limit_policy,
    effective_lazy_throttling_policy,
)
from slaif_gateway.services.responses_policy_validation import (
    validate_key_responses_policy,
)
from slaif_gateway.services.responses_route_capabilities import (
    ResponsesRouteCapabilityError,
    enforce_responses_route_capabilities,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    ResponsesStreamingLiveBurnPolicyError,
    default_responses_streaming_live_burn_policy,
    responses_streaming_live_burn_policy_from_metadata,
)
from slaif_gateway.services.route_resolution import (
    RouteResolutionService,
    matches_model_route,
)
from slaif_gateway.services.routing_errors import (
    AmbiguousRouteError,
    ModelNotAllowedForKeyError,
    ModelNotFoundError,
    ModelRouteDisabledError,
    ProviderDisabledError,
    ProviderNotAllowedForKeyError,
    UnsupportedRouteMatchTypeError,
)
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

# Mirrors the runtime candidate bound in RouteResolutionService.resolve_model.
ROUTE_CANDIDATE_BOUND = 1000

# Fixed safe vocabulary (never operator input, never stored values).
SOURCE_KEY = "key"
SOURCE_DEPLOYMENT = "deployment"
SOURCE_DEFAULT = "default"
SOURCE_NONE = "none"

LAZY_STATE_ABSENT = "absent"
LAZY_STATE_REJECT_CONFIGURED = "reject-configured"
LAZY_STATE_WAIT_CONFIGURED = "wait-configured"
LAZY_STATE_INVALID_STORED = "invalid-stored"

MODULE_STATE_BOUND = "bound"
MODULE_STATE_ABSENT = "absent"
MODULE_STATE_UNAVAILABLE = "unavailable"

RESPONSES_POLICY_STATE_ABSENT = "absent"
RESPONSES_POLICY_STATE_VALID = "valid"
RESPONSES_POLICY_STATE_INVALID = "invalid"

PROVIDER_POLICY_UNRESTRICTED = "unrestricted"
PROVIDER_POLICY_ALLOW_LIST = "allow-list"
PROVIDER_POLICY_DENY_ALL = "deny-all"
PROVIDER_POLICY_INVALID = "invalid"

STATUS_NOTE_NOT_YET_VALID = "not-yet-valid"
STATUS_NOTE_EXPIRED = "expired"
STATUS_NOTE_FENCE_ACTIVE = "external-tool-fence-active"

KEY_STATE_BLOCKER_PREFIX = "key-"

VERDICT_RESOLVED = "resolved"
VERDICT_BLOCKED = "blocked"
VERDICT_NOT_EVALUATED = "not-evaluated"
VERDICT_DISCOVERY = "discovery-separately-authorized"

BLOCKER_ROUTE_CAPABILITY = "route-capability-not-supported"

REASON_UNKNOWN_ENDPOINT = "unknown-endpoint"
REASON_ENDPOINT_PAYLOAD_DEPENDENT = "endpoint-payload-dependent"
REASON_MODEL_REQUIRED = "requested-model-required"

DISCOVERY_NOTE = (
    "Catalog discovery (/v1/models) is separately authorized; it never "
    "auto-grants model access and its listing stays filtered to the key's "
    "allowed models/providers."
)
NOT_EVALUATED_NOTE = (
    "Configuration-only view: request body, tools, media, streaming shape, "
    "pricing, quota, Redis, and provider health are not evaluated here."
)
CONFIG_ONLY_NOTE = (
    "Configuration-only view; not authentication, admission, or proof of "
    "request success."
)
WAITING_NOTE = (
    "Waiting never relaxes hard quota, auth, security, or pricing."
)
REDIS_CONFIG_NOTE = (
    "Redis values are deployment configuration, not live health or capacity "
    "proof."
)
CANDIDATE_ROUTE_NOTE = (
    "Candidate configuration match only (enabled route, enabled provider, "
    "provider allow-list); ranking, ambiguity, and final routability are "
    "reported in verdict/resolution, not in this list."
)
KEY_STATE_BLOCKED_NOTE = (
    "This key is not currently usable for requests ({state}); configuration "
    "facts alone do not make it usable."
)

# Members of a rate-limit policy and the fixed warning text used when an
# inherited deployment rate still applies despite an unlimited lifetime
# quota (operators must see this without the CLI guessing or raising limits).
_RATE_MEMBER_WARNING = (
    "Inherited deployment {member} rate still applies despite an unlimited "
    "lifetime {quota} quota."
)


@dataclass(frozen=True, slots=True)
class KeyPolicyInspectionContext:
    """Read-only repositories for configuration-only explanation."""

    model_routes: ModelRoutesRepository
    provider_configs: ProviderConfigsRepository


def build_inspection_key(
    *,
    gateway_key: GatewayKey,
    settings: Settings,
) -> AuthenticatedGatewayKey:
    """Construct a READ-ONLY policy-context DTO from a stored key row.

    Field derivation mirrors
    ``GatewayAuthService.authenticate_authorization_header`` (scalar rate
    columns, metadata-only window, strictly parsed stored lazy policy,
    trusted-calibration allow-all promotion) so effective values match the
    real authentication context. It performs NO authentication: no HMAC
    verification, no status/fence/time checks, and the result must never be
    used as if the key had authenticated.
    """
    allowed_providers: tuple[str, ...] | None = None
    rate_limit_metadata: dict[str, object] = {}
    lazy_throttling_policy: LazyThrottlingPolicy | None = None
    responses_policy: dict[str, object] | None = None
    chat_streaming_live_burn_policy = default_chat_streaming_live_burn_policy()
    responses_streaming_live_burn_policy = (
        default_responses_streaming_live_burn_policy()
    )
    external_tool_policy = strict_key_policy()
    if isinstance(gateway_key.metadata_json, dict):
        providers = gateway_key.metadata_json.get("allowed_providers")
        if isinstance(providers, list):
            allowed_providers = tuple(str(item) for item in providers)
        raw_rate_limit_metadata = gateway_key.metadata_json.get("rate_limit_policy")
        if isinstance(raw_rate_limit_metadata, dict):
            rate_limit_metadata = raw_rate_limit_metadata
        lazy_throttling_policy = parse_lazy_throttling_policy_metadata(
            gateway_key.metadata_json.get("lazy_throttling_policy"),
            max_wait_seconds_ceiling=settings.LAZY_THROTTLING_MAX_WAIT_SECONDS,
            max_waiting_per_key_ceiling=settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY,
        )
        raw_responses_policy = gateway_key.metadata_json.get("responses_policy")
        if isinstance(raw_responses_policy, dict):
            sanitized_policy = sanitize_metadata_mapping(
                raw_responses_policy,
                drop_content_keys=True,
            )
            responses_policy = (
                sanitized_policy if isinstance(sanitized_policy, dict) else None
            )
        try:
            chat_streaming_live_burn_policy = chat_streaming_live_burn_policy_from_metadata(
                gateway_key.metadata_json,
                max_abs_cost_margin_eur=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                max_abs_token_margin=settings.CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError:
            chat_streaming_live_burn_policy = default_chat_streaming_live_burn_policy()
        try:
            responses_streaming_live_burn_policy = (
                responses_streaming_live_burn_policy_from_metadata(
                    gateway_key.metadata_json,
                    max_abs_cost_margin_eur=settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                    max_abs_token_margin=settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
                )
            )
        except ResponsesStreamingLiveBurnPolicyError:
            responses_streaming_live_burn_policy = (
                default_responses_streaming_live_burn_policy()
            )
        parsed_external_policy = parse_key_external_tool_policy(
            gateway_key.metadata_json.get("external_tool_policy"),
            ceilings=settings.get_external_tool_operator_ceilings(),
        )
        if parsed_external_policy.valid and parsed_external_policy.policy is not None:
            external_tool_policy = parsed_external_policy.policy

    window_seconds = rate_limit_metadata.get("window_seconds")
    if isinstance(window_seconds, bool) or not isinstance(window_seconds, int):
        window_seconds = None

    trusted_calibration = is_trusted_calibration_key(
        key_purpose=getattr(gateway_key, "key_purpose", "standard"),
        capability_policy_mode=getattr(gateway_key, "capability_policy_mode", "standard"),
    )

    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key.id,
        owner_id=gateway_key.owner_id,
        cohort_id=gateway_key.cohort_id,
        public_key_id=gateway_key.public_key_id,
        status=gateway_key.status,
        valid_from=gateway_key.valid_from,
        valid_until=gateway_key.valid_until,
        allow_all_models=gateway_key.allow_all_models or trusted_calibration,
        allowed_models=tuple(gateway_key.allowed_models or ()),
        allow_all_endpoints=gateway_key.allow_all_endpoints or trusted_calibration,
        allowed_endpoints=tuple(gateway_key.allowed_endpoints or ()),
        allowed_providers=allowed_providers,
        cost_limit_eur=gateway_key.cost_limit_eur,
        token_limit_total=gateway_key.token_limit_total,
        request_limit_total=gateway_key.request_limit_total,
        cost_used_eur=gateway_key.cost_used_eur,
        tokens_used_total=gateway_key.tokens_used_total,
        cost_reserved_eur=gateway_key.cost_reserved_eur,
        tokens_reserved_total=gateway_key.tokens_reserved_total,
        rate_limit_policy={
            "requests_per_minute": gateway_key.rate_limit_requests_per_minute,
            "tokens_per_minute": gateway_key.rate_limit_tokens_per_minute,
            "max_concurrent_requests": gateway_key.max_concurrent_requests,
            "window_seconds": window_seconds,
        },
        lazy_throttling=lazy_throttling_policy,
        responses_policy=responses_policy,
        chat_streaming_live_burn_policy=chat_streaming_live_burn_policy.to_metadata(),
        responses_streaming_live_burn_policy=(
            responses_streaming_live_burn_policy.to_metadata()
        ),
        key_purpose=getattr(gateway_key, "key_purpose", "standard"),
        capability_policy_mode=getattr(gateway_key, "capability_policy_mode", "standard"),
        external_tool_policy=external_tool_policy.to_metadata(),
    )


def _decimal_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _rate_member(
    *,
    configured: int | None,
    effective: int | None,
    deployment_default: int | None,
) -> dict[str, object]:
    if configured is not None:
        source = SOURCE_KEY
    elif effective is not None:
        source = SOURCE_DEPLOYMENT
    else:
        source = SOURCE_NONE
    return {"configured": configured, "effective": effective, "source": source}


def _lazy_inspection(
    *,
    stored_raw: object,
    effective: LazyThrottlingPolicy,
    max_wait_seconds_ceiling: int,
    max_waiting_per_key_ceiling: int,
) -> dict[str, object]:
    # Classify with the SAME installation ceilings the effective parser uses:
    # a stored wait that exceeds an operator ceiling is "invalid-stored" and
    # never projects as configured waiting.
    parsed = (
        None
        if stored_raw is None
        else parse_lazy_throttling_policy_metadata(
            stored_raw,
            max_wait_seconds_ceiling=max_wait_seconds_ceiling,
            max_waiting_per_key_ceiling=max_waiting_per_key_ceiling,
        )
    )
    if stored_raw is None:
        stored_state = LAZY_STATE_ABSENT
    elif parsed is None:
        stored_state = LAZY_STATE_INVALID_STORED
    elif parsed.is_wait_mode():
        stored_state = LAZY_STATE_WAIT_CONFIGURED
    else:
        stored_state = LAZY_STATE_REJECT_CONFIGURED
    # Any VALID stored mode is KEY-configured; only absent/invalid fall back
    # to the deployment default source.
    source = (
        SOURCE_KEY
        if stored_state in (LAZY_STATE_WAIT_CONFIGURED, LAZY_STATE_REJECT_CONFIGURED)
        else SOURCE_DEFAULT
    )
    return {
        "stored_state": stored_state,
        "mode": effective.mode,
        "max_wait_seconds": effective.max_wait_seconds,
        "max_waiting_requests": effective.max_waiting_requests,
        "source": source,
        "applicable_endpoints": [
            RouteResolutionService.CHAT_COMPLETIONS_ENDPOINT,
            RouteResolutionService.RESPONSES_ENDPOINT,
        ],
        "note": WAITING_NOTE,
    }


def _status_note(*, gateway_key: GatewayKey, now: datetime) -> str | None:
    if gateway_key.status in ("suspended", "revoked"):
        return gateway_key.status
    fence_state = getattr(gateway_key, "external_tool_fence_state", "none")
    if fence_state in ("active", "held"):
        return STATUS_NOTE_FENCE_ACTIVE
    if now < gateway_key.valid_from:
        return STATUS_NOTE_NOT_YET_VALID
    if now >= gateway_key.valid_until:
        return STATUS_NOTE_EXPIRED
    return None


def _responses_profile_inspection(responses_policy: dict[str, object] | None) -> dict[str, object]:
    """Project a SAFE Responses/Codex profile from the stored policy block.

    Uses the same strict shared 196 authoring validator/registry so unknown,
    malformed, or STALE client-module pins are reported as a fixed
    ``unavailable`` marker without copying any unsupported or private value.
    Only the finite validated capability grants and local tool types are
    displayed; a module pin never grants capabilities by itself.
    """
    note = (
        "Module fixture identity is public registration identity; it is not "
        "replay HMAC authority, and a module pin never grants capabilities."
    )
    if responses_policy is None:
        return {
            "policy_state": RESPONSES_POLICY_STATE_ABSENT,
            "client_module": {"state": MODULE_STATE_ABSENT},
            "capabilities": [],
            "local_tool_types": [],
            "note": note,
        }

    try:
        canonical = validate_key_responses_policy(responses_policy)
    except InvalidGatewayKeyPolicyError:
        # Unknown/malformed/stale block: fixed safe marker, no copied values.
        return {
            "policy_state": RESPONSES_POLICY_STATE_INVALID,
            "client_module": {"state": MODULE_STATE_UNAVAILABLE},
            "capabilities": [],
            "local_tool_types": [],
            "note": note,
        }

    canonical = canonical or {}
    module: dict[str, object] = {"state": MODULE_STATE_ABSENT}
    raw_module = canonical.get("client_module")
    if isinstance(raw_module, dict):
        module = {
            "state": MODULE_STATE_BOUND,
            "id": raw_module.get("id"),
            "version": raw_module.get("version"),
            "fixture_sha256": raw_module.get("fixture_sha256"),
        }
    return {
        "policy_state": RESPONSES_POLICY_STATE_VALID,
        "client_module": module,
        "capabilities": list(canonical.get("allowed_capabilities") or []),
        "local_tool_types": list(canonical.get("allowed_local_tool_types") or []),
        "note": note,
    }


def _provider_policy_inspection(metadata_json: dict[str, object] | None) -> dict[str, object]:
    """Project the stored provider restriction as a SAFE explicit state.

    Preserves the legitimate ``None`` (unrestricted) versus ``[]`` (deny-all)
    distinction. Malformed members (non-string, or empty) are refused with a
    fixed ``invalid`` marker and never echoed, so private/malformed stored
    values cannot reach output.
    """
    raw = metadata_json.get("allowed_providers") if isinstance(metadata_json, dict) else None
    if raw is None:
        return {
            "state": PROVIDER_POLICY_UNRESTRICTED,
            "allowed_providers": None,
            "allow_all_providers": True,
        }
    if (
        isinstance(raw, list)
        and all(isinstance(item, str) and item.strip() for item in raw)
    ):
        values = [item for item in raw]
        state = PROVIDER_POLICY_DENY_ALL if not values else PROVIDER_POLICY_ALLOW_LIST
        return {
            "state": state,
            "allowed_providers": values,
            "allow_all_providers": False,
        }
    return {
        "state": PROVIDER_POLICY_INVALID,
        "allowed_providers": None,
        "allow_all_providers": False,
    }


def build_key_policy_inspection(
    *,
    gateway_key: GatewayKey,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    """Project the key's configured + effective policy as safe JSON values."""
    check_now = now or datetime.now(UTC)
    inspection_key = build_inspection_key(gateway_key=gateway_key, settings=settings)
    policy = build_rate_limit_policy(
        authenticated_key=inspection_key, settings=settings
    )

    requests_member = _rate_member(
        configured=inspection_key.rate_limit_policy.get("requests_per_minute"),
        effective=policy.requests_per_minute,
        deployment_default=settings.DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE,
    )
    tokens_member = _rate_member(
        configured=inspection_key.rate_limit_policy.get("tokens_per_minute"),
        effective=policy.tokens_per_minute,
        deployment_default=settings.DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE,
    )
    concurrency_member = _rate_member(
        configured=inspection_key.rate_limit_policy.get("max_concurrent_requests"),
        effective=policy.concurrent_requests,
        deployment_default=settings.DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS,
    )
    window_configured = inspection_key.rate_limit_policy.get("window_seconds")
    window_member = _rate_member(
        configured=window_configured,
        effective=policy.window_seconds,
        deployment_default=None,
    )
    window_member["source"] = (
        SOURCE_KEY if window_configured is not None else SOURCE_DEFAULT
    )

    warnings: list[str] = []
    if requests_member["source"] == SOURCE_DEPLOYMENT and gateway_key.request_limit_total is None:
        warnings.append(_RATE_MEMBER_WARNING.format(member="request", quota="request"))
    if tokens_member["source"] == SOURCE_DEPLOYMENT and gateway_key.token_limit_total is None:
        warnings.append(_RATE_MEMBER_WARNING.format(member="token", quota="token"))

    # Reuse the shared effective-policy law rather than maintaining a second
    # fallback formula: a missing/malformed stored policy is the reject
    # default; only an explicitly validated stored wait projects through.
    lazy_policy = effective_lazy_throttling_policy(
        authenticated_key=inspection_key, settings=settings
    )
    raw_metadata = (
        gateway_key.metadata_json.get("lazy_throttling_policy")
        if isinstance(gateway_key.metadata_json, dict)
        else None
    )

    quotas: dict[str, object] = {}
    for name, configured, used, reserved in (
        (
            "cost_eur",
            gateway_key.cost_limit_eur,
            gateway_key.cost_used_eur,
            gateway_key.cost_reserved_eur,
        ),
        (
            "tokens",
            gateway_key.token_limit_total,
            gateway_key.tokens_used_total,
            gateway_key.tokens_reserved_total,
        ),
        (
            "requests",
            gateway_key.request_limit_total,
            gateway_key.requests_used_total,
            gateway_key.requests_reserved_total,
        ),
    ):
        unlimited = configured is None
        remaining: Decimal | int | None = None
        if not unlimited:
            remaining = configured - (used or 0) - (reserved or 0)
        quotas[name] = {
            "configured": _decimal_or_none(configured) if isinstance(configured, Decimal) else configured,
            "unlimited": unlimited,
            "used": _decimal_or_none(used) if isinstance(used, Decimal) else used,
            "reserved": _decimal_or_none(reserved) if isinstance(reserved, Decimal) else reserved,
            "remaining": _decimal_or_none(remaining)
            if isinstance(remaining, Decimal)
            else remaining,
        }

    status_note = _status_note(gateway_key=gateway_key, now=check_now)

    return {
        "view": "effective-key-policy",
        "scope": "configuration-only",
        "note": CONFIG_ONLY_NOTE,
        "key": {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "key_prefix": gateway_key.key_prefix,
            "key_hint": gateway_key.key_hint,
            "owner_id": str(gateway_key.owner_id),
            "cohort_id": str(gateway_key.cohort_id)
            if gateway_key.cohort_id is not None
            else None,
            "status": gateway_key.status,
            "status_note": status_note,
            "valid_from": gateway_key.valid_from,
            "valid_until": gateway_key.valid_until,
            "created_at": gateway_key.created_at,
            "updated_at": gateway_key.updated_at,
            "revoked_at": gateway_key.revoked_at,
            "revoked_reason": gateway_key.revoked_reason,
            "key_purpose": gateway_key.key_purpose,
            "capability_policy_mode": gateway_key.capability_policy_mode,
            "template_id": str(gateway_key.template_id)
            if gateway_key.template_id is not None
            else None,
            "template_revision_id": str(gateway_key.template_revision_id)
            if gateway_key.template_revision_id is not None
            else None,
        },
        "rate_limits": {
            "count_semantics": "counts per selected window",
            "window_seconds": window_member,
            "requests_per_window": requests_member,
            "tokens_per_window": tokens_member,
            "concurrency": concurrency_member,
            "warnings": warnings,
        },
        "lazy_throttling": _lazy_inspection(
            stored_raw=raw_metadata,
            effective=lazy_policy,
            max_wait_seconds_ceiling=settings.LAZY_THROTTLING_MAX_WAIT_SECONDS,
            max_waiting_per_key_ceiling=settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY,
        ),
        "quotas": quotas,
        "allowlists": {
            "allow_all_models": inspection_key.allow_all_models,
            "allowed_models": list(inspection_key.allowed_models),
            "allow_all_endpoints": inspection_key.allow_all_endpoints,
            "allowed_endpoints": list(inspection_key.allowed_endpoints),
            **_provider_policy_inspection(gateway_key.metadata_json),
        },
        "responses_profile": _responses_profile_inspection(inspection_key.responses_policy),
        "redis_configuration": {
            "enabled": settings.ENABLE_REDIS_RATE_LIMITS,
            "fail_closed": settings.rate_limit_fail_closed(),
            "has_limits": policy.has_limits(),
            "note": REDIS_CONFIG_NOTE,
        },
    }


_MODEL_ROUTE_ENDPOINT_PATHS: dict[str, str] = {
    CHAT_COMPLETIONS: RouteResolutionService.CHAT_COMPLETIONS_ENDPOINT,
    RESPONSES: RouteResolutionService.RESPONSES_ENDPOINT,
}

_BLOCKER_BY_ERROR = {
    ModelNotAllowedForKeyError: "model-not-allowed-for-key",
    ModelRouteDisabledError: "model-route-disabled",
    ModelNotFoundError: "model-not-found",
    ProviderNotAllowedForKeyError: "provider-not-allowed-for-key",
    ProviderDisabledError: "provider-disabled",
    AmbiguousRouteError: "ambiguous-route",
    UnsupportedRouteMatchTypeError: "unsupported-route-match-type",
}


async def explain_model_route_access(
    *,
    gateway_key: GatewayKey,
    settings: Settings,
    requested_model: str,
    endpoint: str,
    context: KeyPolicyInspectionContext,
    now: datetime | None = None,
) -> dict[str, object]:
    """Explain which configuration grants or blocks model access.

    Configuration-only: it performs no authentication, admission, quota
    reservation, waiting, provider contact, or capture. The runtime
    1000-route candidate bound is preserved and disclosed, not raised.
    """
    inspection_key = build_inspection_key(gateway_key=gateway_key, settings=settings)
    status_note = _status_note(
        gateway_key=gateway_key, now=now or datetime.now(UTC)
    )

    report: dict[str, object] = {
        "view": "route-explanation",
        "scope": "configuration-only",
        "note": CONFIG_ONLY_NOTE,
        "key": {
            "gateway_key_id": str(gateway_key.id),
            "public_key_id": gateway_key.public_key_id,
            "status": gateway_key.status,
            "status_note": status_note,
        },
        "key_state": {
            "status": gateway_key.status,
            "status_note": status_note,
            "usable_for_requests": status_note is None,
        },
        "requested_model": requested_model,
        "endpoint_requested": endpoint,
        "endpoint_known": False,
        "endpoint_stable_id": None,
        "endpoint_allowed": None,
        "verdict": VERDICT_NOT_EVALUATED,
        "blocker": None,
        "message": None,
        "resolution": None,
        "capability_checks": None,
        "allowlist_intersection": None,
        "unevaluated": [NOT_EVALUATED_NOTE],
        "bounds": {
            "route_candidate_bound": ROUTE_CANDIDATE_BOUND,
            "routes_examined": None,
            "possible_unexamined_routes": None,
        },
    }

    # A suspended/revoked/expired/not-yet-valid/fenced key cannot look like a
    # usable key: the known key-state blocker is reported first (the runtime
    # validates these before any route facts), without performing any
    # authentication here.
    if status_note is not None:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = f"{KEY_STATE_BLOCKER_PREFIX}{status_note}"
        report["message"] = KEY_STATE_BLOCKED_NOTE.format(state=status_note)
        report["bounds"]["possible_unexamined_routes"] = False
        return report

    stable_id = canonical_endpoint_id(endpoint)
    if stable_id is None:
        report["message"] = "Endpoint is not a known stable endpoint identifier."
        report["bounds"]["possible_unexamined_routes"] = False
        report["unevaluated"] = [REASON_UNKNOWN_ENDPOINT, NOT_EVALUATED_NOTE]
        return report
    report["endpoint_known"] = True
    report["endpoint_stable_id"] = stable_id

    try:
        EndpointPolicyService().ensure_endpoint_allowed(inspection_key, stable_id)
        endpoint_allowed = True
    except EndpointNotAllowedError:
        endpoint_allowed = False
    report["endpoint_allowed"] = endpoint_allowed

    if stable_id == MODELS_LIST:
        report["verdict"] = VERDICT_DISCOVERY
        if endpoint_allowed:
            report["message"] = DISCOVERY_NOTE
        else:
            report["blocker"] = "endpoint-not-allowed"
            report["message"] = (
                DISCOVERY_NOTE
                + " This key is not currently authorized for catalog discovery."
            )
        report["bounds"]["possible_unexamined_routes"] = False
        return report

    path = _MODEL_ROUTE_ENDPOINT_PATHS.get(stable_id)
    if path is None:
        report["message"] = (
            "This endpoint's access depends on payload or resource state that "
            "configuration-only inspection does not evaluate."
        )
        report["bounds"]["possible_unexamined_routes"] = False
        report["unevaluated"] = [REASON_ENDPOINT_PAYLOAD_DEPENDENT, NOT_EVALUATED_NOTE]
        return report

    if not requested_model:
        report["message"] = "A requested model is required for route explanation."
        report["bounds"]["possible_unexamined_routes"] = False
        report["unevaluated"] = [REASON_MODEL_REQUIRED, NOT_EVALUATED_NOTE]
        return report

    if not endpoint_allowed:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = "endpoint-not-allowed"
        report["message"] = (
            "The key is not authorized for this endpoint; model-route facts "
            "are not evaluated for an unauthorized endpoint."
        )
        report["bounds"]["possible_unexamined_routes"] = False
        return report

    routes = await context.model_routes.list_model_routes(
        endpoint=path, limit=ROUTE_CANDIDATE_BOUND
    )
    report["bounds"]["routes_examined"] = len(routes)
    report["bounds"]["possible_unexamined_routes"] = len(routes) >= ROUTE_CANDIDATE_BOUND

    # Allowlist-versus-enabled-route intersection: finite configured route
    # patterns only; never an exhaustive or infinite model list. Applies the
    # SAME public matching law (matches_model_route) and the same
    # enabled-provider / provider-allow-list restrictions as the resolver,
    # without shadowing ranking or modifying the runtime resolver.
    provider_configs = await context.provider_configs.list_provider_configs()
    enabled_provider_names = {
        provider_config.provider for provider_config in provider_configs if provider_config.enabled
    }
    trusted_calibration = is_trusted_calibration_key(
        key_purpose=inspection_key.key_purpose,
        capability_policy_mode=inspection_key.capability_policy_mode,
    )
    restrict_providers = (
        not trusted_calibration and inspection_key.allowed_providers is not None
    )
    allowed_provider_names = set(inspection_key.allowed_providers or ())

    candidate_routes = [
        route
        for route in routes
        if route.enabled
        and route.provider in enabled_provider_names
        and (not restrict_providers or route.provider in allowed_provider_names)
    ]
    if inspection_key.allow_all_models:
        report["allowlist_intersection"] = {
            "allowed_models": "all",
            "candidate_route_patterns": sorted(
                {route.requested_model for route in candidate_routes}
            ),
            "note": CANDIDATE_ROUTE_NOTE,
        }
    else:
        allowed = set(inspection_key.allowed_models)
        matched: set[str] = set()
        for route in candidate_routes:
            for model in allowed:
                try:
                    if matches_model_route(model, route):
                        matched.add(model)
                except UnsupportedRouteMatchTypeError:
                    continue
        report["allowlist_intersection"] = {
            "allowed_models": sorted(allowed),
            "allowed_models_with_candidate_route": sorted(matched),
            "note": CANDIDATE_ROUTE_NOTE,
        }

    resolution_service = RouteResolutionService(
        model_routes_repository=context.model_routes,
        provider_configs_repository=context.provider_configs,
    )
    try:
        result = await resolution_service.resolve_model(
            requested_model, inspection_key, endpoint=path
        )
    except ModelNotAllowedForKeyError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[ModelNotAllowedForKeyError]
        report["message"] = exc.safe_message
        return report
    except ModelRouteDisabledError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[ModelRouteDisabledError]
        report["message"] = exc.safe_message
        return report
    except ProviderNotAllowedForKeyError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[ProviderNotAllowedForKeyError]
        report["message"] = exc.safe_message
        return report
    except ProviderDisabledError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[ProviderDisabledError]
        report["message"] = exc.safe_message
        return report
    except AmbiguousRouteError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[AmbiguousRouteError]
        report["message"] = exc.safe_message
        return report
    except UnsupportedRouteMatchTypeError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[UnsupportedRouteMatchTypeError]
        report["message"] = exc.safe_message
        return report
    except ModelNotFoundError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = _BLOCKER_BY_ERROR[ModelNotFoundError]
        report["message"] = exc.safe_message
        return report

    report["verdict"] = VERDICT_RESOLVED
    report["message"] = None
    report["resolution"] = {
        "provider": result.provider,
        "resolved_model": result.resolved_model,
        "route_id": str(result.route_id),
        "route_match_type": result.route_match_type,
        "route_pattern": result.route_pattern,
        "priority": result.priority,
        "visible_model_id": result.visible_model_id,
        "supports_streaming": result.supports_streaming,
    }
    # Base-request capability checks use the CURRENT pure runtime enforcers
    # with an EMPTY payload: they prove only the base required capability for
    # the endpoint (Chat text / Responses mandatory text). Optional features
    # (streaming, tools, media, structured output, Codex slices) depend on
    # request shape and remain not-evaluated here.
    try:
        if stable_id == CHAT_COMPLETIONS:
            enforce_chat_completion_route_capabilities(
                payload={},
                route_capabilities=result.capabilities,
                route_supports_streaming=result.supports_streaming,
                requested_model=requested_model,
                provider_kind=result.provider_kind,
            )
        else:
            enforce_responses_route_capabilities(
                route_capabilities=result.capabilities,
                route_supports_streaming=result.supports_streaming,
            )
    except ChatCompletionRouteCapabilityError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = BLOCKER_ROUTE_CAPABILITY
        report["message"] = exc.safe_message
        report["capability_checks"] = {
            "base_request_supported": False,
            "capability_error_code": exc.error_code,
            "unevaluated": [NOT_EVALUATED_NOTE],
        }
        return report
    except ResponsesRouteCapabilityError as exc:
        report["verdict"] = VERDICT_BLOCKED
        report["blocker"] = BLOCKER_ROUTE_CAPABILITY
        report["message"] = exc.safe_message
        report["capability_checks"] = {
            "base_request_supported": False,
            "capability_error_code": exc.error_code,
            "unevaluated": [NOT_EVALUATED_NOTE],
        }
        return report
    report["capability_checks"] = {
        "base_request_supported": True,
        "capability_error_code": None,
        "unevaluated": [NOT_EVALUATED_NOTE],
    }
    return report
