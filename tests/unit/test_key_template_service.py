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
from slaif_gateway.schemas.keys import CreatedGatewayKey

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

    async def get_revision_for_admin_detail(self, revision_id):
        for revision in self.revisions:
            if revision.id == revision_id:
                return revision
        return None


class FakeAuditRepository:
    def __init__(self) -> None:
        self.rows = []

    async def add_audit_log(self, **kwargs):
        row = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.rows.append(row)
        return row


class FakeKeyService:
    def __init__(self) -> None:
        self.payloads = []

    async def create_gateway_key(self, payload):
        self.payloads.append(payload)
        return CreatedGatewayKey(
            gateway_key_id=uuid.uuid4(),
            owner_id=payload.owner_id,
            public_key_id="templatepublic",
            display_prefix="sk-slaif-templatepublic",
            plaintext_key="sk-slaif-templatepublic.once-only",
            one_time_secret_id=uuid.uuid4(),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            rate_limit_policy=payload.rate_limit_policy,
            key_purpose=payload.key_purpose,
            capability_policy_mode=payload.capability_policy_mode,
            template_id=payload.template_id,
            template_revision_id=payload.template_revision_id,
        )


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


def test_create_key_from_template_revision_creates_standard_key_with_provenance() -> None:
    templates = FakeTemplatesRepository()
    audit = FakeAuditRepository()
    key_service = FakeKeyService()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=audit,
        key_service=key_service,
    )
    template, revision = _template_revision(templates)
    owner_id = uuid.uuid4()

    result = asyncio.run(
        service.create_key_from_revision(
            template_revision_id=revision.id,
            owner_id=owner_id,
            reason="Reviewed template",
            confirm_create_key_from_template=True,
        )
    )

    assert result.template is template
    assert result.revision is revision
    assert result.created_key.key_purpose == "standard"
    assert result.created_key.capability_policy_mode == "standard"
    assert result.created_key.template_id == template.id
    assert result.created_key.template_revision_id == revision.id
    payload = key_service.payloads[0]
    assert payload.allowed_endpoints == ["/v1/chat/completions"]
    assert payload.allowed_models == ["gpt-4.1-mini"]
    assert payload.allowed_providers == ["openai"]
    assert payload.request_limit_total == 6
    assert payload.token_limit_total == 90
    assert payload.cost_limit_eur == Decimal("0.030000000")
    assert payload.template_id == template.id
    assert payload.template_revision_id == revision.id
    assert audit.rows[-1].action == "gateway_key.created_from_template"


def test_create_key_from_template_allows_safe_responses_policy_metadata() -> None:
    templates = FakeTemplatesRepository()
    audit = FakeAuditRepository()
    key_service = FakeKeyService()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=audit,
        key_service=key_service,
    )
    template, revision = _template_revision(
        templates,
        allowed_endpoints=["/v1/responses"],
        template_snapshot={"responses_policy": _responses_policy()},
    )

    result = asyncio.run(
        service.create_key_from_revision(
            template_revision_id=revision.id,
            owner_id=uuid.uuid4(),
            reason="Reviewed Responses template",
            confirm_create_key_from_template=True,
        )
    )

    payload = key_service.payloads[0]
    assert result.created_key.template_id == template.id
    assert payload.allowed_endpoints == ["/v1/responses"]
    assert payload.responses_policy == {
        "version": 1,
        "allowed_capabilities": [
            "text",
            "stateless",
            "streaming",
            "json_mode",
            "structured_outputs",
            "function_tools",
            "custom_tools",
            "image_input",
            "file_input",
        ],
        "allowed_local_tool_types": ["function", "custom"],
        "hosted_tools_allowed": [],
        "stateful": False,
        "storage": False,
        "background": False,
        "multimodal": False,
        "notes": "safe summary only",
    }
    assert "responses_policy" in audit.rows[-1].new_values


def test_create_key_from_template_rejects_unsafe_responses_policy_claims() -> None:
    templates = FakeTemplatesRepository()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=FakeAuditRepository(),
        key_service=FakeKeyService(),
    )
    _template, revision = _template_revision(
        templates,
        allowed_endpoints=["/v1/responses"],
        template_snapshot={"responses_policy": _responses_policy(storage=True)},
    )

    with pytest.raises(KeyTemplateError, match="storage"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )

    revision.template_snapshot = {"responses_policy": _responses_policy(hosted_tools_allowed=["web_search"])}
    with pytest.raises(KeyTemplateError, match="hosted tools"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )

    revision.template_snapshot = {"responses_policy": _responses_policy(extra_field="raw_tool_schema")}
    with pytest.raises(KeyTemplateError, match="unsupported Responses policy fields"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )

    revision.template_snapshot = {
        "responses_policy": _responses_policy(raw_image_url="https://example.test/secret.png")
    }
    with pytest.raises(KeyTemplateError, match="unsupported Responses policy fields"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )


def test_create_key_from_template_rejects_responses_without_safe_policy() -> None:
    templates = FakeTemplatesRepository()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=FakeAuditRepository(),
        key_service=FakeKeyService(),
    )
    _template, revision = _template_revision(templates, allowed_endpoints=["/v1/responses"])

    with pytest.raises(KeyTemplateError, match="no safe Responses policy"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )


def test_create_key_from_template_rejects_confirmation_archived_and_missing_owner_policy() -> None:
    templates = FakeTemplatesRepository()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=FakeAuditRepository(),
        key_service=FakeKeyService(),
    )
    template, revision = _template_revision(templates)
    owner_id = uuid.uuid4()

    with pytest.raises(KeyTemplateError, match="Confirm"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=owner_id,
                reason="Reviewed",
                confirm_create_key_from_template=False,
            )
        )

    template.status = "archived"
    with pytest.raises(KeyTemplateError, match="Archived"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=owner_id,
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )
    template.status = "active"
    revision.allowed_endpoints = ["/v1/completions"]
    with pytest.raises(KeyTemplateError, match="no implemented"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=owner_id,
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )


def test_create_key_from_template_rejects_review_required_hosted_capabilities() -> None:
    templates = FakeTemplatesRepository()
    service = KeyTemplateService(
        key_templates_repository=templates,
        audit_repository=FakeAuditRepository(),
        key_service=FakeKeyService(),
    )
    _template, revision = _template_revision(templates)
    revision.hosted_capabilities_requiring_review = ["web_search_options"]

    with pytest.raises(KeyTemplateError, match="hosted capabilities"):
        asyncio.run(
            service.create_key_from_revision(
                template_revision_id=revision.id,
                owner_id=uuid.uuid4(),
                reason="Reviewed",
                confirm_create_key_from_template=True,
            )
        )


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


def _template_revision(
    templates: FakeTemplatesRepository,
    *,
    allowed_endpoints: list[str] | None = None,
    template_snapshot: dict[str, object] | None = None,
):
    template = SimpleNamespace(
        id=uuid.uuid4(),
        name="Participants",
        status="active",
        current_revision_id=None,
        revisions=[],
    )
    revision = SimpleNamespace(
        id=uuid.uuid4(),
        template_id=template.id,
        template=template,
        revision_number=1,
        allowed_endpoints=allowed_endpoints or ["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=[],
        request_limit_total=6,
        token_limit_total=90,
        cost_limit_eur=Decimal("0.030000000"),
        rate_limit_policy={"requests_per_minute": 20},
        validity_days_default=14,
        template_snapshot=template_snapshot or {},
    )
    template.current_revision_id = revision.id
    template.revisions.append(revision)
    templates.templates.append(template)
    templates.revisions.append(revision)
    return template, revision


def _responses_policy(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "version": 1,
        "allowed_capabilities": [
            "text",
            "stateless",
            "streaming",
            "json_mode",
            "structured_outputs",
            "function_tools",
            "custom_tools",
            "image_input",
            "file_input",
        ],
        "allowed_local_tool_types": ["function", "custom"],
        "hosted_tools_allowed": [],
        "stateful": False,
        "storage": False,
        "background": False,
        "multimodal": False,
        "notes": "safe summary only",
    }
    policy.update(overrides)
    return policy
