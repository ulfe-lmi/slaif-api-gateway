from slaif_gateway.api.policy_errors import openai_error_from_request_policy_error
from slaif_gateway.services.policy_errors import (
    AmbiguousOutputTokenLimitError,
    InputTokenLimitExceededError,
    InvalidChatMessagesError,
    InvalidOutputTokenLimitError,
    OutputTokenLimitExceededError,
)


def test_request_policy_errors_have_safe_metadata() -> None:
    errors = [
        InvalidOutputTokenLimitError("invalid", param="max_tokens"),
        OutputTokenLimitExceededError("too high", param="max_tokens"),
        InputTokenLimitExceededError("too many", param="messages"),
        AmbiguousOutputTokenLimitError("ambiguous", param="max_completion_tokens"),
        InvalidChatMessagesError("bad messages", param="messages"),
    ]

    for error in errors:
        assert isinstance(error.status_code, int)
        assert isinstance(error.error_type, str)
        assert isinstance(error.error_code, str)
        assert isinstance(error.safe_message, str)


def test_openai_mapping_preserves_request_policy_metadata() -> None:
    error = OutputTokenLimitExceededError("max too high", param="max_tokens")

    mapped = openai_error_from_request_policy_error(error)

    assert mapped.status_code == 400
    assert mapped.error_type == "invalid_request_error"
    assert mapped.code == "output_token_limit_exceeded"
    assert mapped.param == "max_tokens"
    assert mapped.message == "max too high"
