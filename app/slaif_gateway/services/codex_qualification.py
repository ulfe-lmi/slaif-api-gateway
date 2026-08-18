"""Strict, safe Codex protocol qualification and profile-v2 rendering."""

from __future__ import annotations

import ipaddress
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatchcase
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from slaif_gateway.services.responses_route_capabilities import (
    parse_codex_compaction_compatible_route_ids,
    parse_codex_route_limits,
)
from slaif_gateway.utils.redaction import redact_text

CODEX_QUALIFICATION_KEY = "codex_qualification"
CODEX_MODEL = "gpt-5.6-sol"
CODEX_CLI_VERSION = "0.147.0"
CODEX_PROFILE_VERSION = 1
CODEX_EVIDENCE_PROFILE = "api-key-responses-v1"
CODEX_PROFILE_NAME = "slaif"
CODEX_PROVIDER_NAME = "slaif"
CODEX_FIXTURE_SHA256 = "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
CODEX_RESPONSES_ENDPOINT = "/v1/responses"
CODEX_COMPACT_ENDPOINT = "/v1/responses/compact"

CODEX_QUALIFICATION_METADATA: dict[str, object] = {
    "support_level": "protocol_qualified",
    "profile_version": CODEX_PROFILE_VERSION,
    "cli_version": CODEX_CLI_VERSION,
    "model": CODEX_MODEL,
    "profile": CODEX_EVIDENCE_PROFILE,
    "catalog_source": "bundled",
    "fixture_sha256": CODEX_FIXTURE_SHA256,
    "evidence_date": "2026-08-18",
    "wire_api": "responses",
    "provider_display_name": "OpenAI",
    "remote_compaction": "v1",
    "remote_compaction_v2": False,
    "real_provider_e2e": False,
}

CODEX_RESPONSES_POLICY: dict[str, object] = {
    "version": 1,
    "allowed_capabilities": [
        "codex_request_envelope",
        "codex_client_tools",
        "codex_streaming_tool_events",
        "codex_encrypted_reasoning_replay",
        "codex_compaction",
    ],
    "allowed_local_tool_types": ["function", "custom"],
}

_CODEX_GATES = (
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
    "codex_compaction",
)
_CODEX_ACCOUNTING_REQUIRED = frozenset(
    {
        "long_context_threshold_tokens",
        "long_context_input_multiplier",
        "long_context_output_multiplier",
    }
)
_CODEX_ACCOUNTING_CACHE_FIELDS = frozenset(
    {"cache_write_input_price_per_1m", "cache_write_input_multiplier"}
)
_EXACT_PILOT_ENDPOINTS = frozenset({"/v1/models", CODEX_RESPONSES_ENDPOINT, CODEX_COMPACT_ENDPOINT})


class _RoutesRepository(Protocol):
    async def list_model_routes(self, *, limit: int = 100, offset: int = 0) -> list[object]: ...


class _ProvidersRepository(Protocol):
    async def list_provider_configs(
        self, *, enabled: bool | None = None, limit: int = 100, offset: int = 0
    ) -> list[object]: ...


class _PricingRepository(Protocol):
    async def find_active_pricing_rule(
        self,
        *,
        provider: str,
        upstream_model: str,
        endpoint: str,
        at_time: datetime,
    ) -> object | None: ...


class _FxRepository(Protocol):
    async def find_latest_rate(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        at_time: datetime | None = None,
    ) -> object | None: ...


@dataclass(frozen=True, slots=True)
class CodexQualificationResult:
    """Low-cardinality qualification result safe for admin and CLI output."""

    state: str
    requested_model: str
    provider: str
    endpoint: str
    route_id: uuid.UUID
    paired_route_id: uuid.UUID | None
    reason_codes: tuple[str, ...]
    profile_version: int | None = None
    cli_version: str | None = None
    profile: str | None = None
    catalog_source: str | None = None
    wire_api: str | None = None
    real_provider_e2e: bool | None = None

    @property
    def ready(self) -> bool:
        return self.state == "protocol_qualified"

    @property
    def badge(self) -> str:
        if self.ready:
            return "Protocol-qualified: Codex 0.147.0 / gpt-5.6-sol / profile v1"
        if self.state == "not_declared":
            return "Not declared"
        return "Invalid/not ready"

    def to_safe_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["route_id"] = str(self.route_id)
        payload["paired_route_id"] = (
            str(self.paired_route_id) if self.paired_route_id is not None else None
        )
        payload["reason_codes"] = list(self.reason_codes)
        payload["ready"] = self.ready
        return payload


@dataclass(frozen=True, slots=True)
class CodexProfileArtifacts:
    """Two separate credential-free Codex profile-v2 artifacts."""

    base_config_toml: str
    profile_config_toml: str
    base_config_target: str = "$CODEX_HOME/config.toml"
    profile_config_target: str = "$CODEX_HOME/slaif.config.toml"
    profile: str = CODEX_PROFILE_NAME
    model: str = CODEX_MODEL
    provider: str = CODEX_PROVIDER_NAME
    invocation: str = "codex --profile slaif"

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "base_config_target": self.base_config_target,
            "base_config_mode": "merge_fragment",
            "base_config_toml": self.base_config_toml,
            "profile_config_target": self.profile_config_target,
            "profile_config_mode": "complete_file",
            "profile_config_toml": self.profile_config_toml,
            "profile": self.profile,
            "model": self.model,
            "provider": self.provider,
            "invocation": self.invocation,
        }


class CodexQualificationService:
    """Inspect local route/provider/pricing state without mutating it."""

    def __init__(
        self,
        *,
        provider_configs_repository: _ProvidersRepository,
        model_routes_repository: _RoutesRepository,
        pricing_rules_repository: _PricingRepository,
        fx_rates_repository: _FxRepository,
    ) -> None:
        self._providers = provider_configs_repository
        self._routes = model_routes_repository
        self._pricing = pricing_rules_repository
        self._fx = fx_rates_repository

    async def inspect(self, *, now: datetime | None = None) -> list[CodexQualificationResult]:
        timestamp = _aware_time(now)
        routes = await self._routes.list_model_routes(limit=1000, offset=0)
        providers = await self._providers.list_provider_configs(limit=1000, offset=0)
        provider_by_name = {
            str(getattr(row, "provider", "")): row
            for row in providers
            if str(getattr(row, "provider", ""))
        }
        route_by_id = {
            route_id: row for row in routes if (route_id := _route_uuid(row)) is not None
        }
        results = [
            await self._inspect_route(
                row,
                all_routes=routes,
                route_by_id=route_by_id,
                provider_by_name=provider_by_name,
                now=timestamp,
            )
            for row in routes
        ]
        return sorted(
            results,
            key=lambda result: (
                result.requested_model,
                result.provider,
                result.endpoint,
                str(result.route_id),
            ),
        )

    async def ready_responses_profile(
        self,
        *,
        provider: str | None = None,
        now: datetime | None = None,
    ) -> CodexQualificationResult:
        candidates = [
            result
            for result in await self.inspect(now=now)
            if result.endpoint == CODEX_RESPONSES_ENDPOINT
            and result.requested_model == CODEX_MODEL
            and result.ready
            and (provider is None or result.provider == provider)
        ]
        if len(candidates) != 1:
            raise ValueError("Exactly one ready Codex protocol route pair is required.")
        return candidates[0]

    async def _inspect_route(
        self,
        route: object,
        *,
        all_routes: Sequence[object],
        route_by_id: Mapping[uuid.UUID, object],
        provider_by_name: Mapping[str, object],
        now: datetime,
    ) -> CodexQualificationResult:
        route_id = _required_route_uuid(route)
        requested_model = str(getattr(route, "requested_model", "") or "")
        provider = str(getattr(route, "provider", "") or "")
        endpoint = str(getattr(route, "endpoint", "") or "")
        metadata_state = parse_codex_qualification_metadata(getattr(route, "capabilities", None))
        if metadata_state == "not_declared":
            return _result(
                route_id=route_id,
                requested_model=requested_model,
                provider=provider,
                endpoint=endpoint,
                state="not_declared",
                reasons=("codex_qualification_not_declared",),
            )
        if metadata_state == "invalid":
            return _result(
                route_id=route_id,
                requested_model=requested_model,
                provider=provider,
                endpoint=endpoint,
                state="invalid",
                reasons=("codex_qualification_invalid",),
                include_profile=True,
            )

        reasons: list[str] = []
        if not bool(getattr(route, "enabled", False)):
            reasons.append("route_disabled")
        if endpoint not in {CODEX_RESPONSES_ENDPOINT, CODEX_COMPACT_ENDPOINT}:
            reasons.append("endpoint_invalid")
        if str(getattr(route, "match_type", "") or "") != "exact":
            reasons.append("match_type_invalid")
        if requested_model != CODEX_MODEL:
            reasons.append("requested_model_invalid")
        if str(getattr(route, "upstream_model", "") or "") != CODEX_MODEL:
            reasons.append("upstream_model_invalid")
        if not _is_runtime_selected_route(route, all_routes=all_routes):
            reasons.append("route_not_selected")
        capabilities = getattr(route, "capabilities", None)
        reasons.extend(_route_capability_reasons(route, capabilities=capabilities))

        compatible_ids: frozenset[uuid.UUID] = frozenset()
        try:
            compatible_ids = parse_codex_compaction_compatible_route_ids(capabilities)
        except Exception:
            reasons.append("compatible_route_ids_invalid")
        paired_route: object | None = None
        paired_route_id: uuid.UUID | None = None
        if len(compatible_ids) != 1:
            reasons.append("paired_route_not_exact")
        else:
            paired_route_id = next(iter(compatible_ids))
            paired_route = route_by_id.get(paired_route_id)
            if paired_route is None:
                reasons.append("paired_route_missing")
            else:
                reasons.extend(
                    _paired_route_reasons(
                        route,
                        paired_route,
                        expected_endpoint=(
                            CODEX_COMPACT_ENDPOINT
                            if endpoint == CODEX_RESPONSES_ENDPOINT
                            else CODEX_RESPONSES_ENDPOINT
                        ),
                    )
                )
                if not _is_runtime_selected_route(paired_route, all_routes=all_routes):
                    reasons.append("paired_route_not_selected")

        provider_row = provider_by_name.get(provider)
        if provider_row is None:
            reasons.append("provider_missing")
        elif not bool(getattr(provider_row, "enabled", False)):
            reasons.append("provider_disabled")

        pricing_routes = [route]
        if paired_route is not None:
            pricing_routes.append(paired_route)
        for pricing_route in pricing_routes:
            pricing_endpoint = str(getattr(pricing_route, "endpoint", "") or "")
            pricing_reason_suffix = (
                "responses" if pricing_endpoint == CODEX_RESPONSES_ENDPOINT else "compact"
            )
            pricing = await self._pricing.find_active_pricing_rule(
                provider=provider,
                upstream_model=CODEX_MODEL,
                endpoint=pricing_endpoint,
                at_time=now,
            )
            if pricing is None:
                reasons.append(f"pricing_missing_{pricing_reason_suffix}")
                continue
            if not _pricing_complete(pricing):
                reasons.append(f"pricing_invalid_{pricing_reason_suffix}")
                continue
            currency = str(getattr(pricing, "currency", "") or "").strip().upper()
            if currency != "EUR":
                fx = await self._fx.find_latest_rate(
                    base_currency=currency,
                    quote_currency="EUR",
                    at_time=now,
                )
                if fx is None or not _positive_decimal(getattr(fx, "rate", None)):
                    reasons.append(f"fx_missing_{pricing_reason_suffix}")

        deduplicated = tuple(dict.fromkeys(reasons))
        return _result(
            route_id=route_id,
            requested_model=requested_model,
            provider=provider,
            endpoint=endpoint,
            paired_route_id=paired_route_id,
            state="not_ready" if deduplicated else "protocol_qualified",
            reasons=deduplicated,
            include_profile=True,
        )


def parse_codex_qualification_metadata(capabilities: object) -> str:
    """Return declared state without coercion or model-name inference."""

    if not isinstance(capabilities, Mapping) or CODEX_QUALIFICATION_KEY not in capabilities:
        return "not_declared"
    raw = capabilities.get(CODEX_QUALIFICATION_KEY)
    if not isinstance(raw, Mapping):
        return "invalid"
    if set(raw) != set(CODEX_QUALIFICATION_METADATA):
        return "invalid"
    for field, expected in CODEX_QUALIFICATION_METADATA.items():
        actual = raw.get(field)
        if type(actual) is not type(expected) or actual != expected:  # noqa: E721
            return "invalid"
    return "protocol_qualified"


def validate_codex_pilot_key_input(payload: object, *, confirmed: bool) -> None:
    """Validate the exact finite standard-key preset before key mutation."""

    if not confirmed:
        raise ValueError("Confirm Codex protocol pilot mode before creating this key.")
    if str(getattr(payload, "key_purpose", "")) != "standard":
        raise ValueError("Codex protocol pilot keys must be standard keys.")
    if bool(getattr(payload, "allow_all_models", False)) or bool(
        getattr(payload, "allow_all_endpoints", False)
    ):
        raise ValueError("Codex protocol pilot keys must not use allow-all policy.")
    providers = getattr(payload, "allowed_providers", None)
    if not isinstance(providers, list) or len(providers) != 1:
        raise ValueError("Codex protocol pilot keys require exactly one provider.")
    if list(getattr(payload, "allowed_models", [])) != [CODEX_MODEL]:
        raise ValueError("Codex protocol pilot keys require exactly model gpt-5.6-sol.")
    if frozenset(getattr(payload, "allowed_endpoints", [])) != _EXACT_PILOT_ENDPOINTS or len(
        getattr(payload, "allowed_endpoints", [])
    ) != len(_EXACT_PILOT_ENDPOINTS):
        raise ValueError("Codex protocol pilot keys require exactly the three pilot endpoints.")
    for field in ("request_limit_total", "token_limit_total"):
        value = getattr(payload, field, None)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Codex protocol pilot keys require positive finite hard limits.")
    cost = getattr(payload, "cost_limit_eur", None)
    if not _positive_decimal(cost):
        raise ValueError("Codex protocol pilot keys require positive finite hard limits.")
    reason = getattr(payload, "note", None)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Codex protocol pilot keys require an audit reason.")


def render_codex_profile(base_url: str) -> CodexProfileArtifacts:
    """Render two independent profile-v2 TOML documents without credentials."""

    canonical_url = validate_codex_gateway_base_url(base_url)
    encoded_url = json.dumps(canonical_url, ensure_ascii=True)
    base_config = (
        "[model_providers.slaif]\n"
        'name = "OpenAI"\n'
        f"base_url = {encoded_url}\n"
        'env_key = "OPENAI_API_KEY"\n'
        'wire_api = "responses"\n'
        "requires_openai_auth = false\n"
        "supports_websockets = false\n"
    )
    profile_config = (
        'model = "gpt-5.6-sol"\n'
        'model_provider = "slaif"\n'
        "\n[features]\n"
        "remote_compaction_v2 = false\n"
    )
    return CodexProfileArtifacts(
        base_config_toml=base_config,
        profile_config_toml=profile_config,
    )


def render_codex_profile_text(artifacts: CodexProfileArtifacts) -> str:
    """Render an explicitly non-combined human display of both artifacts."""

    return (
        "Merge this fragment into $CODEX_HOME/config.toml:\n"
        "--- base_config_toml (merge fragment) ---\n"
        f"{artifacts.base_config_toml}"
        "\nPlace this complete content in $CODEX_HOME/slaif.config.toml:\n"
        "--- profile_config_toml (complete file) ---\n"
        f"{artifacts.profile_config_toml}"
        "\nSet the gateway-issued key only in OPENAI_API_KEY.\n"
        "Run: codex --profile slaif\n"
    )


def validate_codex_gateway_base_url(value: str) -> str:
    """Validate and canonicalize a credential-free gateway `/v1` base URL."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Gateway base URL must be a canonical absolute URL ending in /v1.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Gateway base URL must not contain control characters.")
    if redact_text(value) != value:
        raise ValueError("Gateway base URL must not contain secret-looking material.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise ValueError("Gateway base URL must be an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Gateway base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Gateway base URL must not contain a query or fragment.")
    if "%" in parsed.path or "\\" in value:
        raise ValueError("Gateway base URL path must use canonical literal segments.")
    if parsed.path != "/v1" and not parsed.path.endswith("/v1"):
        raise ValueError("Gateway base URL path must end exactly /v1.")
    if (
        parsed.path.endswith("/v1/")
        or "//" in parsed.path
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ValueError("Gateway base URL path must be canonical and end exactly /v1.")
    if parsed.scheme == "http":
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError as exc:
            raise ValueError("HTTP is allowed only for numeric loopback URLs.") from exc
        if not address.is_loopback:
            raise ValueError("HTTP is allowed only for numeric loopback URLs.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Gateway base URL has an invalid port.") from exc
    hostname = parsed.hostname.lower()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))


def _route_capability_reasons(route: object, *, capabilities: object) -> list[str]:
    reasons: list[str] = []
    if not isinstance(capabilities, Mapping):
        return ["route_capabilities_invalid"]
    responses = capabilities.get("responses")
    if not isinstance(responses, Mapping):
        reasons.append("responses_capabilities_invalid")
    else:
        if any(responses.get(gate) is not True for gate in _CODEX_GATES):
            reasons.append("codex_gates_incomplete")
        endpoint = str(getattr(route, "endpoint", "") or "")
        if endpoint == CODEX_RESPONSES_ENDPOINT:
            if responses.get("stateless") is not True or responses.get("streaming") is not True:
                reasons.append("responses_route_capabilities_incomplete")
            if not bool(getattr(route, "visible_in_models", False)):
                reasons.append("responses_route_not_visible")
            if not bool(getattr(route, "supports_streaming", False)):
                reasons.append("responses_route_not_streaming")
        elif endpoint == CODEX_COMPACT_ENDPOINT and responses.get("compact") is not True:
            reasons.append("compact_route_capability_missing")
    try:
        parse_codex_route_limits(capabilities)
    except Exception:
        reasons.append("codex_limits_invalid")
    return reasons


def _is_runtime_selected_route(
    route: object,
    *,
    all_routes: Sequence[object],
) -> bool:
    """Mirror provider-constrained route ranking for the pinned exact model."""

    provider = str(getattr(route, "provider", "") or "")
    endpoint = str(getattr(route, "endpoint", "") or "")
    candidates = [
        candidate
        for candidate in all_routes
        if bool(getattr(candidate, "enabled", False))
        and str(getattr(candidate, "provider", "") or "") == provider
        and str(getattr(candidate, "endpoint", "") or "") == endpoint
        and _route_matches_codex_model(candidate)
        and _route_uuid(candidate) is not None
    ]
    if not candidates:
        return False
    selected = min(candidates, key=_route_rank)
    return _route_uuid(selected) == _route_uuid(route)


def _route_matches_codex_model(route: object) -> bool:
    pattern = str(getattr(route, "requested_model", "") or "")
    match_type = str(getattr(route, "match_type", "") or "")
    if match_type == "exact":
        return pattern == CODEX_MODEL
    if match_type == "prefix":
        return CODEX_MODEL.startswith(pattern)
    if match_type == "glob":
        return fnmatchcase(CODEX_MODEL, pattern)
    return False


def _route_rank(route: object) -> tuple[int, int, int, str]:
    match_type = str(getattr(route, "match_type", "") or "")
    specificity = {"exact": 0, "prefix": 1, "glob": 2}.get(match_type, 99)
    pattern = str(getattr(route, "requested_model", "") or "")
    priority = getattr(route, "priority", 100)
    if isinstance(priority, bool) or not isinstance(priority, int):
        priority = 100
    return (priority, specificity, -len(pattern), str(_route_uuid(route)))


def _paired_route_reasons(
    route: object,
    paired: object,
    *,
    expected_endpoint: str,
) -> list[str]:
    reasons: list[str] = []
    if str(getattr(paired, "endpoint", "") or "") != expected_endpoint:
        reasons.append("paired_endpoint_invalid")
    if not bool(getattr(paired, "enabled", False)):
        reasons.append("paired_route_disabled")
    for field in ("provider", "requested_model", "upstream_model"):
        if getattr(paired, field, None) != getattr(route, field, None):
            reasons.append(f"paired_{field}_mismatch")
    if str(getattr(paired, "match_type", "") or "") != "exact":
        reasons.append("paired_match_type_invalid")
    if parse_codex_qualification_metadata(getattr(paired, "capabilities", None)) != (
        "protocol_qualified"
    ):
        reasons.append("paired_qualification_invalid")
    reasons.extend(
        _route_capability_reasons(paired, capabilities=getattr(paired, "capabilities", None))
    )
    try:
        reciprocal = parse_codex_compaction_compatible_route_ids(
            getattr(paired, "capabilities", None)
        )
    except Exception:
        reasons.append("paired_compatible_route_ids_invalid")
    else:
        route_id = _required_route_uuid(route)
        if reciprocal != frozenset({route_id}):
            reasons.append("paired_route_not_reciprocal")
    return reasons


def _pricing_complete(row: object) -> bool:
    for field in (
        "input_price_per_1m",
        "cached_input_price_per_1m",
        "output_price_per_1m",
        "reasoning_price_per_1m",
    ):
        if not _non_negative_decimal(getattr(row, field, None)):
            return False
    currency = str(getattr(row, "currency", "") or "").strip().upper()
    if not currency or len(currency) != 3 or not currency.isalpha():
        return False
    metadata = getattr(row, "pricing_metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    accounting = metadata.get("codex_accounting")
    if not isinstance(accounting, Mapping):
        return False
    fields = set(accounting)
    cache_fields = fields.intersection(_CODEX_ACCOUNTING_CACHE_FIELDS)
    if len(cache_fields) != 1 or fields != _CODEX_ACCOUNTING_REQUIRED.union(cache_fields):
        return False
    threshold = accounting.get("long_context_threshold_tokens")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        return False
    for field in ("long_context_input_multiplier", "long_context_output_multiplier"):
        if not _positive_decimal_string(accounting.get(field)):
            return False
    cache_field = next(iter(cache_fields))
    if cache_field.endswith("multiplier"):
        return _positive_decimal_string(accounting.get(cache_field))
    return _non_negative_decimal_string(accounting.get(cache_field))


def _positive_decimal_string(value: object) -> bool:
    return isinstance(value, str) and _positive_decimal(value)


def _non_negative_decimal_string(value: object) -> bool:
    return isinstance(value, str) and _non_negative_decimal(value)


def _positive_decimal(value: object) -> bool:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return parsed.is_finite() and parsed > 0


def _non_negative_decimal(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return parsed.is_finite() and parsed >= 0


def _route_uuid(route: object) -> uuid.UUID | None:
    value = getattr(route, "id", None)
    return value if isinstance(value, uuid.UUID) else None


def _required_route_uuid(route: object) -> uuid.UUID:
    route_id = _route_uuid(route)
    if route_id is None:
        raise ValueError("Codex qualification route IDs must be UUIDs.")
    return route_id


def _result(
    *,
    route_id: uuid.UUID,
    requested_model: str,
    provider: str,
    endpoint: str,
    state: str,
    reasons: tuple[str, ...],
    paired_route_id: uuid.UUID | None = None,
    include_profile: bool = False,
) -> CodexQualificationResult:
    return CodexQualificationResult(
        state=state,
        requested_model=requested_model,
        provider=provider,
        endpoint=endpoint,
        route_id=route_id,
        paired_route_id=paired_route_id,
        reason_codes=reasons,
        profile_version=CODEX_PROFILE_VERSION if include_profile else None,
        cli_version=CODEX_CLI_VERSION if include_profile else None,
        profile=CODEX_EVIDENCE_PROFILE if include_profile else None,
        catalog_source="bundled" if include_profile else None,
        wire_api="responses" if include_profile else None,
        real_provider_e2e=False if include_profile else None,
    )


def _aware_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
