"""Runtime admission facts for the bounded Responses web-search contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai_web_search import WebSearchRequestFacts
from slaif_gateway.services.openai_web_search_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    EXTERNAL_TOOL_FENCED,
    ExternalToolAdmissionDecision,
    ExternalToolKeyLimitFacts,
)
from slaif_gateway.services.openai_web_search_contract import (
    WebSearchContractError,
    maximum_tool_fee,
    validate_web_search_request,
)
from slaif_gateway.schemas.pricing import ExternalToolPricing


class ExternalToolRuntimeError(ValueError):
    """Safe admission failure with no request or provider content."""


@dataclass(frozen=True, slots=True)
class ExternalWebSearchAdmission:
    """Content-free facts retained for the request's accounting boundary."""

    request: WebSearchRequestFacts
    decision: ExternalToolAdmissionDecision
    maximum_fee_native: Decimal
    pricing: ExternalToolPricing | None = None


def admit_web_search_request(
    body: Mapping[str, object],
    *,
    authenticated_key: AuthenticatedGatewayKey,
    route_provider: str,
    route_capabilities: Mapping[str, object] | None,
) -> ExternalWebSearchAdmission:
    """Validate exact key/route/provider/capability admission before mutation."""
    route_policy = route_capabilities.get("external_tools") if route_capabilities else None
    key_limits = ExternalToolKeyLimitFacts(
        key_purpose=authenticated_key.key_purpose,
        request_limit_total=authenticated_key.request_limit_total,
        token_limit_total=authenticated_key.token_limit_total,
        cost_limit_eur=authenticated_key.cost_limit_eur,
    )
    try:
        request = validate_web_search_request(
            body,
            provider=route_provider,
            key_policy=authenticated_key.external_tool_policy,
            route_policy=route_policy,
            key_limits=key_limits,
            ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
        )
    except (TypeError, ValueError, WebSearchContractError) as exc:
        raise ExternalToolRuntimeError("The Responses hosted web-search contract is not permitted.") from exc
    decision = ExternalToolAdmissionDecision(
        allowed=True,
        quota_mode=EXTERNAL_TOOL_FENCED,
        effective_tool_call_cap=request.effective_tool_call_cap,
        reason_code="external_tool_fenced_allowed",
        exclusive_key_fence_required=True,
        single_request_overrun_accepted=True,
        hold_on_missing_or_ambiguous_final_cost=True,
        following_requests_block_after_exhaustion=True,
    )
    return ExternalWebSearchAdmission(
        request=request,
        decision=decision,
        maximum_fee_native=Decimal("0"),
    )


def with_pricing(
    admission: ExternalWebSearchAdmission,
    *,
    pricing: ExternalToolPricing,
) -> ExternalWebSearchAdmission:
    """Attach only the bounded maximum fee after active pricing validation."""
    return ExternalWebSearchAdmission(
        request=admission.request,
        decision=admission.decision,
        maximum_fee_native=maximum_tool_fee(admission.request.max_tool_calls, pricing),
        pricing=pricing,
    )
