"""PostgreSQL checks for key template persistence."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.key_templates import KeyTemplatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.services.calibration_summary_service import (
    CalibrationObservedSummary,
    CalibrationPolicyProposal,
    CalibrationPreviewResult,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.key_template_service import KeyTemplateService
from slaif_gateway.utils.secrets import generate_secret_key

PROMPT_TEXT = "prompt text must not persist"
COMPLETION_TEXT = "completion text must not persist"
SECRET_VALUE = "sk-live-secret-must-not-persist"


def _key_template_columns(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("key_templates")}


def _key_template_revision_columns(sync_connection) -> set[str]:
    return {
        column["name"] for column in inspect(sync_connection).get_columns("key_template_revisions")
    }


def _key_template_indexes(sync_connection) -> set[str]:
    return {index["name"] for index in inspect(sync_connection).get_indexes("key_templates")}


def _gateway_key_columns(sync_connection) -> set[str]:
    return {column["name"] for column in inspect(sync_connection).get_columns("gateway_keys")}


def _gateway_key_indexes(sync_connection) -> set[str]:
    return {index["name"] for index in inspect(sync_connection).get_indexes("gateway_keys")}


@pytest.mark.asyncio
async def test_migration_creates_key_template_tables_and_indexes(migrated_engine) -> None:
    async with migrated_engine.connect() as connection:
        template_columns = await connection.run_sync(_key_template_columns)
        revision_columns = await connection.run_sync(_key_template_revision_columns)
        gateway_key_columns = await connection.run_sync(_gateway_key_columns)
        indexes = await connection.run_sync(_key_template_indexes)
        gateway_key_indexes = await connection.run_sync(_gateway_key_indexes)

    assert "current_revision_id" in template_columns
    assert "template_snapshot" in revision_columns
    assert "hosted_capabilities_requiring_review" in revision_columns
    assert "uq_key_templates_name_lower" in indexes
    assert "template_id" in gateway_key_columns
    assert "template_revision_id" in gateway_key_columns
    assert "ix_gateway_keys_template_id" in gateway_key_indexes
    assert "ix_gateway_keys_template_revision_id" in gateway_key_indexes


@pytest.mark.asyncio
async def test_repository_create_get_and_list_template(async_test_session: AsyncSession) -> None:
    source_key = await _create_gateway_key(async_test_session)
    repo = KeyTemplatesRepository(async_test_session)

    template = await repo.create_template_record(name=f"Template {uuid.uuid4()}")
    revision = await repo.create_revision_record(
        template_id=template.id,
        revision_number=1,
        created_by_admin_id=None,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=source_key.id,
        source_time_window_start=datetime.now(UTC) - timedelta(hours=1),
        source_time_window_end=datetime.now(UTC),
        source_multiplier=Decimal("3"),
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=["web_search_options"],
        request_limit_total=5,
        token_limit_total=100,
        template_snapshot={"warnings": ["review hosted capabilities"]},
    )
    await repo.set_current_revision(template_id=template.id, revision_id=revision.id)

    detail = await repo.get_template_for_admin_detail(template.id)
    templates = await repo.list_templates_for_admin()
    revisions = await repo.list_revisions_for_template(template.id)

    assert detail is not None
    assert detail.current_revision_id == revision.id
    assert any(row.id == template.id for row in templates)
    assert revisions == [revision]


@pytest.mark.asyncio
async def test_template_constraints_reject_invalid_values(async_test_session: AsyncSession) -> None:
    repo = KeyTemplatesRepository(async_test_session)

    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            await repo.create_template_record(name="   ")

    template = await repo.create_template_record(name=f"Constraints {uuid.uuid4()}")
    with pytest.raises(IntegrityError):
        async with async_test_session.begin_nested():
            await repo.create_revision_record(
                template_id=template.id,
                revision_number=0,
                created_by_admin_id=None,
                source_type="calibration_proposal",
                source_calibration_gateway_key_id=None,
                source_time_window_start=None,
                source_time_window_end=None,
                source_multiplier=Decimal("3"),
                allowed_endpoints=[],
                allowed_models=[],
                allowed_providers=[],
                allowed_hosted_capabilities=[],
                hosted_capabilities_requiring_review=[],
                request_limit_total=0,
                token_limit_total=-1,
            )


@pytest.mark.asyncio
async def test_service_creates_audit_and_safe_snapshot(async_test_session: AsyncSession) -> None:
    source_key = await _create_gateway_key(async_test_session)
    service = KeyTemplateService(
        key_templates_repository=KeyTemplatesRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )

    result = await service.create_from_calibration_proposal(
        preview=_preview(source_key.id),
        name=f"Service template {uuid.uuid4()}",
        reason="Reviewed calibration proposal",
        confirm_create_template=True,
    )

    assert result.template.current_revision_id == result.revision.id
    assert result.audit_log.action == "key_template.created"
    assert result.revision.created_audit_log_id == result.audit_log.id
    payload = json.dumps(result.revision.template_snapshot, default=str, sort_keys=True)
    assert PROMPT_TEXT not in payload
    assert COMPLETION_TEXT not in payload
    assert SECRET_VALUE not in payload


@pytest.mark.asyncio
async def test_service_creates_standard_key_from_template_revision(async_test_session: AsyncSession) -> None:
    source_key = await _create_gateway_key(async_test_session)
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Participant",
        surname="Key",
        email=f"participant-{uuid.uuid4()}@example.test",
    )
    template_service = KeyTemplateService(
        key_templates_repository=KeyTemplatesRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )
    template_result = await template_service.create_from_calibration_proposal(
        preview=_preview(source_key.id, hosted_review=()),
        name=f"Creatable template {uuid.uuid4()}",
        reason="Reviewed calibration proposal",
        confirm_create_template=True,
        validity_days_default=7,
    )
    key_service = KeyService(
        settings=Settings(
            APP_ENV="test",
            TOKEN_HMAC_SECRET="hmac-secret-for-template-key-tests",
            ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ),
        gateway_keys_repository=GatewayKeysRepository(async_test_session),
        one_time_secrets_repository=OneTimeSecretsRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    )
    template_key_service = KeyTemplateService(
        key_templates_repository=KeyTemplatesRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
        key_service=key_service,
    )

    created = await template_key_service.create_key_from_revision(
        template_revision_id=template_result.revision.id,
        owner_id=owner.id,
        reason="Create one participant key",
        confirm_create_key_from_template=True,
    )
    key = await async_test_session.get(type(source_key), created.created_key.gateway_key_id)

    assert key is not None
    assert key.key_purpose == "standard"
    assert key.capability_policy_mode == "standard"
    assert key.template_id == template_result.template.id
    assert key.template_revision_id == template_result.revision.id
    assert key.allowed_endpoints == ["/v1/chat/completions"]
    assert key.allowed_models == ["gpt-4.1-mini"]
    assert key.request_limit_total == template_result.revision.request_limit_total
    assert key.token_limit_total == template_result.revision.token_limit_total
    assert key.metadata_json["allowed_providers"] == ["openai"]
    assert created.audit_log.action == "gateway_key.created_from_template"


async def _create_gateway_key(async_test_session: AsyncSession):
    owner = await OwnersRepository(async_test_session).create_owner(
        name="Template",
        surname="Source",
        email=f"template-source-{uuid.uuid4()}@example.test",
    )
    now = datetime.now(UTC)
    return await GatewayKeysRepository(async_test_session).create_gateway_key_record(
        public_key_id=f"k_{uuid.uuid4().hex}",
        token_hash=f"hash-{uuid.uuid4().hex}",
        owner_id=owner.id,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(hours=1),
        request_limit_total=5,
        allow_all_models=True,
        allow_all_endpoints=True,
        key_purpose="trusted_calibration",
        capability_policy_mode="trusted_calibration_discovery",
    )


def _preview(
    key_id: uuid.UUID,
    *,
    hosted_review: tuple[str, ...] = ("web_search_options",),
) -> CalibrationPreviewResult:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    summary = CalibrationObservedSummary(
        gateway_key_id=key_id,
        public_key_id="public-calibration",
        owner_id=None,
        owner_email=None,
        owner_display_name=None,
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        time_window_start=now,
        time_window_end=now,
        observed_request_count=2,
        observed_endpoints=("/v1/chat/completions",),
        observed_providers=("openai",),
        observed_requested_models=("gpt-4.1-mini",),
        observed_resolved_upstream_models=("gpt-4.1-mini",),
        observed_provider_hosts=("api.openai.com",),
        observed_provider_endpoint_paths=("/v1/chat/completions",),
        observed_hosted_capabilities=("web_search_options",),
        observed_unknown_hosted_capabilities=(),
        observed_denied_capabilities=(),
        total_input_tokens=10,
        total_output_tokens=20,
        total_tokens=30,
        total_reasoning_tokens=None,
        total_cached_tokens=None,
        max_input_tokens_per_request=6,
        max_output_tokens_per_request=11,
        max_total_tokens_per_request=17,
        max_reasoning_tokens_per_request=None,
        max_cached_tokens_per_request=None,
        total_slaif_calculated_cost=Decimal("0.010000000"),
        total_provider_reported_cost=None,
        max_slaif_calculated_cost_per_request=Decimal("0.006000000"),
        max_provider_reported_cost_per_request=None,
        cost_currencies=("EUR",),
        cost_confidence="slaif_calculated",
        warnings=(),
    )
    proposal = CalibrationPolicyProposal(
        proposed_allowed_endpoints=("/v1/chat/completions",),
        proposed_allowed_models=("gpt-4.1-mini",),
        proposed_allowed_providers=("openai",),
        proposed_allowed_hosted_capabilities=(),
        hosted_capabilities_requiring_review=hosted_review,
        proposed_request_limit_total=6,
        proposed_token_limit_total=90,
        proposed_input_token_limit_total=30,
        proposed_output_token_limit_total=60,
        proposed_reasoning_token_limit_total=None,
        proposed_cost_limit_eur=Decimal("0.030000000"),
        proposed_max_input_tokens_per_request=18,
        proposed_max_output_tokens_per_request=33,
        proposed_max_total_tokens_per_request=51,
        proposed_max_single_request_cost_eur=Decimal("0.018000000"),
        proposed_rate_limit_policy=None,
        warnings=(f"{PROMPT_TEXT} {COMPLETION_TEXT} {SECRET_VALUE}",),
        assumptions=("safe metadata only",),
        source_gateway_key_id=key_id,
        source_time_window_start=now,
        source_time_window_end=now,
        multiplier=Decimal("3"),
    )
    return CalibrationPreviewResult(
        summary=summary,
        proposal=proposal,
        is_empty=False,
        warnings=proposal.warnings,
    )
