"""Request policy for the stateless text-only /v1/responses foundation."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.schemas.policy import ResponsesPolicyResult
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.policy_errors import RequestPolicyError

_SUPPORTED_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "max_output_tokens",
        "temperature",
        "top_p",
        "metadata",
        "stream",
        "store",
        "text",
        "service_tier",
    }
)
_TEXT_FORMAT_TYPES = frozenset({"text"})


class ResponsesRequestPolicyError(RequestPolicyError):
    """Request-policy error for Responses field validation."""

    def __init__(self, safe_message: str, *, param: str, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(safe_message, param=param)


class ResponsesRequestPolicy:
    """Apply narrow Responses guardrails before route/rate/quota/provider work."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, body: Mapping[str, Any]) -> ResponsesPolicyResult:
        effective_body = copy.deepcopy(dict(body))
        self._reject_unknown_fields(effective_body)

        model = effective_body.get("model")
        if not isinstance(model, str) or not model.strip():
            _raise(
                "model",
                "responses_field_invalid_type",
                "The 'model' field must be a non-empty string.",
            )

        input_text = self._validate_input(effective_body.get("input"))
        instructions = self._validate_optional_string(
            effective_body.get("instructions"),
            param="instructions",
            max_bytes=self._settings.RESPONSES_MAX_INSTRUCTIONS_BYTES,
        )
        self._validate_stateless_fields(effective_body)
        self._validate_scalar_controls(effective_body)
        self._validate_metadata(effective_body.get("metadata"))
        self._validate_text_config(effective_body.get("text"))
        output_tokens, injected_default = self._resolve_output_token_limit(effective_body)

        estimated_input_tokens = self._estimate_input_tokens(
            input_text=input_text,
            instructions=instructions,
            body=effective_body,
        )
        if estimated_input_tokens > self._settings.HARD_MAX_INPUT_TOKENS:
            _raise(
                "input",
                "input_token_limit_exceeded",
                "Estimated Responses input size exceeds the configured hard maximum.",
            )

        return ResponsesPolicyResult(
            effective_body=effective_body,
            requested_output_tokens=output_tokens,
            effective_output_tokens=output_tokens,
            estimated_input_tokens=estimated_input_tokens,
            estimated_message_input_tokens=estimated_input_tokens,
            estimated_non_message_input_tokens=0,
            estimated_non_message_input_bytes=0,
            estimated_non_message_input_fields=(),
            injected_default_output_tokens=injected_default,
        )

    def _reject_unknown_fields(self, body: Mapping[str, Any]) -> None:
        for field in body:
            field_name = str(field)
            if field_name not in _SUPPORTED_FIELDS:
                code = _unsupported_code_for_field(field_name)
                _raise(
                    field_name,
                    code,
                    "This Responses request field is not enabled by this gateway.",
                )

    def _validate_input(self, value: Any) -> str:
        if not isinstance(value, str) or not value:
            _raise(
                "input",
                "responses_field_invalid_type",
                "The 'input' field must be a non-empty text string.",
            )
        self._validate_string_bytes(
            value,
            param="input",
            max_bytes=self._settings.RESPONSES_MAX_INPUT_TEXT_BYTES,
        )
        return value

    def _validate_optional_string(self, value: Any, *, param: str, max_bytes: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            _raise(
                param,
                "responses_field_invalid_type",
                f"The '{param}' field must be a string.",
            )
        self._validate_string_bytes(value, param=param, max_bytes=max_bytes)
        return value

    def _validate_stateless_fields(self, body: dict[str, Any]) -> None:
        if body.get("stream") is True:
            _raise(
                "stream",
                "responses_streaming_not_supported",
                "Streaming Responses are not enabled by this gateway.",
            )
        if "stream" in body and body.get("stream") is not False and body.get("stream") is not None:
            _raise(
                "stream",
                "responses_field_invalid_type",
                "The 'stream' field must be false when provided.",
            )
        if body.get("store") is True:
            _raise(
                "store",
                "responses_store_not_supported",
                "Provider-side Responses storage is not enabled by this gateway.",
            )
        if "store" in body and body.get("store") is not False and body.get("store") is not None:
            _raise(
                "store",
                "responses_field_invalid_type",
                "The 'store' field must be false when provided.",
            )
        body["store"] = False

        service_tier = body.get("service_tier")
        if service_tier not in (None, "auto"):
            _raise(
                "service_tier",
                "responses_service_tier_not_supported",
                "Non-default Responses service tiers are not enabled by this gateway.",
            )

    def _validate_scalar_controls(self, body: Mapping[str, Any]) -> None:
        self._validate_number_range(body.get("temperature"), param="temperature", minimum=0, maximum=2)
        self._validate_number_range(body.get("top_p"), param="top_p", minimum=0, maximum=1)

    def _validate_number_range(
        self,
        value: Any,
        *,
        param: str,
        minimum: float,
        maximum: float,
    ) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int | float):
            _raise(
                param,
                "responses_field_invalid_type",
                f"The '{param}' field must be a number.",
            )
        if value < minimum or value > maximum:
            _raise(
                param,
                "responses_field_value_out_of_range",
                f"The '{param}' field is outside the supported range.",
            )

    def _validate_metadata(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, Mapping):
            _raise(
                "metadata",
                "responses_field_invalid_type",
                "The 'metadata' field must be an object.",
            )
        if len(value) > self._settings.RESPONSES_MAX_METADATA_KEYS:
            _raise(
                "metadata",
                "responses_field_too_many_items",
                "The 'metadata' field has too many keys.",
            )
        for key in value:
            if not isinstance(key, str):
                _raise(
                    "metadata",
                    "responses_field_invalid_type",
                    "Responses metadata keys must be strings.",
                )
        if len(canonical_json_bytes(value)) > self._settings.RESPONSES_MAX_METADATA_BYTES:
            _raise(
                "metadata",
                "responses_field_too_large",
                "The 'metadata' field exceeds the gateway size limit.",
            )

    def _validate_text_config(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, Mapping):
            _raise(
                "text",
                "responses_field_invalid_type",
                "The 'text' field must be an object.",
            )
        unknown = set(value) - {"format"}
        if unknown:
            _raise(
                f"text.{sorted(unknown)[0]}",
                "responses_field_not_supported",
                "This Responses text configuration field is not enabled by this gateway.",
            )
        text_format = value.get("format")
        if text_format is None:
            return
        if not isinstance(text_format, Mapping):
            _raise(
                "text.format",
                "responses_field_invalid_type",
                "The 'text.format' field must be an object.",
            )
        format_type = text_format.get("type")
        if format_type not in _TEXT_FORMAT_TYPES:
            _raise(
                "text.format",
                "responses_field_not_supported",
                "Structured Responses output is not enabled by this gateway.",
            )
        unknown_format = set(text_format) - {"type"}
        if unknown_format:
            _raise(
                f"text.format.{sorted(unknown_format)[0]}",
                "responses_field_not_supported",
                "This Responses text format field is not enabled by this gateway.",
            )

    def _resolve_output_token_limit(self, body: dict[str, Any]) -> tuple[int, bool]:
        value = body.get("max_output_tokens")
        if value is None:
            body["max_output_tokens"] = self._settings.DEFAULT_MAX_OUTPUT_TOKENS
            return self._settings.DEFAULT_MAX_OUTPUT_TOKENS, True
        if isinstance(value, bool) or not isinstance(value, int):
            _raise(
                "max_output_tokens",
                "invalid_output_token_limit",
                "The 'max_output_tokens' field must be a positive integer.",
            )
        if value <= 0:
            _raise(
                "max_output_tokens",
                "invalid_output_token_limit",
                "The 'max_output_tokens' field must be a positive integer.",
            )
        if value > self._settings.HARD_MAX_OUTPUT_TOKENS:
            _raise(
                "max_output_tokens",
                "output_token_limit_exceeded",
                "The 'max_output_tokens' field exceeds the configured hard maximum.",
            )
        return value, False

    def _estimate_input_tokens(
        self,
        *,
        input_text: str,
        instructions: str | None,
        body: Mapping[str, Any],
    ) -> int:
        total_bytes = len(input_text.encode("utf-8"))
        if instructions is not None:
            total_bytes += len(instructions.encode("utf-8"))
        for field in ("text",):
            if field in body and body[field] is not None:
                total_bytes += len(canonical_json_bytes({field: body[field]}))
        return max(1, (total_bytes + 2) // 3)

    def _validate_string_bytes(self, value: str, *, param: str, max_bytes: int) -> None:
        if len(value.encode("utf-8")) > max_bytes:
            _raise(
                param,
                "responses_field_too_large",
                f"The '{param}' field exceeds the gateway size limit.",
            )


def _unsupported_code_for_field(field_name: str) -> str:
    if field_name == "tools" or field_name == "tool_choice" or field_name == "parallel_tool_calls":
        return "responses_tools_not_supported"
    if field_name in {"previous_response_id", "conversation"}:
        return "responses_state_not_supported"
    if field_name == "background":
        return "responses_background_not_supported"
    if field_name in {"modalities", "audio", "include"}:
        return "responses_multimodal_not_supported"
    if field_name in {"prompt", "prompt_cache_key", "prompt_cache_retention"}:
        return "responses_state_not_supported"
    return "responses_field_not_supported"


def _raise(param: str, code: str, message: str) -> None:
    raise ResponsesRequestPolicyError(message, param=param, error_code=code)
