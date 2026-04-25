"""Service-layer policy schemas for request normalization and caps."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatCompletionPolicyResult(BaseModel):
    """Result of applying chat-completions request caps/policy checks."""

    effective_body: dict[str, Any]
    requested_output_tokens: int
    effective_output_tokens: int
    estimated_input_tokens: int
    injected_default_output_tokens: bool
