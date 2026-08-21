"""Provider-category request checks that must run before generic forwarding."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from slaif_gateway.schemas.routing import RouteResolutionResult

_BUILTIN_PROVIDERS = frozenset({"openai", "openrouter"})
_INLINE_IMAGE_DATA_URL = re.compile(
    r"^data:image/(?:png|jpeg|webp|gif);base64,",
    re.IGNORECASE,
)


class OpenAICompatibleRequestBoundaryError(ValueError):
    """A safe request-boundary rejection for a generic provider route."""

    def __init__(self, *, param: str) -> None:
        self.param = param
        super().__init__(param)


def enforce_openai_compatible_request_boundary(
    body: Mapping[str, Any],
    *,
    route: RouteResolutionResult,
    endpoint: str,
) -> None:
    """Reject generic-provider image fetch markers before side effects.

    This deliberately walks only image fields defined by the selected endpoint;
    arbitrary URLs in tool schemas, descriptions, and tool payloads are not
    interpreted as provider fetch requests here.
    """

    if route.provider_kind != "openai_compatible":
        return
    if route.provider.lower() in _BUILTIN_PROVIDERS:
        return

    if endpoint == "chat.completions":
        _check_chat_images(body)
    elif endpoint == "responses":
        _check_response_images(body)


def _check_chat_images(body: Mapping[str, Any]) -> None:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    for message_index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part_index, part in enumerate(content):
            if not isinstance(part, Mapping) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            param = f"messages[{message_index}].content[{part_index}].image_url.url"
            if not isinstance(image_url, Mapping) or not isinstance(image_url.get("url"), str):
                raise OpenAICompatibleRequestBoundaryError(param=param)
            _require_inline_image(image_url["url"], param=param)


def _check_response_images(body: Mapping[str, Any]) -> None:
    inputs = body.get("input")
    if not isinstance(inputs, list):
        return
    for input_index, item in enumerate(inputs):
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "input_image":
            _check_response_image_part(
                item,
                param=f"input[{input_index}].image_url",
            )
            continue
        if item.get("type") != "message" and "role" not in item:
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part_index, part in enumerate(content):
            if not isinstance(part, Mapping) or part.get("type") != "input_image":
                continue
            _check_response_image_part(
                part,
                param=f"input[{input_index}].content[{part_index}].image_url",
            )


def _check_response_image_part(part: Mapping[str, Any], *, param: str) -> None:
    value = part.get("image_url")
    if not isinstance(value, str):
        raise OpenAICompatibleRequestBoundaryError(param=param)
    _require_inline_image(value, param=param)


def _require_inline_image(value: str, *, param: str) -> None:
    if not _INLINE_IMAGE_DATA_URL.match(value):
        raise OpenAICompatibleRequestBoundaryError(param=param)
