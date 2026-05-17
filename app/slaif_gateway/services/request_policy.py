"""Request policy service for /v1/chat/completions safety caps and normalization."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.services.chat_completion_field_policy import (
    enforce_chat_completion_field_policy,
)
from slaif_gateway.services.hosted_tool_policy import enforce_chat_completion_capability_policy
from slaif_gateway.services.input_token_estimation import estimate_chat_completion_input_tokens
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidChatMessagesError,
    InvalidChoiceCountError,
    InvalidOutputTokenLimitError,
    InvalidRequestBodyError,
    InvalidStreamOptionsError,
    MULTI_CHOICE_UNSUPPORTED_MESSAGE,
    OutputTokenLimitExceededError,
)


class ChatCompletionRequestPolicy:
    """Apply output/input guardrails before any provider forwarding logic."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(
        self,
        body: Mapping[str, Any],
        *,
        capability_policy_mode: str = "standard",
    ) -> ChatCompletionPolicyResult:
        effective_body = copy.deepcopy(dict(body))
        enforce_chat_completion_field_policy(
            effective_body,
            capability_policy_mode=capability_policy_mode,
        )
        self._validate_choice_count(effective_body.get("n"))
        messages = self._validate_messages(effective_body.get("messages"))

        requested_output_tokens, effective_output_tokens, injected_default = (
            self._resolve_output_token_limit(effective_body)
        )
        self._force_streaming_usage_metadata(effective_body)
        enforce_chat_completion_capability_policy(
            effective_body,
            requested_model=str(effective_body.get("model") or ""),
            capability_policy_mode=capability_policy_mode,
            allow_unknown_hosted_tools=self._settings.TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS,
            allow_external_authority=self._settings.TRUSTED_CALIBRATION_ALLOW_EXTERNAL_AUTHORITY,
        )

        try:
            input_estimate = estimate_chat_completion_input_tokens(
                effective_body,
                messages=messages,
            )
        except ValueError as exc:
            raise InvalidRequestBodyError(
                "Request body contains a field that is not JSON-serializable.",
                param="request",
            ) from exc

        if input_estimate.total_input_tokens_estimate > self._settings.HARD_MAX_INPUT_TOKENS:
            raise InputTokenLimitExceededError(
                (
                    "Estimated input size exceeds the configured hard maximum "
                    f"({self._settings.HARD_MAX_INPUT_TOKENS})."
                ),
                param="request",
            )

        return ChatCompletionPolicyResult(
            effective_body=effective_body,
            requested_output_tokens=requested_output_tokens,
            effective_output_tokens=effective_output_tokens,
            estimated_input_tokens=input_estimate.total_input_tokens_estimate,
            estimated_message_input_tokens=input_estimate.message_input_tokens_estimate,
            estimated_non_message_input_tokens=input_estimate.non_message_input_tokens_estimate,
            estimated_non_message_input_bytes=input_estimate.counted_bytes,
            estimated_non_message_input_fields=input_estimate.counted_fields,
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
