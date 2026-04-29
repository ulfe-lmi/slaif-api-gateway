"""Repository helpers for model_routes table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute


class ModelRoutesRepository:
    """Encapsulates CRUD-style access for ModelRoute rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_model_route(
        self,
        *,
        requested_model: str,
        provider: str,
        upstream_model: str,
        match_type: str = "exact",
        endpoint: str = "/v1/chat/completions",
        priority: int = 100,
        enabled: bool = True,
        visible_in_models: bool = True,
        supports_streaming: bool = True,
        capabilities: dict[str, object] | None = None,
        notes: str | None = None,
    ) -> ModelRoute:
        row = ModelRoute(
            requested_model=requested_model,
            provider=provider,
            upstream_model=upstream_model,
            match_type=match_type,
            endpoint=endpoint,
            priority=priority,
            enabled=enabled,
            visible_in_models=visible_in_models,
            supports_streaming=supports_streaming,
            capabilities=capabilities or {},
            notes=notes,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_model_route_by_id(self, route_id: uuid.UUID) -> ModelRoute | None:
        return await self._session.get(ModelRoute, route_id)

    async def list_model_routes(
        self,
        *,
        endpoint: str | None = None,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ModelRoute]:
        statement: Select[tuple[ModelRoute]] = select(ModelRoute)
        if endpoint is not None:
            statement = statement.where(ModelRoute.endpoint == endpoint)
        if provider is not None:
            statement = statement.where(ModelRoute.provider == provider)

        statement = (
            statement.order_by(ModelRoute.priority.asc(), ModelRoute.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

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
    ) -> list[ModelRoute]:
        statement: Select[tuple[ModelRoute]] = select(ModelRoute)
        if provider is not None:
            statement = statement.where(ModelRoute.provider == provider)
        if requested_model is not None:
            statement = statement.where(ModelRoute.requested_model.ilike(f"%{requested_model}%"))
        if match_type is not None:
            statement = statement.where(ModelRoute.match_type == match_type)
        if enabled is not None:
            statement = statement.where(ModelRoute.enabled == enabled)
        if visible is not None:
            statement = statement.where(ModelRoute.visible_in_models == visible)

        statement = (
            statement.order_by(ModelRoute.priority.asc(), ModelRoute.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_model_route_for_admin_detail(self, route_id: uuid.UUID) -> ModelRoute | None:
        return await self._session.get(ModelRoute, route_id)

    async def list_enabled_model_routes(self, *, endpoint: str | None = None) -> list[ModelRoute]:
        statement: Select[tuple[ModelRoute]] = select(ModelRoute).where(ModelRoute.enabled.is_(True))
        if endpoint is not None:
            statement = statement.where(ModelRoute.endpoint == endpoint)

        statement = statement.order_by(ModelRoute.priority.asc(), ModelRoute.created_at.asc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_visible_model_routes(self, *, endpoint: str | None = None) -> list[ModelRoute]:
        statement: Select[tuple[ModelRoute]] = select(ModelRoute).where(
            ModelRoute.enabled.is_(True), ModelRoute.visible_in_models.is_(True)
        )
        if endpoint is not None:
            statement = statement.where(ModelRoute.endpoint == endpoint)

        statement = statement.order_by(ModelRoute.priority.asc(), ModelRoute.created_at.asc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_model_route_enabled(self, route_id: uuid.UUID, *, enabled: bool) -> bool:
        row = await self.get_model_route_by_id(route_id)
        if row is None:
            return False
        row.enabled = enabled
        await self._session.flush()
        return True

    async def update_model_route_priority(self, route_id: uuid.UUID, *, priority: int) -> bool:
        row = await self.get_model_route_by_id(route_id)
        if row is None:
            return False
        row.priority = priority
        await self._session.flush()
        return True

    async def update_model_route_metadata(
        self,
        route_id: uuid.UUID,
        *,
        requested_model: str | None = None,
        match_type: str | None = None,
        endpoint: str | None = None,
        provider: str | None = None,
        upstream_model: str | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
        visible_in_models: bool | None = None,
        supports_streaming: bool | None = None,
        capabilities: dict[str, object] | None = None,
        notes: str | None = None,
    ) -> bool:
        row = await self.get_model_route_by_id(route_id)
        if row is None:
            return False

        if requested_model is not None:
            row.requested_model = requested_model
        if match_type is not None:
            row.match_type = match_type
        if endpoint is not None:
            row.endpoint = endpoint
        if provider is not None:
            row.provider = provider
        if upstream_model is not None:
            row.upstream_model = upstream_model
        if priority is not None:
            row.priority = priority
        if enabled is not None:
            row.enabled = enabled
        if visible_in_models is not None:
            row.visible_in_models = visible_in_models
        if supports_streaming is not None:
            row.supports_streaming = supports_streaming
        if capabilities is not None:
            row.capabilities = capabilities
        if notes is not None:
            row.notes = notes

        await self._session.flush()
        return True

    async def find_candidate_routes_for_model(self, requested_model: str) -> list[ModelRoute]:
        statement: Select[tuple[ModelRoute]] = (
            select(ModelRoute)
            .where(
                ModelRoute.enabled.is_(True),
                or_(
                    (ModelRoute.match_type == "exact") & (ModelRoute.requested_model == requested_model),
                    (ModelRoute.match_type == "prefix")
                    & (literal(requested_model).like(ModelRoute.requested_model + "%")),
                    (ModelRoute.match_type == "glob")
                    & (literal(requested_model).like(func.replace(ModelRoute.requested_model, "*", "%"))),
                ),
            )
            .order_by(ModelRoute.priority.asc(), ModelRoute.created_at.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())
