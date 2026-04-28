"""Read-only service for admin provider, route, pricing, and FX pages."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from slaif_gateway.db.models import FxRate, ModelRoute, PricingRule, ProviderConfig
from slaif_gateway.schemas.admin_catalog import (
    AdminFxRateDetail,
    AdminFxRateListRow,
    AdminPricingRuleDetail,
    AdminPricingRuleListRow,
    AdminPricingRuleSummary,
    AdminProviderDetail,
    AdminProviderListRow,
    AdminProviderSummary,
    AdminRouteDetail,
    AdminRouteListRow,
    AdminRouteSummary,
)


class AdminCatalogNotFoundError(Exception):
    """Raised when a requested admin catalog record is not found."""


class _ProviderConfigsAdminRepository(Protocol):
    async def list_provider_configs_for_admin(
        self,
        *,
        provider: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProviderConfig]: ...

    async def get_provider_config_for_admin_detail(self, provider_config_id: uuid.UUID) -> ProviderConfig | None: ...

    async def get_provider_config_by_provider(self, provider: str) -> ProviderConfig | None: ...


class _ModelRoutesAdminRepository(Protocol):
    async def list_model_routes_for_admin(
        self,
        *,
        provider: str | None = None,
        requested_model: str | None = None,
        match_type: str | None = None,
        enabled: bool | None = None,
        visible: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelRoute]: ...

    async def get_model_route_for_admin_detail(self, route_id: uuid.UUID) -> ModelRoute | None: ...


class _PricingRulesAdminRepository(Protocol):
    async def list_pricing_rules_for_admin(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        currency: str | None = None,
        enabled: bool | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PricingRule]: ...

    async def get_pricing_rule_for_admin_detail(self, pricing_rule_id: uuid.UUID) -> PricingRule | None: ...


class _FxRatesAdminRepository(Protocol):
    async def list_fx_rates_for_admin(
        self,
        *,
        base_currency: str | None = None,
        quote_currency: str | None = None,
        source: str | None = None,
        active: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FxRate]: ...

    async def get_fx_rate_for_admin_detail(self, fx_rate_id: uuid.UUID) -> FxRate | None: ...


class AdminCatalogDashboardService:
    """Build safe read-only DTOs for admin catalog pages."""

    def __init__(
        self,
        *,
        provider_configs_repository: _ProviderConfigsAdminRepository,
        model_routes_repository: _ModelRoutesAdminRepository,
        pricing_rules_repository: _PricingRulesAdminRepository,
        fx_rates_repository: _FxRatesAdminRepository,
    ) -> None:
        self._providers = provider_configs_repository
        self._routes = model_routes_repository
        self._pricing = pricing_rules_repository
        self._fx_rates = fx_rates_repository

    async def list_providers(
        self,
        *,
        provider: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminProviderListRow]:
        rows = await self._providers.list_provider_configs_for_admin(
            provider=_clean_filter(provider),
            enabled=enabled,
            limit=limit,
            offset=offset,
        )
        return [_to_provider_list_row(row) for row in rows]

    async def get_provider_detail(self, provider_config_id: uuid.UUID) -> AdminProviderDetail:
        row = await self._providers.get_provider_config_for_admin_detail(provider_config_id)
        if row is None:
            raise AdminCatalogNotFoundError("Provider config not found")
        list_row = _to_provider_list_row(row)
        routes = await self._routes.list_model_routes_for_admin(provider=row.provider, limit=5, offset=0)
        pricing = await self._pricing.list_pricing_rules_for_admin(provider=row.provider, limit=5, offset=0)
        return AdminProviderDetail(
            **asdict(list_row),
            route_summaries=tuple(_to_route_summary(route) for route in routes),
            pricing_summaries=tuple(_to_pricing_summary(rule) for rule in pricing),
        )

    async def list_routes(
        self,
        *,
        provider: str | None = None,
        requested_model: str | None = None,
        match_type: str | None = None,
        enabled: bool | None = None,
        visible: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminRouteListRow]:
        rows = await self._routes.list_model_routes_for_admin(
            provider=_clean_filter(provider),
            requested_model=_clean_filter(requested_model),
            match_type=_clean_filter(match_type),
            enabled=enabled,
            visible=visible,
            limit=limit,
            offset=offset,
        )
        return [_to_route_list_row(row) for row in rows]

    async def get_route_detail(self, route_id: uuid.UUID) -> AdminRouteDetail:
        row = await self._routes.get_model_route_for_admin_detail(route_id)
        if row is None:
            raise AdminCatalogNotFoundError("Model route not found")
        list_row = _to_route_list_row(row)
        provider_config = await self._providers.get_provider_config_by_provider(row.provider)
        return AdminRouteDetail(
            **asdict(list_row),
            provider_config=_to_provider_summary(provider_config) if provider_config is not None else None,
        )

    async def list_pricing_rules(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        currency: str | None = None,
        enabled: bool | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminPricingRuleListRow]:
        timestamp = _utcnow(now)
        rows = await self._pricing.list_pricing_rules_for_admin(
            provider=_clean_filter(provider),
            model=_clean_filter(model),
            endpoint=_clean_filter(endpoint),
            currency=_normalize_currency_filter(currency),
            enabled=enabled,
            active=active,
            now=timestamp,
            limit=limit,
            offset=offset,
        )
        return [_to_pricing_list_row(row) for row in rows]

    async def get_pricing_rule_detail(self, pricing_rule_id: uuid.UUID) -> AdminPricingRuleDetail:
        row = await self._pricing.get_pricing_rule_for_admin_detail(pricing_rule_id)
        if row is None:
            raise AdminCatalogNotFoundError("Pricing rule not found")
        list_row = _to_pricing_list_row(row)
        provider_config = await self._providers.get_provider_config_by_provider(row.provider)
        return AdminPricingRuleDetail(
            **asdict(list_row),
            provider_config=_to_provider_summary(provider_config) if provider_config is not None else None,
        )

    async def list_fx_rates(
        self,
        *,
        base_currency: str | None = None,
        quote_currency: str | None = None,
        source: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[AdminFxRateListRow]:
        timestamp = _utcnow(now)
        rows = await self._fx_rates.list_fx_rates_for_admin(
            base_currency=_normalize_currency_filter(base_currency),
            quote_currency=_normalize_currency_filter(quote_currency),
            source=_clean_filter(source),
            active=active,
            now=timestamp,
            limit=limit,
            offset=offset,
        )
        return [_to_fx_rate_list_row(row) for row in rows]

    async def get_fx_rate_detail(self, fx_rate_id: uuid.UUID) -> AdminFxRateDetail:
        row = await self._fx_rates.get_fx_rate_for_admin_detail(fx_rate_id)
        if row is None:
            raise AdminCatalogNotFoundError("FX rate not found")
        return AdminFxRateDetail(**asdict(_to_fx_rate_list_row(row)))


def _to_provider_list_row(row: ProviderConfig) -> AdminProviderListRow:
    return AdminProviderListRow(
        id=row.id,
        provider=row.provider,
        display_name=row.display_name,
        kind=row.kind,
        enabled=row.enabled,
        base_url=row.base_url,
        api_key_env_var=row.api_key_env_var,
        timeout_seconds=row.timeout_seconds,
        max_retries=row.max_retries,
        notes=row.notes,
        route_count=None,
        pricing_rule_count=None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_provider_summary(row: ProviderConfig) -> AdminProviderSummary:
    return AdminProviderSummary(
        id=row.id,
        provider=row.provider,
        display_name=row.display_name,
        enabled=row.enabled,
        base_url=row.base_url,
        api_key_env_var=row.api_key_env_var,
    )


def _to_route_list_row(row: ModelRoute) -> AdminRouteListRow:
    return AdminRouteListRow(
        id=row.id,
        requested_model=row.requested_model,
        match_type=row.match_type,
        endpoint=row.endpoint,
        provider=row.provider,
        upstream_model=row.upstream_model,
        priority=row.priority,
        enabled=row.enabled,
        visible_in_models=row.visible_in_models,
        supports_streaming=row.supports_streaming,
        capabilities_summary=_json_summary(row.capabilities),
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_route_summary(row: ModelRoute) -> AdminRouteSummary:
    return AdminRouteSummary(
        id=row.id,
        requested_model=row.requested_model,
        match_type=row.match_type,
        endpoint=row.endpoint,
        upstream_model=row.upstream_model,
        priority=row.priority,
        enabled=row.enabled,
        visible_in_models=row.visible_in_models,
    )


def _to_pricing_list_row(row: PricingRule) -> AdminPricingRuleListRow:
    return AdminPricingRuleListRow(
        id=row.id,
        provider=row.provider,
        upstream_model=row.upstream_model,
        endpoint=row.endpoint,
        currency=row.currency,
        input_price_per_1m=row.input_price_per_1m,
        cached_input_price_per_1m=row.cached_input_price_per_1m,
        output_price_per_1m=row.output_price_per_1m,
        reasoning_price_per_1m=row.reasoning_price_per_1m,
        request_price=row.request_price,
        enabled=row.enabled,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        source_url=row.source_url,
        notes=row.notes,
        metadata_summary=_json_summary(row.pricing_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_pricing_summary(row: PricingRule) -> AdminPricingRuleSummary:
    return AdminPricingRuleSummary(
        id=row.id,
        upstream_model=row.upstream_model,
        endpoint=row.endpoint,
        currency=row.currency,
        enabled=row.enabled,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
    )


def _to_fx_rate_list_row(row: FxRate) -> AdminFxRateListRow:
    return AdminFxRateListRow(
        id=row.id,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        source=row.source,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        created_at=row.created_at,
    )


def _json_summary(value: dict[str, object] | None) -> str:
    if not value:
        return "None"
    keys = sorted(str(key) for key in value if str(key).strip())
    if not keys:
        return "None"
    visible = ", ".join(keys[:5])
    if len(keys) > 5:
        return f"{visible}, +{len(keys) - 5} more"
    return visible


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_currency_filter(value: str | None) -> str | None:
    cleaned = _clean_filter(value)
    return cleaned.upper() if cleaned else None


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)
