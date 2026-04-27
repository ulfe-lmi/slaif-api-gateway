"""Helpers for OpenAI-compatible provider SSE streaming."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ParsedSSEEvent:
    """Parsed SSE event data from an upstream provider."""

    data: str
    raw_event: str
    json_body: Mapping[str, Any] | None
    is_done: bool


def parse_sse_lines(lines: Iterable[str]) -> list[ParsedSSEEvent]:
    """Parse complete SSE events from line strings.

    This helper is intentionally small and does not log or persist event data.
    """
    events: list[ParsedSSEEvent] = []
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                events.append(_event_from_data_lines(data_lines))
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)

    if data_lines:
        events.append(_event_from_data_lines(data_lines))
    return events


def format_sse_data(data: str) -> str:
    """Format data as an SSE event compatible with OpenAI SDK streaming."""
    return "".join(f"data: {line}\n" for line in data.splitlines() or [""]) + "\n"


def format_openai_error_event(*, message: str, error_type: str, code: str | None) -> str:
    """Format a safe OpenAI-shaped error event for an already-open stream."""
    payload = {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": code,
        }
    }
    return format_sse_data(json.dumps(payload, separators=(",", ":")))


def _event_from_data_lines(data_lines: list[str]) -> ParsedSSEEvent:
    data = "\n".join(data_lines)
    json_body: Mapping[str, Any] | None = None
    is_done = data.strip() == "[DONE]"
    if not is_done:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping):
            json_body = parsed

    return ParsedSSEEvent(
        data=data,
        raw_event=format_sse_data(data),
        json_body=json_body,
        is_done=is_done,
    )
