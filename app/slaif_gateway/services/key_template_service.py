"""Key template creation from reviewed calibration proposals."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from slaif_gateway.db.models import AuditLog, KeyTemplate, KeyTemplateRevision
from slaif_gateway.services.calibration_summary_service import CalibrationPreviewResult
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

_UNIMPLEMENTED_ENDPOINTS = frozenset({"/v1/responses", "/v1/completions"})
_ALLOWED_DEFAULT_EMAIL_MODES = frozenset({"none", "pending"})


class KeyTemplateError(ValueError):
    """Safe user-facing key template error."""


@dataclass(frozen=True, slots=True)
class KeyTemplateCreationResult:
    template: KeyTemplate
    revision: KeyTemplateRevision
    audit_log: AuditLog


class _KeyTemplatesRepository(Protocol):
    async def create_template_record(
        self,
        *,
        name: str,
        description: str | None = None,
        created_by_admin_id: uuid.UUID | None = None,
        notes: str | None = None,
        status: str = "active",
    ) -> KeyTemplate:
        pass

    async def create_revision_record(
        self,
        *,
        template_id: uuid.UUID,
        revision_number: int,
        created_by_admin_id: uuid.UUID | None,
        source_type: str,
        source_calibration_gateway_key_id: uuid.UUID | None,
        source_time_window_start: datetime | None,
        source_time_window_end: datetime | None,
        source_multiplier: Decimal | None,
        allowed_endpoints: list[str],
        allowed_models: list[str],
        allowed_providers: list[str],
        allowed_hosted_capabilities: list[str],
        hosted_capabilities_requiring_review: list[str],
        request_limit_total: int,
        token_limit_total: int,
        input_token_limit_total: int | None = None,
        output_token_limit_total: int | None = None,
        reasoning_token_limit_total: int | None = None,
        cost_limit_eur: Decimal | None = None,
        max_input_tokens_per_request: int | None = None,
        max_output_tokens_per_request: int | None = None,
        max_total_tokens_per_request: int | None = None,
        max_single_request_cost_eur: Decimal | None = None,
        rate_limit_policy: dict[str, object] | None = None,
        validity_days_default: int | None = None,
        email_delivery_mode_default: str | None = None,
        template_snapshot: dict[str, object] | None = None,
        created_audit_log_id: uuid.UUID | None = None,
    ) -> KeyTemplateRevision:
        pass

    async def set_current_revision(
        self,
        *,
        template_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> KeyTemplate | None:
        pass


class _AuditRepository(Protocol):
    async def add_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        admin_user_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        note: str | None = None,
    ) -> AuditLog:
        pass


class KeyTemplateService:
    """Create durable key templates from reviewed safe calibration proposals."""

    def __init__(
        self,
        *,
        key_templates_repository: _KeyTemplatesRepository,
        audit_repository: _AuditRepository,
    ) -> None:
        self._key_templates = key_templates_repository
        self._audit = audit_repository

    async def create_from_calibration_proposal(
        self,
        *,
        preview: CalibrationPreviewResult,
        name: str,
        description: str | None = None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str,
        confirm_create_template: bool,
        validity_days_default: int | None = None,
        email_delivery_mode_default: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> KeyTemplateCreationResult:
        cleaned_name = _clean_required_name(name)
        cleaned_reason = _clean_required_reason(reason)
        cleaned_description = _clean_optional_text(description)
        cleaned_email_mode = _clean_email_mode(email_delivery_mode_default)
        if not confirm_create_template:
            raise KeyTemplateError("Confirm template creation before continuing.")
        if preview.is_empty or preview.summary.observed_request_count == 0:
            raise KeyTemplateError("Refusing to create a template from an empty calibration proposal.")
        if validity_days_default is not None and validity_days_default <= 0:
            raise KeyTemplateError("validity_days_default must be positive.")

        proposal = preview.proposal
        implemented = set(IMPLEMENTED_CLIENT_ENDPOINTS) - _UNIMPLEMENTED_ENDPOINTS
        endpoints = tuple(endpoint for endpoint in proposal.proposed_allowed_endpoints if endpoint in implemented)
        if not endpoints:
            raise KeyTemplateError("Calibration proposal has no implemented participant endpoints.")
        dropped_endpoints = set(proposal.proposed_allowed_endpoints) - set(endpoints)
        if dropped_endpoints:
            raise KeyTemplateError("Calibration proposal includes unsupported endpoints.")
        if proposal.proposed_allowed_hosted_capabilities:
            raise KeyTemplateError("Hosted capabilities must remain review-required in this template workflow.")
        if proposal.proposed_request_limit_total <= 0:
            raise KeyTemplateError("Calibration proposal request limit must be positive.")
        if proposal.proposed_token_limit_total < 0:
            raise KeyTemplateError("Calibration proposal token limit must be non-negative.")

        snapshot = _safe_snapshot(preview)
        template = await self._key_templates.create_template_record(
            name=cleaned_name,
            description=cleaned_description,
            created_by_admin_id=actor_admin_id,
            notes="Created from reviewed trusted calibration proposal.",
        )
        audit = await self._audit.add_audit_log(
            action="key_template.created",
            entity_type="key_template",
            admin_user_id=actor_admin_id,
            entity_id=template.id,
            new_values={
                "template_name": cleaned_name,
                "source_calibration_gateway_key_id": str(proposal.source_gateway_key_id),
                "source_time_window_start": _json_value(proposal.source_time_window_start),
                "source_time_window_end": _json_value(proposal.source_time_window_end),
                "multiplier": str(proposal.multiplier),
                "revision_number": 1,
                "allowed_endpoint_count": len(endpoints),
                "allowed_model_count": len(proposal.proposed_allowed_models),
                "hosted_capabilities_requiring_review_count": len(
                    proposal.hosted_capabilities_requiring_review
                ),
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            note=cleaned_reason,
        )
        revision = await self._key_templates.create_revision_record(
            template_id=template.id,
            revision_number=1,
            created_by_admin_id=actor_admin_id,
            source_type="calibration_proposal",
            source_calibration_gateway_key_id=proposal.source_gateway_key_id,
            source_time_window_start=proposal.source_time_window_start,
            source_time_window_end=proposal.source_time_window_end,
            source_multiplier=proposal.multiplier,
            allowed_endpoints=list(endpoints),
            allowed_models=list(proposal.proposed_allowed_models),
            allowed_providers=list(proposal.proposed_allowed_providers),
            allowed_hosted_capabilities=[],
            hosted_capabilities_requiring_review=list(
                proposal.hosted_capabilities_requiring_review
            ),
            request_limit_total=proposal.proposed_request_limit_total,
            token_limit_total=proposal.proposed_token_limit_total,
            input_token_limit_total=proposal.proposed_input_token_limit_total,
            output_token_limit_total=proposal.proposed_output_token_limit_total,
            reasoning_token_limit_total=proposal.proposed_reasoning_token_limit_total,
            cost_limit_eur=proposal.proposed_cost_limit_eur,
            max_input_tokens_per_request=proposal.proposed_max_input_tokens_per_request,
            max_output_tokens_per_request=proposal.proposed_max_output_tokens_per_request,
            max_total_tokens_per_request=proposal.proposed_max_total_tokens_per_request,
            max_single_request_cost_eur=proposal.proposed_max_single_request_cost_eur,
            rate_limit_policy=proposal.proposed_rate_limit_policy,
            validity_days_default=validity_days_default,
            email_delivery_mode_default=cleaned_email_mode,
            template_snapshot=snapshot,
            created_audit_log_id=audit.id,
        )
        updated_template = await self._key_templates.set_current_revision(
            template_id=template.id,
            revision_id=revision.id,
        )
        return KeyTemplateCreationResult(
            template=updated_template or template,
            revision=revision,
            audit_log=audit,
        )


def _safe_snapshot(preview: CalibrationPreviewResult) -> dict[str, object]:
    payload = {
        "source_type": "calibration_proposal",
        "summary": asdict(preview.summary),
        "proposal": asdict(preview.proposal),
        "warnings": list(preview.warnings),
        "is_empty": preview.is_empty,
        "template_creation_note": (
            "Participant key creation is future work; hosted capabilities remain review-required."
        ),
    }
    sanitized = sanitize_metadata_mapping(_json_value(payload), drop_content_keys=True)
    cleaned = _drop_forbidden_text_values(sanitized)
    return cleaned if isinstance(cleaned, dict) else {}


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


_FORBIDDEN_TEXT_MARKERS = (
    "prompt",
    "completion",
    "raw request",
    "raw response",
    "request body",
    "response body",
    "tool schema",
    "tool argument",
    "tool result",
    "authorization",
    "cookie",
    "csrf_token",
    "session_token",
    "encrypted_payload",
    "nonce",
    "provider key",
    "gateway plaintext",
    "chain-of-thought",
)


def _drop_forbidden_text_values(value: object) -> object:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_TEXT_MARKERS):
            return "[removed]"
        return value
    if isinstance(value, list):
        return [_drop_forbidden_text_values(item) for item in value]
    if isinstance(value, dict):
        return {key: _drop_forbidden_text_values(item) for key, item in value.items()}
    return value


def _clean_required_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise KeyTemplateError("Template name is required.")
    if len(cleaned) > 200:
        raise KeyTemplateError("Template name is too long.")
    return cleaned


def _clean_required_reason(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise KeyTemplateError("Audit reason is required.")
    if len(cleaned) > 1000:
        raise KeyTemplateError("Audit reason is too long.")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_email_mode(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        return None
    if cleaned not in _ALLOWED_DEFAULT_EMAIL_MODES:
        raise KeyTemplateError("Default email delivery mode must be none or pending.")
    return cleaned
