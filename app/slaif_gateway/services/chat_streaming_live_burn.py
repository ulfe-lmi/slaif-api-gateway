"""Chat Completions streaming live-burn policy and estimation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.services.input_token_estimation import _estimate_text_tokens
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

CHAT_STREAMING_LIVE_BURN_METADATA_KEY = "chat_streaming_live_burn"
CHAT_STREAMING_LIVE_BURN_ERROR_CODE = "streaming_live_burn_limit_exceeded"
CHAT_STREAMING_LIVE_BURN_ERROR_MESSAGE = (
    "The streaming response was stopped because the estimated Chat Completions usage "
    "crossed this key's streaming live-burn margin."
)
_DEFAULT_COST_MARGIN = Decimal("0.000000000")
_EUR_QUANTUM = Decimal("0.000000001")
_ONE_MILLION = Decimal("1000000")


class ChatStreamingLiveBurnPolicyError(ValueError):
    """Raised when a Chat streaming live-burn policy is invalid."""

    def __init__(self, message: str, *, param: str | None = None) -> None:
        self.param = param
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ChatStreamingLiveBurnPolicy:
    """Per-key policy for Chat Completions streaming live-burn monitoring."""

    enabled: bool = True
    cost_margin_eur: Decimal = _DEFAULT_COST_MARGIN
    token_margin: int = 0
    version: int = 1

    def to_metadata(self) -> dict[str, object]:
        return {
            "version": self.version,
            "enabled": self.enabled,
            "cost_margin_eur": _format_eur(self.cost_margin_eur),
            "token_margin": self.token_margin,
        }


@dataclass(frozen=True, slots=True)
class ChatStreamingLiveBurnBudget:
    """Request-specific live-burn cutoffs after PostgreSQL quota reservation."""

    policy: ChatStreamingLiveBurnPolicy
    cost_cutoff_eur: Decimal | None
    token_cutoff: int | None
    admission_input_tokens: int
    admission_input_cost_eur: Decimal
    output_price_per_1m_eur: Decimal
    estimate_multiplier: Decimal


@dataclass(frozen=True, slots=True)
class ChatStreamingLiveBurnEstimate:
    """Safe estimate state at the moment live-burn monitoring stops a stream."""

    estimated_output_tokens: int
    estimated_request_tokens: int
    estimated_cost_eur: Decimal
    stop_reason: str
    metadata: dict[str, object]


def default_chat_streaming_live_burn_policy() -> ChatStreamingLiveBurnPolicy:
    return ChatStreamingLiveBurnPolicy()


def normalize_chat_streaming_live_burn_policy(
    value: Mapping[str, object] | ChatStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    """Validate and normalize a policy from metadata, form data, or CLI input."""
    if isinstance(value, ChatStreamingLiveBurnPolicy):
        policy = value
    elif value is None:
        policy = default_chat_streaming_live_burn_policy()
    elif isinstance(value, Mapping):
        version = value.get("version", 1)
        if isinstance(version, bool) or version != 1:
            raise ChatStreamingLiveBurnPolicyError(
                "Chat streaming live-burn policy version must be 1.",
                param="version",
            )
        raw_enabled = value.get("enabled", True)
        if not isinstance(raw_enabled, bool):
            raise ChatStreamingLiveBurnPolicyError(
                "Chat streaming live-burn enabled must be boolean.",
                param="enabled",
            )
        policy = ChatStreamingLiveBurnPolicy(
            enabled=raw_enabled,
            cost_margin_eur=_parse_cost_margin(value.get("cost_margin_eur", _DEFAULT_COST_MARGIN)),
            token_margin=_parse_token_margin(value.get("token_margin", 0)),
        )
    else:
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn policy must be an object.",
            param=CHAT_STREAMING_LIVE_BURN_METADATA_KEY,
        )

    _validate_policy_bounds(
        policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )
    return policy


def chat_streaming_live_burn_policy_from_metadata(
    metadata: Mapping[str, object] | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    if not isinstance(metadata, Mapping):
        return default_chat_streaming_live_burn_policy()
    raw_policy = metadata.get(CHAT_STREAMING_LIVE_BURN_METADATA_KEY)
    if raw_policy is None:
        return default_chat_streaming_live_burn_policy()
    if not isinstance(raw_policy, Mapping):
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn policy must be an object.",
            param=CHAT_STREAMING_LIVE_BURN_METADATA_KEY,
        )
    return normalize_chat_streaming_live_burn_policy(
        raw_policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def metadata_with_chat_streaming_live_burn_policy(
    metadata: Mapping[str, object] | None,
    policy: Mapping[str, object] | ChatStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> dict[str, object]:
    sanitized = sanitize_metadata_mapping(metadata or {}, drop_content_keys=True)
    result = dict(sanitized if isinstance(sanitized, dict) else {})
    normalized = normalize_chat_streaming_live_burn_policy(
        policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )
    result[CHAT_STREAMING_LIVE_BURN_METADATA_KEY] = normalized.to_metadata()
    return result


def build_chat_streaming_live_burn_budget(
    *,
    policy: ChatStreamingLiveBurnPolicy,
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
) -> ChatStreamingLiveBurnBudget | None:
    """Build request-specific cutoffs after the current reservation is persisted."""
    if not policy.enabled:
        return None

    cost_cutoff: Decimal | None = None
    if cost_limit_eur is not None:
        other_reserved_cost = max(cost_reserved_eur - current_reserved_cost_eur, Decimal("0"))
        cost_budget = cost_limit_eur - cost_used_eur - other_reserved_cost
        cost_cutoff = cost_budget - policy.cost_margin_eur

    token_cutoff: int | None = None
    if token_limit_total is not None:
        other_reserved_tokens = max(tokens_reserved_total - current_reserved_tokens, 0)
        token_budget = token_limit_total - tokens_used_total - other_reserved_tokens
        token_cutoff = token_budget - policy.token_margin

    if cost_cutoff is None and token_cutoff is None:
        return None

    return ChatStreamingLiveBurnBudget(
        policy=policy,
        cost_cutoff_eur=cost_cutoff,
        token_cutoff=token_cutoff,
        admission_input_tokens=cost_estimate.estimated_input_tokens,
        admission_input_cost_eur=_input_cost_eur(cost_estimate),
        output_price_per_1m_eur=_output_price_per_1m_eur(cost_estimate),
        estimate_multiplier=estimate_multiplier,
    )


class ChatStreamingLiveBurnMonitor:
    """In-memory streaming estimator for one Chat Completions request."""

    def __init__(self, budget: ChatStreamingLiveBurnBudget) -> None:
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

    def observe_chunk(self, chunk_json: Mapping[str, Any] | None) -> ChatStreamingLiveBurnEstimate | None:
        delta_text = generated_chat_streaming_delta_text(chunk_json)
        if delta_text:
            self._estimated_output_tokens += estimate_chat_streaming_output_delta_tokens(
                delta_text,
                multiplier=self._budget.estimate_multiplier,
            )
        return self.check()

    def check(self) -> ChatStreamingLiveBurnEstimate | None:
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
        return self._estimate(stop_reason=stop_reason)

    def _estimate(self, *, stop_reason: str) -> ChatStreamingLiveBurnEstimate:
        metadata = safe_chat_streaming_live_burn_stop_metadata(
            estimated_tokens_at_stop=self.estimated_request_tokens,
            estimated_cost_eur_at_stop=self.estimated_cost_eur,
            stop_reason=stop_reason,
            policy=self._budget.policy,
            final_provider_usage_available=False,
        )
        return ChatStreamingLiveBurnEstimate(
            estimated_output_tokens=self._estimated_output_tokens,
            estimated_request_tokens=self.estimated_request_tokens,
            estimated_cost_eur=self.estimated_cost_eur,
            stop_reason=stop_reason,
            metadata=metadata,
        )


def generated_chat_streaming_delta_text(chunk_json: Mapping[str, Any] | None) -> str:
    """Extract generated Chat Completions streamed text and discard it after counting."""
    if not isinstance(chunk_json, Mapping):
        return ""
    choices = chunk_json.get("choices")
    if not isinstance(choices, list):
        return ""
    fragments: list[str] = []
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        delta = choice.get("delta")
        if not isinstance(delta, Mapping):
            continue
        content = delta.get("content")
        if isinstance(content, str):
            fragments.append(content)
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, Mapping):
                    continue
                function = tool_call.get("function")
                if not isinstance(function, Mapping):
                    continue
                name = function.get("name")
                if isinstance(name, str):
                    fragments.append(name)
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    fragments.append(arguments)
    return "".join(fragments)


def estimate_chat_streaming_output_delta_tokens(text: str, *, multiplier: Decimal) -> int:
    if not text:
        return 0
    byte_estimate = ceil(len(text.encode("utf-8")) / 3)
    base_estimate = max(_estimate_text_tokens(text), byte_estimate)
    return max(1, ceil_decimal(Decimal(base_estimate) * multiplier))


def safe_chat_streaming_live_burn_stop_metadata(
    *,
    estimated_tokens_at_stop: int,
    estimated_cost_eur_at_stop: Decimal,
    stop_reason: str,
    policy: ChatStreamingLiveBurnPolicy,
    final_provider_usage_available: bool,
) -> dict[str, object]:
    return {
        "streaming_live_burn_enabled": policy.enabled,
        "streaming_live_burn_triggered": True,
        "streaming_live_burn_stop_reason": stop_reason,
        "estimated_tokens_at_stop": estimated_tokens_at_stop,
        "estimated_cost_eur_at_stop": _format_eur(estimated_cost_eur_at_stop),
        "cost_margin_eur": _format_eur(policy.cost_margin_eur),
        "token_margin": policy.token_margin,
        "final_provider_usage_available": final_provider_usage_available,
        "estimate_is_invoice_grade": False,
    }


def pre_provider_chat_streaming_live_burn_error(
    budget: ChatStreamingLiveBurnBudget | None,
) -> ChatStreamingLiveBurnEstimate | None:
    if budget is None:
        return None
    monitor = ChatStreamingLiveBurnMonitor(budget)
    return monitor.check()


def build_chat_streaming_estimate_monitor(
    *,
    cost_estimate: ChatCostEstimate,
    estimate_multiplier: Decimal,
    budget: ChatStreamingLiveBurnBudget | None = None,
) -> ChatStreamingLiveBurnMonitor:
    """Return a monitor that always tracks streamed output estimates.

    When live-burn is disabled or no request-specific cutoffs exist, the
    returned monitor still counts safe token-bearing output for interrupted
    streaming accounting, but never trips a cutoff on its own.
    """
    runtime_budget = budget or ChatStreamingLiveBurnBudget(
        policy=default_chat_streaming_live_burn_policy(),
        cost_cutoff_eur=None,
        token_cutoff=None,
        admission_input_tokens=_safe_estimated_tokens(cost_estimate, field_name="estimated_input_tokens"),
        admission_input_cost_eur=_safe_input_cost_eur(cost_estimate),
        output_price_per_1m_eur=_safe_output_price_per_1m_eur(cost_estimate),
        estimate_multiplier=estimate_multiplier,
    )
    return ChatStreamingLiveBurnMonitor(runtime_budget)


def safe_chat_streaming_interrupted_estimate_metadata(
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    estimated_total_tokens: int,
    estimated_cost_eur: Decimal,
    interruption_reason: str,
    final_provider_usage_available: bool,
) -> dict[str, object]:
    return {
        "stream_interruption_reason": interruption_reason,
        "estimated_input_tokens_at_stop": estimated_input_tokens,
        "estimated_output_tokens_at_stop": estimated_output_tokens,
        "estimated_tokens_at_stop": estimated_total_tokens,
        "estimated_cost_eur_at_stop": _format_eur(estimated_cost_eur),
        "final_provider_usage_available": final_provider_usage_available,
        "estimate_is_invoice_grade": False,
    }


def parse_chat_streaming_live_burn_form_policy(
    *,
    enabled: bool,
    cost_margin_eur: object | None,
    token_margin: object | None,
    existing_policy: ChatStreamingLiveBurnPolicy | None = None,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    base = existing_policy or default_chat_streaming_live_burn_policy()
    raw_policy = {
        "version": 1,
        "enabled": enabled,
        "cost_margin_eur": (
            base.cost_margin_eur
            if not enabled and _is_blank(cost_margin_eur)
            else _DEFAULT_COST_MARGIN
            if _is_blank(cost_margin_eur)
            else cost_margin_eur
        ),
        "token_margin": (
            base.token_margin
            if not enabled and _is_blank(token_margin)
            else 0
            if _is_blank(token_margin)
            else token_margin
        ),
    }
    return normalize_chat_streaming_live_burn_policy(
        raw_policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def _parse_cost_margin(value: object) -> Decimal:
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn cost margin must be a finite decimal string.",
            param="cost_margin_eur",
        ) from exc
    if not decimal_value.is_finite():
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn cost margin must be finite.",
            param="cost_margin_eur",
        )
    return decimal_value.quantize(_EUR_QUANTUM)


def _parse_token_margin(value: object) -> int:
    if isinstance(value, bool):
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn token margin must be an integer.",
            param="token_margin",
        )
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text or not re_decimal_integer(text):
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn token margin must be an integer.",
            param="token_margin",
        )
    return int(text, 10)


def _validate_policy_bounds(
    policy: ChatStreamingLiveBurnPolicy,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> None:
    if max_abs_cost_margin_eur < 0:
        raise ChatStreamingLiveBurnPolicyError(
            "Maximum absolute cost margin must be non-negative.",
            param="max_abs_cost_margin_eur",
        )
    if max_abs_token_margin < 0:
        raise ChatStreamingLiveBurnPolicyError(
            "Maximum absolute token margin must be non-negative.",
            param="max_abs_token_margin",
        )
    if abs(policy.cost_margin_eur) > max_abs_cost_margin_eur:
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn cost margin exceeds the configured absolute bound.",
            param="cost_margin_eur",
        )
    if abs(policy.token_margin) > max_abs_token_margin:
        raise ChatStreamingLiveBurnPolicyError(
            "Chat streaming live-burn token margin exceeds the configured absolute bound.",
            param="token_margin",
        )


def _output_price_per_1m_eur(cost_estimate: ChatCostEstimate) -> Decimal:
    native_price = cost_estimate.output_price_per_1m
    if native_price is None:
        if cost_estimate.estimated_output_tokens <= 0:
            return Decimal("0")
        native_price = (
            cost_estimate.estimated_output_cost_native
            * _ONE_MILLION
            / Decimal(cost_estimate.estimated_output_tokens)
        )
    fx_rate = cost_estimate.fx_rate
    if fx_rate is None:
        if cost_estimate.estimated_total_cost_native == 0:
            return Decimal("0")
        fx_rate = cost_estimate.estimated_total_cost_eur / cost_estimate.estimated_total_cost_native
    return native_price * fx_rate


def _input_cost_eur(cost_estimate: ChatCostEstimate) -> Decimal:
    fx_rate = _fx_rate(cost_estimate)
    return cost_estimate.estimated_input_cost_native * fx_rate


def _safe_output_price_per_1m_eur(cost_estimate: object) -> Decimal:
    if isinstance(cost_estimate, ChatCostEstimate):
        return _output_price_per_1m_eur(cost_estimate)
    direct_price = getattr(cost_estimate, "output_price_per_1m", None)
    if direct_price is not None:
        return _coerce_decimal(direct_price)
    output_tokens = _safe_estimated_tokens(cost_estimate, field_name="estimated_output_tokens")
    if output_tokens <= 0:
        return Decimal("0")
    output_cost_native = _coerce_decimal(getattr(cost_estimate, "estimated_output_cost_native", Decimal("0")))
    fx_rate = _safe_fx_rate(cost_estimate)
    return output_cost_native * fx_rate * _ONE_MILLION / Decimal(output_tokens)


def _safe_input_cost_eur(cost_estimate: object) -> Decimal:
    if isinstance(cost_estimate, ChatCostEstimate):
        return _input_cost_eur(cost_estimate)
    input_cost_native = _coerce_decimal(getattr(cost_estimate, "estimated_input_cost_native", Decimal("0")))
    return input_cost_native * _safe_fx_rate(cost_estimate)


def _fx_rate(cost_estimate: ChatCostEstimate) -> Decimal:
    if cost_estimate.fx_rate is not None:
        return cost_estimate.fx_rate
    if cost_estimate.estimated_total_cost_native == 0:
        return Decimal("0")
    return cost_estimate.estimated_total_cost_eur / cost_estimate.estimated_total_cost_native


def _safe_fx_rate(cost_estimate: object) -> Decimal:
    if isinstance(cost_estimate, ChatCostEstimate):
        return _fx_rate(cost_estimate)
    fx_rate = getattr(cost_estimate, "fx_rate", None)
    if fx_rate is not None:
        return _coerce_decimal(fx_rate)
    total_native = _coerce_decimal(getattr(cost_estimate, "estimated_total_cost_native", Decimal("0")))
    if total_native == 0:
        return Decimal("0")
    total_eur = _coerce_decimal(getattr(cost_estimate, "estimated_total_cost_eur", Decimal("0")))
    return total_eur / total_native


def _safe_estimated_tokens(cost_estimate: object, *, field_name: str) -> int:
    value = getattr(cost_estimate, field_name, 0)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _coerce_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _format_eur(value: Decimal) -> str:
    return format(value.quantize(_EUR_QUANTUM), "f")


def ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding="ROUND_CEILING"))


def re_decimal_integer(text: str) -> bool:
    if text.startswith(("-", "+")):
        return text[1:].isdigit()
    return text.isdigit()


def _is_blank(value: object | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
