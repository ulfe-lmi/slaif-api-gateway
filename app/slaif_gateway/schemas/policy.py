"""Service-layer policy schemas for request normalization and caps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatCompletionPolicyResult(BaseModel):
    """Result of applying chat-completions request caps/policy checks."""

    effective_body: dict[str, Any]
    requested_output_tokens: int
    effective_output_tokens: int
    effective_output_tokens_per_choice: int = 0
    effective_choice_count: int = 1
    estimated_input_tokens: int
    unadjusted_input_tokens: int | None = None
    estimated_media_input_tokens: int = 0
    encoded_media_input_bytes: int = 0
    estimated_message_input_tokens: int = 0
    estimated_non_message_input_tokens: int = 0
    estimated_non_message_input_bytes: int = 0
    estimated_non_message_input_fields: tuple[str, ...] = ()
    injected_default_output_tokens: bool


class ResponsesPolicyResult(BaseModel):
    """Result of applying stateless text-output Responses request policy checks."""

    effective_body: dict[str, Any]
    requested_output_tokens: int
    effective_output_tokens: int
    effective_output_tokens_per_choice: int = 0
    effective_choice_count: int = 1
    estimated_input_tokens: int
    unadjusted_input_tokens: int | None = None
    estimated_media_input_tokens: int = 0
    encoded_media_input_bytes: int = 0
    estimated_message_input_tokens: int = 0
    estimated_non_message_input_tokens: int = 0
    estimated_non_message_input_bytes: int = 0
    estimated_non_message_input_fields: tuple[str, ...] = ()
    injected_default_output_tokens: bool
    codex_context_window_tokens: int | None = None
    codex_limits_applied: bool = False
