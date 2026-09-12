"""Bounded incremental SSE framing for the Local Coding transport."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import dataclass

import httpx

from slaif_gateway.providers.errors import ProviderResponseParseError
from slaif_gateway.providers.streaming import (
    MAX_CODEX_TYPED_RESPONSE_DELTA_BYTES,
    MAX_CODEX_TYPED_RESPONSE_SEMANTIC_BYTES,
    ParsedSSEEvent,
    format_sse_data,
)

# The strict Codex/Local terminal has at most three output items, each with at
# most one MiB of aggregate content/arguments; a one-MiB response envelope is
# retained separately. Individual progress/item/delta events are no larger
# than one MiB. JSON escaping can expand a one-byte control character to six
# ASCII bytes (``\\u00XX``); the remaining 128 KiB covers field names, IDs,
# indexes, usage arrays, punctuation, and other fixed JSON structure. This is
# a derivation, not a provider/client or environment-configurable limit.
JSON_ASCII_ESCAPE_EXPANSION = 6
JSON_STRUCTURAL_OVERHEAD_BYTES = 131_072
MAX_SSE_JOINED_DATA_BYTES = (
    MAX_CODEX_TYPED_RESPONSE_SEMANTIC_BYTES * JSON_ASCII_ESCAPE_EXPANSION
    + JSON_STRUCTURAL_OVERHEAD_BYTES
)
# vLLM emits one JSON data record per event; the compatibility tolerance is a
# finite 64 semantic-part allowance times 32 framing lines per part. Neither
# route nor provider data can raise this source constant.
MAX_SSE_SEMANTIC_PARTS = 64
MAX_SSE_LINES_PER_SEMANTIC_PART = 32
MAX_SSE_DATA_SEGMENTS = MAX_SSE_SEMANTIC_PARTS * MAX_SSE_LINES_PER_SEMANTIC_PART
MAX_SSE_LINE_BYTES = MAX_SSE_JOINED_DATA_BYTES + len(b"data: ") + 1  # optional CR
# Four existing 65,536-byte semantic delta bounds provide a finite allowance
# for ignored comments/fields; their content is discarded, not forwarded.
MAX_SSE_IGNORED_FIELD_MULTIPLIER = 4
MAX_SSE_IGNORED_FIELD_OVERHEAD_BYTES = (
    MAX_SSE_IGNORED_FIELD_MULTIPLIER * MAX_CODEX_TYPED_RESPONSE_DELTA_BYTES
)
MAX_SSE_DATA_LINE_OVERHEAD_BYTES = len(b"data: \r\n")
MAX_SSE_FRAME_BYTES = (
    MAX_SSE_JOINED_DATA_BYTES
    + MAX_SSE_DATA_SEGMENTS * MAX_SSE_DATA_LINE_OVERHEAD_BYTES
    - max(0, MAX_SSE_DATA_SEGMENTS - 1)  # already included joined-data newlines
    + MAX_SSE_IGNORED_FIELD_OVERHEAD_BYTES
    + len(b"\r\n")  # final blank-line delimiter
)


@dataclass(frozen=True, slots=True)
class SSEFramingLimits:
    """Static production limits; smaller values are accepted for unit tests."""

    max_line_bytes: int = MAX_SSE_LINE_BYTES
    max_frame_bytes: int = MAX_SSE_FRAME_BYTES
    max_joined_data_bytes: int = MAX_SSE_JOINED_DATA_BYTES
    max_data_segments: int = MAX_SSE_DATA_SEGMENTS

    def __post_init__(self) -> None:
        if (
            self.max_line_bytes < 1
            or self.max_line_bytes > MAX_SSE_LINE_BYTES
            or self.max_frame_bytes < 1
            or self.max_frame_bytes > MAX_SSE_FRAME_BYTES
            or self.max_joined_data_bytes < 1
            or self.max_joined_data_bytes > MAX_SSE_JOINED_DATA_BYTES
            or self.max_data_segments < 1
            or self.max_data_segments > MAX_SSE_DATA_SEGMENTS
        ):
            raise ValueError("Local Coding SSE framing limits are outside the reviewed bounds")


DEFAULT_SSE_FRAMING_LIMITS = SSEFramingLimits()


@dataclass(frozen=True, slots=True)
class SSEFramingStats:
    """Content-free bounded state exposed for tests and safe diagnostics."""

    events_emitted: int
    max_line_bytes_retained: int
    max_frame_bytes_retained: int
    max_joined_data_bytes_retained: int
    max_data_segments_retained: int
    current_line_bytes: int
    current_frame_bytes: int
    current_joined_data_bytes: int
    current_data_segments: int


def _parse_error(code: str, message: str) -> ProviderResponseParseError:
    return ProviderResponseParseError(
        provider="local-coding",
        error_code=code,
        safe_message=message,
    )


class BoundedSSEFramer:
    """Incrementally frame one raw Local Coding response without whole-stream state."""

    def __init__(self, *, limits: SSEFramingLimits = DEFAULT_SSE_FRAMING_LIMITS) -> None:
        self._limits = limits
        self._line = bytearray()
        self._data_segments: list[bytes] = []
        self._frame_bytes = 0
        self._joined_data_bytes = 0
        self._events_emitted = 0
        self._max_line_bytes = 0
        self._max_frame_bytes = 0
        self._max_joined_data_bytes = 0
        self._max_data_segments = 0

    @property
    def stats(self) -> SSEFramingStats:
        return SSEFramingStats(
            events_emitted=self._events_emitted,
            max_line_bytes_retained=self._max_line_bytes,
            max_frame_bytes_retained=self._max_frame_bytes,
            max_joined_data_bytes_retained=self._max_joined_data_bytes,
            max_data_segments_retained=self._max_data_segments,
            current_line_bytes=len(self._line),
            current_frame_bytes=self._frame_bytes,
            current_joined_data_bytes=self._joined_data_bytes,
            current_data_segments=len(self._data_segments),
        )

    async def iter_events(self, response: httpx.Response) -> AsyncIterator[ParsedSSEEvent]:
        """Yield one bounded parsed event at a time from an identity/raw response stream."""

        try:
            self._validate_content_encoding(response)
            async for chunk in response.aiter_raw():
                if not isinstance(chunk, bytes):
                    raise _parse_error(
                        "local_coding_sse_malformed_chunk",
                        "Local Coding returned an invalid streaming chunk.",
                    )
                for event in self._feed_chunk(chunk):
                    yield event
            for event in self._finish_at_eof():
                yield event
        except BaseException:
            self._clear_current_state()
            with suppress(BaseException):
                await response.aclose()
            raise

    def _validate_content_encoding(self, response: httpx.Response) -> None:
        content_encoding = response.headers.get("content-encoding")
        if content_encoding is None:
            return
        encodings = tuple(
            value.strip().lower() for value in content_encoding.split(",") if value.strip()
        )
        if encodings not in ((), ("identity",)):
            raise _parse_error(
                "local_coding_sse_content_encoding_unsupported",
                "Local Coding streaming content encoding is not supported.",
            )

    def _feed_chunk(self, chunk: bytes) -> Iterator[ParsedSSEEvent]:
        start = 0
        while start < len(chunk):
            newline = chunk.find(b"\n", start)
            has_newline = newline >= 0
            end = newline if has_newline else len(chunk)
            segment_length = end - start
            frame_increment = segment_length + (1 if has_newline else 0)
            self._retain_segment(chunk[start:end], frame_increment=frame_increment)
            if not has_newline:
                return
            start = newline + 1
            yield from self._complete_line()

    def _retain_segment(self, segment: bytes, *, frame_increment: int) -> None:
        if len(self._line) + len(segment) > self._limits.max_line_bytes:
            raise _parse_error(
                "local_coding_sse_line_too_large",
                "Local Coding returned an oversized SSE line.",
            )
        if self._frame_bytes + frame_increment > self._limits.max_frame_bytes:
            raise _parse_error(
                "local_coding_sse_frame_too_large",
                "Local Coding returned an oversized SSE frame.",
            )
        self._line.extend(segment)
        self._frame_bytes += frame_increment
        self._max_line_bytes = max(self._max_line_bytes, len(self._line))
        self._max_frame_bytes = max(self._max_frame_bytes, self._frame_bytes)

    def _complete_line(self) -> Iterator[ParsedSSEEvent]:
        raw_line = bytes(self._line)
        self._line.clear()
        line = raw_line[:-1] if raw_line.endswith(b"\r") else raw_line
        try:
            line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _parse_error(
                "local_coding_sse_invalid_utf8",
                "Local Coding returned invalid UTF-8 in its SSE stream.",
            ) from exc

        if not line:
            event = self._dispatch_event()
            if event is not None:
                yield event
            return
        if line.startswith(b":") or not line.startswith(b"data:"):
            return

        value = line[5:]
        if value.startswith(b" "):
            value = value[1:]
        if len(self._data_segments) >= self._limits.max_data_segments:
            raise _parse_error(
                "local_coding_sse_data_segments_too_many",
                "Local Coding returned too many SSE data segments.",
            )
        projected = self._joined_data_bytes + len(value)
        if self._data_segments:
            projected += 1
        if projected > self._limits.max_joined_data_bytes:
            raise _parse_error(
                "local_coding_sse_data_too_large",
                "Local Coding returned oversized SSE data.",
            )
        self._data_segments.append(bytes(value))
        self._joined_data_bytes = projected
        self._max_joined_data_bytes = max(self._max_joined_data_bytes, projected)
        self._max_data_segments = max(self._max_data_segments, len(self._data_segments))

    def _finish_at_eof(self) -> Iterator[ParsedSSEEvent]:
        if self._line:
            yield from self._complete_line()
        event = self._dispatch_event()
        if event is not None:
            yield event

    def _dispatch_event(self) -> ParsedSSEEvent | None:
        if not self._data_segments:
            self._reset_event()
            return None
        joined = b"\n".join(self._data_segments)
        try:
            data = joined.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _parse_error(
                "local_coding_sse_invalid_utf8",
                "Local Coding returned invalid UTF-8 in its SSE data.",
            ) from exc
        if data.strip() == "[DONE]":
            event = ParsedSSEEvent(
                data=data,
                raw_event=format_sse_data(data),
                json_body=None,
                is_done=True,
            )
            self._events_emitted += 1
            self._reset_event()
            return event
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise _parse_error(
                "local_coding_sse_invalid_json",
                "Local Coding returned invalid JSON in its SSE data.",
            ) from exc
        if not isinstance(parsed, dict):
            raise _parse_error(
                "local_coding_sse_json_not_object",
                "Local Coding SSE data must be a JSON object.",
            )
        event = ParsedSSEEvent(
            data=data,
            raw_event=format_sse_data(data),
            json_body=parsed,
            is_done=False,
        )
        self._events_emitted += 1
        self._reset_event()
        return event

    def _reset_event(self) -> None:
        self._data_segments.clear()
        self._frame_bytes = 0
        self._joined_data_bytes = 0

    def _clear_current_state(self) -> None:
        self._line.clear()
        self._data_segments.clear()
        self._frame_bytes = 0
        self._joined_data_bytes = 0
