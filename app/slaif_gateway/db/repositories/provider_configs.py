"""Repository helpers for provider_configs table operations."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ProviderConfig


class ProviderConfigsRepository:
    """Encapsulates CRUD-style access for ProviderConfig rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_provider_config(
        self,
        *,
        provider: str,
        display_name: str,
        base_url: str,
        api_key_env_var: str,
        kind: str = "openai_compatible",
        enabled: bool = True,
        timeout_seconds: int = 300,
        max_retries: int = 2,
        notes: str | None = None,
    ) -> ProviderConfig:
        row = ProviderConfig(
            provider=provider,
            display_name=display_name,
            kind=kind,
            base_url=base_url,
            api_key_env_var=api_key_env_var,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            notes=notes,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_provider_config_by_id(self, provider_config_id: uuid.UUID) -> ProviderConfig | None:
        return await self._session.get(ProviderConfig, provider_config_id)

    async def get_provider_config_by_provider(self, provider: str) -> ProviderConfig | None:
        result = await self._session.execute(
            select(ProviderConfig).where(ProviderConfig.provider == provider)
        )
        return result.scalar_one_or_none()

    async def list_provider_configs(
        self,
        *,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProviderConfig]:
        statement: Select[tuple[ProviderConfig]] = select(ProviderConfig)
        if enabled is not None:
            statement = statement.where(ProviderConfig.enabled == enabled)

        statement = statement.order_by(ProviderConfig.provider.asc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_provider_enabled(self, provider_config_id: uuid.UUID, *, enabled: bool) -> bool:
        row = await self.get_provider_config_by_id(provider_config_id)
        if row is None:
            return False
        row.enabled = enabled
        await self._session.flush()
        return True

    async def update_provider_metadata(
        self,
        provider_config_id: uuid.UUID,
        *,
        display_name: str | None = None,
        kind: str | None = None,
        base_url: str | None = None,
        api_key_env_var: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        notes: str | None = None,
    ) -> bool:
        row = await self.get_provider_config_by_id(provider_config_id)
        if row is None:
            return False

        if display_name is not None:
            row.display_name = display_name
        if kind is not None:
            row.kind = kind
        if base_url is not None:
            row.base_url = base_url
        if api_key_env_var is not None:
            row.api_key_env_var = api_key_env_var
        if timeout_seconds is not None:
            row.timeout_seconds = timeout_seconds
        if max_retries is not None:
            row.max_retries = max_retries
        if notes is not None:
            row.notes = notes

        await self._session.flush()
        return True
