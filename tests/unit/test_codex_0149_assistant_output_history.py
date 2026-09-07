from __future__ import annotations

import asyncio
import json

from scripts import verify_codex_0149_assistant_output_history as verifier


def _history_body(text: str = "history-only-text") -> dict[str, object]:
    return {
        "model": verifier.CODEX_MODEL,
        "stream": True,
        "input": [
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
                    {"type": "input_text", "text": "crop"},
                ],
            },
        ],
    }


def test_history_projection_is_structural_and_discards_text() -> None:
    raw_text = "UNRETAINED_ASSISTANT_TEXT_161A"
    projection = verifier._safe_history_projection(_history_body(raw_text))

    assert projection == {
        "body_object": True,
        "assistant_history_count": 1,
        "assistant_history_present": True,
        "assistant_role_exact": True,
        "assistant_output_text_count": 1,
        "assistant_output_text_type_exact": True,
        "assistant_output_text_nonempty_unicode": True,
        "assistant_output_text_size_class": "bounded",
        "image_part_count_class": "one",
        "raw_value_retained": False,
    }
    assert raw_text not in repr(projection)


def test_history_projection_rejects_empty_invalid_and_oversized_text_classes() -> None:
    empty = verifier._safe_history_projection(_history_body(""))
    oversized = verifier._safe_history_projection(
        _history_body("x" * (verifier.MAX_HISTORY_TEXT_BYTES + 1))
    )
    invalid = verifier._safe_history_projection(_history_body("\udcff"))

    assert empty["assistant_output_text_nonempty_unicode"] is False
    assert empty["assistant_output_text_size_class"] == "empty"
    assert oversized["assistant_output_text_nonempty_unicode"] is False
    assert oversized["assistant_output_text_size_class"] == "oversized"
    assert invalid["assistant_output_text_nonempty_unicode"] is False
    assert invalid["assistant_output_text_size_class"] == "invalid_unicode"


def test_error_projection_is_closed_and_does_not_retain_raw_values() -> None:
    private_code = "private-code-161a"
    private_param = "input[5].content[0].private"
    body = json.dumps(
        {"error": {"code": private_code, "param": private_param, "message": "private"}}
    ).encode()
    projection = verifier._safe_error_projection(body)

    assert projection == {"json_object": True, "error_code": "other", "param_class": "other"}
    assert private_code not in repr(projection)
    assert private_param not in repr(projection)


def test_zero_retry_and_resume_image_command_shape_is_explicit(tmp_path) -> None:
    command = verifier._resume_command(
        tmp_path / "codex",
        workdir=tmp_path,
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "last.json",
        thread_id="123e4567-e89b-12d3-a456-426614174000",
        image=tmp_path / "synthetic.png",
    )
    shape = verifier._command_shape(command)

    assert shape == {
        "zero_request_retries": True,
        "zero_stream_retries": True,
        "resume": True,
        "image": True,
    }
    assert "123e4567-e89b-12d3-a456-426614174000" in command
    assert str(tmp_path / "synthetic.png") in command


def test_gateway_observer_projects_second_body_without_raw_values() -> None:
    sent: list[dict[str, object]] = []
    body = json.dumps(_history_body("not-retained-observer-text")).encode()

    async def app(scope, receive, send) -> None:
        assert scope["path"] == "/v1/responses"
        message = await receive()
        assert message["body"] == body
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "error": {
                            "code": verifier._ALLOWED_ERROR_CODE,
                            "param": "input[5].content[0].type",
                        }
                    }
                ).encode(),
                "more_body": False,
            }
        )

    messages = iter(({"type": "http.request", "body": body, "more_body": False},))

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    observer = verifier.GatewayObservation(app)
    observer.request_count = 1
    asyncio.run(
        observer(
            {"type": "http", "method": "POST", "path": "/v1/responses"},
            receive,
            send,
        )
    )

    assert observer.request_count == 2
    assert observer.response_statuses == [400]
    assert observer.error_codes == [verifier._ALLOWED_ERROR_CODE]
    assert observer.param_classes == ["input_5_content_0_type"]
    assert observer.second_projection is not None
    assert observer.second_projection["assistant_output_text_nonempty_unicode"] is True
    assert "not-retained-observer-text" not in repr(observer.second_projection)
    assert "not-retained-observer-text" not in repr(sent)


def test_error_projection_unknown_and_malformed_inputs_are_fixed() -> None:
    assert verifier._safe_error_projection(b"not-json") == {
        "json_object": False,
        "error_code": "other",
        "param_class": "other",
    }
    assert (
        verifier._fixed_param_class("input[1].content[0].type")
        == "input_index_1_content_index_0_type"
    )
    assert verifier._fixed_param_class("input[5].content[0].type.extra") == "other"
