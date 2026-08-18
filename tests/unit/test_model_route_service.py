import uuid
from datetime import UTC, datetime

import pytest

from slaif_gateway.db.models import ModelRoute
from slaif_gateway.services.model_route_service import ModelRouteService


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _route(**overrides) -> ModelRoute:
    values = {
        "id": uuid.uuid4(),
        "requested_model": "gpt-test-mini",
        "match_type": "exact",
        "endpoint": "/v1/chat/completions",
        "provider": "openai",
        "upstream_model": "gpt-test-mini",
        "priority": 10,
        "enabled": True,
        "visible_in_models": True,
        "supports_streaming": True,
        "capabilities": {"vision": False},
        "notes": "safe note",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return ModelRoute(**values)


class _RoutesRepo:
    def __init__(self, row: ModelRoute | None = None) -> None:
        self.row = row

    async def create_model_route(self, **kwargs):
        self.row = _route(**kwargs)
        return self.row

    async def get_model_route_by_id(self, route_id):
        if self.row is not None and self.row.id == route_id:
            return self.row
        return None

    async def update_model_route_metadata(self, route_id, **kwargs):
        if self.row is None or self.row.id != route_id:
            return False
        for key, value in kwargs.items():
            if value is not None:
                setattr(self.row, key, value)
        return True

    async def set_model_route_enabled(self, route_id, *, enabled):
        if self.row is None or self.row.id != route_id:
            return False
        self.row.enabled = enabled
        return True


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.rows.append(kwargs)


def _service(row: ModelRoute | None = None) -> tuple[ModelRouteService, _RoutesRepo, _AuditRepo]:
    routes = _RoutesRepo(row)
    audit = _AuditRepo()
    return (
        ModelRouteService(model_routes_repository=routes, audit_repository=audit),
        routes,
        audit,
    )


@pytest.mark.asyncio
async def test_model_route_create_writes_safe_actor_audit() -> None:
    service, _routes, audit = _service()
    actor_admin_id = uuid.uuid4()

    row = await service.create_model_route(
        requested_model="gpt-test-mini",
        match_type="exact",
        provider="openai",
        upstream_model="gpt-upstream-mini",
        priority=10,
        visible_in_models=True,
        enabled=True,
        supports_streaming=True,
        capabilities={"vision": False},
        notes="safe note",
        actor_admin_id=actor_admin_id,
        reason="routing setup",
    )

    assert row.upstream_model == "gpt-upstream-mini"
    assert row.capabilities["vision"] is False
    assert row.capabilities["chat_completions"]["chat_text"] is True
    assert row.capabilities["chat_completions"]["chat_streaming"] is True
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "model_route_created"
    assert audit.rows[0]["new_values"]["provider"] == "openai"
    assert "api_key_value" not in audit.rows[0]["new_values"]


@pytest.mark.asyncio
async def test_model_route_update_writes_safe_actor_audit() -> None:
    existing = _route()
    service, _routes, audit = _service(existing)
    actor_admin_id = uuid.uuid4()

    updated = await service.update_model_route(
        existing.id,
        requested_model="gpt-test-mini",
        match_type="exact",
        provider="openai",
        upstream_model="gpt-updated-mini",
        priority=20,
        visible_in_models=False,
        enabled=False,
        supports_streaming=False,
        capabilities={"json": True},
        notes="updated note",
        actor_admin_id=actor_admin_id,
        reason="maintenance",
    )

    assert updated.enabled is False
    assert updated.priority == 20
    assert updated.capabilities["json"] is True
    assert updated.capabilities["chat_completions"]["chat_streaming"] is False
    assert audit.rows[0]["admin_user_id"] == actor_admin_id
    assert audit.rows[0]["action"] == "model_route_updated"
    assert audit.rows[0]["old_values"]["enabled"] is True
    assert audit.rows[0]["new_values"]["enabled"] is False


@pytest.mark.asyncio
async def test_model_route_service_rejects_invalid_match_type() -> None:
    service, _routes, _audit = _service()

    with pytest.raises(ValueError, match="match_type"):
        await service.create_model_route(
            requested_model="gpt-test-mini",
            match_type="regex",
            provider="openai",
            upstream_model="gpt-test-mini",
            priority=10,
            visible_in_models=True,
            enabled=True,
            notes=None,
        )


@pytest.mark.asyncio
async def test_model_route_external_tool_metadata_is_canonical_before_mutation_and_audit() -> None:
    service, routes, audit = _service()
    policy = {
        "version": 1,
        "supported_capabilities": ["provider_web_search"],
        "approved_destination_ids": [],
        "max_provider_tool_calls_per_request": 2,
        "call_limit_enforced": True,
        "final_usage_required": True,
        "final_cost_required": True,
    }
    row = await service.create_model_route(
        requested_model="gpt-test-mini",
        match_type="exact",
        provider="openai",
        upstream_model="gpt-test-mini",
        priority=10,
        visible_in_models=True,
        enabled=True,
        notes="reviewed future support",
        capabilities={"external_tools": policy},
    )
    assert row.capabilities["external_tools"] == policy
    assert audit.rows[0]["new_values"]["capabilities"]["external_tools"] == policy

    with pytest.raises(ValueError, match="External-tool route policy"):
        await service.update_model_route(
            row.id,
            requested_model=row.requested_model,
            match_type=row.match_type,
            provider=row.provider,
            upstream_model=row.upstream_model,
            priority=row.priority,
            visible_in_models=row.visible_in_models,
            enabled=row.enabled,
            supports_streaming=row.supports_streaming,
            capabilities={"external_tools": {"server_url": "https://forbidden.invalid"}},
            notes=row.notes,
        )
    assert len(audit.rows) == 1
    assert routes.row.capabilities["external_tools"] == policy
