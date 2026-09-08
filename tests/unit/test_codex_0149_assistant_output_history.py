from __future__ import annotations

import asyncio
import base64
import json

import pytest

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
        "image_wire_class": "other",
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


def test_exact_image_fixture_and_resume_command_shape_is_explicit(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    facts = verifier._validate_image_pair(written["full_path"], written["crop_path"])
    initial = verifier._initial_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "first.json",
        full_image=facts["full_path"],
    )
    command = verifier._resume_last_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "last.json",
        crop_image=facts["crop_path"],
    )
    verifier._validate_command_binding(initial, expected_image=facts["full_path"], resume=False)
    verifier._validate_command_binding(command, expected_image=facts["crop_path"], resume=True)

    initial_suffix = initial[initial.index("--cd") :]
    assert initial_suffix[:7] == [
        "--cd",
        str(tmp_path / "workspace"),
        "--image",
        str(facts["full_path"]),
        "--output-last-message",
        str(tmp_path / "first.json"),
        "Describe the attached synthetic full scene briefly without tools.",
    ]
    resume_index = command.index("resume")
    assert command[resume_index : resume_index + 5] == [
        "resume",
        "--last",
        "--json",
        "--strict-config",
        "--ignore-user-config",
    ]
    assert command[command.index("--image") : command.index("--image") + 2] == [
        "--image",
        str(facts["crop_path"]),
    ]
    assert "--output-last-message" in command
    assert "resume" in command and "--last" in command
    assert not any("123e4567" in item for item in command)


def test_image_fixture_negatives_are_bounded_and_fail_closed(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    with pytest.raises(verifier.VerificationError, match="image_fixture_missing"):
        written["full_path"].unlink()
        verifier._validate_image_pair(written["full_path"], written["crop_path"])

    written = verifier._write_image_fixtures(tmp_path)
    written["crop_path"].write_bytes(b"not-a-png")
    with pytest.raises(verifier.VerificationError, match="image_fixture_crop_invalid"):
        verifier._validate_image_pair(written["full_path"], written["crop_path"])

    written = verifier._write_image_fixtures(tmp_path)
    written["crop_path"].write_bytes(written["full_path"].read_bytes())
    with pytest.raises(verifier.VerificationError, match="image_fixture_pair_not_distinct"):
        verifier._validate_image_pair(written["full_path"], written["crop_path"])


def test_image_command_negatives_cover_binding_placement_and_cardinality(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    command = verifier._resume_last_command(
        tmp_path / "codex",
        workdir=tmp_path / "workspace",
        port=43123,
        model_catalog=tmp_path / "catalog.json",
        output=tmp_path / "last.json",
        crop_image=written["crop_path"],
    )
    missing = [item for item in command if item not in {"--image", str(written["crop_path"])}]
    with pytest.raises(verifier.VerificationError, match="image_command_missing"):
        verifier._validate_command_binding(
            missing, expected_image=written["crop_path"], resume=True
        )

    stale = list(command)
    stale[stale.index(str(written["crop_path"]))] = str(written["full_path"])
    with pytest.raises(verifier.VerificationError, match="image_command_binding_invalid"):
        verifier._validate_command_binding(stale, expected_image=written["crop_path"], resume=True)

    multiple = list(command)
    image_index = multiple.index("--image")
    multiple[image_index:image_index] = ["--image", str(written["full_path"])]
    with pytest.raises(verifier.VerificationError, match="image_command_multiple"):
        verifier._validate_command_binding(
            multiple, expected_image=written["crop_path"], resume=True
        )

    misplaced = list(command)
    image_index = misplaced.index("--image")
    output_index = misplaced.index("--output-last-message")
    output_flag = misplaced.pop(output_index)
    misplaced.insert(image_index, output_flag)
    with pytest.raises(verifier.VerificationError, match="image_command_suffix_invalid"):
        verifier._validate_command_binding(
            misplaced, expected_image=written["crop_path"], resume=True
        )


def test_image_wire_projection_discards_data_url_and_classifies_fixture(tmp_path) -> None:
    written = verifier._write_image_fixtures(tmp_path)
    facts = verifier._validate_image_pair(written["full_path"], written["crop_path"])
    expectations = verifier._image_expectations(facts)
    encoded = base64.b64encode(written["crop_path"].read_bytes()).decode()
    raw_url = "data:image/png;base64," + encoded
    projection = verifier._safe_history_projection(
        {
            "input": [
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "safe"}],
                },
                {"role": "user", "content": [{"type": "input_image", "image_url": raw_url}]},
            ]
        },
        image_expectations=expectations,
    )
    assert projection["image_wire_class"] == "crop"
    assert raw_url not in repr(projection)


def test_gateway_observer_marks_bounded_body_overflow(monkeypatch) -> None:
    monkeypatch.setattr(verifier, "MAX_CAPTURE_BODY_BYTES", 4)
    body = b"12345"

    async def app(scope, receive, send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    messages = iter(({"type": "http.request", "body": body, "more_body": False},))

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(_message: dict[str, object]) -> None:
        return None

    observer = verifier.GatewayObservation(app)
    asyncio.run(
        observer(
            {"type": "http", "method": "POST", "path": "/v1/responses"},
            receive,
            send,
        )
    )
    assert observer.request_overflow_classes == ["request_body_overflow"]
    assert observer.request_projections == []


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


def _catalog_document() -> dict[str, object]:
    return {
        "schema": "synthetic-catalog-v1",
        "models": [
            {"slug": "other-model", "unrelated": {"stable": True}},
            {
                "slug": verifier.CODEX_MODEL,
                "display_name": "synthetic",
                "unrelated": {"stable": True},
            },
        ],
    }


def test_vision_catalog_positive_facts_are_exact_and_preserve_unrelated_fields(tmp_path) -> None:
    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    facts = verifier._validate_vision_catalog_document(
        prepared, model=verifier.CODEX_MODEL, baseline=baseline
    )
    assert facts["modalities_exact"] is True
    assert facts["image_detail_false"] is True
    assert facts["context_exact"] is True
    assert facts["max_context_exact"] is True
    assert facts["parallel_tools_false"] is True
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    assert selected["input_modalities"] == ["text", "image"]
    assert selected["supports_image_detail_original"] is False
    assert selected["context_window"] == 100_000
    assert selected["max_context_window"] == 100_000
    assert selected["supports_parallel_tool_calls"] is False
    assert selected["unrelated"] == {"stable": True}
    assert verifier.LOCAL_005Q_SOURCE_COMMIT == "64e50172ee02563e2b021554f6b0d345cc7dfdec"
    assert verifier.LOCAL_005Q_VISION_SOURCE_PATH == "tests/helpers/vision_e2e_support.py"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("input_modalities", ["image", "text"], "vision_catalog_modalities_invalid"),
        ("input_modalities", ["text", "image", "audio"], "vision_catalog_modalities_invalid"),
        ("supports_image_detail_original", True, "vision_catalog_image_detail_invalid"),
        ("supports_image_detail_original", None, "vision_catalog_image_detail_invalid"),
        ("context_window", 99_999, "vision_catalog_context_invalid"),
        ("context_window", True, "vision_catalog_context_invalid"),
        ("max_context_window", 100_001, "vision_catalog_context_invalid"),
        ("max_context_window", None, "vision_catalog_context_invalid"),
        ("supports_parallel_tool_calls", True, "vision_catalog_parallel_tools_invalid"),
        ("supports_parallel_tool_calls", None, "vision_catalog_parallel_tools_invalid"),
    ],
)
def test_vision_catalog_rejects_malformed_or_unapproved_facts(field, value, error) -> None:
    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    selected[field] = value
    with pytest.raises(verifier.VerificationError, match=error):
        verifier._validate_vision_catalog_document(prepared, model=verifier.CODEX_MODEL)


def test_vision_catalog_rejects_missing_duplicate_and_unknown_mutation_without_raw_value() -> None:
    missing = {"models": [{"slug": "different"}]}
    with pytest.raises(verifier.VerificationError, match="vision_catalog_model_missing"):
        verifier._prepare_vision_catalog_document(missing, model=verifier.CODEX_MODEL)

    duplicate = {"models": [{"slug": verifier.CODEX_MODEL}, {"slug": verifier.CODEX_MODEL}]}
    with pytest.raises(verifier.VerificationError, match="vision_catalog_model_duplicate"):
        verifier._prepare_vision_catalog_document(duplicate, model=verifier.CODEX_MODEL)

    baseline = _catalog_document()
    prepared = verifier._prepare_vision_catalog_document(baseline, model=verifier.CODEX_MODEL)
    raw_canary = "UNRETAINED_CATALOG_CANARY_161C"
    selected = next(item for item in prepared["models"] if item["slug"] == verifier.CODEX_MODEL)
    selected["unreviewed_mutation"] = raw_canary
    with pytest.raises(verifier.VerificationError) as exc_info:
        verifier._validate_vision_catalog_document(
            prepared, model=verifier.CODEX_MODEL, baseline=baseline
        )
    assert exc_info.value.args[0] == "vision_catalog_unrelated_mutation"
    assert raw_canary not in str(exc_info.value)


def test_vision_catalog_write_is_canonical_bounded_and_mode_0600(tmp_path) -> None:
    baseline = _catalog_document()
    path = tmp_path / "catalog.json"
    facts = verifier._write_and_validate_vision_catalog(path, baseline, model=verifier.CODEX_MODEL)
    assert facts["model_present"] is True
    assert path.stat().st_mode & 0o777 == 0o600
    raw = path.read_bytes()
    assert (
        raw
        == (
            json.dumps(json.loads(raw), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        ).encode()
    )

    oversized = _catalog_document()
    oversized["models"][1]["description"] = "x" * (verifier.MAX_CAPTURE_BODY_BYTES + 1)
    with pytest.raises(verifier.VerificationError, match="vision_catalog_oversized"):
        verifier._write_and_validate_vision_catalog(
            tmp_path / "oversized.json", oversized, model=verifier.CODEX_MODEL
        )

    with pytest.raises(verifier.VerificationError, match="vision_catalog_noncanonical"):
        verifier._prepare_vision_catalog_document(
            {"models": [{"slug": verifier.CODEX_MODEL, "bad": object()}]},
            model=verifier.CODEX_MODEL,
        )
