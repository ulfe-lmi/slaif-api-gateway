from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from slaif_gateway.services.openai_compatible_discovery import (
    DiscoveryError,
    discover_openai_compatible_models,
)


def _provider(**overrides: object) -> SimpleNamespace:
    values = {
        "provider": "lan-qwen",
        "kind": "openai_compatible",
        "enabled": True,
        "base_url": "https://qwen.example/v1",
        "api_key_env_var": "LAN_QWEN_KEY",
        "timeout_seconds": 12,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_discovery_uses_exact_bounded_authenticated_models_request(respx_mock) -> None:
    route = respx_mock.get("https://qwen.example/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "qwen/a"}, {"id": "qwen/b", "owned_by": "safe"}]},
            headers={"content-type": "application/json"},
        )
    )

    result = await discover_openai_compatible_models(
        _provider(), secret_lookup=lambda name: "operator-secret" if name == "LAN_QWEN_KEY" else None
    )

    assert result.provider == "lan-qwen"
    assert result.models == ("qwen/a", "qwen/b")
    assert route.called
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url == "https://qwen.example/v1/models"
    assert dict(request.headers) == {
        "host": "qwen.example",
        "accept": "application/json",
        "authorization": "Bearer operator-secret",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "provider", "secret", "message"),
    [
        (httpx.Response(200, json={"data": [{"id": "qwen/a"}, {"id": "qwen/a"}]}), None, "secret", "duplicate"),
        (httpx.Response(200, json={"data": [{"id": "Bearer secret"}]}), None, "secret", "unsafe"),
        (httpx.Response(200, json={"data": [{"id": "https://host/model"}]}), None, "secret", "unsafe"),
        (httpx.Response(302, headers={"location": "https://elsewhere"}), None, "secret", "redirect"),
        (httpx.Response(200, json={"data": []}, headers={"content-type": "text/plain"}), None, "secret", "JSON"),
        (httpx.Response(200, json={"data": [{"id": "qwen/a"}]}), SimpleNamespace(enabled=False), "secret", "disabled"),
        (httpx.Response(200, json={"data": [{"id": "qwen/a"}]}), None, None, "unavailable"),
    ],
)
async def test_discovery_rejects_bounded_negative_cases(
    respx_mock, response: httpx.Response, provider: SimpleNamespace | None, secret: str | None, message: str
) -> None:
    respx_mock.get("https://qwen.example/v1/models").mock(return_value=response)
    row = _provider(**(vars(provider) if provider is not None else {}))
    with pytest.raises(DiscoveryError, match=message):
        await discover_openai_compatible_models(row, secret_lookup=lambda _: secret)


@pytest.mark.asyncio
async def test_discovery_rejects_oversize_response_before_json_materialization(respx_mock) -> None:
    respx_mock.get("https://qwen.example/v1/models").mock(
        return_value=httpx.Response(
            200,
            content=b"{}",
            headers={"content-type": "application/json", "content-length": "1048577"},
        )
    )
    with pytest.raises(DiscoveryError, match="too large"):
        await discover_openai_compatible_models(_provider(), secret_lookup=lambda _: "secret")


@pytest.mark.asyncio
async def test_discovery_rejects_built_in_provider_and_does_not_call_upstream(respx_mock) -> None:
    route = respx_mock.get("https://qwen.example/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(DiscoveryError):
        await discover_openai_compatible_models(_provider(provider="openai"), secret_lookup=lambda _: "secret")
    assert not route.called
