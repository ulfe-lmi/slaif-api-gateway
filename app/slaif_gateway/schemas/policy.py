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
    estimated_message_input_tokens: int = 0
    estimated_non_message_input_tokens: int = 0
    estimated_non_message_input_bytes: int = 0
    estimated_non_message_input_fields: tuple[str, ...] = ()
    injected_default_output_tokens: bool
