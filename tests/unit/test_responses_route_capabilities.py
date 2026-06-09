from __future__ import annotations

import pytest

from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_route_capabilities import (
    default_responses_capabilities,
    enforce_responses_route_capabilities,
    ensure_default_responses_capabilities,
)


def test_responses_text_route_capability_passes_when_explicit() -> None:
    enforce_responses_route_capabilities(
        route_capabilities={"responses": default_responses_capabilities()}
    )


def test_responses_streaming_route_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        streaming_requested=True,
        route_supports_streaming=True,
    )


def test_json_mode_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["json_mode"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        json_mode_requested=True,
    )


def test_structured_output_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["structured_outputs"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        structured_output_requested=True,
    )


def test_function_tools_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["function_tools"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        function_tools_requested=True,
    )


def test_custom_tools_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["custom_tools"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        custom_tools_requested=True,
    )


def test_image_input_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["image_input"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        image_input_requested=True,
    )


def test_file_input_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["file_input"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        file_input_requested=True,
    )


def test_input_token_count_capability_passes_when_explicit() -> None:
    capabilities = default_responses_capabilities()
    capabilities["input_token_count"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        input_token_count_requested=True,
    )


def test_stored_response_capability_passes_when_explicit_without_stateless() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["stored_responses"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        stored_responses_requested=True,
    )


def test_previous_response_id_capability_passes_when_explicit_without_stateless() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["previous_response_id"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        previous_response_id_requested=True,
    )


def test_list_input_items_capability_passes_when_explicit_without_stateless() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["list_input_items"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        list_input_items_requested=True,
    )


def test_compact_capability_passes_when_explicit_without_stateless() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["compact"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        compact_requested=True,
    )


def test_conversations_capability_passes_when_explicit_without_stateless() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["conversations"] = True

    enforce_responses_route_capabilities(
        route_capabilities={"responses": capabilities},
        conversations_requested=True,
    )


def test_default_responses_capabilities_keep_stored_responses_disabled() -> None:
    capabilities = default_responses_capabilities()

    assert capabilities["stored_responses"] is False
    assert capabilities["previous_response_id"] is False
    assert capabilities["list_input_items"] is False
    assert capabilities["compact"] is False
    assert capabilities["conversations"] is False


def test_streaming_image_input_requires_streaming_capability_too() -> None:
    capabilities = default_responses_capabilities()
    capabilities["image_input"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            streaming_requested=True,
            route_supports_streaming=True,
            image_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_route_capability_not_supported"
    assert exc_info.value.param == "stream"


def test_streaming_file_input_requires_streaming_capability_too() -> None:
    capabilities = default_responses_capabilities()
    capabilities["file_input"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            streaming_requested=True,
            route_supports_streaming=True,
            file_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_route_capability_not_supported"
    assert exc_info.value.param == "stream"


def test_streaming_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            streaming_requested=True,
            route_supports_streaming=True,
        )

    assert exc_info.value.error_code == "responses_route_capability_not_supported"
    assert exc_info.value.param == "stream"


def test_json_mode_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            json_mode_requested=True,
        )

    assert exc_info.value.error_code == "responses_json_mode_not_supported"
    assert exc_info.value.param == "text.format"


def test_structured_output_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            structured_output_requested=True,
        )

    assert exc_info.value.error_code == "responses_structured_output_not_supported"
    assert exc_info.value.param == "text.format"


def test_function_tools_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            function_tools_requested=True,
        )

    assert exc_info.value.error_code == "responses_function_tool_capability_not_supported"
    assert exc_info.value.param == "tools"


def test_custom_tools_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            custom_tools_requested=True,
        )

    assert exc_info.value.error_code == "responses_custom_tool_capability_not_supported"
    assert exc_info.value.param == "tools"


def test_image_input_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            image_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_image_input_capability_not_supported"
    assert exc_info.value.param == "input"


def test_list_input_items_request_requires_explicit_capability() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stored_responses"] = True
    capabilities["previous_response_id"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            list_input_items_requested=True,
        )

    assert exc_info.value.error_code == "responses_list_input_items_capability_not_supported"
    assert exc_info.value.param == "response_id"


def test_file_input_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            file_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_file_input_capability_not_supported"
    assert exc_info.value.param == "input"


def test_input_token_count_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            input_token_count_requested=True,
        )

    assert exc_info.value.error_code == "responses_input_token_count_capability_not_supported"
    assert exc_info.value.param == "model"


def test_compact_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            compact_requested=True,
        )

    assert exc_info.value.error_code == "responses_compact_capability_not_supported"
    assert exc_info.value.param == "model"


def test_conversation_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            conversations_requested=True,
        )

    assert exc_info.value.error_code == "responses_conversation_capability_not_supported"
    assert exc_info.value.param == "conversation"


def test_stateful_response_capabilities_do_not_imply_compact() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stored_responses"] = True
    capabilities["previous_response_id"] = True
    capabilities["list_input_items"] = True
    capabilities["input_token_count"] = True
    capabilities["stateless"] = False

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            compact_requested=True,
        )

    assert exc_info.value.error_code == "responses_compact_capability_not_supported"


def test_stateful_response_capabilities_do_not_imply_conversations() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stored_responses"] = True
    capabilities["previous_response_id"] = True
    capabilities["list_input_items"] = True
    capabilities["compact"] = True
    capabilities["stateless"] = False

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            conversations_requested=True,
        )

    assert exc_info.value.error_code == "responses_conversation_capability_not_supported"


def test_store_true_request_fails_when_stored_response_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            stored_responses_requested=True,
        )

    assert exc_info.value.error_code == "responses_stored_response_capability_not_supported"
    assert exc_info.value.param == "store"


def test_previous_response_id_request_fails_when_capability_absent() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": default_responses_capabilities()},
            previous_response_id_requested=True,
        )

    assert exc_info.value.error_code == "responses_previous_response_capability_not_supported"
    assert exc_info.value.param == "previous_response_id"


def test_stored_response_capability_alone_does_not_allow_previous_response_id() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["stored_responses"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            previous_response_id_requested=True,
        )

    assert exc_info.value.error_code == "responses_previous_response_capability_not_supported"


def test_store_false_still_requires_stateless_capability() -> None:
    capabilities = default_responses_capabilities()
    capabilities["stateless"] = False
    capabilities["stored_responses"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(route_capabilities={"responses": capabilities})

    assert exc_info.value.error_code == "responses_route_capability_not_supported"
    assert exc_info.value.param == "model"


def test_function_tools_capability_does_not_imply_custom_tools() -> None:
    capabilities = default_responses_capabilities()
    capabilities["function_tools"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            custom_tools_requested=True,
        )

    assert exc_info.value.error_code == "responses_custom_tool_capability_not_supported"


def test_create_response_capabilities_do_not_imply_input_token_count() -> None:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = True
    capabilities["function_tools"] = True
    capabilities["custom_tools"] = True
    capabilities["image_input"] = True
    capabilities["file_input"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            input_token_count_requested=True,
        )

    assert exc_info.value.error_code == "responses_input_token_count_capability_not_supported"


def test_streaming_request_fails_when_route_flag_absent() -> None:
    capabilities = default_responses_capabilities()
    capabilities["streaming"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            streaming_requested=True,
            route_supports_streaming=False,
        )

    assert exc_info.value.error_code == "responses_route_capability_not_supported"
    assert exc_info.value.param == "stream"


def test_missing_responses_capability_fails_closed() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(route_capabilities={"chat_completions": {"chat_text": True}})

    assert exc_info.value.error_code == "responses_route_capability_missing"
    assert exc_info.value.param == "model"


def test_false_text_capability_rejects() -> None:
    capabilities = default_responses_capabilities()
    capabilities["text"] = False

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(route_capabilities={"responses": capabilities})

    assert exc_info.value.error_code == "responses_route_capability_not_supported"


def test_unknown_capability_metadata_rejects() -> None:
    capabilities = default_responses_capabilities()
    capabilities["hosted_web_search"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(route_capabilities={"responses": capabilities})

    assert exc_info.value.error_code == "responses_route_capability_invalid"


def test_defaults_are_added_only_for_responses_routes() -> None:
    assert "responses" in ensure_default_responses_capabilities(None, endpoint="/v1/responses")
    assert "responses" in ensure_default_responses_capabilities(
        None,
        endpoint="/v1/responses/input_tokens",
    )
    assert "responses" in ensure_default_responses_capabilities(
        None,
        endpoint="/v1/responses/compact",
    )
    assert ensure_default_responses_capabilities(None, endpoint="/v1/chat/completions") == {}


def test_default_responses_capabilities_keep_custom_tools_disabled() -> None:
    capabilities = default_responses_capabilities()

    assert capabilities["custom_tools"] is False


def test_default_responses_capabilities_keep_image_input_disabled() -> None:
    capabilities = default_responses_capabilities()

    assert capabilities["image_input"] is False


def test_default_responses_capabilities_keep_file_input_disabled() -> None:
    capabilities = default_responses_capabilities()

    assert capabilities["file_input"] is False


def test_chat_image_capability_does_not_imply_responses_image_input() -> None:
    capabilities = default_responses_capabilities()
    capabilities["chat_image_inputs"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            image_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_route_capability_invalid"


def test_responses_image_input_does_not_imply_file_input() -> None:
    capabilities = default_responses_capabilities()
    capabilities["image_input"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            file_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_file_input_capability_not_supported"


def test_chat_file_capability_does_not_imply_responses_file_input() -> None:
    capabilities = default_responses_capabilities()
    capabilities["chat_file_inputs"] = True

    with pytest.raises(RequestPolicyError) as exc_info:
        enforce_responses_route_capabilities(
            route_capabilities={"responses": capabilities},
            file_input_requested=True,
        )

    assert exc_info.value.error_code == "responses_route_capability_invalid"
