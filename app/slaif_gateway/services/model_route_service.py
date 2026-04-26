"""Service helpers for model route metadata."""

from __future__ import annotations

import uuid

from slaif_gateway.db.models import MATCH_TYPE_VALUES_MODEL_ROUTES, ModelRoute
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.record_errors import RecordNotFoundError


CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"


class ModelRouteService:
    """Small service layer for model route CLI operations."""

    def __init__(
        self,
        *,
        model_routes_repository: ModelRoutesRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._routes = model_routes_repository
        self._audit = audit_repository

    async def create_model_route(
        self,
        *,
        requested_model: str,
        match_type: str,
        provider: str,
        upstream_model: str | None,
        priority: int,
        visible_in_models: bool,
        enabled: bool,
        notes: str | None,
        endpoint: str = CHAT_COMPLETIONS_ENDPOINT,
    ) -> ModelRoute:
        normalized_requested_model = _required_text(requested_model, "Requested model")
        normalized_match_type = _normalize_match_type(match_type)
        if priority < 0:
            raise ValueError("Priority must be non-negative")

        row = await self._routes.create_model_route(
            requested_model=normalized_requested_model,
            match_type=normalized_match_type,
            endpoint=normalize_endpoint(endpoint),
            provider=_required_text(provider, "Provider"),
            upstream_model=_clean_optional(upstream_model) or normalized_requested_model,
            priority=priority,
            enabled=enabled,
            visible_in_models=visible_in_models,
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="model_route_created",
            entity_type="model_route",
            entity_id=row.id,
            new_values=_safe_audit_values(row),
        )
        return row

    async def list_model_routes(
        self,
        *,
        provider: str | None,
        enabled_only: bool,
        visible_only: bool,
        limit: int,
    ) -> list[ModelRoute]:
        rows = await self._routes.list_model_routes(
            provider=_clean_optional(provider),
            limit=limit,
        )
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        if visible_only:
            rows = [row for row in rows if row.visible_in_models]
        return rows

    async def get_model_route(self, route_id: uuid.UUID) -> ModelRoute:
        row = await self._routes.get_model_route_by_id(route_id)
        if row is None:
            raise RecordNotFoundError("Model route")
        return row

    async def set_model_route_enabled(self, route_id: uuid.UUID, *, enabled: bool) -> ModelRoute:
        row = await self.get_model_route(route_id)
        old_enabled = row.enabled
        updated = await self._routes.set_model_route_enabled(route_id, enabled=enabled)
        if not updated:
            raise RecordNotFoundError("Model route")
        row.enabled = enabled
        await self._audit.add_audit_log(
            action="model_route_enabled" if enabled else "model_route_disabled",
            entity_type="model_route",
            entity_id=row.id,
            old_values={"enabled": old_enabled},
            new_values={"enabled": enabled},
        )
        return row


def normalize_endpoint(value: str) -> str:
    endpoint = _required_text(value, "Endpoint")
    if endpoint == "chat.completions":
        return CHAT_COMPLETIONS_ENDPOINT
    return endpoint


def _normalize_match_type(value: str) -> str:
    normalized = _required_text(value, "Match type")
    if normalized not in MATCH_TYPE_VALUES_MODEL_ROUTES:
        allowed = ", ".join(MATCH_TYPE_VALUES_MODEL_ROUTES)
        raise ValueError(f"match_type must be one of: {allowed}")
    return normalized


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _safe_audit_values(row: ModelRoute) -> dict[str, object]:
    return {
        "requested_model": row.requested_model,
        "match_type": row.match_type,
        "endpoint": row.endpoint,
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "priority": row.priority,
        "enabled": row.enabled,
        "visible_in_models": row.visible_in_models,
        "supports_streaming": row.supports_streaming,
        "capabilities": row.capabilities,
        "notes": row.notes,
    }
