"""Safe reporting helpers for Chat Completions streaming live-burn metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
CHAT_LIVE_BURN_STOP_REASONS = {"cost", "tokens", "both"}


@dataclass(frozen=True, slots=True)
class ChatLiveBurnUsageDetail:
    """Sanitized Chat streaming live-burn metadata for one usage ledger row."""

    monitoring_enabled: bool | None
    triggered: bool
    stop_reason: str | None
    estimated_tokens_at_stop: int | None
    estimated_cost_eur_at_stop: Decimal | None
    cost_margin_eur: Decimal | None
    token_margin: int | None
    final_provider_usage_available: bool | None
    estimate_is_invoice_grade: bool

    @property
    def stopped_label(self) -> str | None:
        if not self.triggered:
            return None
        reason = self.stop_reason if self.stop_reason in CHAT_LIVE_BURN_STOP_REASONS else "unknown"
        return f"Live-burn: stopped ({reason})"


@dataclass(frozen=True, slots=True)
class ChatLiveBurnAggregate:
    """Safe aggregate counts for Chat streaming live-burn reporting."""

    triggered_total: int
    stop_reason_tokens: int
    stop_reason_cost: int
    stop_reason_both: int
    stop_reason_unknown: int
    final_provider_usage_available: int
    final_provider_usage_missing: int
    estimated_tokens_at_stop_sum: int
    estimated_cost_eur_at_stop_sum: Decimal


def parse_chat_live_burn_usage_detail(
    *,
    endpoint: str | None,
    streaming: bool,
    response_metadata: Mapping[str, object] | None,
) -> ChatLiveBurnUsageDetail | None:
    """Return sanitized live-burn telemetry for Chat streaming rows only."""
    if endpoint != CHAT_COMPLETIONS_ENDPOINT or streaming is not True or not isinstance(response_metadata, Mapping):
        return None

    has_live_burn_metadata = any(
        key in response_metadata
        for key in (
            "streaming_live_burn_enabled",
            "streaming_live_burn_triggered",
            "streaming_live_burn_stop_reason",
            "estimated_tokens_at_stop",
            "estimated_cost_eur_at_stop",
            "cost_margin_eur",
            "token_margin",
            "final_provider_usage_available",
            "estimate_is_invoice_grade",
        )
    )
    if not has_live_burn_metadata:
        return None

    triggered = _optional_bool(response_metadata.get("streaming_live_burn_triggered"))
    enabled = _optional_bool(response_metadata.get("streaming_live_burn_enabled"))
    stop_reason = _safe_stop_reason(response_metadata.get("streaming_live_burn_stop_reason"))

    return ChatLiveBurnUsageDetail(
        monitoring_enabled=enabled,
        triggered=triggered is True,
        stop_reason=stop_reason,
        estimated_tokens_at_stop=_optional_non_negative_int(response_metadata.get("estimated_tokens_at_stop")),
        estimated_cost_eur_at_stop=_optional_non_negative_decimal(
            response_metadata.get("estimated_cost_eur_at_stop")
        ),
        cost_margin_eur=_optional_decimal(response_metadata.get("cost_margin_eur")),
        token_margin=_optional_int(response_metadata.get("token_margin")),
        final_provider_usage_available=_optional_bool(response_metadata.get("final_provider_usage_available")),
        estimate_is_invoice_grade=False,
    )


def aggregate_chat_live_burn_usage(
    rows: list[ChatLiveBurnUsageDetail | None],
) -> ChatLiveBurnAggregate:
    """Aggregate sanitized live-burn details without exposing raw metadata."""
    triggered_rows = [row for row in rows if row is not None and row.triggered]
    return ChatLiveBurnAggregate(
        triggered_total=len(triggered_rows),
        stop_reason_tokens=sum(1 for row in triggered_rows if row.stop_reason == "tokens"),
        stop_reason_cost=sum(1 for row in triggered_rows if row.stop_reason == "cost"),
        stop_reason_both=sum(1 for row in triggered_rows if row.stop_reason == "both"),
        stop_reason_unknown=sum(
            1 for row in triggered_rows if row.stop_reason not in CHAT_LIVE_BURN_STOP_REASONS
        ),
        final_provider_usage_available=sum(
            1 for row in triggered_rows if row.final_provider_usage_available is True
        ),
        final_provider_usage_missing=sum(
            1 for row in triggered_rows if row.final_provider_usage_available is False
        ),
        estimated_tokens_at_stop_sum=sum(row.estimated_tokens_at_stop or 0 for row in triggered_rows),
        estimated_cost_eur_at_stop_sum=sum(
            (row.estimated_cost_eur_at_stop or Decimal("0")) for row in triggered_rows
        ),
    )


def _safe_stop_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in CHAT_LIVE_BURN_STOP_REASONS:
        return normalized
    return "unknown"


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _optional_non_negative_int(value: object) -> int | None:
    parsed = _optional_int(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _optional_non_negative_decimal(value: object) -> Decimal | None:
    parsed = _optional_decimal(value)
    if parsed is None or parsed < 0:
        return None
    return parsed
