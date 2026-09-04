from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from slaif_gateway.config import Settings
from slaif_gateway.modules.facial_scoring import FacialScoringAdapter
from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.providers.errors import MissingProviderApiKeyError, ProviderConfigurationError
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.providers.openai import OpenAIProviderAdapter
from slaif_gateway.providers.openai_compatible import OpenAICompatibleProviderAdapter
from slaif_gateway.providers.openrouter import OpenRouterProviderAdapter
from slaif_gateway.schemas.routing import RouteResolutionResult

LOCAL_CODING_ROUTE_CAPABILITIES = {
    "local_coding": {
        "contract_version": "local-coding-v1",
        "route_name": "factory-test",
        "tool_policy_version": "responses-tool-policy-v1",
        "identity_mode": "signed_identity_v1",
        "replay_mode": "process_local_ttl_lru",
        "deployment_mode": "single_worker",
    }
}


def test_factory_returns_openai_adapter() -> None:
    adapter = get_provider_adapter("openai", Settings(OPENAI_UPSTREAM_API_KEY="openai-key"))

    assert isinstance(adapter, OpenAIProviderAdapter)
    assert adapter._base_url == "https://api.openai.com/v1"


def test_factory_returns_openrouter_adapter() -> None:
    adapter = get_provider_adapter("openrouter", Settings(OPENROUTER_API_KEY="openrouter-key"))

    assert isinstance(adapter, OpenRouterProviderAdapter)
    assert adapter._base_url == "https://openrouter.ai/api/v1"


def test_factory_returns_static_facial_scoring_adapter(monkeypatch) -> None:
    monkeypatch.setenv("FACIAL_SCORING_API_KEY", "facial-native-key")
    route = RouteResolutionResult(
        requested_model="facial-manipulation-scoring",
        resolved_model="facial-manipulation-scoring",
        provider="facial_scoring",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="facial-manipulation-scoring",
        priority=100,
        provider_kind="module",
        provider_base_url="https://facial-native.example",
        provider_timeout_seconds=17,
        provider_max_retries=0,
    )

    adapter = get_provider_adapter(route, Settings())

    assert isinstance(adapter, FacialScoringAdapter)
    assert adapter.module_id == "facial_scoring"
    assert adapter._api_key == "facial-native-key"
    assert adapter._max_retries == 0


def test_factory_rejects_facial_scoring_secret_alias(monkeypatch) -> None:
    monkeypatch.setenv("OTHER_NATIVE_KEY", "facial-native-key")
    route = SimpleNamespace(
        provider="facial_scoring",
        provider_kind="module",
        provider_base_url="https://facial-native.example",
        provider_api_key_env_var="OTHER_NATIVE_KEY",
        provider_timeout_seconds=17,
        provider_max_retries=0,
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        get_provider_adapter(route, Settings())

    assert exc_info.value.error_code == "invalid_provider_configuration"
    assert "OTHER_NATIVE_KEY" not in str(exc_info.value)


def test_factory_builds_openai_adapter_from_route_metadata(monkeypatch) -> None:
    monkeypatch.setenv("CLASSROOM_OPENAI_KEY", "configured-openai-key")
    route = RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-test-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_base_url="https://gateway-openai.example/v1/",
        provider_api_key_env_var="CLASSROOM_OPENAI_KEY",
        provider_timeout_seconds=17,
        provider_max_retries=3,
    )

    adapter = get_provider_adapter(route, Settings(OPENAI_UPSTREAM_API_KEY=None))

    assert isinstance(adapter, OpenAIProviderAdapter)
    assert adapter._base_url == "https://gateway-openai.example/v1"
    assert adapter._api_key == "configured-openai-key"
    assert adapter._timeout_seconds == 17
    assert adapter._max_retries == 3


def test_factory_builds_openrouter_adapter_from_provider_config_metadata(monkeypatch) -> None:
    monkeypatch.setenv("CLASSROOM_OPENROUTER_KEY", "configured-openrouter-key")
    provider_config = SimpleNamespace(
        provider="openrouter",
        base_url="https://gateway-openrouter.example/api/v1",
        api_key_env_var="CLASSROOM_OPENROUTER_KEY",
        timeout_seconds=23,
        max_retries=1,
    )

    adapter = get_provider_adapter(provider_config, Settings(OPENROUTER_API_KEY=None))

    assert isinstance(adapter, OpenRouterProviderAdapter)
    assert adapter._base_url == "https://gateway-openrouter.example/api/v1"
    assert adapter._api_key == "configured-openrouter-key"
    assert adapter._timeout_seconds == 23
    assert adapter._max_retries == 1


def test_factory_missing_configured_api_key_env_var_raises_safe_error(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
    route = SimpleNamespace(provider="openai", api_key_env_var="MISSING_PROVIDER_KEY")

    with pytest.raises(MissingProviderApiKeyError) as exc_info:
        get_provider_adapter(route, Settings(OPENAI_UPSTREAM_API_KEY="fallback-must-not-be-used"))

    assert exc_info.value.provider == "openai"
    assert "fallback-must-not-be-used" not in exc_info.value.safe_message
    assert "MISSING_PROVIDER_KEY" in exc_info.value.safe_message


def test_factory_does_not_fallback_to_client_openai_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-provider-value-aaaaaaaa")
    monkeypatch.delenv("OPENAI_UPSTREAM_API_KEY", raising=False)

    with pytest.raises(MissingProviderApiKeyError) as exc_info:
        get_provider_adapter("openai", Settings(OPENAI_UPSTREAM_API_KEY=None))

    assert exc_info.value.provider == "openai"
    assert "OPENAI_UPSTREAM_API_KEY" in exc_info.value.safe_message
    assert "sk-real-provider-value" not in exc_info.value.safe_message


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        get_provider_adapter("unknown", Settings())

    assert exc_info.value.error_code == "unsupported_provider"


def test_factory_builds_generic_adapter_with_operator_slug(monkeypatch) -> None:
    monkeypatch.setenv("LAN_QWEN_KEY", "operator-key")
    route = SimpleNamespace(
        provider="lan-qwen-text",
        provider_kind="openai_compatible",
        provider_base_url="http://qwen.lan:8000/v1/",
        provider_api_key_env_var="LAN_QWEN_KEY",
        provider_timeout_seconds=12,
        provider_max_retries=1,
    )

    adapter = get_provider_adapter(route, Settings())

    assert isinstance(adapter, OpenAICompatibleProviderAdapter)
    assert adapter.provider_name == "lan-qwen-text"
    assert adapter._base_url == "http://qwen.lan:8000/v1"
    assert adapter._api_key == "operator-key"


def test_factory_builds_local_coding_responses_only_adapter_from_route_metadata(monkeypatch) -> None:
    service_secret = "factory-local-coding-service-bearer-secret-0123456789"
    monkeypatch.setenv("FACTORY_LOCAL_CODING_KEY", service_secret)
    route = SimpleNamespace(
        provider="local-model",
        provider_kind="openai_compatible",
        provider_base_url="http://local-coding.lan/v1",
        provider_api_key_env_var="FACTORY_LOCAL_CODING_KEY",
        provider_timeout_seconds=12,
        provider_max_retries=0,
        capabilities=LOCAL_CODING_ROUTE_CAPABILITIES,
    )

    adapter = get_provider_adapter(
        route,
        Settings(
            LOCAL_CODING_SIGNING_SECRET_V1="factory-local-coding-signing-secret-0123456789",
            LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1="factory-local-coding-derivation-secret-0123456789",
        ),
    )

    assert isinstance(adapter, LocalCodingAdapter)
    assert not isinstance(adapter, OpenAIProviderAdapter)
    assert adapter._api_key == service_secret
    assert adapter._base_url == "http://local-coding.lan/v1"


def test_factory_rejects_generic_bad_url_and_client_env_name(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "client-key-must-not-be-used")
    route = SimpleNamespace(
        provider="lan-qwen-text",
        provider_kind="openai_compatible",
        provider_base_url="http://qwen.lan:8000/model",
        provider_api_key_env_var="OPENAI_API_KEY",
    )

    with pytest.raises(ProviderConfigurationError):
        get_provider_adapter(route, Settings())


def test_generic_adapter_never_falls_back_to_openai_secret() -> None:
    adapter = OpenAICompatibleProviderAdapter(
        Settings(OPENAI_UPSTREAM_API_KEY="built-in-secret"),
        provider_name="lan-qwen-text",
        base_url="https://qwen.lan/v1",
    )

    with pytest.raises(MissingProviderApiKeyError) as exc_info:
        import asyncio

        asyncio.run(adapter.forward_chat_completion(SimpleNamespace(
            endpoint="/v1/chat/completions",
            body={"messages": []},
            upstream_model="qwen",
            request_id="request",
            extra_headers={},
        )))

    assert exc_info.value.provider == "lan-qwen-text"
    assert "built-in-secret" not in str(exc_info.value)
