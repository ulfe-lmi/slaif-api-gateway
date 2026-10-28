"""Repository helpers for provider_configs table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.utils.admin_list_filters import as_value_tuple, or_equals


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

    async def get_provider_config_for_update(self, provider_or_id: str) -> ProviderConfig | None:
        """Administrative row-lock read for a partial provider update (199-a).

        Resolves a UUID or the exact provider slug under ``FOR UPDATE`` so a
        typed partial update can assemble complete service inputs while
        holding the lock. Read-only for every other caller; runtime
        selection semantics are unchanged.
        """
        value = str(provider_or_id).strip()
        try:
            identifier = uuid.UUID(value)
        except ValueError:
            statement = select(ProviderConfig).where(ProviderConfig.provider == value)
        else:
            statement = select(ProviderConfig).where(ProviderConfig.id == identifier)
        result = await self._session.execute(statement.with_for_update())
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

    async def list_provider_configs_latest(self, *, enabled: bool, limit: int) -> list[ProviderConfig]:
        """Bounded LATEST-first provider select for the key policy catalog.

        The policy catalog renders the latest ``limit`` enabled providers;
        older providers stay reachable through the providers server search
        (read-only record-choices lookup, kind=policy_provider).
        """
        statement: Select[tuple[ProviderConfig]] = (
            select(ProviderConfig)
            .where(ProviderConfig.enabled == enabled)
            .order_by(desc(ProviderConfig.created_at), asc(ProviderConfig.provider))
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_enabled_provider_slugs_matching(
        self, slugs: Sequence[str]
    ) -> set[str]:
        """Bounded submit-time eligibility point query.

        Returns exactly the subset of the given (small, form-submitted)
        slug candidates that are ENABLED provider configs, checking both
        the raw and lowercased spellings (provider slugs are stored
        lowercase). Unknown or disabled slugs are simply absent from the
        result, so they are denied by the caller. This keeps the visible
        latest-100 catalog page a presentation detail — an older enabled
        provider found through the providers search still validates —
        without materializing the whole registry in Python.
        """
        candidates = {
            candidate
            for raw in slugs
            for candidate in (str(raw).strip(), str(raw).strip().lower())
            if str(raw).strip()
        }
        if not candidates:
            return set()
        result = await self._session.execute(
            select(ProviderConfig.provider).where(
                ProviderConfig.enabled == True,  # noqa: E712
                ProviderConfig.provider.in_(candidates),
            )
        )
        return {str(row[0]) for row in result.all()}

    async def list_provider_configs_for_admin(
        self,
        *,
        provider: str | Sequence[str] | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProviderConfig]:
        providers = as_value_tuple(provider)
        # 195-a: OR WITHIN the provider field (exact equality, no case
        # folding — the pre-195 normalization is preserved per member).
        statement: Select[tuple[ProviderConfig]] = select(ProviderConfig)
        if providers is not None:
            statement = statement.where(
                or_equals(ProviderConfig.provider, providers)
            )
        if enabled is not None:
            statement = statement.where(ProviderConfig.enabled == enabled)

        statement = statement.order_by(ProviderConfig.provider.asc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_provider_config_for_admin_detail(self, provider_config_id: uuid.UUID) -> ProviderConfig | None:
        return await self._session.get(ProviderConfig, provider_config_id)

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
        provider: str | None = None,
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

        if provider is not None:
            row.provider = provider
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
