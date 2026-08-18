"""Responses streaming live-burn policy and estimation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnBudget,
    ChatStreamingLiveBurnEstimate,
    build_chat_streaming_estimate_monitor,
    ChatStreamingLiveBurnPolicy,
    ChatStreamingLiveBurnPolicyError,
    build_chat_streaming_live_burn_budget,
    default_chat_streaming_live_burn_policy,
    estimate_chat_streaming_output_delta_tokens,
    normalize_chat_streaming_live_burn_policy,
    safe_chat_streaming_interrupted_estimate_metadata,
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
    _delta_keys: set[tuple[str, str, int]] = field(default_factory=set)
    _done_keys: set[tuple[str, str, int]] = field(default_factory=set)

    def __init__(self, budget: ResponsesStreamingLiveBurnBudget) -> None:
        self._budget = budget
        self._estimated_output_tokens = 0
        self._delta_keys = set()
        self._done_keys = set()

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
        for delta_text in self._generated_text_segments(chunk_json):
            self._estimated_output_tokens += estimate_chat_streaming_output_delta_tokens(
                delta_text,
                multiplier=self._budget.estimate_multiplier,
            )
        return self.check()

    def _generated_text_segments(
        self,
        chunk_json: Mapping[str, Any] | None,
    ) -> tuple[str, ...]:
        if not isinstance(chunk_json, Mapping):
            return ()
        event_type = chunk_json.get("type")
        delta_categories = {
            "response.output_text.delta": "output_text",
            "response.function_call_arguments.delta": "function_arguments",
            "response.custom_tool_call_input.delta": "custom_input",
            "response.reasoning_summary_text.delta": "reasoning_summary",
            "response.reasoning_text.delta": "reasoning_text",
        }
        category = delta_categories.get(event_type)
        if category is not None:
            delta = chunk_json.get("delta")
            if not isinstance(delta, str) or not delta:
                return ()
            key = _responses_stream_generated_key(chunk_json, category=category)
            self._delta_keys.add(key)
            return (delta,)
        if event_type == "response.reasoning_summary_text.done":
            key = _responses_stream_generated_key(chunk_json, category="reasoning_summary")
            return self._count_done_text(key, chunk_json.get("text"))
        if event_type != "response.output_item.done":
            return ()
        item = chunk_json.get("item")
        if not isinstance(item, Mapping):
            return ()
        item_type = item.get("type")
        item_id = item.get("id") if isinstance(item.get("id"), str) else ""
        if item_type == "function_call":
            return self._count_done_text(
                ("function_arguments", item_id, 0), item.get("arguments")
            )
        if item_type == "custom_tool_call":
            return self._count_done_text(("custom_input", item_id, 0), item.get("input"))
        if item_type == "message":
            return self._count_done_parts(
                item.get("content"),
                category="output_text",
                item_id=item_id,
                expected_part_type="output_text",
            )
        if item_type == "reasoning":
            return (
                *self._count_done_parts(
                    item.get("summary"),
                    category="reasoning_summary",
                    item_id=item_id,
                    expected_part_type="summary_text",
                ),
                *self._count_done_parts(
                    item.get("content"),
                    category="reasoning_text",
                    item_id=item_id,
                    expected_part_type="reasoning_text",
                ),
            )
        return ()

    def _count_done_parts(
        self,
        value: Any,
        *,
        category: str,
        item_id: str,
        expected_part_type: str,
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        segments: list[str] = []
        for index, part in enumerate(value):
            if not isinstance(part, Mapping) or part.get("type") != expected_part_type:
                continue
            segments.extend(
                self._count_done_text((category, item_id, index), part.get("text"))
            )
        return tuple(segments)

    def _count_done_text(
        self,
        key: tuple[str, str, int],
        value: Any,
    ) -> tuple[str, ...]:
        if key in self._done_keys:
            return ()
        self._done_keys.add(key)
        category, item_id, index = key
        anonymous_key = (category, "", index)
        if key in self._delta_keys or (item_id and anonymous_key in self._delta_keys):
            return ()
        return (value,) if isinstance(value, str) and value else ()

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
    """Extract one generated Responses delta string and discard it after counting."""
    if not isinstance(chunk_json, Mapping):
        return ""
    if chunk_json.get("type") not in {
        "response.output_text.delta",
        "response.function_call_arguments.delta",
        "response.custom_tool_call_input.delta",
        "response.reasoning_summary_text.delta",
        "response.reasoning_text.delta",
    }:
        return ""
    delta = chunk_json.get("delta")
    return delta if isinstance(delta, str) else ""


def _responses_stream_generated_key(
    chunk_json: Mapping[str, Any],
    *,
    category: str,
) -> tuple[str, str, int]:
    item_id = chunk_json.get("item_id")
    if not isinstance(item_id, str):
        item_id = ""
    index_field = (
        "summary_index"
        if category == "reasoning_summary"
        else "content_index" if category in {"output_text", "reasoning_text"} else None
    )
    index = chunk_json.get(index_field) if index_field is not None else 0
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        index = 0
    return category, item_id, index


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


def build_responses_streaming_estimate_monitor(
    *,
    cost_estimate: ChatCostEstimate,
    estimate_multiplier: Decimal,
    budget: ResponsesStreamingLiveBurnBudget | None = None,
) -> ResponsesStreamingLiveBurnMonitor:
    chat_monitor = build_chat_streaming_estimate_monitor(
        cost_estimate=cost_estimate,
        estimate_multiplier=estimate_multiplier,
        budget=budget,
    )
    monitor = ResponsesStreamingLiveBurnMonitor(chat_monitor._budget)
    monitor._estimated_output_tokens = chat_monitor.estimated_output_tokens
    return monitor


def safe_responses_streaming_interrupted_estimate_metadata(
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    estimated_total_tokens: int,
    estimated_cost_eur: Decimal,
    interruption_reason: str,
    final_provider_usage_available: bool,
) -> dict[str, object]:
    return safe_chat_streaming_interrupted_estimate_metadata(
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_total_tokens=estimated_total_tokens,
        estimated_cost_eur=estimated_cost_eur,
        interruption_reason=interruption_reason,
        final_provider_usage_available=final_provider_usage_available,
    )
