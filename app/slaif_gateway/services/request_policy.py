"""Request policy service for /v1/chat/completions safety caps and normalization."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidChatMessagesError,
    InvalidChoiceCountError,
    InvalidOutputTokenLimitError,
    InvalidStreamOptionsError,
    MULTI_CHOICE_UNSUPPORTED_MESSAGE,
    OutputTokenLimitExceededError,
)


class ChatCompletionRequestPolicy:
    """Apply output/input guardrails before any provider forwarding logic."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, body: Mapping[str, Any]) -> ChatCompletionPolicyResult:
        effective_body = copy.deepcopy(dict(body))
        self._validate_choice_count(effective_body.get("n"))
        messages = self._validate_messages(effective_body.get("messages"))

        requested_output_tokens, effective_output_tokens, injected_default = (
            self._resolve_output_token_limit(effective_body)
        )
        self._force_streaming_usage_metadata(effective_body)

        estimated_input_tokens = self._estimate_input_tokens(messages)
        if estimated_input_tokens > self._settings.HARD_MAX_INPUT_TOKENS:
            raise InputTokenLimitExceededError(
                (
                    "Estimated input tokens exceed the configured hard maximum "
                    f"({self._settings.HARD_MAX_INPUT_TOKENS})."
                ),
                param="messages",
            )

        return ChatCompletionPolicyResult(
            effective_body=effective_body,
            requested_output_tokens=requested_output_tokens,
            effective_output_tokens=effective_output_tokens,
            estimated_input_tokens=estimated_input_tokens,
            injected_default_output_tokens=injected_default,
        )

    def _resolve_output_token_limit(self, body: dict[str, Any]) -> tuple[int, int, bool]:
        max_tokens = body.get("max_tokens")
        max_completion_tokens = body.get("max_completion_tokens")

        if max_tokens is not None and max_completion_tokens is not None:
            if max_tokens != max_completion_tokens:
                raise AmbiguousOutputTokenLimitError(
                    "Request must not set both 'max_tokens' and 'max_completion_tokens' with "
                    "different values.",
                    param="max_completion_tokens",
                )

        if max_completion_tokens is not None:
            limit = self._validate_output_token_value(
                max_completion_tokens,
                param="max_completion_tokens",
            )
            return limit, limit, False

        if max_tokens is not None:
            limit = self._validate_output_token_value(max_tokens, param="max_tokens")
            return limit, limit, False

        default_limit = self._settings.DEFAULT_MAX_OUTPUT_TOKENS
        body["max_completion_tokens"] = default_limit
        return default_limit, default_limit, True

    def _validate_choice_count(self, value: Any) -> None:
        if value is None:
            return

        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidChoiceCountError(
                "The 'n' field must be the integer 1.",
                param="n",
            )

        if value < 1:
            raise InvalidChoiceCountError(
                "The 'n' field must be the integer 1.",
                param="n",
            )

        if value > 1:
            raise InvalidChoiceCountError(
                MULTI_CHOICE_UNSUPPORTED_MESSAGE,
                param="n",
            )

    def _force_streaming_usage_metadata(self, body: dict[str, Any]) -> None:
        if body.get("stream") is not True:
            return

        stream_options = body.get("stream_options")
        if stream_options is None:
            body["stream_options"] = {"include_usage": True}
            return

        if not isinstance(stream_options, Mapping):
            raise InvalidStreamOptionsError(
                "The 'stream_options' field must be an object when streaming is enabled.",
                param="stream_options",
            )

        body["stream_options"] = {
            **dict(stream_options),
            "include_usage": True,
        }

    def _validate_output_token_value(self, value: Any, *, param: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidOutputTokenLimitError(
                f"The '{param}' field must be a positive integer.",
                param=param,
            )

        if value <= 0:
            raise InvalidOutputTokenLimitError(
                f"The '{param}' field must be a positive integer.",
                param=param,
            )

        if value > self._settings.HARD_MAX_OUTPUT_TOKENS:
            raise OutputTokenLimitExceededError(
                (
                    f"The '{param}' field exceeds the configured hard maximum "
                    f"({self._settings.HARD_MAX_OUTPUT_TOKENS})."
                ),
                param=param,
            )

        return value

    def _validate_messages(self, messages: Any) -> list[Mapping[str, Any]]:
        if not isinstance(messages, list):
            raise InvalidChatMessagesError(
                "The 'messages' field must be a list.",
                param="messages",
            )

        validated: list[Mapping[str, Any]] = []
        for idx, message in enumerate(messages):
            if not isinstance(message, Mapping):
                raise InvalidChatMessagesError(
                    f"Message at index {idx} must be an object.",
                    param="messages",
                )

            role = message.get("role")
            if not isinstance(role, str):
                raise InvalidChatMessagesError(
                    f"Message at index {idx} must include a string 'role'.",
                    param="messages",
                )

            validated.append(message)

        return validated

    def _estimate_input_tokens(self, messages: list[Mapping[str, Any]]) -> int:
        # Conservative guardrail estimator only; this is not provider billing tokenization.
        # We over-estimate by counting UTF-8 bytes and converting to tokens with a 3-byte bucket
        # plus a fixed overhead per message.
        total_tokens = 0

        for message in messages:
            total_tokens += 16
            for value in message.values():
                total_tokens += self._estimate_value_tokens(value)

        return total_tokens

    def _estimate_value_tokens(self, value: Any) -> int:
        if value is None:
            return 0

        if isinstance(value, str):
            return self._estimate_text_tokens(value)

        if isinstance(value, Mapping):
            if "text" in value and isinstance(value.get("text"), str):
                return self._estimate_text_tokens(value["text"]) + 4
            return self._estimate_text_tokens(self._safe_json_dumps(value))

        if isinstance(value, list):
            subtotal = 0
            for item in value:
                subtotal += self._estimate_value_tokens(item)
            return subtotal + 4

        return self._estimate_text_tokens(self._safe_json_dumps(value))

    def _estimate_text_tokens(self, text: str) -> int:
        byte_len = len(text.encode("utf-8"))
        return max(1, (byte_len + 2) // 3)

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
