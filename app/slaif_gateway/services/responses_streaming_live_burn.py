"""Responses streaming live-burn policy and estimation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnBudget,
    ChatStreamingLiveBurnEstimate,
    ChatStreamingLiveBurnPolicy,
    ChatStreamingLiveBurnPolicyError,
    build_chat_streaming_live_burn_budget,
    default_chat_streaming_live_burn_policy,
    estimate_chat_streaming_output_delta_tokens,
    normalize_chat_streaming_live_burn_policy,
)
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY = "responses_streaming_live_burn"
RESPONSES_STREAMING_LIVE_BURN_ERROR_CODE = "streaming_live_burn_limit_exceeded"
RESPONSES_STREAMING_LIVE_BURN_ERROR_MESSAGE = (
    "The streaming response was stopped because the estimated Responses usage "
    "crossed this key's streaming live-burn margin."
)

ResponsesStreamingLiveBurnPolicy = ChatStreamingLiveBurnPolicy
ResponsesStreamingLiveBurnBudget = ChatStreamingLiveBurnBudget
ResponsesStreamingLiveBurnEstimate = ChatStreamingLiveBurnEstimate
ResponsesStreamingLiveBurnPolicyError = ChatStreamingLiveBurnPolicyError


def default_responses_streaming_live_burn_policy() -> ResponsesStreamingLiveBurnPolicy:
    return default_chat_streaming_live_burn_policy()


def normalize_responses_streaming_live_burn_policy(
    value: Mapping[str, object] | ResponsesStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ResponsesStreamingLiveBurnPolicy:
    return normalize_chat_streaming_live_burn_policy(
        value,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def responses_streaming_live_burn_policy_from_metadata(
    metadata: Mapping[str, object] | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ResponsesStreamingLiveBurnPolicy:
    if not isinstance(metadata, Mapping):
        return default_responses_streaming_live_burn_policy()
    raw_policy = metadata.get(RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY)
    if raw_policy is None:
        return default_responses_streaming_live_burn_policy()
    if not isinstance(raw_policy, Mapping):
        raise ResponsesStreamingLiveBurnPolicyError(
            "Responses streaming live-burn policy must be an object.",
            param=RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY,
        )
    return normalize_responses_streaming_live_burn_policy(
        raw_policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def metadata_with_responses_streaming_live_burn_policy(
    metadata: Mapping[str, object] | None,
    policy: Mapping[str, object] | ResponsesStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> dict[str, object]:
    sanitized = sanitize_metadata_mapping(metadata or {}, drop_content_keys=True)
    result = dict(sanitized if isinstance(sanitized, dict) else {})
    normalized = normalize_responses_streaming_live_burn_policy(
        policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )
    result[RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY] = normalized.to_metadata()
    return result


def build_responses_streaming_live_burn_budget(
    *,
    policy: ResponsesStreamingLiveBurnPolicy,
    cost_limit_eur: Decimal | None,
    token_limit_total: int | None,
    cost_used_eur: Decimal,
    tokens_used_total: int,
    cost_reserved_eur: Decimal,
    tokens_reserved_total: int,
    current_reserved_cost_eur: Decimal,
    current_reserved_tokens: int,
    cost_estimate: ChatCostEstimate,
    estimate_multiplier: Decimal,
) -> ResponsesStreamingLiveBurnBudget | None:
    return build_chat_streaming_live_burn_budget(
        policy=policy,
        cost_limit_eur=cost_limit_eur,
        token_limit_total=token_limit_total,
        cost_used_eur=cost_used_eur,
        tokens_used_total=tokens_used_total,
        cost_reserved_eur=cost_reserved_eur,
        tokens_reserved_total=tokens_reserved_total,
        current_reserved_cost_eur=current_reserved_cost_eur,
        current_reserved_tokens=current_reserved_tokens,
        cost_estimate=cost_estimate,
        estimate_multiplier=estimate_multiplier,
    )


_ONE_MILLION = Decimal("1000000")


@dataclass(slots=True)
class ResponsesStreamingLiveBurnMonitor:
    """In-memory streaming estimator for one Responses request."""

    _budget: ResponsesStreamingLiveBurnBudget
    _estimated_output_tokens: int = 0

    def __init__(self, budget: ResponsesStreamingLiveBurnBudget) -> None:
        self._budget = budget
        self._estimated_output_tokens = 0

    @property
    def estimated_output_tokens(self) -> int:
        return self._estimated_output_tokens

    @property
    def estimated_request_tokens(self) -> int:
        return self._budget.admission_input_tokens + self._estimated_output_tokens

    @property
    def estimated_cost_eur(self) -> Decimal:
        return self._budget.admission_input_cost_eur + (
            Decimal(self._estimated_output_tokens)
            / _ONE_MILLION
            * self._budget.output_price_per_1m_eur
        )

    def observe_chunk(
        self,
        chunk_json: Mapping[str, Any] | None,
    ) -> ResponsesStreamingLiveBurnEstimate | None:
        delta_text = generated_responses_streaming_delta_text(chunk_json)
        if delta_text:
            self._estimated_output_tokens += estimate_chat_streaming_output_delta_tokens(
                delta_text,
                multiplier=self._budget.estimate_multiplier,
            )
        return self.check()

    def check(self) -> ResponsesStreamingLiveBurnEstimate | None:
        cost_crossed = (
            self._budget.cost_cutoff_eur is not None
            and self.estimated_cost_eur >= self._budget.cost_cutoff_eur
        )
        token_crossed = (
            self._budget.token_cutoff is not None
            and self.estimated_request_tokens >= self._budget.token_cutoff
        )
        if not cost_crossed and not token_crossed:
            return None
        if cost_crossed and token_crossed:
            stop_reason = "both"
        elif cost_crossed:
            stop_reason = "cost"
        else:
            stop_reason = "tokens"
        return ResponsesStreamingLiveBurnEstimate(
            estimated_output_tokens=self.estimated_output_tokens,
            estimated_request_tokens=self.estimated_request_tokens,
            estimated_cost_eur=self.estimated_cost_eur,
            stop_reason=stop_reason,
            metadata=safe_responses_streaming_live_burn_stop_metadata(
                estimated_tokens_at_stop=self.estimated_request_tokens,
                estimated_cost_eur_at_stop=self.estimated_cost_eur,
                stop_reason=stop_reason,
                policy=self._budget.policy,
                final_provider_usage_available=False,
            ),
        )


def generated_responses_streaming_delta_text(chunk_json: Mapping[str, Any] | None) -> str:
    """Extract generated Responses streamed text and discard it after counting."""
    if not isinstance(chunk_json, Mapping):
        return ""
    if chunk_json.get("type") != "response.output_text.delta":
        return ""
    delta = chunk_json.get("delta")
    return delta if isinstance(delta, str) else ""


def safe_responses_streaming_live_burn_stop_metadata(
    *,
    estimated_tokens_at_stop: int,
    estimated_cost_eur_at_stop: Decimal,
    stop_reason: str,
    policy: ResponsesStreamingLiveBurnPolicy,
    final_provider_usage_available: bool,
) -> dict[str, object]:
    return {
        "streaming_live_burn_enabled": policy.enabled,
        "streaming_live_burn_triggered": True,
        "streaming_live_burn_stop_reason": stop_reason,
        "estimated_tokens_at_stop": estimated_tokens_at_stop,
        "estimated_cost_eur_at_stop": format(
            estimated_cost_eur_at_stop.quantize(Decimal("0.000000001")),
            "f",
        ),
        "cost_margin_eur": format(policy.cost_margin_eur.quantize(Decimal("0.000000001")), "f"),
        "token_margin": policy.token_margin,
        "final_provider_usage_available": final_provider_usage_available,
        "estimate_is_invoice_grade": False,
    }


def pre_provider_responses_streaming_live_burn_error(
    budget: ResponsesStreamingLiveBurnBudget | None,
) -> ResponsesStreamingLiveBurnEstimate | None:
    if budget is None:
        return None
    monitor = ResponsesStreamingLiveBurnMonitor(budget)
    return monitor.check()
