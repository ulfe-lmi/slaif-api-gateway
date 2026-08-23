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
        provider="OPENAI",
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
    assert updated.provider == "openai"
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


@pytest.mark.asyncio
async def test_generic_http_requires_confirmation_and_reason() -> None:
    service, _providers, _audit = _service()

    with pytest.raises(ValueError, match="confirmation"):
        await service.create_provider_config(
            provider="lan-qwen-text",
            display_name="LAN Qwen",
            base_url="http://qwen.lan:8000/v1",
            api_key_env_var="LAN_QWEN_KEY",
            enabled=True,
            notes=None,
        )

    row = await service.create_provider_config(
        provider="lan-qwen-text",
        display_name="LAN Qwen",
        base_url="http://qwen.lan:8000/v1/",
        api_key_env_var="LAN_QWEN_KEY",
        enabled=True,
        notes=None,
        reason="LAN reverse proxy is operator-owned",
        confirm_insecure_http=True,
    )
    assert row.base_url == "http://qwen.lan:8000/v1"


@pytest.mark.asyncio
async def test_provider_slug_is_canonical_and_http_acknowledgement_is_audited() -> None:
    service, _providers, audit = _service()

    row = await service.create_provider_config(
        provider="LAN-QWEN-TEXT",
        display_name="LAN Qwen",
        base_url="http://qwen.lan:8000/v1",
        api_key_env_var="LAN_QWEN_KEY",
        enabled=True,
        notes=None,
        reason="operator-owned LAN reverse proxy",
        confirm_insecure_http=True,
    )

    assert row.provider == "lan-qwen-text"
    values = audit.rows[0]["new_values"]
    assert values["insecure_http_confirmed"] is True
    assert values["base_url"] == "http://qwen.lan:8000/v1"
    assert values["insecure_http_audit_reason"] == "operator-owned LAN reverse proxy"


@pytest.mark.asyncio
async def test_provider_slug_rejects_secret_like_or_unsafe_values() -> None:
    service, _providers, _audit = _service()
    for value in ("sk-provider-secret", "provider name", "provider/route", "a" * 65):
        with pytest.raises(ValueError):
            await service.create_provider_config(
                provider=value,
                display_name="Provider",
                base_url="https://provider.lan/v1",
                api_key_env_var="PROVIDER_KEY",
                enabled=True,
                notes=None,
            )


@pytest.mark.asyncio
async def test_module_provider_config_accepts_operator_url_and_audits_kind() -> None:
    service, _providers, audit = _service()

    row = await service.create_provider_config(
        provider="face-score",
        display_name="Face score",
        kind="module",
        base_url="https://operator.example/score",
        api_key_env_var="FACE_SCORE_KEY",
        enabled=True,
        notes="foundation only",
        reason="reviewed module configuration",
    )

    assert row.kind == "module"
    assert row.base_url == "https://operator.example/score"
    assert audit.rows[0]["new_values"]["kind"] == "module"


@pytest.mark.asyncio
async def test_module_http_requires_existing_confirmation_and_reason_boundary() -> None:
    service, _providers, _audit = _service()

    with pytest.raises(ValueError, match="confirmation"):
        await service.create_provider_config(
            provider="face-score",
            display_name="Face score",
            kind="module",
            base_url="http://module.lan:8000/score",
            api_key_env_var="FACE_SCORE_KEY",
            enabled=True,
            notes=None,
        )

    row = await service.create_provider_config(
        provider="face-score",
        display_name="Face score",
        kind="module",
        base_url="http://module.lan:8000/score",
        api_key_env_var="FACE_SCORE_KEY",
        enabled=True,
        notes=None,
        reason="operator-owned LAN module",
        confirm_insecure_http=True,
    )

    assert row.kind == "module"
