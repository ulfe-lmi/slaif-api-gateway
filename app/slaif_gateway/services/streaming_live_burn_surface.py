"""Reusable operator-surface helpers for streaming live-burn policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from slaif_gateway.services.chat_streaming_live_burn import (
    CHAT_STREAMING_LIVE_BURN_METADATA_KEY,
    ChatStreamingLiveBurnPolicy,
    ChatStreamingLiveBurnPolicyError,
    default_chat_streaming_live_burn_policy,
    normalize_chat_streaming_live_burn_policy,
    parse_chat_streaming_live_burn_form_policy,
)


@dataclass(frozen=True, slots=True)
class StreamingLiveBurnSurfaceSpec:
    """Endpoint-scoped Admin/CLI labels and field names for live-burn policy."""

    metadata_key: str
    display_title: str
    endpoint_label: str
    streaming_scope_label: str
    enabled_field_name: str
    cost_margin_field_name: str
    token_margin_field_name: str
    update_route_path: str
    audit_action_name: str
    cli_flag_prefix: str
    help_text: tuple[str, ...]


CHAT_STREAMING_LIVE_BURN_SURFACE = StreamingLiveBurnSurfaceSpec(
    metadata_key=CHAT_STREAMING_LIVE_BURN_METADATA_KEY,
    display_title="Chat Completions streaming live-burn monitoring",
    endpoint_label="/v1/chat/completions",
    streaming_scope_label="/v1/chat/completions stream=true",
    enabled_field_name="chat_streaming_live_burn_enabled",
    cost_margin_field_name="chat_streaming_live_burn_cost_margin_eur",
    token_margin_field_name="chat_streaming_live_burn_token_margin",
    update_route_path="/chat-streaming-live-burn",
    audit_action_name="update_chat_streaming_live_burn_policy",
    cli_flag_prefix="chat-streaming-live-burn",
    help_text=(
        "Applies only to /v1/chat/completions with stream=true.",
        "Positive margin stops streams early before quota boundary.",
        "Zero margin stops near estimated quota boundary.",
        "Negative margin allows bounded estimated overrun; the key may finish negative.",
        "Final provider usage/cost remains authoritative.",
        "Live estimates are provisional, not invoice-grade.",
    ),
)

ACTIVE_STREAMING_LIVE_BURN_SURFACES = (CHAT_STREAMING_LIVE_BURN_SURFACE,)


def normalize_streaming_live_burn_surface_policy(
    spec: StreamingLiveBurnSurfaceSpec,
    value: Mapping[str, object] | ChatStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    """Normalize a policy for an active Admin/CLI streaming live-burn surface."""
    _ensure_supported_spec(spec)
    return normalize_chat_streaming_live_burn_policy(
        value,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def parse_streaming_live_burn_surface_form_policy(
    spec: StreamingLiveBurnSurfaceSpec,
    *,
    enabled: bool,
    cost_margin_eur: object | None,
    token_margin: object | None,
    existing_policy: ChatStreamingLiveBurnPolicy | None = None,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    """Parse an Admin form policy using the registered endpoint surface."""
    _ensure_supported_spec(spec)
    return parse_chat_streaming_live_burn_form_policy(
        enabled=enabled,
        cost_margin_eur=cost_margin_eur,
        token_margin=token_margin,
        existing_policy=existing_policy,
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def streaming_live_burn_surface_policy_from_cli_options(
    spec: StreamingLiveBurnSurfaceSpec,
    *,
    enabled: bool,
    cost_margin_eur: object | None,
    token_margin: object | None,
    max_abs_cost_margin_eur: Decimal,
    max_abs_token_margin: int,
) -> ChatStreamingLiveBurnPolicy:
    """Build a normalized policy from endpoint-scoped CLI flags."""
    _ensure_supported_spec(spec)
    return normalize_chat_streaming_live_burn_policy(
        {
            "version": 1,
            "enabled": enabled,
            "cost_margin_eur": "0.000000000" if cost_margin_eur is None else cost_margin_eur,
            "token_margin": 0 if token_margin is None else token_margin,
        },
        max_abs_cost_margin_eur=max_abs_cost_margin_eur,
        max_abs_token_margin=max_abs_token_margin,
    )


def streaming_live_burn_surface_policy_summary(
    spec: StreamingLiveBurnSurfaceSpec,
    policy: Mapping[str, object] | ChatStreamingLiveBurnPolicy | None,
    *,
    max_abs_cost_margin_eur: Decimal = Decimal("1000000"),
    max_abs_token_margin: int = 1000000000,
) -> str:
    """Return a compact safe summary for operator pages and CLI output."""
    _ensure_supported_spec(spec)
    try:
        normalized = normalize_chat_streaming_live_burn_policy(
            policy,
            max_abs_cost_margin_eur=max_abs_cost_margin_eur,
            max_abs_token_margin=max_abs_token_margin,
        )
    except ChatStreamingLiveBurnPolicyError:
        normalized = default_chat_streaming_live_burn_policy()
    state = "on" if normalized.enabled else "off"
    ignored = " (margins ignored)" if not normalized.enabled else ""
    return (
        f"Chat live-burn: {state}{ignored}, "
        f"cost margin EUR {normalized.to_metadata()['cost_margin_eur']}, "
        f"token margin {normalized.token_margin}"
    )


def _ensure_supported_spec(spec: StreamingLiveBurnSurfaceSpec) -> None:
    if spec.metadata_key != CHAT_STREAMING_LIVE_BURN_METADATA_KEY:
        raise ChatStreamingLiveBurnPolicyError(
            "Unsupported streaming live-burn surface.",
            param="metadata_key",
        )
