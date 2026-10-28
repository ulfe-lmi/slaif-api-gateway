"""Shared typed key-configuration operations (R1) for create, update, and export.

Pure helpers shared by the CLI (typed flags and ``--policy-file``) and the
service layer:

- build a ``CreateGatewayKeyInput`` from a presence-aware
  :class:`~slaif_gateway.schemas.key_configuration.KeyConfiguration`
  (identity/validity/delivery flags accompany the file, policy fields come
  from it);
- project presence semantics for the partial-update groups (request policy
  group, quota members);
- canonicalize a stored Responses policy block for export, failing
  explicitly when the stored block cannot be administered by this tool.

Field-level service rules (route-aware request policy, rate/lazy/live-burn/
external-tool validation, fences, audit, transactions) remain owned by
:class:`~slaif_gateway.services.key_service.KeyService`; nothing in this
module mutates state.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from slaif_gateway.schemas.key_configuration import (
    ABSENT,
    RATE_POLICY_LEGACY_ALIASES,
    RATE_POLICY_MEMBER_NAMES,
    KeyConfiguration,
)
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.modules.clients.registry import resolve_responses_client_module
from slaif_gateway.modules.contracts import ModuleSelectionError
from slaif_gateway.services.key_errors import (
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyPolicyError,
    KeyManagementError,
)
from slaif_gateway.services.responses_policy_validation import (
    validate_key_responses_policy,
)

#: Request-policy members: an update is a partial, per-member change.
#: Any present member triggers the (merged, validated) request-policy write.
REQUEST_POLICY_GROUP_FIELDS: tuple[str, ...] = (
    "allowed_models",
    "allow_all_models",
    "allowed_endpoints",
    "allow_all_endpoints",
)

#: Quota members: each present member replaces that column; absent members
#: keep the key's current value on update.
QUOTA_FIELDS: tuple[str, ...] = (
    "cost_limit_eur",
    "token_limit_total",
    "request_limit_total",
)


class KeyConfigurationExportError(KeyManagementError):
    """The stored key policy cannot be rendered as a consumable export."""

    error_code = "key_configuration_export_unavailable"
    message = "Stored key policy cannot be administered by this configuration tool."


def responses_policy_canonical(block: dict[str, object] | None) -> dict[str, object] | None:
    """Validate one authored/stored Responses block to its canonical form."""
    return validate_key_responses_policy(block)


def is_request_policy_group_present(config: KeyConfiguration) -> bool:
    return any(config.has(name) for name in REQUEST_POLICY_GROUP_FIELDS)


def is_quota_group_present(config: KeyConfiguration) -> bool:
    return any(config.has(name) for name in QUOTA_FIELDS)


def request_policy_group_values(
    config: KeyConfiguration,
    *,
    current_allowed_models: list[str] | None,
    current_allow_all_models: bool,
    current_allowed_endpoints: list[str] | None,
    current_allow_all_endpoints: bool,
) -> tuple[list[str], bool, list[str], bool]:
    """Concrete request-policy values for a partial update.

    Omission law: a present member uses its explicit value (an explicit
    null list is the empty list - reject/deny for that dimension); an
    absent member PRESERVES the current locked-row value. The combined
    resulting state is what the service validates (route-aware).
    """
    if config.has("allowed_models"):
        models = config.allowed_models
        models = [] if models is None else list(models)
    else:
        models = list(current_allowed_models or [])
    allow_all_models = (
        bool(config.allow_all_models)
        if config.has("allow_all_models")
        else bool(current_allow_all_models)
    )
    if config.has("allowed_endpoints"):
        endpoints = config.allowed_endpoints
        endpoints = [] if endpoints is None else list(endpoints)
    else:
        endpoints = list(current_allowed_endpoints or [])
    allow_all_endpoints = (
        bool(config.allow_all_endpoints)
        if config.has("allow_all_endpoints")
        else bool(current_allow_all_endpoints)
    )
    return models, allow_all_models, endpoints, allow_all_endpoints


#: A stored block with NO client-module binding (the runtime default module
#: applies; an initial explicit binding may be made on update).
UNBOUND: object = None

#: ("resolved", (module_id, module_version, fixture_sha256)) - the CURRENT
#: runtime resolver resolves the stored block (explicit registered pin or
#: the implicit historical five-gate shape).
#
#: ("stored", pin_or_None) - a pin is present in the stored block but does
#: NOT currently resolve (stale historical identity, unregistered module,
#: or malformed pin). ``pin_or_None`` is the exact stored pin only when it
#: is well-formed (exactly id/version/fixture_sha256 strings); otherwise it
#: is ``None`` and can never match a proposed pin. A stored binding is
#: NEVER initial binding: only the reviewed client-module migration
#: workflow may change it.
ModuleBinding = tuple[str, tuple[str, str, str] | dict[str, str] | None]

_CLIENT_MODULE_PIN_KEYS: tuple[str, ...] = ("id", "version", "fixture_sha256")


def _well_formed_stored_pin(raw: Mapping[str, object]) -> dict[str, str] | None:
    """The exact stored pin, or ``None`` when it is malformed (unmatchable)."""
    if set(raw) != set(_CLIENT_MODULE_PIN_KEYS):
        return None
    pin = {key: raw[key] for key in _CLIENT_MODULE_PIN_KEYS}
    if not all(isinstance(value, str) and value.strip() for value in pin.values()):
        return None
    return {key: pin[key] for key in _CLIENT_MODULE_PIN_KEYS}


def stored_module_binding(block: Mapping[str, object] | None) -> object:
    """Classify the client-module binding of a stored Responses block.

    Returns :data:`UNBOUND` when the block carries no binding (the default
    module would apply); otherwise a ``(state, identity_or_pin)`` tuple as
    documented above. The classification uses the CURRENT runtime resolver
    so implicit legacy bindings stay guarded, and it preserves a stored
    pin even when that pin no longer resolves (stale identities are bound,
    never unbound).
    """
    if not isinstance(block, Mapping):
        return UNBOUND
    try:
        module = resolve_responses_client_module(block)
    except ModuleSelectionError:
        # The resolver failed because of the stored pin (stale identity,
        # unregistered module, or malformed pin shape). Any present
        # client_module field is a stored binding, never initial binding.
        if "client_module" in block:
            raw_pin = block.get("client_module")
            return (
                "stored",
                _well_formed_stored_pin(raw_pin) if isinstance(raw_pin, Mapping) else None,
            )
        return UNBOUND
    fixture = getattr(module, "fixture_sha256", None)
    if isinstance(fixture, str):
        return ("resolved", (module.module_id, module.module_version, fixture))
    if "client_module" in block:
        # A pin the resolver accepted but that exposes no reviewed fixture
        # digest (non-Codex module identity): still a stored binding.
        raw_pin = block.get("client_module")
        return (
            "stored",
            _well_formed_stored_pin(raw_pin) if isinstance(raw_pin, Mapping) else None,
        )
    return UNBOUND


def proposed_matches_stored_binding(
    stored: object, canonical_block: Mapping[str, object]
) -> bool:
    """Whether a validated canonical block keeps the stored binding.

    ``stored`` is a :func:`stored_module_binding` result (never
    :data:`UNBOUND` here). A resolved stored identity matches only the same
    resolved identity; a stored (stale/malformed) pin matches only the
    exact same well-formed pin. A canonical block without a pin applies the
    default module and never matches a stored binding.
    """
    proposed = stored_module_binding(canonical_block)
    if proposed is UNBOUND:
        return False
    if stored[0] == "resolved":
        return proposed == stored
    stored_pin = stored[1]
    proposed_pin = canonical_block.get("client_module")
    if stored_pin is None or not isinstance(proposed_pin, Mapping):
        return False
    return _well_formed_stored_pin(proposed_pin) == stored_pin


def quota_group_values(
    config: KeyConfiguration,
    *,
    current_cost_limit_eur: Decimal | None,
    current_token_limit_total: int | None,
    current_request_limit_total: int | None,
) -> tuple[Decimal | None, int | None, int | None]:
    """Concrete quota column values for a triggered quota update.

    Present members use their explicit value (null means unlimited); absent
    members keep the key's current column value.
    """
    cost = (
        current_cost_limit_eur
        if not config.has("cost_limit_eur")
        else config.cost_limit_eur
    )
    tokens = (
        current_token_limit_total
        if not config.has("token_limit_total")
        else config.token_limit_total
    )
    requests = (
        current_request_limit_total
        if not config.has("request_limit_total")
        else config.request_limit_total
    )
    return cost, tokens, requests


def canonical_rate_policy_members(
    block: Mapping[str, object] | None,
) -> dict[str, object]:
    """Strictly canonicalize an incoming rate-limit override block.

    Unknown members (and legacy aliases with no canonical spelling) are
    rejected with a fixed safe message instead of being silently ignored;
    the historical ``concurrent_requests`` alias is canonicalized to
    ``max_concurrent_requests``, and supplying both spellings for one
    member is rejected as ambiguous. Values are carried through verbatim
    (``None`` keeps its reset semantics); value validation stays with the
    existing rate-limit validator.
    """
    if block is None:
        return {}
    if not isinstance(block, Mapping):
        raise InvalidGatewayKeyLimitsError(
            "Rate limit policy must be an object with nullable members.",
            param="rate_limit_policy",
        )
    canonical: dict[str, object] = {}
    for key, value in block.items():
        if not isinstance(key, str):
            raise InvalidGatewayKeyLimitsError(
                "Rate limit policy contains unsupported fields.",
                param="rate_limit_policy",
            )
        target = RATE_POLICY_LEGACY_ALIASES.get(key, key)
        if target not in RATE_POLICY_MEMBER_NAMES:
            raise InvalidGatewayKeyLimitsError(
                "Rate limit policy contains unsupported fields.",
                param="rate_limit_policy",
            )
        if target in canonical:
            raise InvalidGatewayKeyLimitsError(
                "Rate limit policy repeats one member through an alias.",
                param="rate_limit_policy",
            )
        canonical[target] = value
    return canonical


def _present_or(config: KeyConfiguration, name: str, default: Any) -> Any:
    if not config.has(name):
        return default
    value = getattr(config, name)
    return default if value is ABSENT else value


def build_create_gateway_key_input(
    *,
    config: KeyConfiguration,
    owner_id: UUID,
    valid_from: datetime,
    valid_until: datetime,
    cohort_id: UUID | None = None,
    created_by_admin_id: UUID | None = None,
    note: str | None = None,
    key_purpose: str = "standard",
    capability_policy_mode: str = "standard",
    calibration_metadata: dict[str, object] | None = None,
    confirm_trusted_calibration: bool = False,
) -> CreateGatewayKeyInput:
    """Build the create payload for a typed-configuration key creation.

    Identity, validity, actor, reason, purpose, and delivery flags accompany
    the configuration; every policy field comes from it (absent fields take
    the service defaults). The Responses block is authoring-validated here;
    all other blocks are revalidated by the create service path.
    """
    models = _present_or(config, "allowed_models", None)
    endpoints = _present_or(config, "allowed_endpoints", None)
    rate_policy = _present_or(config, "rate_limit_policy", None)
    if rate_policy is not None and not isinstance(rate_policy, dict):
        raise InvalidGatewayKeyPolicyError(
            "Rate-limit policy must be an object or null.", param="rate_limit_policy"
        )
    return CreateGatewayKeyInput(
        owner_id=owner_id,
        cohort_id=cohort_id,
        valid_from=valid_from,
        valid_until=valid_until,
        created_by_admin_id=created_by_admin_id,
        cost_limit_eur=_present_or(config, "cost_limit_eur", None),
        token_limit_total=_present_or(config, "token_limit_total", None),
        request_limit_total=_present_or(config, "request_limit_total", None),
        allowed_models=list(models) if models else [],
        allowed_endpoints=list(endpoints) if endpoints else [],
        allow_all_models=bool(_present_or(config, "allow_all_models", False)),
        allow_all_endpoints=bool(_present_or(config, "allow_all_endpoints", False)),
        key_purpose=key_purpose,
        capability_policy_mode=capability_policy_mode,
        calibration_metadata=dict(calibration_metadata or {}),
        responses_policy=responses_policy_canonical(
            _present_or(config, "responses_policy", None)
        ),
        allowed_providers=_present_or(config, "allowed_providers", None),
        confirm_trusted_calibration=confirm_trusted_calibration,
        rate_limit_policy=dict(rate_policy) if rate_policy else None,
        lazy_throttling_policy=_present_or(config, "lazy_throttling_policy", None),
        chat_streaming_live_burn_policy=_present_or(
            config, "chat_streaming_live_burn_policy", None
        ),
        external_tool_policy=_present_or(config, "external_tool_policy", None),
        confirm_external_tool_fenced=bool(
            _present_or(config, "confirm_external_tool_fenced", False)
        ),
        note=note,
    )
