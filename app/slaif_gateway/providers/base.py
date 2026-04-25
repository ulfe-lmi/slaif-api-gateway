"""Common provider adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderUsage


class ProviderAdapter(ABC):
    """Async interface implemented by upstream provider adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider name used by routing."""

    @abstractmethod
    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        """Forward a non-streaming Chat Completions request."""

    def parse_usage(self, payload: Mapping[str, Any]) -> ProviderUsage | None:
        """Parse optional usage metadata from an upstream JSON response."""
        usage = payload.get("usage")
        if not isinstance(usage, Mapping):
            return None

        other_usage = dict(usage)
        return ProviderUsage(
            prompt_tokens=_first_int(usage, "prompt_tokens", "input_tokens"),
            completion_tokens=_optional_int(
                _first_present(usage, "completion_tokens", "output_tokens")
            ),
            total_tokens=_optional_int(usage.get("total_tokens")),
            cached_tokens=_optional_int(
                _first_present(
                    usage,
                    "cached_tokens",
                    _nested_key("prompt_tokens_details", "cached_tokens"),
                    _nested_key("input_tokens_details", "cached_tokens"),
                )
            ),
            reasoning_tokens=_optional_int(
                _first_present(
                    usage,
                    "reasoning_tokens",
                    _nested_key("completion_tokens_details", "reasoning_tokens"),
                    _nested_key("output_tokens_details", "reasoning_tokens"),
                )
            ),
            other_usage=other_usage,
        )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _first_int(payload: Mapping[str, Any], *keys: str) -> int | None:
    return _optional_int(_first_present(payload, *keys))


def _first_present(payload: Mapping[str, Any], *keys: object) -> object:
    for key in keys:
        if isinstance(key, tuple):
            value = _nested_value(payload, key[0], key[1])
        elif isinstance(key, str):
            value = payload.get(key)
        else:
            value = None
        if value is not None:
            return value
    return None


def _nested_key(parent: str, key: str) -> tuple[str, str]:
    return parent, key


def _nested_value(payload: Mapping[str, Any], parent: str, key: str) -> object:
    nested = payload.get(parent)
    if not isinstance(nested, Mapping):
        return None
    return nested.get(key)
