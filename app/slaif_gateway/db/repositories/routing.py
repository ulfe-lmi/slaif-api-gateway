"""Repository helpers for model_routes table operations."""

from __future__ import annotations

from collections.abc import Sequence
import uuid

from sqlalchemy import Select, asc, desc, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ModelRoute, ProviderConfig
from slaif_gateway.utils.admin_list_filters import as_value_tuple, or_equals


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

    async def get_model_route_for_update(self, route_id: uuid.UUID) -> ModelRoute | None:
        """Administrative row-lock read for a reviewed single-row route update (199-a).

        Holds ``FOR UPDATE`` on the exact route row while a plan's expected
        pre-state is revalidated and the complete merged candidate is
        assembled. Read-only for every other caller; runtime selection
        semantics are unchanged.
        """
        result = await self._session.execute(
            select(ModelRoute).where(ModelRoute.id == route_id).with_for_update()
        )
        return result.scalar_one_or_none()

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
        provider: str | Sequence[str] | None = None,
        requested_model: str | Sequence[str] | None = None,
        match_type: str | None = None,
        enabled: bool | None = None,
        visible: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelRoute]:
        providers = as_value_tuple(provider)
        requested_models = as_value_tuple(requested_model)
        # 195-a: OR WITHIN a field; the pre-195 per-member normalization is
        # preserved exactly (exact provider equality, case-insensitive
        # substring for the requested model, no added case folding).
        statement: Select[tuple[ModelRoute]] = select(ModelRoute)
        if providers is not None:
            statement = statement.where(or_equals(ModelRoute.provider, providers))
        if requested_models is not None:
            statement = statement.where(
                or_(
                    *[
                        ModelRoute.requested_model.ilike(f"%{value}%")
                        for value in requested_models
                    ]
                )
            )
        if match_type is not None:
            statement = statement.where(ModelRoute.match_type == match_type)
        if enabled is not None:
            statement = statement.where(ModelRoute.enabled == enabled)
        if visible is not None:
            statement = statement.where(ModelRoute.visible_in_models == visible)

        statement = (
            statement.order_by(
                ModelRoute.priority.asc(), ModelRoute.created_at.asc(), ModelRoute.id.asc()
            )
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

    async def list_enabled_model_routes_latest(
        self,
        *,
        endpoints: Sequence[str],
        limit: int,
    ) -> list[ModelRoute]:
        """Bounded LATEST enabled-route select for the key policy catalog.

        Base catalog eligibility — ENABLED routes on ENABLED providers
        (SQL subquery against provider_configs, no registry
        materialization in Python) over the given endpoint paths — is
        filtered in SQL BEFORE the LIMIT, so the page is the latest
        ``limit`` catalog-relevant routes; older routes remain reachable
        through the models server search (the read-only record-choices
        lookup).
        """
        enabled_providers = (
            select(ProviderConfig.provider)
            .where(
                ProviderConfig.enabled.is_(True),
                ProviderConfig.provider.is_not(None),
                ProviderConfig.provider != "",
            )
            .scalar_subquery()
        )
        statement = (
            select(ModelRoute)
            .where(
                ModelRoute.enabled.is_(True),
                ModelRoute.provider.in_(enabled_providers),
                ModelRoute.endpoint.in_(tuple(endpoints)),
            )
            .order_by(desc(ModelRoute.created_at), asc(ModelRoute.id))
            .limit(limit)
        )
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
        clear_notes: bool = False,
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
        # notes=None (default) PRESERVES the stored notes; only the
        # explicit clear_notes intent writes NULL (199-c provider law).
        if clear_notes:
            row.notes = None
        elif notes is not None:
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
