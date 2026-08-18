"""Focused PostgreSQL evidence for objective-013 external-tool policy metadata."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.key_templates import KeyTemplatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.keys import (
    CreateGatewayKeyInput,
    UpdateGatewayKeyExternalToolPolicyInput,
)
from slaif_gateway.services.auth_service import GatewayAuthService
from slaif_gateway.services.external_tool_policy_contract import strict_key_policy
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.key_template_service import (
    external_tool_policy_for_template_revision,
)
from slaif_gateway.services.model_route_service import ModelRouteService
from slaif_gateway.utils.secrets import generate_secret_key


KEY_POLICY = {
    "version": 1,
    "mode": "external_tool_fenced",
    "allowed_capabilities": ["provider_connector", "provider_web_search"],
    "allowed_destination_ids": ["connector:reviewed_crm"],
    "max_provider_tool_calls_per_request": 2,
    "single_request_overrun_acknowledged": True,
}
ROUTE_POLICY = {
    "version": 1,
    "supported_capabilities": ["provider_connector", "provider_web_search"],
    "approved_destination_ids": ["connector:reviewed_crm"],
    "max_provider_tool_calls_per_request": 2,
    "call_limit_enforced": True,
    "final_usage_required": True,
    "final_cost_required": True,
}


@pytest.mark.asyncio
async def test_external_tool_key_route_template_audit_and_old_default_round_trip(
    async_test_session: AsyncSession,
) -> None:
    settings = Settings(
        APP_ENV="test",
        TOKEN_HMAC_SECRET="objective-013-hmac-secret",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
    )
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Policy",
        surname="Owner",
        email=f"external-tool-{uuid.uuid4()}@example.org",
    )
    keys = GatewayKeysRepository(async_test_session)
    audit = AuditRepository(async_test_session)
    key_service = KeyService(
        settings=settings,
        gateway_keys_repository=keys,
        one_time_secrets_repository=OneTimeSecretsRepository(async_test_session),
        audit_repository=audit,
    )
    now = datetime.now(UTC)

    old_created = await key_service.create_gateway_key(
        CreateGatewayKeyInput(
            owner_id=owner.id,
            valid_from=now,
            valid_until=now + timedelta(days=7),
            cost_limit_eur=Decimal("2"),
            token_limit_total=200,
            request_limit_total=20,
            allowed_models=["gpt-test"],
            allowed_endpoints=["/v1/chat/completions"],
            allowed_providers=["openai"],
            note="old-key strict-default setup",
        )
    )
    old_row = await async_test_session.get(GatewayKey, old_created.gateway_key_id)
    assert old_row is not None
    old_row.metadata_json = {
        key: value for key, value in old_row.metadata_json.items() if key != "external_tool_policy"
    }
    await async_test_session.flush()
    authenticated = await GatewayAuthService(
        settings=settings,
        gateway_keys_repository=keys,
    ).authenticate_authorization_header(f"Bearer {old_created.plaintext_key}", now=now)
    assert authenticated.external_tool_policy == strict_key_policy().to_metadata()

    fenced_created = await key_service.create_gateway_key(
        CreateGatewayKeyInput(
            owner_id=owner.id,
            valid_from=now,
            valid_until=now + timedelta(days=7),
            cost_limit_eur=Decimal("5"),
            token_limit_total=500,
            request_limit_total=50,
            allowed_models=["gpt-test"],
            allowed_endpoints=["/v1/chat/completions"],
            allowed_providers=["openai"],
            external_tool_policy=KEY_POLICY,
            confirm_external_tool_fenced=True,
            note="reviewed fenced policy",
        )
    )
    fenced_row = await async_test_session.get(GatewayKey, fenced_created.gateway_key_id)
    assert fenced_row is not None
    assert fenced_row.metadata_json["external_tool_policy"] == KEY_POLICY

    await key_service.update_gateway_key_external_tool_policy(
        UpdateGatewayKeyExternalToolPolicyInput(
            gateway_key_id=fenced_row.id,
            external_tool_policy=KEY_POLICY,
            confirm_external_tool_fenced=True,
            reason="reaffirm reviewed policy",
        )
    )
    audit_result = await async_test_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == fenced_row.id,
            AuditLog.action == "update_external_tool_policy",
        )
    )
    policy_audit = audit_result.scalar_one()
    assert policy_audit.new_values["external_tool_policy"] == KEY_POLICY
    assert "server_url" not in str(policy_audit.new_values)

    route = await ModelRouteService(
        model_routes_repository=ModelRoutesRepository(async_test_session),
        audit_repository=audit,
        external_tool_ceilings=settings.get_external_tool_operator_ceilings(),
    ).create_model_route(
        requested_model=f"external-tool-route-{uuid.uuid4()}",
        match_type="exact",
        provider="openai",
        upstream_model="gpt-test",
        priority=10,
        visible_in_models=False,
        enabled=False,
        notes="future support only",
        capabilities={"external_tools": ROUTE_POLICY},
        reason="reviewed route support",
    )
    assert route.capabilities["external_tools"] == ROUTE_POLICY

    templates = KeyTemplatesRepository(async_test_session)
    template = await templates.create_template_record(name=f"External {uuid.uuid4()}")
    revision = await templates.create_revision_record(
        template_id=template.id,
        revision_number=1,
        created_by_admin_id=None,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=fenced_row.id,
        source_time_window_start=now - timedelta(hours=1),
        source_time_window_end=now,
        source_multiplier=Decimal("3"),
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-test"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=[],
        request_limit_total=50,
        token_limit_total=500,
        cost_limit_eur=Decimal("5"),
        template_snapshot={"external_tool_policy": KEY_POLICY},
    )
    await templates.set_current_revision(template_id=template.id, revision_id=revision.id)
    loaded_revision = await templates.get_revision_for_admin_detail(revision.id)
    assert loaded_revision is not None
    assert external_tool_policy_for_template_revision(loaded_revision).to_metadata() == KEY_POLICY
