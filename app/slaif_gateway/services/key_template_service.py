"""Key template creation from reviewed calibration proposals."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from slaif_gateway.db.models import AuditLog, KeyTemplate, KeyTemplateRevision
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, CreatedGatewayKey
from slaif_gateway.services.calibration_summary_service import CalibrationPreviewResult
from slaif_gateway.services.key_policy_validation import (
    IMPLEMENTED_CLIENT_ENDPOINTS,
    RESPONSES_ENDPOINT,
)
from slaif_gateway.services.responses_route_capabilities import (
    RESPONSES_CAPABILITY_CUSTOM_TOOLS,
    RESPONSES_CAPABILITY_FILE_INPUT,
    RESPONSES_CAPABILITY_FUNCTION_TOOLS,
    RESPONSES_CAPABILITY_IMAGE_INPUT,
    RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT,
    RESPONSES_CAPABILITY_JSON_MODE,
    RESPONSES_CAPABILITY_STATELESS,
    RESPONSES_CAPABILITY_STORED_RESPONSES,
    RESPONSES_CAPABILITY_STREAMING,
    RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS,
    RESPONSES_CAPABILITY_TEXT,
)
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

_CALIBRATION_TEMPLATE_UNIMPLEMENTED_ENDPOINTS = frozenset({RESPONSES_ENDPOINT, "/v1/completions"})
_TEMPLATE_KEY_UNIMPLEMENTED_ENDPOINTS = frozenset({"/v1/completions"})
_ALLOWED_DEFAULT_EMAIL_MODES = frozenset({"none", "pending"})
_RESPONSES_POLICY_KEY = "responses_policy"
_RESPONSES_POLICY_ALLOWED_KEYS = frozenset(
    {
        "version",
        "allowed_capabilities",
        "allowed_local_tool_types",
        "hosted_tools_allowed",
        "stateful",
        "storage",
        "background",
        "multimodal",
        "notes",
    }
)
_RESPONSES_POLICY_ALLOWED_CAPABILITIES = frozenset(
    {
        RESPONSES_CAPABILITY_TEXT,
        RESPONSES_CAPABILITY_STATELESS,
        RESPONSES_CAPABILITY_STREAMING,
        RESPONSES_CAPABILITY_JSON_MODE,
        RESPONSES_CAPABILITY_STRUCTURED_OUTPUTS,
        RESPONSES_CAPABILITY_FUNCTION_TOOLS,
        RESPONSES_CAPABILITY_CUSTOM_TOOLS,
        RESPONSES_CAPABILITY_IMAGE_INPUT,
        RESPONSES_CAPABILITY_FILE_INPUT,
        RESPONSES_CAPABILITY_INPUT_TOKEN_COUNT,
        RESPONSES_CAPABILITY_STORED_RESPONSES,
    }
)
_RESPONSES_POLICY_REQUIRED_BASE_CAPABILITIES = frozenset(
    {RESPONSES_CAPABILITY_TEXT, RESPONSES_CAPABILITY_STATELESS}
)
_RESPONSES_POLICY_ALLOWED_LOCAL_TOOL_TYPES = frozenset({"function", "custom"})
_RESPONSES_POLICY_FORBIDDEN_FLAGS = ("stateful", "storage", "background", "multimodal")


class KeyTemplateError(ValueError):
    """Safe user-facing key template error."""


@dataclass(frozen=True, slots=True)
class KeyTemplateCreationResult:
    template: KeyTemplate
    revision: KeyTemplateRevision
    audit_log: AuditLog


@dataclass(frozen=True, slots=True)
class KeyFromTemplateCreationResult:
    created_key: CreatedGatewayKey
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

    async def get_revision_for_admin_detail(
        self,
        revision_id: uuid.UUID,
    ) -> KeyTemplateRevision | None:
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


class _KeyService(Protocol):
    async def create_gateway_key(self, payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
        pass


class KeyTemplateService:
    """Create durable key templates from reviewed safe calibration proposals."""

    def __init__(
        self,
        *,
        key_templates_repository: _KeyTemplatesRepository,
        audit_repository: _AuditRepository,
        key_service: _KeyService | None = None,
    ) -> None:
        self._key_templates = key_templates_repository
        self._audit = audit_repository
        self._key_service = key_service

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
        implemented = set(IMPLEMENTED_CLIENT_ENDPOINTS) - _CALIBRATION_TEMPLATE_UNIMPLEMENTED_ENDPOINTS
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

    async def create_key_from_revision(
        self,
        *,
        template_revision_id: uuid.UUID,
        owner_id: uuid.UUID,
        cohort_id: uuid.UUID | None = None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str,
        confirm_create_key_from_template: bool,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        valid_days: int | None = None,
    ) -> KeyFromTemplateCreationResult:
        if self._key_service is None:
            raise KeyTemplateError("Key service is required for template key creation.")
        cleaned_reason = _clean_required_reason(reason)
        if not confirm_create_key_from_template:
            raise KeyTemplateError("Confirm key creation from template before continuing.")

        revision = await self._key_templates.get_revision_for_admin_detail(template_revision_id)
        if revision is None:
            raise KeyTemplateError("Template revision not found.")
        template = getattr(revision, "template", None)
        if template is None:
            raise KeyTemplateError("Template revision is not attached to a template.")
        if getattr(template, "status", None) != "active":
            raise KeyTemplateError("Archived or inactive templates cannot create keys.")
        if revision.allowed_hosted_capabilities or revision.hosted_capabilities_requiring_review:
            raise KeyTemplateError(
                "This template contains hosted capabilities that require review; "
                "participant keys are not created from it yet."
            )

        implemented = set(IMPLEMENTED_CLIENT_ENDPOINTS) - _TEMPLATE_KEY_UNIMPLEMENTED_ENDPOINTS
        allowed_endpoints = [endpoint for endpoint in revision.allowed_endpoints if endpoint in implemented]
        if not allowed_endpoints:
            raise KeyTemplateError("Template revision has no implemented participant endpoints.")
        if set(revision.allowed_endpoints) - set(allowed_endpoints):
            raise KeyTemplateError("Template revision includes unsupported endpoints.")
        responses_policy = _responses_policy_for_revision(revision)

        start = _coerce_valid_from(valid_from)
        until = _resolve_template_valid_until(
            valid_from=start,
            valid_until=valid_until,
            valid_days=valid_days,
            default_validity_days=revision.validity_days_default,
        )
        if until <= start:
            raise KeyTemplateError("Template key validity window is invalid.")

        payload = CreateGatewayKeyInput(
            owner_id=owner_id,
            cohort_id=cohort_id,
            created_by_admin_id=actor_admin_id,
            valid_from=start,
            valid_until=until,
            cost_limit_eur=revision.cost_limit_eur,
            token_limit_total=revision.token_limit_total,
            request_limit_total=revision.request_limit_total,
            allowed_models=list(revision.allowed_models or []),
            allowed_endpoints=allowed_endpoints,
            allow_all_models=False,
            allow_all_endpoints=False,
            key_purpose="standard",
            capability_policy_mode="standard",
            responses_policy=responses_policy,
            template_id=template.id,
            template_revision_id=revision.id,
            allowed_providers=list(revision.allowed_providers) if revision.allowed_providers else None,
            rate_limit_policy=_rate_limit_policy_for_key(revision.rate_limit_policy),
            note=cleaned_reason,
        )
        created = await self._key_service.create_gateway_key(payload)
        audit = await self._audit.add_audit_log(
            action="gateway_key.created_from_template",
            entity_type="gateway_key",
            admin_user_id=actor_admin_id,
            entity_id=created.gateway_key_id,
            new_values={
                "gateway_key_id": str(created.gateway_key_id),
                "owner_id": str(owner_id),
                "cohort_id": str(cohort_id) if cohort_id else None,
                "template_id": str(template.id),
                "template_revision_id": str(revision.id),
                "template_revision_number": revision.revision_number,
                "allowed_endpoint_count": len(allowed_endpoints),
                "allowed_model_count": len(revision.allowed_models or []),
                "request_limit_total": revision.request_limit_total,
                "token_limit_total": revision.token_limit_total,
                "cost_limit_eur": str(revision.cost_limit_eur) if revision.cost_limit_eur else None,
                "responses_policy": responses_policy,
            },
            note=cleaned_reason,
        )
        return KeyFromTemplateCreationResult(
            created_key=created,
            template=template,
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


def _coerce_valid_from(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_template_valid_until(
    *,
    valid_from: datetime,
    valid_until: datetime | None,
    valid_days: int | None,
    default_validity_days: int | None,
) -> datetime:
    if valid_until is not None and valid_days is not None:
        raise KeyTemplateError("Use either valid_until or valid_days, not both.")
    if valid_days is not None:
        if valid_days <= 0:
            raise KeyTemplateError("valid_days must be positive.")
        return valid_from + timedelta(days=valid_days)
    if valid_until is not None:
        if valid_until.tzinfo is None:
            return valid_until.replace(tzinfo=UTC)
        return valid_until.astimezone(UTC)
    if default_validity_days is None:
        raise KeyTemplateError("Template revision has no default validity; provide valid_days or valid_until.")
    return valid_from + timedelta(days=default_validity_days)


def _rate_limit_policy_for_key(value: object) -> dict[str, int | None] | None:
    if not isinstance(value, dict):
        return None
    allowed_names = {
        "requests_per_minute",
        "tokens_per_minute",
        "max_concurrent_requests",
        "window_seconds",
    }
    policy: dict[str, int | None] = {}
    for name in allowed_names:
        item = value.get(name)
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise KeyTemplateError("Template revision has an invalid rate-limit policy.")
        policy[name] = item
    return policy or None


def _responses_policy_for_revision(revision: KeyTemplateRevision) -> dict[str, object] | None:
    endpoints = set(getattr(revision, "allowed_endpoints", None) or [])
    snapshot = getattr(revision, "template_snapshot", None)
    raw_policy = snapshot.get(_RESPONSES_POLICY_KEY) if isinstance(snapshot, dict) else None
    if raw_policy is None:
        if RESPONSES_ENDPOINT in endpoints:
            raise KeyTemplateError(
                "Template revision allows /v1/responses but has no safe Responses policy summary."
            )
        return None
    return _normalize_responses_template_policy(raw_policy)


def _normalize_responses_template_policy(raw_policy: object) -> dict[str, object]:
    if not isinstance(raw_policy, dict):
        raise KeyTemplateError("Template revision has an invalid Responses policy summary.")
    unknown_keys = set(str(key) for key in raw_policy) - _RESPONSES_POLICY_ALLOWED_KEYS
    if unknown_keys:
        raise KeyTemplateError("Template revision has unsupported Responses policy fields.")

    version = raw_policy.get("version")
    if isinstance(version, bool) or version != 1:
        raise KeyTemplateError("Template revision has an unsupported Responses policy version.")

    capabilities = _clean_string_list(
        raw_policy.get("allowed_capabilities"),
        allowed_values=_RESPONSES_POLICY_ALLOWED_CAPABILITIES,
        field_name="Responses capabilities",
    )
    if not _RESPONSES_POLICY_REQUIRED_BASE_CAPABILITIES.issubset(capabilities):
        raise KeyTemplateError("Responses template policy must include text and stateless capabilities.")

    local_tool_types = _clean_string_list(
        raw_policy.get("allowed_local_tool_types", []),
        allowed_values=_RESPONSES_POLICY_ALLOWED_LOCAL_TOOL_TYPES,
        field_name="Responses local tool types",
    )
    if RESPONSES_CAPABILITY_FUNCTION_TOOLS in capabilities and "function" not in local_tool_types:
        raise KeyTemplateError("Responses function-tool capability requires the function local tool type.")
    if RESPONSES_CAPABILITY_CUSTOM_TOOLS in capabilities and "custom" not in local_tool_types:
        raise KeyTemplateError("Responses custom-tool capability requires the custom local tool type.")
    if "function" in local_tool_types and RESPONSES_CAPABILITY_FUNCTION_TOOLS not in capabilities:
        raise KeyTemplateError("Responses function local tool type requires function_tools capability.")
    if "custom" in local_tool_types and RESPONSES_CAPABILITY_CUSTOM_TOOLS not in capabilities:
        raise KeyTemplateError("Responses custom local tool type requires custom_tools capability.")

    hosted_tools = raw_policy.get("hosted_tools_allowed", [])
    if hosted_tools not in ([], ()):
        raise KeyTemplateError("Responses hosted tools remain unsupported for template-created keys.")
    for flag in _RESPONSES_POLICY_FORBIDDEN_FLAGS:
        value = raw_policy.get(flag, False)
        if value is not False:
            raise KeyTemplateError(f"Responses template policy cannot enable {flag}.")

    policy: dict[str, object] = {
        "version": 1,
        "allowed_capabilities": list(capabilities),
        "allowed_local_tool_types": list(local_tool_types),
        "hosted_tools_allowed": [],
        "stateful": False,
        "storage": False,
        "background": False,
        "multimodal": False,
    }
    notes = raw_policy.get("notes")
    if notes is not None:
        cleaned_notes = _clean_optional_text(str(notes))
        if cleaned_notes:
            if len(cleaned_notes) > 1000:
                raise KeyTemplateError("Responses template policy notes are too long.")
            policy["notes"] = cleaned_notes
    sanitized = sanitize_metadata_mapping(policy, drop_content_keys=True)
    if not isinstance(sanitized, dict):
        raise KeyTemplateError("Template revision has an invalid Responses policy summary.")
    return sanitized


def _clean_string_list(
    value: object,
    *,
    allowed_values: frozenset[str],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KeyTemplateError(f"{field_name} must be a list.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise KeyTemplateError(f"{field_name} must use string values.")
        normalized = item.strip()
        if normalized not in allowed_values:
            raise KeyTemplateError(f"{field_name} includes an unsupported value.")
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return tuple(cleaned)
