"""Atomic setup workflow for discovered generic OpenAI-compatible models."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute, PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.model_route_service import ModelRouteService
from slaif_gateway.services.openai_compatible_discovery import (
    DiscoveredModels,
    OpenAICompatibleDiscoveryService,
)
from slaif_gateway.services.pricing_rule_service import PricingRuleService

CHAT_TEXT_PRESET = "chat_text_v1"
RESPONSES_TEXT_PRESET = "responses_text_v1"
CHAT_AND_RESPONSES_TEXT_PRESET = "chat_and_responses_text_v1"
SETUP_PRESETS = frozenset(
    {CHAT_TEXT_PRESET, RESPONSES_TEXT_PRESET, CHAT_AND_RESPONSES_TEXT_PRESET}
)
LOCAL_ZERO_PRICING = "local_zero"
EXPLICIT_PRICING = "explicit"
PRICING_MODES = frozenset({LOCAL_ZERO_PRICING, EXPLICIT_PRICING})
MAX_SELECTED_MODELS = 100
MAX_PUBLIC_MODEL_ID_BYTES = 255

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9._:/-]{0,253}[a-z0-9])?$")


class SetupError(ValueError):
    """Safe setup validation or conflict failure."""


@dataclass(frozen=True, slots=True)
class SetupRequest:
    """Validated scalar choices supplied by an operator confirmation step."""

    provider: str
    selected_models: tuple[str, ...]
    preset: str
    public_model_ids: Mapping[str, str] | None = None
    priority: int = 100
    visible_in_models: bool = True
    streaming: bool = False
    local_function_tools: bool = False
    confirm_enable_unqualified: bool = False
    pricing_mode: str = LOCAL_ZERO_PRICING
    input_price_per_1m: str | Decimal | None = None
    output_price_per_1m: str | Decimal | None = None
    reason: str = ""
    actor_admin_id: Any = None


@dataclass(frozen=True, slots=True)
class SetupResult:
    """Safe summary of rows created by one atomic setup transaction."""

    provider: str
    models: tuple[str, ...]
    routes: tuple[ModelRoute, ...]
    pricing_rules: tuple[PricingRule, ...]
    enabled: bool


class OpenAICompatibleSetupService:
    """Re-probe, validate, and create route/pricing rows without committing."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider_configs_repository: ProviderConfigsRepository,
        model_routes_repository: ModelRoutesRepository,
        pricing_rules_repository: PricingRulesRepository,
        audit_repository: AuditRepository,
        discovery_service: OpenAICompatibleDiscoveryService,
    ) -> None:
        self._session = session
        self._providers = provider_configs_repository
        self._routes = model_routes_repository
        self._pricing = pricing_rules_repository
        self._audit = audit_repository
        self._discovery = discovery_service

    async def execute(self, request: SetupRequest) -> SetupResult:
        normalized = _normalize_request(request)
        provider = await self._providers.get_provider_config_by_provider(normalized.provider)
        if provider is None:
            raise SetupError("Configured provider was not found")

        fresh = await self._discovery.discover(normalized.provider)
        _require_selected_models(fresh, normalized.selected_models)
        public_ids = _public_ids(provider.provider, normalized)
        endpoints = _preset_endpoints(normalized.preset)
        await self._preflight_conflicts(
            provider.provider,
            normalized,
            public_ids,
            endpoints,
        )

        enabled = normalized.confirm_enable_unqualified
        route_service = ModelRouteService(
            model_routes_repository=self._routes,
            audit_repository=self._audit,
        )
        pricing_service = PricingRuleService(
            pricing_rules_repository=self._pricing,
            audit_repository=self._audit,
        )
        input_price, output_price, metadata = _pricing_values(normalized)
        routes: list[ModelRoute] = []
        pricing_rules: list[PricingRule] = []
        now = datetime.now(UTC)
        for upstream_model in normalized.selected_models:
            for endpoint in endpoints:
                capabilities = _capabilities(
                    endpoint,
                    streaming=normalized.streaming,
                    local_function_tools=normalized.local_function_tools,
                )
                route = await route_service.create_model_route(
                    requested_model=public_ids[upstream_model],
                    match_type="exact",
                    provider=provider.provider,
                    upstream_model=upstream_model,
                    priority=normalized.priority,
                    visible_in_models=normalized.visible_in_models,
                    enabled=enabled,
                    notes="OpenAI-compatible setup; qualification remains operator-owned",
                    endpoint=endpoint,
                    supports_streaming=normalized.streaming,
                    capabilities=capabilities,
                    actor_admin_id=normalized.actor_admin_id,
                    reason=normalized.reason,
                )
                routes.append(route)
                pricing_rules.append(
                    await pricing_service.create_pricing_rule(
                        provider=provider.provider,
                        model=upstream_model,
                        endpoint=endpoint,
                        currency="EUR",
                        input_price_per_1m=input_price,
                        output_price_per_1m=output_price,
                        cached_input_price_per_1m=None,
                        reasoning_price_per_1m=None,
                        request_price=None,
                        valid_from=now,
                        valid_until=None,
                        source_url=None,
                        notes="Operator-confirmed local pricing; not provider invoice truth",
                        enabled=enabled,
                        pricing_metadata=metadata,
                        actor_admin_id=normalized.actor_admin_id,
                        reason=normalized.reason,
                    )
                )

        await self._audit.add_audit_log(
            action="openai_compatible_setup_executed",
            entity_type="provider_config",
            entity_id=provider.id,
            admin_user_id=normalized.actor_admin_id,
            new_values={
                "provider": provider.provider,
                "preset": normalized.preset,
                "model_count": len(normalized.selected_models),
                "route_count": len(routes),
                "pricing_count": len(pricing_rules),
                "enabled": enabled,
                "pricing_mode": normalized.pricing_mode,
            },
            note=normalized.reason,
        )
        return SetupResult(
            provider=provider.provider,
            models=normalized.selected_models,
            routes=tuple(routes),
            pricing_rules=tuple(pricing_rules),
            enabled=enabled,
        )

    async def _preflight_conflicts(
        self,
        provider: str,
        request: SetupRequest,
        public_ids: Mapping[str, str],
        endpoints: Sequence[str],
    ) -> None:
        routes = await self._routes.list_model_routes(provider=provider, limit=10_000)
        route_keys = {
            (row.requested_model, row.endpoint)
            for row in routes
            if row.match_type == "exact"
        }
        pricing: list[PricingRule] = []
        for model in request.selected_models:
            pricing.extend(
                await self._pricing.list_pricing_rules_for_provider_model(
                    provider=provider,
                    upstream_model=model,
                )
            )
        pricing_keys = {
            (row.upstream_model, row.endpoint)
            for row in pricing
            if row.enabled
        }
        for model in request.selected_models:
            for endpoint in endpoints:
                if (public_ids[model], endpoint) in route_keys:
                    raise SetupError("Setup conflicts with an existing exact model route")
                if (model, endpoint) in pricing_keys:
                    raise SetupError("Setup conflicts with an active pricing rule")


def _normalize_request(request: SetupRequest) -> SetupRequest:
    provider = _required_scalar(request.provider, "Provider").lower()
    selected = tuple(request.selected_models)
    if not selected or len(selected) > MAX_SELECTED_MODELS:
        raise SetupError("Select between one and 100 models")
    if len(set(selected)) != len(selected):
        raise SetupError("Selected models must be unique")
    for model in selected:
        _validate_identifier(model, "Selected model")
    if request.preset not in SETUP_PRESETS:
        raise SetupError("Unknown setup preset")
    if request.pricing_mode not in PRICING_MODES:
        raise SetupError("Unknown pricing mode")
    if request.priority < 0:
        raise SetupError("Priority must be non-negative")
    reason = _required_scalar(request.reason, "Audit reason")
    if len(reason.encode("utf-8")) > 1024:
        raise SetupError("Audit reason is too long")
    if request.pricing_mode == EXPLICIT_PRICING:
        _decimal(request.input_price_per_1m, "Input price")
        _decimal(request.output_price_per_1m, "Output price")
    return SetupRequest(
        provider=provider,
        selected_models=selected,
        preset=request.preset,
        public_model_ids=request.public_model_ids,
        priority=request.priority,
        visible_in_models=bool(request.visible_in_models),
        streaming=bool(request.streaming),
        local_function_tools=bool(request.local_function_tools),
        confirm_enable_unqualified=bool(request.confirm_enable_unqualified),
        pricing_mode=request.pricing_mode,
        input_price_per_1m=request.input_price_per_1m,
        output_price_per_1m=request.output_price_per_1m,
        reason=reason,
        actor_admin_id=request.actor_admin_id,
    )


def _public_ids(provider: str, request: SetupRequest) -> dict[str, str]:
    supplied = request.public_model_ids or {}
    result: dict[str, str] = {}
    for upstream in request.selected_models:
        public = supplied.get(upstream, f"{provider}/{upstream}")
        _validate_identifier(public, "Public model")
        result[upstream] = public
    if len(set(result.values())) != len(result):
        raise SetupError("Public model identifiers must be unique")
    return result


def _require_selected_models(discovered: DiscoveredModels, selected: Sequence[str]) -> None:
    available = set(discovered.models)
    if any(model not in available for model in selected):
        raise SetupError("A selected model was not present in the fresh discovery result")


def _preset_endpoints(preset: str) -> tuple[str, ...]:
    if preset == CHAT_TEXT_PRESET:
        return ("/v1/chat/completions",)
    if preset == RESPONSES_TEXT_PRESET:
        return ("/v1/responses",)
    return ("/v1/chat/completions", "/v1/responses")


def _capabilities(endpoint: str, *, streaming: bool, local_function_tools: bool) -> dict[str, object]:
    if endpoint == "/v1/chat/completions":
        return {
            "chat_completions": {
                "chat_text": True,
                "chat_streaming": streaming,
                "chat_function_tools": local_function_tools,
                "chat_legacy_functions": local_function_tools,
                "chat_custom_tools": False,
                "chat_structured_outputs": False,
                "chat_json_mode": False,
                "chat_logprobs": False,
                "chat_reasoning_usage": False,
                "chat_cached_input_usage": False,
                "hosted_web_search": False,
                "hosted_file_search": False,
                "hosted_code_interpreter": False,
                "hosted_computer_use": False,
                "hosted_image_generation": False,
                "hosted_tool_search": False,
                "external_mcp_connectors": False,
                "chat_image_inputs": False,
                "chat_multimodal": False,
                "chat_audio": False,
                "chat_file_inputs": False,
                "chat_audio_inputs": False,
                "chat_audio_outputs": False,
                "chat_service_tier_non_default": False,
                "chat_multiple_choices": False,
            }
        }
    return {
        "responses": {
            "text": True,
            "stateless": True,
            "streaming": streaming,
            "tools": False,
            "function_tools": local_function_tools,
            "custom_tools": False,
            "image_input": False,
            "file_input": False,
            "input_token_count": False,
            "stored_responses": False,
            "previous_response_id": False,
            "list_input_items": False,
            "compact": False,
            "conversations": False,
            "conversation_items": False,
            "multimodal": False,
            "storage": False,
            "background": False,
            "json_mode": False,
            "structured_outputs": False,
            "codex_request_envelope": False,
            "codex_client_tools": False,
            "codex_streaming_tool_events": False,
            "codex_encrypted_reasoning_replay": False,
            "codex_compaction": False,
        }
    }


def _pricing_values(request: SetupRequest) -> tuple[Decimal, Decimal, dict[str, str]]:
    if request.pricing_mode == LOCAL_ZERO_PRICING:
        return Decimal("0"), Decimal("0"), {"pricing_basis": "operator_confirmed_local_zero"}
    return (
        _decimal(request.input_price_per_1m, "Input price"),
        _decimal(request.output_price_per_1m, "Output price"),
        {"pricing_basis": "operator_confirmed_explicit_local_pricing"},
    )


def _decimal(value: str | Decimal | None, label: str) -> Decimal:
    if value is None:
        raise SetupError(f"{label} is required")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise SetupError(f"{label} must be a finite non-negative decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise SetupError(f"{label} must be a finite non-negative decimal")
    return parsed


def _required_scalar(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SetupError(f"{label} is required")
    return value.strip()


def _validate_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SetupError(f"{label} is invalid")
    if len(value.encode("utf-8")) > MAX_PUBLIC_MODEL_ID_BYTES:
        raise SetupError(f"{label} is too long")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SetupError(f"{label} is invalid")
    if not _SLUG.fullmatch(value) or "://" in value or "@" in value:
        raise SetupError(f"{label} is unsafe")
    lowered = value.lower()
    if lowered.startswith(("sk-", "sk_", "sk-or-")) or any(
        token in lowered for token in ("bearer", "cookie", "secret", "password", "api_key", "token")
    ):
        raise SetupError(f"{label} is unsafe")
