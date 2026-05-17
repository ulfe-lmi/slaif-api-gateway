"""Preview-only calibration usage summaries and strict policy proposals."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from typing import Protocol

from slaif_gateway.db.models import GatewayKey, UsageProfile
from slaif_gateway.services.key_modes import is_trusted_calibration_key
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS

_MIN_MULTIPLIER = Decimal("1.0")
_MAX_MULTIPLIER = Decimal("10.0")
_UNIMPLEMENTED_ENDPOINTS = frozenset({"/v1/responses", "/v1/completions"})


class CalibrationSummaryError(ValueError):
    """Safe user-facing calibration summary error."""


class _GatewayKeysRepository(Protocol):
    async def get_key_for_admin_detail(self, gateway_key_id: uuid.UUID) -> GatewayKey | None: ...


class _UsageProfilesRepository(Protocol):
    async def list_for_gateway_key(
        self,
        gateway_key_id: uuid.UUID,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = 100,
    ) -> list[UsageProfile]: ...


@dataclass(frozen=True, slots=True)
class CalibrationObservedSummary:
    gateway_key_id: uuid.UUID
    public_key_id: str
    owner_id: uuid.UUID | None
    owner_email: str | None
    owner_display_name: str | None
    institution_id: uuid.UUID | None
    institution_name: str | None
    cohort_id: uuid.UUID | None
    cohort_name: str | None
    time_window_start: datetime | None
    time_window_end: datetime | None
    observed_request_count: int
    observed_endpoints: tuple[str, ...]
    observed_providers: tuple[str, ...]
    observed_requested_models: tuple[str, ...]
    observed_resolved_upstream_models: tuple[str, ...]
    observed_provider_hosts: tuple[str, ...]
    observed_provider_endpoint_paths: tuple[str, ...]
    observed_hosted_capabilities: tuple[str, ...]
    observed_unknown_hosted_capabilities: tuple[str, ...]
    observed_denied_capabilities: tuple[str, ...]
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_reasoning_tokens: int | None
    total_cached_tokens: int | None
    max_input_tokens_per_request: int
    max_output_tokens_per_request: int
    max_total_tokens_per_request: int
    max_reasoning_tokens_per_request: int | None
    max_cached_tokens_per_request: int | None
    total_slaif_calculated_cost: Decimal | None
    total_provider_reported_cost: Decimal | None
    max_slaif_calculated_cost_per_request: Decimal | None
    max_provider_reported_cost_per_request: Decimal | None
    cost_currencies: tuple[str, ...]
    cost_confidence: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CalibrationPolicyProposal:
    proposed_allowed_endpoints: tuple[str, ...]
    proposed_allowed_models: tuple[str, ...]
    proposed_allowed_providers: tuple[str, ...]
    proposed_allowed_hosted_capabilities: tuple[str, ...]
    hosted_capabilities_requiring_review: tuple[str, ...]
    proposed_request_limit_total: int
    proposed_token_limit_total: int
    proposed_input_token_limit_total: int
    proposed_output_token_limit_total: int
    proposed_reasoning_token_limit_total: int | None
    proposed_cost_limit_eur: Decimal | None
    proposed_max_input_tokens_per_request: int
    proposed_max_output_tokens_per_request: int
    proposed_max_total_tokens_per_request: int
    proposed_max_single_request_cost_eur: Decimal | None
    proposed_rate_limit_policy: dict[str, int] | None
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    source_gateway_key_id: uuid.UUID
    source_time_window_start: datetime | None
    source_time_window_end: datetime | None
    multiplier: Decimal


@dataclass(frozen=True, slots=True)
class CalibrationPreviewResult:
    summary: CalibrationObservedSummary
    proposal: CalibrationPolicyProposal
    is_empty: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


class CalibrationSummaryService:
    """Build preview-only calibration summaries from safe usage profile rows."""

    def __init__(
        self,
        *,
        gateway_keys_repository: _GatewayKeysRepository,
        usage_profiles_repository: _UsageProfilesRepository,
    ) -> None:
        self._gateway_keys_repository = gateway_keys_repository
        self._usage_profiles_repository = usage_profiles_repository

    async def summarize_calibration_key_usage(
        self,
        *,
        gateway_key_id: uuid.UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        multiplier: Decimal = Decimal("3"),
        minimum_request_limit: int = 1,
    ) -> CalibrationPreviewResult:
        multiplier = validate_multiplier(multiplier)
        start_at = _normalize_datetime(start_at)
        end_at = _normalize_datetime(end_at)
        if start_at is not None and end_at is not None and end_at < start_at:
            raise CalibrationSummaryError("end_at must be greater than or equal to start_at.")
        if minimum_request_limit < 1:
            raise CalibrationSummaryError("minimum_request_limit must be positive.")

        key = await self._gateway_keys_repository.get_key_for_admin_detail(gateway_key_id)
        if key is None:
            raise CalibrationSummaryError("Gateway key not found.")
        if not is_trusted_calibration_key(
            key_purpose=str(getattr(key, "key_purpose", "standard") or "standard"),
            capability_policy_mode=str(getattr(key, "capability_policy_mode", "standard") or "standard"),
        ):
            raise CalibrationSummaryError("Calibration summaries are available only for trusted calibration keys.")

        rows = await self._usage_profiles_repository.list_for_gateway_key(
            gateway_key_id,
            start_at=start_at,
            end_at=end_at,
            limit=None,
        )
        summary = _build_observed_summary(
            key=key,
            rows=rows,
            start_at=start_at,
            end_at=end_at,
        )
        proposal = build_participant_policy_proposal(
            summary,
            multiplier=multiplier,
            minimum_request_limit=minimum_request_limit,
        )
        warnings = tuple(dict.fromkeys((*summary.warnings, *proposal.warnings)))
        return CalibrationPreviewResult(
            summary=summary,
            proposal=proposal,
            is_empty=summary.observed_request_count == 0,
            warnings=warnings,
        )


def build_participant_policy_proposal(
    summary: CalibrationObservedSummary,
    *,
    multiplier: Decimal,
    minimum_request_limit: int = 1,
) -> CalibrationPolicyProposal:
    multiplier = validate_multiplier(multiplier)
    implemented = set(IMPLEMENTED_CLIENT_ENDPOINTS) - _UNIMPLEMENTED_ENDPOINTS
    endpoints = tuple(endpoint for endpoint in summary.observed_endpoints if endpoint in implemented)
    warnings: list[str] = []
    assumptions = [
        "Proposal is advisory and preview-only; it does not create templates or keys.",
        "Limits are derived from safe usage-profile metadata and require admin review.",
        "Cost limits are SLAIF local accounting assumptions, not invoice-grade provider guarantees.",
        "Admins should narrow participant policies before issuing keys.",
    ]

    dropped_endpoints = sorted(set(summary.observed_endpoints) - set(endpoints))
    if dropped_endpoints:
        warnings.append(
            "Observed unsupported endpoints were excluded from the participant proposal: "
            + ", ".join(dropped_endpoints)
        )
    if summary.observed_request_count == 0:
        warnings.append("Not enough usage-profile data to build a reliable participant policy.")
    if summary.observed_unknown_hosted_capabilities:
        warnings.append(
            "Unknown hosted capabilities were observed and are not allowed by default for participant keys."
        )
    if summary.observed_hosted_capabilities:
        warnings.append(
            "Hosted capabilities were observed; review them explicitly before any future participant policy allows them."
        )
    if summary.observed_denied_capabilities:
        warnings.append("External MCP/connectors or provider authority markers remain denied by default.")

    request_limit = max(
        minimum_request_limit,
        _ceil_int(Decimal(summary.observed_request_count) * multiplier),
    )
    return CalibrationPolicyProposal(
        proposed_allowed_endpoints=endpoints,
        proposed_allowed_models=summary.observed_requested_models,
        proposed_allowed_providers=summary.observed_providers,
        proposed_allowed_hosted_capabilities=(),
        hosted_capabilities_requiring_review=summary.observed_hosted_capabilities,
        proposed_request_limit_total=request_limit,
        proposed_token_limit_total=_ceil_int(Decimal(summary.total_tokens) * multiplier),
        proposed_input_token_limit_total=_ceil_int(Decimal(summary.total_input_tokens) * multiplier),
        proposed_output_token_limit_total=_ceil_int(Decimal(summary.total_output_tokens) * multiplier),
        proposed_reasoning_token_limit_total=_ceil_optional_int(summary.total_reasoning_tokens, multiplier),
        proposed_cost_limit_eur=_multiply_optional_decimal(summary.total_slaif_calculated_cost, multiplier),
        proposed_max_input_tokens_per_request=_ceil_int(
            Decimal(summary.max_input_tokens_per_request) * multiplier
        ),
        proposed_max_output_tokens_per_request=_ceil_int(
            Decimal(summary.max_output_tokens_per_request) * multiplier
        ),
        proposed_max_total_tokens_per_request=_ceil_int(
            Decimal(summary.max_total_tokens_per_request) * multiplier
        ),
        proposed_max_single_request_cost_eur=_multiply_optional_decimal(
            summary.max_slaif_calculated_cost_per_request,
            multiplier,
        ),
        proposed_rate_limit_policy=None,
        warnings=tuple(dict.fromkeys(warnings)),
        assumptions=tuple(assumptions),
        source_gateway_key_id=summary.gateway_key_id,
        source_time_window_start=summary.time_window_start,
        source_time_window_end=summary.time_window_end,
        multiplier=multiplier,
    )


def validate_multiplier(value: Decimal) -> Decimal:
    try:
        multiplier = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CalibrationSummaryError("multiplier must be a decimal value.") from exc
    if not multiplier.is_finite() or multiplier < _MIN_MULTIPLIER or multiplier > _MAX_MULTIPLIER:
        raise CalibrationSummaryError("multiplier must be between 1.0 and 10.0.")
    return multiplier


def _build_observed_summary(
    *,
    key: GatewayKey,
    rows: Sequence[UsageProfile],
    start_at: datetime | None,
    end_at: datetime | None,
) -> CalibrationObservedSummary:
    owner = getattr(key, "owner", None)
    institution = getattr(owner, "institution", None) if owner is not None else None
    cohort = getattr(key, "cohort", None)
    warnings: list[str] = []
    if not rows:
        warnings.append("Not enough data: no usage-profile rows exist for this key and window.")

    reasoning_counts = [row.reasoning_tokens for row in rows if row.reasoning_tokens is not None]
    cached_counts = [row.cached_tokens for row in rows if row.cached_tokens is not None]
    slaif_costs = [row.slaif_calculated_cost for row in rows if row.slaif_calculated_cost is not None]
    provider_costs = [row.provider_reported_cost for row in rows if row.provider_reported_cost is not None]
    cost_sources = _sorted_non_empty(row.cost_source for row in rows)

    return CalibrationObservedSummary(
        gateway_key_id=key.id,
        public_key_id=key.public_key_id,
        owner_id=getattr(key, "owner_id", None),
        owner_email=getattr(owner, "email", None),
        owner_display_name=_owner_display_name(owner),
        institution_id=getattr(institution, "id", None),
        institution_name=getattr(institution, "name", None),
        cohort_id=getattr(key, "cohort_id", None),
        cohort_name=getattr(cohort, "name", None),
        time_window_start=start_at,
        time_window_end=end_at,
        observed_request_count=len(rows),
        observed_endpoints=_sorted_non_empty(row.endpoint_path for row in rows),
        observed_providers=_sorted_non_empty(row.provider for row in rows),
        observed_requested_models=_sorted_non_empty(row.requested_model for row in rows),
        observed_resolved_upstream_models=_sorted_non_empty(row.resolved_upstream_model for row in rows),
        observed_provider_hosts=_sorted_non_empty(row.provider_host for row in rows),
        observed_provider_endpoint_paths=_sorted_non_empty(row.provider_endpoint_path for row in rows),
        observed_hosted_capabilities=_metadata_set(rows, "observed_hosted_capability_types"),
        observed_unknown_hosted_capabilities=_metadata_set(rows, "unknown_hosted_capability_types"),
        observed_denied_capabilities=_metadata_set(rows, "denied_external_authority_markers"),
        total_input_tokens=sum(int(row.input_tokens or 0) for row in rows),
        total_output_tokens=sum(int(row.output_tokens or 0) for row in rows),
        total_tokens=sum(int(row.total_tokens or 0) for row in rows),
        total_reasoning_tokens=sum(reasoning_counts) if reasoning_counts else None,
        total_cached_tokens=sum(cached_counts) if cached_counts else None,
        max_input_tokens_per_request=max((int(row.input_tokens or 0) for row in rows), default=0),
        max_output_tokens_per_request=max((int(row.output_tokens or 0) for row in rows), default=0),
        max_total_tokens_per_request=max((int(row.total_tokens or 0) for row in rows), default=0),
        max_reasoning_tokens_per_request=max(reasoning_counts) if reasoning_counts else None,
        max_cached_tokens_per_request=max(cached_counts) if cached_counts else None,
        total_slaif_calculated_cost=sum(slaif_costs, Decimal("0")) if slaif_costs else None,
        total_provider_reported_cost=sum(provider_costs, Decimal("0")) if provider_costs else None,
        max_slaif_calculated_cost_per_request=max(slaif_costs) if slaif_costs else None,
        max_provider_reported_cost_per_request=max(provider_costs) if provider_costs else None,
        cost_currencies=_sorted_non_empty(row.cost_currency for row in rows),
        cost_confidence=_cost_confidence(
            cost_sources,
            has_slaif_cost=bool(slaif_costs),
            has_provider_cost=bool(provider_costs),
        ),
        warnings=tuple(warnings),
    )


def _metadata_set(rows: Sequence[UsageProfile], key: str) -> tuple[str, ...]:
    values: set[str] = set()
    for row in rows:
        metadata = row.profile_metadata if isinstance(row.profile_metadata, dict) else {}
        raw = metadata.get(key)
        if isinstance(raw, list):
            values.update(str(item).strip() for item in raw if str(item).strip())
    return tuple(sorted(values))


def _sorted_non_empty(values) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if value is not None and str(value).strip()}))


def _cost_confidence(
    cost_sources: tuple[str, ...],
    *,
    has_slaif_cost: bool,
    has_provider_cost: bool,
) -> str:
    if has_slaif_cost and has_provider_cost:
        return "mixed"
    if has_slaif_cost:
        return "slaif_calculated"
    if has_provider_cost:
        return "provider_reported"
    if not cost_sources or cost_sources == ("unknown",):
        return "unknown"
    if len(cost_sources) == 1:
        return cost_sources[0]
    return "mixed"


def _ceil_optional_int(value: int | None, multiplier: Decimal) -> int | None:
    if value is None:
        return None
    return _ceil_int(Decimal(value) * multiplier)


def _ceil_int(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _multiply_optional_decimal(value: Decimal | None, multiplier: Decimal) -> Decimal | None:
    if value is None:
        return None
    return (value * multiplier).quantize(Decimal("0.000000001"), rounding=ROUND_CEILING)


def _owner_display_name(owner: object | None) -> str | None:
    if owner is None:
        return None
    name = str(getattr(owner, "name", "") or "").strip()
    surname = str(getattr(owner, "surname", "") or "").strip()
    display = f"{name} {surname}".strip()
    return display or None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
