from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
)
from slaif_gateway.modules.servers.local_coding.sse_framing import (
    DEFAULT_SSE_FRAMING_LIMITS,
    MAX_SSE_DATA_SEGMENTS,
    MAX_SSE_DATA_LINE_OVERHEAD_BYTES,
    MAX_SSE_FRAME_BYTES,
    MAX_SSE_JOINED_DATA_BYTES,
    MAX_SSE_LINE_BYTES,
    BoundedSSEFramer,
    SSEFramingLimits,
)
from slaif_gateway.providers.errors import ProviderResponseParseError
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.config import Settings


SERVICE_SECRET = "local-coding-service-bearer-secret-0123456789"
STATIC_ROUTE_CAPABILITIES = {
    "local_coding": {
        "contract_version": LOCAL_CODING_SERVER_MODULE_ID,
        "route_name": "vision",
        "tool_policy_version": "responses-tool-policy-v1",
        "identity_mode": "static",
        "replay_mode": "process_local_ttl_lru",
        "deployment_mode": "single_worker",
    }
}


# This literal map is the review manifest for Objective 163's regression
# obligations.  Parameter IDs are intentionally descriptive and stable so the
# collector can prove that no mapped sibling was silently omitted.
LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE = {
    "framing.normal": "tests/unit/test_local_coding_sse_framing.py::test_framer_preserves_normal_events_across_ordinary_network_chunks",
    "framing.byte-by-byte-utf8": "tests/unit/test_local_coding_sse_framing.py::test_framer_handles_normal_small_chunks_and_utf8_split_at_byte_boundaries",
    "framing.crlf": "tests/unit/test_local_coding_sse_framing.py::test_framer_handles_crlf_split_boundary_and_multiline_data",
    "framing.multiline-data": "tests/unit/test_local_coding_sse_framing.py::test_framer_handles_crlf_split_boundary_and_multiline_data",
    "framing.comments-ignored-fields": "tests/unit/test_local_coding_sse_framing.py::test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event",
    "bounds.derivation": "tests/unit/test_local_coding_sse_framing.py::test_static_bound_derivation_is_explicit_and_cannot_be_raised",
    "bounds.maximum-event": "tests/unit/test_local_coding_sse_framing.py::test_maximum_reviewed_semantic_event_serializes_within_all_wire_ceilings",
    "bounds.line-one-byte-over": "tests/unit/test_local_coding_sse_framing.py::test_one_byte_over_bounds_fail_before_oversized_state_is_retained[line-one-byte-over]",
    "bounds.frame-one-byte-over": "tests/unit/test_local_coding_sse_framing.py::test_one_byte_over_bounds_fail_before_oversized_state_is_retained[frame-one-byte-over]",
    "bounds.joined-data-one-byte-over": "tests/unit/test_local_coding_sse_framing.py::test_one_byte_over_bounds_fail_before_oversized_state_is_retained[joined-data-one-byte-over]",
    "bounds.data-segments-one-byte-over": "tests/unit/test_local_coding_sse_framing.py::test_one_byte_over_bounds_fail_before_oversized_state_is_retained[data-segments-one-byte-over]",
    "bounds.unterminated-line": "tests/unit/test_local_coding_sse_framing.py::test_unterminated_line_fails_at_first_over_bound_byte",
    "bounds.many-data-lines": "tests/unit/test_local_coding_sse_framing.py::test_many_small_data_segments_are_bounded_before_joining",
    "eof.valid-final-event": "tests/unit/test_local_coding_sse_framing.py::test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event",
    "eof.malformed-final-event": "tests/unit/test_local_coding_sse_framing.py::test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[invalid-json]",
    "eof.comment-only": "tests/unit/test_local_coding_sse_framing.py::test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event",
    "parse.invalid-json": "tests/unit/test_local_coding_sse_framing.py::test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[invalid-json]",
    "parse.non-object-json": "tests/unit/test_local_coding_sse_framing.py::test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[non-object-json]",
    "parse.invalid-utf8": "tests/unit/test_local_coding_sse_framing.py::test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[invalid-utf8]",
    "parse.dangling-utf8": "tests/unit/test_local_coding_sse_framing.py::test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[dangling-utf8]",
    "close.parser-error": "tests/unit/test_local_coding_sse_framing.py::test_local_adapter_uses_bounded_framer_and_closes_after_parse_error",
    "close.consumer-aclose": "tests/unit/test_local_coding_sse_framing.py::test_consumer_aclose_closes_upstream_stream_promptly",
    "close.cancellation": "tests/unit/test_local_coding_sse_framing.py::test_cancellation_closes_upstream_stream_and_is_not_swallowed",
    "incremental.many-events": "tests/unit/test_local_coding_sse_framing.py::test_done_marker_and_many_events_are_incremental_and_content_free_stats_only",
    "encoding.unsupported": "tests/unit/test_local_coding_sse_framing.py::test_unsupported_content_encoding_fails_before_raw_iteration",
    "accounting.pre-output": "tests/e2e/test_openai_python_client_responses.py::test_local_coding_malformed_stream_before_output_releases_accounting",
    "accounting.post-output": "tests/e2e/test_openai_python_client_responses.py::test_local_coding_malformed_stream_after_output_records_interruption",
    "objective-162.zero-argument": "tests/unit/test_responses_codex_streaming_tools.py::test_codex_0149_zero_argument_source_lifecycle_accepts_without_synthetic_events",
    "objective-162.function-lifecycle": "tests/unit/test_responses_codex_streaming_tools.py::test_codex_0149_function_lifecycle_is_ordered_and_declared",
    "objective-162.reasoning-message-terminal": "tests/unit/test_responses_codex_streaming_tools.py::test_reasoning_message_and_terminal_event_table_is_bounded",
    "objective-162.usage": "tests/unit/test_responses_codex_streaming_tools.py::test_codex_0149_completed_requires_usage_and_no_active_output",
    "objective-162.replay-privacy": "tests/unit/test_responses_codex_streaming_tools.py::test_event_and_replay_size_caps_fail_closed_without_echoing_content",
}


def test_objective_163_obligation_map_is_literal_and_nonempty() -> None:
    assert set(LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE)
    assert all("[" not in key for key in LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE)
    assert all(
        value.startswith("tests/") for value in LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE.values()
    )


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.iterated = False
        self.closed = False

    async def __aiter__(self):
        self.iterated = True
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class CancelledStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        raise asyncio.CancelledError
        yield b""

    async def aclose(self) -> None:
        self.closed = True


def _response(stream: ChunkStream, *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream", **(headers or {})},
        stream=stream,
        request=httpx.Request("POST", "http://local-coding.test/v1/responses"),
    )


def _event_bytes(payload: object, *, ending: bytes = b"\n\n") -> bytes:
    return (
        b"data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + ending
    )


def _small_limits(**overrides: int) -> SSEFramingLimits:
    values = {
        "max_line_bytes": 64,
        "max_frame_bytes": 128,
        "max_joined_data_bytes": 64,
        "max_data_segments": 8,
    }
    values.update(overrides)
    return SSEFramingLimits(**values)


async def _collect(framer: BoundedSSEFramer, response: httpx.Response):
    return [event async for event in framer.iter_events(response)]


def test_static_bound_derivation_is_explicit_and_cannot_be_raised() -> None:
    assert DEFAULT_SSE_FRAMING_LIMITS.max_line_bytes == MAX_SSE_LINE_BYTES
    assert DEFAULT_SSE_FRAMING_LIMITS.max_frame_bytes == MAX_SSE_FRAME_BYTES
    assert DEFAULT_SSE_FRAMING_LIMITS.max_joined_data_bytes == MAX_SSE_JOINED_DATA_BYTES
    assert DEFAULT_SSE_FRAMING_LIMITS.max_data_segments == MAX_SSE_DATA_SEGMENTS
    with pytest.raises(ValueError):
        SSEFramingLimits(max_line_bytes=MAX_SSE_LINE_BYTES + 1)
    with pytest.raises(ValueError):
        SSEFramingLimits(max_frame_bytes=MAX_SSE_FRAME_BYTES + 1)
    with pytest.raises(ValueError):
        SSEFramingLimits(max_joined_data_bytes=MAX_SSE_JOINED_DATA_BYTES + 1)
    with pytest.raises(ValueError):
        SSEFramingLimits(max_data_segments=MAX_SSE_DATA_SEGMENTS + 1)


def test_maximum_escaped_semantic_budget_fits_joined_data_ceiling() -> None:
    # Five MiB is the reviewed semantic event budget (reasoning summary and
    # visible content are separate one-MiB fields); six is the worst-case
    # JSON ASCII expansion and 128 KiB is the fixed structural allowance.
    assert MAX_SSE_JOINED_DATA_BYTES == 5 * 1_048_576 * 6 + 131_072
    assert MAX_SSE_LINE_BYTES == MAX_SSE_JOINED_DATA_BYTES + 7
    assert MAX_SSE_DATA_LINE_OVERHEAD_BYTES == 8
    assert MAX_SSE_FRAME_BYTES == (
        MAX_SSE_JOINED_DATA_BYTES
        + MAX_SSE_DATA_SEGMENTS * MAX_SSE_DATA_LINE_OVERHEAD_BYTES
        + MAX_SSE_DATA_SEGMENTS
        - 1
        + 262_144
        + 2
    )


def test_maximum_reviewed_semantic_event_serializes_within_all_wire_ceilings() -> None:
    mib = 1_048_576
    control_text = "\x00" * mib
    response = {
        "id": "response_maximum",
        "status": "completed",
        "instructions": control_text,
        "output": [
            {
                "type": "reasoning",
                "id": "reasoning_maximum",
                "summary": [{"type": "summary_text", "text": control_text}],
                "content": [{"type": "reasoning_text", "text": control_text}],
                "encrypted_content": None,
                "status": None,
            },
            {
                "type": "function_call",
                "id": "function_maximum",
                "call_id": "call_maximum",
                "name": "bounded",
                "arguments": control_text,
                "status": "completed",
            },
            {
                "type": "message",
                "id": "message_maximum",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": control_text}],
                "phase": None,
            },
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    encoded_response = json.dumps(
        response, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    event_data = json.dumps(
        {"type": "response.completed", "sequence_number": 99, "response": response},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")

    assert len(encoded_response) <= MAX_SSE_JOINED_DATA_BYTES
    assert len(event_data) <= MAX_SSE_JOINED_DATA_BYTES
    assert len(b"data: " + event_data + b"\n") <= MAX_SSE_LINE_BYTES
    assert len(b"data: " + event_data + b"\n\n") <= MAX_SSE_FRAME_BYTES

    stream = ChunkStream([b"data: " + event_data + b"\n\n"])
    events = asyncio.run(_collect(BoundedSSEFramer(), _response(stream)))
    assert events[0].json_body["type"] == "response.completed"


def test_framer_handles_normal_small_chunks_and_utf8_split_at_byte_boundaries() -> None:
    payload = {"type": "response.output_text.delta", "delta": "ž"}
    raw = _event_bytes(payload)
    stream = ChunkStream([raw[index : index + 1] for index in range(len(raw))])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits(max_line_bytes=64, max_frame_bytes=128))

    events = asyncio.run(_collect(framer, response))

    assert len(events) == 1
    assert events[0].json_body == payload
    assert events[0].data == json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert framer.stats.events_emitted == 1
    assert stream.closed is True


def test_framer_handles_crlf_split_boundary_and_multiline_data() -> None:
    raw = b'data: {"value":\r\ndata: "split"}\r\n\r\n'
    stream = ChunkStream([raw[:17], raw[17:31], raw[31:]])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits(max_line_bytes=64, max_frame_bytes=128))

    events = asyncio.run(_collect(framer, response))

    assert len(events) == 1
    assert events[0].data == '{"value":\n"split"}'
    assert events[0].json_body == {"value": "split"}


def test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event() -> None:
    raw = b': comment\nevent: ignored\ndata: {"ok":true}'
    stream = ChunkStream([raw])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits(max_line_bytes=64, max_frame_bytes=128))

    events = asyncio.run(_collect(framer, response))

    assert [event.json_body for event in events] == [{"ok": True}]
    assert framer.stats.max_data_segments_retained == 1

    comments_only = ChunkStream([b": comment\nignored: value"])
    comment_response = _response(comments_only)
    assert asyncio.run(_collect(BoundedSSEFramer(limits=_small_limits()), comment_response)) == []


def test_framer_preserves_normal_events_across_ordinary_network_chunks() -> None:
    payload = {"type": "response.created", "response": {"id": "resp"}}
    raw = _event_bytes(payload)
    stream = ChunkStream([raw[:4], raw[4:19], raw[19:]])

    events = asyncio.run(_collect(BoundedSSEFramer(limits=_small_limits()), _response(stream)))

    assert [event.json_body for event in events] == [payload]


@pytest.mark.parametrize(
    ("chunks", "limits", "error_code"),
    [
        pytest.param(
            [b"x" * 9],
            _small_limits(max_line_bytes=8),
            "local_coding_sse_line_too_large",
            id="line-one-byte-over",
        ),
        pytest.param(
            [b":123456789\n:123456789\n:1"],
            _small_limits(max_frame_bytes=20),
            "local_coding_sse_frame_too_large",
            id="frame-one-byte-over",
        ),
        pytest.param(
            [b"data: 1234\ndata: 56789\n"],
            _small_limits(max_joined_data_bytes=9),
            "local_coding_sse_data_too_large",
            id="joined-data-one-byte-over",
        ),
        pytest.param(
            [b"data: 1\ndata: 2\ndata: 3\n"],
            _small_limits(max_data_segments=2),
            "local_coding_sse_data_segments_too_many",
            id="data-segments-one-byte-over",
        ),
    ],
)
def test_one_byte_over_bounds_fail_before_oversized_state_is_retained(
    chunks: list[bytes], limits: SSEFramingLimits, error_code: str
) -> None:
    stream = ChunkStream(chunks)
    response = _response(stream)
    framer = BoundedSSEFramer(limits=limits)

    with pytest.raises(ProviderResponseParseError) as exc_info:
        asyncio.run(_collect(framer, response))

    assert exc_info.value.error_code == error_code
    assert stream.closed is True
    assert framer.stats.max_line_bytes_retained <= limits.max_line_bytes
    assert framer.stats.max_frame_bytes_retained <= limits.max_frame_bytes
    assert framer.stats.max_joined_data_bytes_retained <= limits.max_joined_data_bytes
    assert framer.stats.max_data_segments_retained <= limits.max_data_segments


def test_unterminated_line_fails_at_first_over_bound_byte() -> None:
    stream = ChunkStream([b"data: 123456789"])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits(max_line_bytes=12))

    with pytest.raises(ProviderResponseParseError) as exc_info:
        asyncio.run(_collect(framer, response))

    assert exc_info.value.error_code == "local_coding_sse_line_too_large"
    assert framer.stats.max_line_bytes_retained <= 12


def test_many_small_data_segments_are_bounded_before_joining() -> None:
    raw = b"".join(b"data: 1\n" for _ in range(21))
    stream = ChunkStream([raw])
    response = _response(stream)
    framer = BoundedSSEFramer(
        limits=_small_limits(
            max_frame_bytes=256,
            max_joined_data_bytes=39,
            max_data_segments=64,
        )
    )

    with pytest.raises(ProviderResponseParseError) as exc_info:
        asyncio.run(_collect(framer, response))

    assert exc_info.value.error_code == "local_coding_sse_data_too_large"
    assert framer.stats.max_data_segments_retained <= 64
    assert framer.stats.max_joined_data_bytes_retained <= 39


@pytest.mark.parametrize(
    ("raw", "error_code"),
    [
        pytest.param(b"data: {\n\n", "local_coding_sse_invalid_json", id="invalid-json"),
        pytest.param(b"data: 7\n\n", "local_coding_sse_json_not_object", id="non-object-json"),
        pytest.param(b"data: \xff\n\n", "local_coding_sse_invalid_utf8", id="invalid-utf8"),
        pytest.param(b"data: \xc5\n", "local_coding_sse_invalid_utf8", id="dangling-utf8"),
    ],
)
def test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo(
    raw: bytes, error_code: str
) -> None:
    stream = ChunkStream([raw])
    response = _response(stream)
    with pytest.raises(ProviderResponseParseError) as exc_info:
        asyncio.run(_collect(BoundedSSEFramer(limits=_small_limits()), response))

    assert exc_info.value.error_code == error_code
    assert raw.decode("utf-8", errors="replace") not in exc_info.value.safe_message
    assert stream.closed is True


def test_done_marker_and_many_events_are_incremental_and_content_free_stats_only() -> None:
    raw = b"".join(_event_bytes({"n": index}) for index in range(200)) + b"data: [DONE]\n\n"
    stream = ChunkStream([raw])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits(max_line_bytes=64, max_frame_bytes=128))

    events = asyncio.run(_collect(framer, response))

    assert len(events) == 201
    assert events[-1].is_done is True
    assert framer.stats.events_emitted == 201
    assert framer.stats.max_data_segments_retained == 1
    assert framer.stats.max_frame_bytes_retained <= 128


def test_unsupported_content_encoding_fails_before_raw_iteration() -> None:
    stream = ChunkStream([_event_bytes({"ok": True})])
    response = _response(stream, headers={"content-encoding": "gzip"})

    with pytest.raises(ProviderResponseParseError) as exc_info:
        asyncio.run(_collect(BoundedSSEFramer(limits=_small_limits()), response))

    assert exc_info.value.error_code == "local_coding_sse_content_encoding_unsupported"
    assert stream.iterated is False
    assert stream.closed is True


def test_consumer_aclose_closes_upstream_stream_promptly() -> None:
    stream = ChunkStream([_event_bytes({"ok": True}), b"data: "])
    response = _response(stream)
    framer = BoundedSSEFramer(limits=_small_limits())
    generator = framer.iter_events(response)

    async def consume_one() -> None:
        await anext(generator)
        await generator.aclose()

    asyncio.run(consume_one())
    assert stream.closed is True


def test_cancellation_closes_upstream_stream_and_is_not_swallowed() -> None:
    stream = CancelledStream()
    response = _response(stream)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_collect(BoundedSSEFramer(), response))

    assert stream.closed is True


@pytest.mark.asyncio
async def test_local_adapter_uses_bounded_framer_and_closes_after_parse_error() -> None:
    stream = ChunkStream([b"data: {malformed}\n\n"])

    async def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return _response(stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LocalCodingAdapter(
            Settings(),
            provider_name="local-coding",
            api_key=SERVICE_SECRET,
            base_url="http://local-coding.test/v1",
            http_client=client,
            route_capabilities=STATIC_ROUTE_CAPABILITIES,
        )
        provider_request = ProviderRequest(
            provider="local-coding",
            upstream_model="qwen",
            endpoint="/v1/responses",
            body={"input": "synthetic"},
        )
        with pytest.raises(ProviderResponseParseError) as exc_info:
            [chunk async for chunk in adapter.stream_response(provider_request)]

    assert exc_info.value.error_code == "local_coding_sse_invalid_json"
    assert stream.closed is True


@pytest.mark.asyncio
async def test_local_adapter_yields_bounded_events_and_preserves_done_marker() -> None:
    stream = ChunkStream([_event_bytes({"type": "response.created"}), b"data: [DONE]\r\n\r\n"])

    async def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return _response(stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = LocalCodingAdapter(
            Settings(),
            provider_name="local-coding",
            api_key=SERVICE_SECRET,
            base_url="http://local-coding.test/v1",
            http_client=client,
            route_capabilities=STATIC_ROUTE_CAPABILITIES,
        )
        provider_request = ProviderRequest(
            provider="local-coding",
            upstream_model="qwen",
            endpoint="/v1/responses",
            body={"input": "synthetic"},
        )
        chunks = [chunk async for chunk in adapter.stream_response(provider_request)]

    assert [chunk.data for chunk in chunks] == [
        '{"type":"response.created"}',
        "[DONE]",
    ]
    assert chunks[-1].is_done is True
    assert stream.closed is True
