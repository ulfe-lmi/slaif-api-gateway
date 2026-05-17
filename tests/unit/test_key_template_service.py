from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.services.calibration_summary_service import (
    CalibrationObservedSummary,
    CalibrationPolicyProposal,
    CalibrationPreviewResult,
)
from slaif_gateway.services.key_template_service import KeyTemplateError, KeyTemplateService

PROMPT_TEXT = "prompt text must not persist"
COMPLETION_TEXT = "completion text must not persist"
SECRET_VALUE = "sk-live-secret-must-not-persist"


class FakeTemplatesRepository:
    def __init__(self) -> None:
        self.templates = []
        self.revisions = []

    async def create_template_record(self, **kwargs):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            current_revision_id=None,
            revisions=[],
            **kwargs,
        )
        self.templates.append(row)
        return row

    async def create_revision_record(self, **kwargs):
        row = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.revisions.append(row)
        self.templates[-1].revisions.append(row)
        return row

    async def set_current_revision(self, *, template_id, revision_id):
        for template in self.templates:
            if template.id == template_id:
                template.current_revision_id = revision_id
                return template
        return None


class FakeAuditRepository:
    def __init__(self) -> None:
        self.rows = []

    async def add_audit_log(self, **kwargs):
        row = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.rows.append(row)
        return row


def test_create_template_from_calibration_proposal_creates_template_revision_and_audit() -> None:
    templates = FakeTemplatesRepository()
    audit = FakeAuditRepository()
    service = KeyTemplateService(key_templates_repository=templates, audit_repository=audit)
    preview = _preview()

    result = asyncio.run(
        service.create_from_calibration_proposal(
            preview=preview,
            name="Workshop participants",
            description="Strict participant policy",
            actor_admin_id=uuid.uuid4(),
            reason="Reviewed calibration proposal",
            confirm_create_template=True,
            validity_days_default=14,
            email_delivery_mode_default="pending",
        )
    )

    assert result.template.name == "Workshop participants"
    assert result.template.current_revision_id == result.revision.id
    assert result.revision.revision_number == 1
    assert result.revision.source_type == "calibration_proposal"
    assert result.revision.source_calibration_gateway_key_id == preview.summary.gateway_key_id
    assert result.revision.source_time_window_start == preview.summary.time_window_start
    assert result.revision.source_time_window_end == preview.summary.time_window_end
    assert result.revision.source_multiplier == Decimal("3")
    assert result.revision.allowed_endpoints == ["/v1/chat/completions"]
    assert result.revision.allowed_models == ["gpt-4.1-mini"]
    assert result.revision.allowed_providers == ["openai"]
    assert result.revision.allowed_hosted_capabilities == []
    assert result.revision.hosted_capabilities_requiring_review == ["web_search_options"]
    assert result.revision.request_limit_total == 6
    assert result.revision.token_limit_total == 90
    assert result.revision.validity_days_default == 14
    assert result.revision.email_delivery_mode_default == "pending"
    assert result.revision.created_audit_log_id == result.audit_log.id
    assert audit.rows[0].new_values["revision_number"] == 1


def test_template_snapshot_is_safe_and_omits_forbidden_content() -> None:
    service = KeyTemplateService(
        key_templates_repository=FakeTemplatesRepository(),
        audit_repository=FakeAuditRepository(),
    )
    preview = _preview(
        extra_warning=f"{PROMPT_TEXT} {COMPLETION_TEXT} {SECRET_VALUE}",
    )

    result = asyncio.run(
        service.create_from_calibration_proposal(
            preview=preview,
            name="Safe template",
            reason="Reviewed",
            confirm_create_template=True,
        )
    )

    payload = json.dumps(result.revision.template_snapshot, default=str, sort_keys=True)
    assert PROMPT_TEXT not in payload
    assert COMPLETION_TEXT not in payload
    assert SECRET_VALUE not in payload
    assert "web_search_options" in payload


def test_rejects_missing_confirmation_and_reason() -> None:
    service = KeyTemplateService(
        key_templates_repository=FakeTemplatesRepository(),
        audit_repository=FakeAuditRepository(),
    )

    with pytest.raises(KeyTemplateError, match="Confirm"):
        asyncio.run(
            service.create_from_calibration_proposal(
                preview=_preview(),
                name="No confirm",
                reason="Reviewed",
                confirm_create_template=False,
            )
        )

    with pytest.raises(KeyTemplateError, match="Audit reason"):
        asyncio.run(
            service.create_from_calibration_proposal(
                preview=_preview(),
                name="No reason",
                reason="",
                confirm_create_template=True,
            )
        )


def test_rejects_empty_calibration_proposal() -> None:
    service = KeyTemplateService(
        key_templates_repository=FakeTemplatesRepository(),
        audit_repository=FakeAuditRepository(),
    )

    with pytest.raises(KeyTemplateError, match="empty"):
        asyncio.run(
            service.create_from_calibration_proposal(
                preview=_preview(empty=True),
                name="Empty",
                reason="Reviewed",
                confirm_create_template=True,
            )
        )


def test_rejects_unimplemented_endpoints_and_participant_hosted_allowlist() -> None:
    service = KeyTemplateService(
        key_templates_repository=FakeTemplatesRepository(),
        audit_repository=FakeAuditRepository(),
    )

    with pytest.raises(KeyTemplateError, match="no implemented"):
        asyncio.run(
            service.create_from_calibration_proposal(
                preview=_preview(endpoints=("/v1/responses",)),
                name="Bad endpoint",
                reason="Reviewed",
                confirm_create_template=True,
            )
        )

    with pytest.raises(KeyTemplateError, match="Hosted capabilities"):
        asyncio.run(
            service.create_from_calibration_proposal(
                preview=_preview(allowed_hosted=("web_search",)),
                name="Hosted",
                reason="Reviewed",
                confirm_create_template=True,
            )
        )


def test_does_not_mutate_existing_gateway_keys() -> None:
    templates = FakeTemplatesRepository()
    service = KeyTemplateService(key_templates_repository=templates, audit_repository=FakeAuditRepository())

    asyncio.run(
        service.create_from_calibration_proposal(
            preview=_preview(),
            name="No key mutation",
            reason="Reviewed",
            confirm_create_template=True,
        )
    )

    assert len(templates.templates) == 1
    assert not hasattr(templates, "gateway_keys")


def _preview(
    *,
    empty: bool = False,
    endpoints: tuple[str, ...] = ("/v1/chat/completions",),
    allowed_hosted: tuple[str, ...] = (),
    extra_warning: str | None = None,
) -> CalibrationPreviewResult:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    key_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    request_count = 0 if empty else 2
    summary = CalibrationObservedSummary(
        gateway_key_id=key_id,
        public_key_id="public-calibration",
        owner_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        owner_email="owner@example.org",
        owner_display_name="Owner Name",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        time_window_start=now,
        time_window_end=now,
        observed_request_count=request_count,
        observed_endpoints=endpoints,
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
        proposed_allowed_endpoints=endpoints,
        proposed_allowed_models=("gpt-4.1-mini",),
        proposed_allowed_providers=("openai",),
        proposed_allowed_hosted_capabilities=allowed_hosted,
        hosted_capabilities_requiring_review=("web_search_options",),
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
        warnings=tuple(filter(None, (extra_warning,))),
        assumptions=("safe metadata only",),
        source_gateway_key_id=key_id,
        source_time_window_start=now,
        source_time_window_end=now,
        multiplier=Decimal("3"),
    )
    warnings = tuple(filter(None, (extra_warning,)))
    return CalibrationPreviewResult(summary=summary, proposal=proposal, is_empty=empty, warnings=warnings)
