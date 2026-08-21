from __future__ import annotations

from types import SimpleNamespace

import pytest

from slaif_gateway.services.openai_compatible_request_boundary import (
    OpenAICompatibleRequestBoundaryError,
    enforce_openai_compatible_request_boundary,
)


def _route(*, provider: str = "lan-qwen", kind: str = "openai_compatible"):
    return SimpleNamespace(provider=provider, provider_kind=kind)


def test_generic_chat_allows_multiple_inline_images() -> None:
    enforce_openai_compatible_request_boundary(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAAA"},
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/webp;base64,BBBB"},
                        },
                    ],
                }
            ]
        },
        route=_route(),
        endpoint="chat.completions",
    )


@pytest.mark.parametrize(
    ("endpoint", "body", "param"),
    [
        (
            "chat.completions",
            {
                "messages": [
                    {
                        "content": [
                            {"type": "image_url", "image_url": {"url": "https://lan/image.png"}}
                        ]
                    }
                ]
            },
            "messages[0].content[0].image_url.url",
        ),
        (
            "responses",
            {
                "input": [
                    {
                        "type": "message",
                        "content": [{"type": "input_image", "image_url": "file_id_123"}],
                    }
                ]
            },
            "input[0].content[0].image_url",
        ),
    ],
)
def test_generic_provider_rejects_external_or_file_image_markers(
    endpoint: str, body: dict[str, object], param: str
) -> None:
    with pytest.raises(OpenAICompatibleRequestBoundaryError) as raised:
        enforce_openai_compatible_request_boundary(body, route=_route(), endpoint=endpoint)
    assert raised.value.param == param
    assert "https://" not in str(raised.value)
    assert "file_id_123" not in str(raised.value)


def test_responses_direct_inline_image_is_allowed_and_tool_urls_are_ignored() -> None:
    enforce_openai_compatible_request_boundary(
        {
            "input": [
                {"type": "input_image", "image_url": "data:image/jpeg;base64,AAAA"},
            ],
            "tools": [{"type": "function", "function": {"description": "https://example.invalid"}}],
        },
        route=_route(),
        endpoint="responses",
    )


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_builtin_providers_are_unchanged(provider: str) -> None:
    enforce_openai_compatible_request_boundary(
        {
            "messages": [
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.invalid/image.png"}}
                    ]
                }
            ]
        },
        route=_route(provider=provider),
        endpoint="chat.completions",
    )


def test_non_generic_provider_is_unchanged() -> None:
    enforce_openai_compatible_request_boundary(
        {
            "messages": [
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.invalid/image.png"}}
                    ]
                }
            ]
        },
        route=_route(kind="openai"),
        endpoint="chat.completions",
    )
