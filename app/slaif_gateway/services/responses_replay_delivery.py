"""Bounded, memory-only delivery barrier for client-managed replay events.

Validation and authorization remain owned by the gateway. This buffer merely
keeps a client from retaining an item before its replay authorization commits.
After the first such item, the whole tail is held to preserve SSE ordering.
"""

from collections.abc import Iterator, Mapping
from typing import Any


class ReplayDeliveryBufferFull(ValueError):
    """No payload or identifier is included in a buffer overflow error."""


class ResponsesReplayDeliveryBuffer:
    def __init__(self, *, enabled: bool, encrypted_reasoning: bool, max_bytes: int):
        self.enabled = enabled
        self.encrypted_reasoning = encrypted_reasoning
        self.max_bytes = max_bytes
        self.pending = False
        self.incomplete_item = False
        self._events: list[str] = []
        self._bytes = 0

    def hold(self, payload: Mapping[str, Any] | None, event: str) -> bool:
        """Receive only already-validated events; return whether delivery is held."""
        if not self.enabled:
            return False
        if isinstance(payload, Mapping) and payload.get("type") in {
            "response.output_item.added", "response.output_item.done",
        }:
            item = payload.get("item")
            if isinstance(item, Mapping):
                kind = item.get("type")
                if kind in {"function_call", "custom_tool_call"} or (
                    kind == "reasoning" and self.encrypted_reasoning
                ):
                    self.pending = True
                    if item.get("status") == "incomplete" and (
                        kind != "reasoning" or bool(item.get("encrypted_content"))
                    ):
                        self.incomplete_item = True
        if not self.pending:
            return False
        size = len(event.encode("utf-8"))
        if self._bytes + size > self.max_bytes:
            raise ReplayDeliveryBufferFull from None
        self._events.append(event)
        self._bytes += size
        return True

    def release(self) -> Iterator[str]:
        """The caller must commit accounting and replay ownership before release."""
        yield from self._events
        self.clear()

    def clear(self) -> None:
        self._events.clear()
        self._bytes = 0
