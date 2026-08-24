from __future__ import annotations

import uuid

import pytest

from slaif_gateway.api import admin as admin_module
from slaif_gateway.config import Settings
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
    ChatCompletionRouteCapabilityError,
    default_chat_completion_capabilities,
    enforce_chat_completion_route_capabilities,
)


def _module_route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="module-score",
        resolved_model="module-score-v1",
        provider="test-module",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="module-score",
        priority=100,
        provider_kind="module",
        provider_base_url="https://module.example/score",
        provider_api_key_env_var="MODULE_UPSTREAM_KEY",
    )


def test_unregistered_module_fails_closed_without_dynamic_import(monkeypatch) -> None:
    monkeypatch.setenv("MODULE_UPSTREAM_KEY", "module-secret")

    with pytest.raises(ProviderConfigurationError) as exc_info:
        get_provider_adapter(_module_route(), Settings())

    assert exc_info.value.error_code == "unsupported_module"
    assert "module-secret" not in str(exc_info.value)


def test_admin_validation_accepts_module_url_without_hardcoded_v1_path() -> None:
    form = {
        "provider": "face-score",
        "display_name": "Face score",
        "kind": "module",
        "base_url": "https://operator.example/score/v1",
        "api_key_env_var": "FACE_SCORE_KEY",
        "enabled": "true",
        "timeout_seconds": "30",
        "max_retries": "0",
        "notes": "foundation only",
        "reason": "reviewed module metadata",
        "confirm_insecure_http": "",
    }

    parsed = admin_module._parse_provider_config_form(form, require_reason=True)

    assert parsed["kind"] == "module"
    assert parsed["base_url"] == "https://operator.example/score/v1"


def test_module_streaming_is_denied_even_if_route_metadata_is_broad() -> None:
    capabilities = default_chat_completion_capabilities(supports_streaming=True)
    with pytest.raises(ChatCompletionRouteCapabilityError) as exc_info:
        enforce_chat_completion_route_capabilities(
            {
                "model": "module-score",
                "messages": [],
                "stream": True,
            },
            route_capabilities={CHAT_COMPLETIONS_CAPABILITIES_KEY: capabilities},
            route_supports_streaming=True,
            requested_model="module-score",
            provider_kind="module",
        )

    assert exc_info.value.error_code == "module_streaming_not_supported"
    assert exc_info.value.param == "stream"
