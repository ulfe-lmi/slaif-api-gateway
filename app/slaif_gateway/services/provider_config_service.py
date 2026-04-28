"""Service helpers for provider configuration metadata."""

from __future__ import annotations

import uuid

from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError


class ProviderConfigService:
    """Small service layer for provider configuration CLI operations."""

    def __init__(
        self,
        *,
        provider_configs_repository: ProviderConfigsRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._providers = provider_configs_repository
        self._audit = audit_repository

    async def create_provider_config(
        self,
        *,
        provider: str,
        display_name: str | None,
        base_url: str | None,
        api_key_env_var: str,
        enabled: bool,
        notes: str | None,
        kind: str = "openai_compatible",
        timeout_seconds: int = 300,
        max_retries: int = 2,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ProviderConfig:
        normalized_provider = _required_text(provider, "Provider")
        normalized_kind = _validate_kind(kind)
        normalized_env_var = _required_text(api_key_env_var, "API key environment variable")
        if _looks_like_secret(normalized_env_var):
            raise ValueError("Store the provider API key in an environment variable; pass only its name")
        if await self._providers.get_provider_config_by_provider(normalized_provider) is not None:
            raise DuplicateRecordError("Provider config", "provider")

        row = await self._providers.create_provider_config(
            provider=normalized_provider,
            display_name=_clean_optional(display_name) or normalized_provider,
            base_url=_clean_optional(base_url) or _default_base_url(normalized_provider),
            api_key_env_var=normalized_env_var,
            kind=normalized_kind,
            enabled=enabled,
            timeout_seconds=_positive_int(timeout_seconds, "Timeout seconds"),
            max_retries=_non_negative_int(max_retries, "Max retries"),
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="provider_config_created",
            entity_type="provider_config",
            admin_user_id=actor_admin_id,
            entity_id=row.id,
            new_values=_safe_audit_values(row),
            note=_clean_optional(reason),
        )
        return row

    async def list_provider_configs(
        self,
        *,
        enabled_only: bool,
        limit: int,
    ) -> list[ProviderConfig]:
        return await self._providers.list_provider_configs(
            enabled=True if enabled_only else None,
            limit=limit,
        )

    async def get_provider_config(self, provider_or_id: str) -> ProviderConfig:
        value = _required_text(provider_or_id, "Provider")
        row: ProviderConfig | None
        try:
            row = await self._providers.get_provider_config_by_id(uuid.UUID(value))
        except ValueError:
            row = await self._providers.get_provider_config_by_provider(value)
        if row is None:
            raise RecordNotFoundError("Provider config")
        return row

    async def update_provider_config(
        self,
        provider_or_id: str,
        *,
        provider: str,
        display_name: str | None,
        kind: str,
        base_url: str,
        api_key_env_var: str,
        enabled: bool,
        timeout_seconds: int,
        max_retries: int,
        notes: str | None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ProviderConfig:
        row = await self.get_provider_config(provider_or_id)
        old_values = _safe_audit_values(row)
        normalized_provider = _required_text(provider, "Provider")
        normalized_env_var = _required_text(api_key_env_var, "API key environment variable")
        if _looks_like_secret(normalized_env_var):
            raise ValueError("Store the provider API key in an environment variable; pass only its name")
        if normalized_provider != row.provider:
            existing = await self._providers.get_provider_config_by_provider(normalized_provider)
            if existing is not None and existing.id != row.id:
                raise DuplicateRecordError("Provider config", "provider")

        updated = await self._providers.update_provider_metadata(
            row.id,
            provider=normalized_provider,
            display_name=_clean_optional(display_name) or normalized_provider,
            kind=_validate_kind(kind),
            base_url=_required_text(base_url, "Base URL"),
            api_key_env_var=normalized_env_var,
            timeout_seconds=_positive_int(timeout_seconds, "Timeout seconds"),
            max_retries=_non_negative_int(max_retries, "Max retries"),
            notes=_clean_optional(notes),
        )
        if not updated:
            raise RecordNotFoundError("Provider config")
        refreshed = await self._providers.get_provider_config_by_id(row.id)
        if refreshed is None:
            raise RecordNotFoundError("Provider config")
        refreshed.enabled = enabled
        await self._providers.set_provider_enabled(refreshed.id, enabled=enabled)
        await self._audit.add_audit_log(
            action="provider_config_updated",
            entity_type="provider_config",
            admin_user_id=actor_admin_id,
            entity_id=refreshed.id,
            old_values=old_values,
            new_values=_safe_audit_values(refreshed),
            note=_clean_optional(reason),
        )
        return refreshed

    async def set_provider_enabled(
        self,
        provider_or_id: str,
        *,
        enabled: bool,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ProviderConfig:
        row = await self.get_provider_config(provider_or_id)
        old_enabled = row.enabled
        updated = await self._providers.set_provider_enabled(row.id, enabled=enabled)
        if not updated:
            raise RecordNotFoundError("Provider config")
        row.enabled = enabled
        await self._audit.add_audit_log(
            action="provider_config_enabled" if enabled else "provider_config_disabled",
            entity_type="provider_config",
            admin_user_id=actor_admin_id,
            entity_id=row.id,
            old_values={"enabled": old_enabled},
            new_values={"enabled": enabled},
            note=_clean_optional(reason),
        )
        return row


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


def _default_base_url(provider: str) -> str:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1"
    raise ValueError("--base-url is required for providers without a built-in default")


def _validate_kind(value: str) -> str:
    kind = _required_text(value, "Provider kind")
    if kind != "openai_compatible":
        raise ValueError("Provider kind must be openai_compatible")
    return kind


def _positive_int(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _non_negative_int(value: int, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("sk-", "sk_", "sk-or-")) or " " in value


def _safe_audit_values(row: ProviderConfig) -> dict[str, object]:
    return {
        "provider": row.provider,
        "display_name": row.display_name,
        "kind": row.kind,
        "base_url": row.base_url,
        "api_key_env_var": row.api_key_env_var,
        "enabled": row.enabled,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "notes": row.notes,
    }
