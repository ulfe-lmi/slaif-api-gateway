import uuid
from datetime import UTC, datetime

import pytest

from slaif_gateway.db.models import ProviderConfig
from slaif_gateway.services.provider_config_service import ProviderConfigService


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _provider(**overrides) -> ProviderConfig:
    values = {
        "id": uuid.uuid4(),
        "provider": "openai",
        "display_name": "OpenAI",
        "kind": "openai_compatible",
        "base_url": "https://api.openai.example/v1",
        "api_key_env_var": "OPENAI_UPSTREAM_API_KEY",
        "enabled": True,
        "timeout_seconds": 300,
        "max_retries": 2,
        "notes": "safe note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return ProviderConfig(**values)


class _ProvidersRepo:
    def __init__(self, row: ProviderConfig | None = None) -> None:
        self.row = row

    async def get_provider_config_by_provider(self, provider):
        if self.row is not None and self.row.provider == provider:
            return self.row
        return None

    async def get_provider_config_by_id(self, provider_config_id):
        if self.row is not None and self.row.id == provider_config_id:
            return self.row
        return None

    async def create_provider_config(self, **kwargs):
        self.row = _provider(**kwargs)
        return self.row

    async def update_provider_metadata(self, provider_config_id, **kwargs):
        if self.row is None or self.row.id != provider_config_id:
            return False
        for key, value in kwargs.items():
            if value is not None:
                setattr(self.row, key, value)
        return True

    async def set_provider_enabled(self, provider_config_id, *, enabled):
        if self.row is None or self.row.id != provider_config_id:
            return False
        self.row.enabled = enabled
        return True


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


def _service(row: ProviderConfig | None = None) -> tuple[ProviderConfigService, _ProvidersRepo, _AuditRepo]:
    providers = _ProvidersRepo(row)
    audit = _AuditRepo()
    return (
        ProviderConfigService(provider_configs_repository=providers, audit_repository=audit),
        providers,
        audit,
    )


@pytest.mark.asyncio
async def test_provider_config_create_writes_safe_actor_audit() -> None:
    service, _providers, audit = _service()
    actor_admin_id = uuid.uuid4()

    row = await service.create_provider_config(
        provider="openrouter",
        display_name="OpenRouter",
        base_url="https://openrouter.example/api/v1",
        api_key_env_var="OPENROUTER_API_KEY",
        enabled=True,
        notes="safe note",
        actor_admin_id=actor_admin_id,
        reason="catalog setup",
    )

    assert row.api_key_env_var == "OPENROUTER_API_KEY"
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "provider_config_created"
    assert audit.rows[0]["new_values"]["api_key_env_var"] == "OPENROUTER_API_KEY"
    assert "api_key_value" not in audit.rows[0]["new_values"]


@pytest.mark.asyncio
async def test_provider_config_update_writes_safe_actor_audit() -> None:
    existing = _provider()
    service, _providers, audit = _service(existing)
    actor_admin_id = uuid.uuid4()

    updated = await service.update_provider_config(
        str(existing.id),
        provider="openai",
        display_name="OpenAI Updated",
        kind="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
        enabled=False,
        timeout_seconds=120,
        max_retries=0,
        notes="updated note",
        actor_admin_id=actor_admin_id,
        reason="maintenance",
    )

    assert updated.enabled is False
    assert updated.timeout_seconds == 120
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "provider_config_updated"
    assert audit.rows[0]["old_values"]["enabled"] is True
    assert audit.rows[0]["new_values"]["enabled"] is False


@pytest.mark.asyncio
async def test_provider_config_service_rejects_secret_looking_env_var() -> None:
    service, _providers, _audit = _service()

    with pytest.raises(ValueError, match="environment variable"):
        await service.create_provider_config(
            provider="openai",
            display_name="OpenAI",
            base_url="https://api.openai.example/v1",
            api_key_env_var="sk-real-looking-secret",
            enabled=True,
            notes=None,
        )
