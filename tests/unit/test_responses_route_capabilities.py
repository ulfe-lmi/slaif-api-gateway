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
    assert ensure_default_responses_capabilities(None, endpoint="/v1/chat/completions") == {}
