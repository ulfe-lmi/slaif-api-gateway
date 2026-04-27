from __future__ import annotations

from slaif_gateway.providers.streaming import format_sse_data, parse_sse_lines


def test_parse_sse_lines_detects_json_and_done() -> None:
    events = parse_sse_lines(
        [
            "data: {\"id\":\"chunk-1\",\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":2,\"total_tokens\":3}}",
            "",
            "data: [DONE]",
            "",
        ]
    )

    assert len(events) == 2
    assert events[0].json_body is not None
    assert events[0].json_body["id"] == "chunk-1"
    assert events[0].is_done is False
    assert events[1].data == "[DONE]"
    assert events[1].is_done is True


def test_format_sse_data_preserves_openai_data_event_shape() -> None:
    assert format_sse_data("{\"id\":\"chunk\"}") == 'data: {"id":"chunk"}\n\n'
