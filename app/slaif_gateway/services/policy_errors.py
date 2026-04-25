"""Domain-layer request policy errors for OpenAI-compatible request validation."""

from __future__ import annotations


class RequestPolicyError(Exception):
    """Base domain error for request-policy violations."""

    status_code: int = 400
    error_type: str = "invalid_request_error"
    error_code: str = "request_policy_error"

    def __init__(self, safe_message: str, *, param: str | None = None) -> None:
        self.safe_message = safe_message
        self.param = param
        super().__init__(safe_message)


class InvalidOutputTokenLimitError(RequestPolicyError):
    error_code = "invalid_output_token_limit"


class OutputTokenLimitExceededError(RequestPolicyError):
    error_code = "output_token_limit_exceeded"


class InputTokenLimitExceededError(RequestPolicyError):
    error_code = "input_token_limit_exceeded"


class AmbiguousOutputTokenLimitError(RequestPolicyError):
    error_code = "ambiguous_output_token_limit"


class InvalidChatMessagesError(RequestPolicyError):
    error_code = "invalid_messages"
