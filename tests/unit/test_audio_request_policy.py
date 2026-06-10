from __future__ import annotations

import io

import pytest
from starlette.datastructures import FormData, Headers, UploadFile

from slaif_gateway.config import Settings
from slaif_gateway.services.audio_request_policy import AudioRequestPolicy
from slaif_gateway.services.policy_errors import RequestPolicyError


def _settings(**overrides: object) -> Settings:
    values = {
        "AUDIO_UPLOAD_MAX_FILE_BYTES": 32,
        "AUDIO_SPEECH_MAX_INPUT_CHARS": 32,
        "AUDIO_SPEECH_MAX_INSTRUCTIONS_BYTES": 32,
        "AUDIO_TRANSCRIPTION_MAX_PROMPT_BYTES": 32,
        "AUDIO_TRANSLATION_MAX_PROMPT_BYTES": 32,
    }
    values.update(overrides)
    return Settings(**values)


def _upload(
    *,
    filename: str = "sample.wav",
    content_type: str = "audio/wav",
    data: bytes = b"audio-bytes",
) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_valid_minimal_speech_request_is_accepted() -> None:
    result = AudioRequestPolicy(_settings()).apply_speech(
        {"model": "tts-1", "input": "hello", "voice": "alloy"}
    )

    assert result.effective_body == {"model": "tts-1", "input": "hello", "voice": "alloy"}
    assert result.content_type == "audio/mpeg"
    assert result.estimated_input_tokens > 0


@pytest.mark.parametrize("response_format", ["mp3", "aac", "wav", "flac", "opus", "pcm"])
def test_supported_speech_response_formats_are_accepted(response_format: str) -> None:
    result = AudioRequestPolicy(_settings()).apply_speech(
        {
            "model": "tts-1",
            "input": "hello",
            "voice": "verse",
            "response_format": response_format,
        }
    )

    assert result.effective_body["response_format"] == response_format


def test_overlong_speech_input_is_rejected_without_echoing_text() -> None:
    raw_input = "secret-audio-input-marker-" + ("x" * 40)

    with pytest.raises(RequestPolicyError) as exc_info:
        AudioRequestPolicy(_settings(AUDIO_SPEECH_MAX_INPUT_CHARS=8)).apply_speech(
            {"model": "tts-1", "input": raw_input, "voice": "alloy"}
        )

    assert exc_info.value.error_code == "audio_speech_input_limit_exceeded"
    assert raw_input not in exc_info.value.safe_message


def test_unknown_speech_fields_are_rejected() -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        AudioRequestPolicy(_settings()).apply_speech(
            {
                "model": "tts-1",
                "input": "hello",
                "voice": "alloy",
                "stream_format": "sse",
            }
        )

    assert exc_info.value.error_code == "audio_field_not_supported"


def test_unsupported_speech_voice_format_and_custom_voice_object_are_rejected() -> None:
    policy = AudioRequestPolicy(_settings())

    with pytest.raises(RequestPolicyError) as voice_exc:
        policy.apply_speech({"model": "tts-1", "input": "hello", "voice": "custom"})
    assert voice_exc.value.param == "voice"

    with pytest.raises(RequestPolicyError) as format_exc:
        policy.apply_speech(
            {
                "model": "tts-1",
                "input": "hello",
                "voice": "alloy",
                "response_format": "ogg",
            }
        )
    assert format_exc.value.param == "response_format"

    with pytest.raises(RequestPolicyError) as custom_exc:
        policy.apply_speech(
            {"model": "tts-1", "input": "hello", "voice": {"id": "voice_123"}}
        )
    assert custom_exc.value.param == "voice"


@pytest.mark.parametrize("speed", ["fast", 0.2, 4.1])
def test_invalid_speech_speed_is_rejected(speed: object) -> None:
    with pytest.raises(RequestPolicyError) as exc_info:
        AudioRequestPolicy(_settings()).apply_speech(
            {"model": "tts-1", "input": "hello", "voice": "alloy", "speed": speed}
        )

    assert exc_info.value.param == "speed"


@pytest.mark.asyncio
async def test_valid_multipart_transcription_is_accepted() -> None:
    policy = AudioRequestPolicy(_settings())
    form = FormData(
        [
            ("file", _upload()),
            ("model", "whisper-1"),
            ("language", "en"),
            ("prompt", "hello"),
            ("response_format", "verbose_json"),
            ("temperature", "0.2"),
            ("timestamp_granularities", "word"),
            ("include", "logprobs"),
        ]
    )

    result, upload = await policy.apply_transcription(form)

    assert result.effective_body["model"] == "whisper-1"
    assert result.effective_body["timestamp_granularities"] == ["word"]
    assert result.effective_body["include"] == ["logprobs"]
    assert upload.filename == "sample.wav"


@pytest.mark.asyncio
async def test_transcription_accepts_safe_sdk_wav_content_type_alias() -> None:
    policy = AudioRequestPolicy(_settings())
    form = FormData(
        [
            ("file", _upload(content_type="audio/x-wav")),
            ("model", "whisper-1"),
        ]
    )

    _, upload = await policy.apply_transcription(form)

    assert upload.content_type == "audio/wav"


@pytest.mark.asyncio
async def test_transcription_rejects_large_upload_unsupported_extension_mime_and_non_file_input() -> None:
    policy = AudioRequestPolicy(_settings(AUDIO_UPLOAD_MAX_FILE_BYTES=4))

    with pytest.raises(RequestPolicyError) as size_exc:
        await policy.apply_transcription(
            FormData([("file", _upload(data=b"abcdef")), ("model", "whisper-1")])
        )
    assert size_exc.value.error_code == "audio_upload_limit_exceeded"

    with pytest.raises(RequestPolicyError) as ext_exc:
        await policy.apply_transcription(
            FormData([("file", _upload(filename="sample.txt")), ("model", "whisper-1")])
        )
    assert ext_exc.value.param == "file"

    with pytest.raises(RequestPolicyError) as mime_exc:
        await policy.apply_transcription(
            FormData(
                [("file", _upload(content_type="text/plain")), ("model", "whisper-1")]
            )
        )
    assert mime_exc.value.param == "file"

    with pytest.raises(RequestPolicyError) as url_exc:
        await policy.apply_transcription(
            FormData([("file", "https://example.test/audio.wav"), ("model", "whisper-1")])
        )
    assert url_exc.value.param == "file"


@pytest.mark.asyncio
async def test_transcription_rejects_unknown_fields_and_unsupported_options() -> None:
    policy = AudioRequestPolicy(_settings())

    with pytest.raises(RequestPolicyError) as field_exc:
        await policy.apply_transcription(
            FormData([("file", _upload()), ("model", "whisper-1"), ("chunking_strategy", "auto")])
        )
    assert field_exc.value.error_code == "audio_field_not_supported"

    with pytest.raises(RequestPolicyError) as format_exc:
        await policy.apply_transcription(
            FormData(
                [("file", _upload()), ("model", "whisper-1"), ("response_format", "diarized_json")]
            )
        )
    assert format_exc.value.param == "response_format"

    with pytest.raises(RequestPolicyError) as include_exc:
        await policy.apply_transcription(
            FormData([("file", _upload()), ("model", "whisper-1"), ("include", "speaker_labels")])
        )
    assert include_exc.value.param == "include"

    with pytest.raises(RequestPolicyError) as granularity_exc:
        await policy.apply_transcription(
            FormData(
                [
                    ("file", _upload()),
                    ("model", "whisper-1"),
                    ("response_format", "json"),
                    ("timestamp_granularities", "word"),
                ]
            )
        )
    assert granularity_exc.value.param == "timestamp_granularities"


@pytest.mark.asyncio
async def test_translation_accepts_valid_request_and_rejects_unknown_fields() -> None:
    policy = AudioRequestPolicy(_settings())

    result, _upload_payload = await policy.apply_translation(
        FormData(
            [
                ("file", _upload(filename="sample.mp3", content_type="audio/mpeg")),
                ("model", "whisper-1"),
                ("prompt", "translate"),
                ("response_format", "text"),
                ("temperature", "0.0"),
            ]
        )
    )
    assert result.effective_body["response_format"] == "text"

    with pytest.raises(RequestPolicyError) as exc_info:
        await policy.apply_translation(
            FormData(
                [
                    ("file", _upload(filename="sample.mp3", content_type="audio/mpeg")),
                    ("model", "whisper-1"),
                    ("language", "sl"),
                ]
            )
        )
    assert exc_info.value.error_code == "audio_field_not_supported"
