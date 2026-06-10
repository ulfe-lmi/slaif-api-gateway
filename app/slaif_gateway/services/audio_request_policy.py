"""Request policy for standalone Audio API endpoints."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from typing import Any

from starlette.datastructures import FormData, UploadFile

from slaif_gateway.config import Settings
from slaif_gateway.schemas.audio import AudioPolicyResult, AudioUploadPayload
from slaif_gateway.services.input_token_estimation import estimate_serialized_json_input_tokens
from slaif_gateway.services.policy_errors import (
    AudioInvalidMultipartError,
    AudioSpeechInputLimitExceededError,
    AudioUnsupportedFieldError,
    AudioUnsupportedOptionError,
    AudioUploadLimitExceededError,
)

_SPEECH_FIELDS = frozenset({"model", "input", "voice", "response_format", "speed", "instructions"})
_TRANSCRIPTION_FIELDS = frozenset(
    {
        "file",
        "model",
        "language",
        "prompt",
        "response_format",
        "temperature",
        "timestamp_granularities",
        "timestamp_granularities[]",
        "include",
        "include[]",
    }
)
_TRANSLATION_FIELDS = frozenset({"file", "model", "prompt", "response_format", "temperature"})


class AudioRequestPolicy:
    """Apply standalone Audio API request validation and normalization."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply_speech(self, body: Mapping[str, Any]) -> AudioPolicyResult:
        effective_body = dict(body)
        _reject_unknown_fields(effective_body, allowed_fields=_SPEECH_FIELDS)

        model = _required_str(effective_body.get("model"), field_name="model")

        input_text = _required_str(effective_body.get("input"), field_name="input")
        if len(input_text) > self._settings.AUDIO_SPEECH_MAX_INPUT_CHARS:
            raise AudioSpeechInputLimitExceededError(
                "Speech input exceeds the configured standalone Audio API maximum length.",
                param="input",
            )

        voice = effective_body.get("voice")
        if not isinstance(voice, str):
            raise AudioUnsupportedOptionError(
                "Standalone Audio API speech requires a supported built-in voice string.",
                param="voice",
            )
        voice = voice.strip().lower()
        if voice not in _csv_set(self._settings.AUDIO_SPEECH_ALLOWED_VOICES):
            raise AudioUnsupportedOptionError(
                "The requested standalone Audio API voice is not supported.",
                param="voice",
            )

        response_format = effective_body.get("response_format")
        if response_format is not None:
            response_format = _required_str(response_format, field_name="response_format").lower()
            if response_format not in _csv_set(self._settings.AUDIO_SPEECH_ALLOWED_RESPONSE_FORMATS):
                raise AudioUnsupportedOptionError(
                    "The requested standalone Audio API speech response format is not supported.",
                    param="response_format",
                )
            effective_body["response_format"] = response_format

        speed = effective_body.get("speed")
        if speed is not None:
            if isinstance(speed, bool) or not isinstance(speed, int | float):
                raise AudioUnsupportedOptionError(
                    "Speech speed must be a number between 0.25 and 4.0.",
                    param="speed",
                )
            if math.isnan(float(speed)) or float(speed) < 0.25 or float(speed) > 4.0:
                raise AudioUnsupportedOptionError(
                    "Speech speed must be a number between 0.25 and 4.0.",
                    param="speed",
                )
            effective_body["speed"] = float(speed)

        instructions = effective_body.get("instructions")
        if instructions is not None:
            instructions = _required_str(instructions, field_name="instructions")
            if len(instructions.encode("utf-8")) > self._settings.AUDIO_SPEECH_MAX_INSTRUCTIONS_BYTES:
                raise AudioSpeechInputLimitExceededError(
                    "Speech instructions exceed the configured standalone Audio API maximum length.",
                    param="instructions",
                )
            effective_body["instructions"] = instructions

        effective_body["model"] = model
        effective_body["input"] = input_text
        effective_body["voice"] = voice

        estimate_payload = {"input": input_text}
        if instructions is not None:
            estimate_payload["instructions"] = instructions

        return AudioPolicyResult(
            effective_body=effective_body,
            estimated_input_tokens=estimate_serialized_json_input_tokens(estimate_payload),
            content_type=_speech_content_type(response_format),
        )

    async def apply_transcription(
        self,
        form: FormData,
    ) -> tuple[AudioPolicyResult, AudioUploadPayload]:
        return await self._apply_multipart_audio(
            form,
            allowed_fields=_TRANSCRIPTION_FIELDS,
            allowed_response_formats=_csv_set(
                self._settings.AUDIO_TRANSCRIPTION_ALLOWED_RESPONSE_FORMATS
            ),
            endpoint_name="transcription",
            allow_language=True,
            allow_prompt=True,
            allow_include=True,
            allow_timestamp_granularities=True,
            max_prompt_bytes=self._settings.AUDIO_TRANSCRIPTION_MAX_PROMPT_BYTES,
        )

    async def apply_translation(
        self,
        form: FormData,
    ) -> tuple[AudioPolicyResult, AudioUploadPayload]:
        return await self._apply_multipart_audio(
            form,
            allowed_fields=_TRANSLATION_FIELDS,
            allowed_response_formats=_csv_set(self._settings.AUDIO_TRANSLATION_ALLOWED_RESPONSE_FORMATS),
            endpoint_name="translation",
            allow_language=False,
            allow_prompt=True,
            allow_include=False,
            allow_timestamp_granularities=False,
            max_prompt_bytes=self._settings.AUDIO_TRANSLATION_MAX_PROMPT_BYTES,
        )

    async def _apply_multipart_audio(
        self,
        form: FormData,
        *,
        allowed_fields: frozenset[str],
        allowed_response_formats: set[str],
        endpoint_name: str,
        allow_language: bool,
        allow_prompt: bool,
        allow_include: bool,
        allow_timestamp_granularities: bool,
        max_prompt_bytes: int,
    ) -> tuple[AudioPolicyResult, AudioUploadPayload]:
        _reject_unknown_fields(set(form.keys()), allowed_fields=allowed_fields)
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise AudioInvalidMultipartError(
                f"Standalone Audio API {endpoint_name} requests require a multipart file upload.",
                param="file",
            )

        validated_upload = await _validated_upload(upload, settings=self._settings)
        model = _required_str(form.get("model"), field_name="model")

        effective_body: dict[str, Any] = {"model": model}
        prompt = None

        if allow_language and form.get("language") is not None:
            language = _required_str(form.get("language"), field_name="language")
            if len(language.encode("utf-8")) > 16:
                raise AudioUnsupportedOptionError(
                    "Standalone Audio API language must be a short ISO-style code.",
                    param="language",
                )
            effective_body["language"] = language

        if allow_prompt and form.get("prompt") is not None:
            prompt = _required_str(form.get("prompt"), field_name="prompt")
            if len(prompt.encode("utf-8")) > max_prompt_bytes:
                raise AudioSpeechInputLimitExceededError(
                    f"Standalone Audio API {endpoint_name} prompt exceeds the configured maximum length.",
                    param="prompt",
                )
            effective_body["prompt"] = prompt

        response_format = form.get("response_format")
        if response_format is not None:
            parsed_response_format = _required_str(
                response_format,
                field_name="response_format",
            ).lower()
            if parsed_response_format not in allowed_response_formats:
                raise AudioUnsupportedOptionError(
                    f"The requested standalone Audio API {endpoint_name} response format is not supported.",
                    param="response_format",
                )
            effective_body["response_format"] = parsed_response_format

        temperature = form.get("temperature")
        if temperature is not None:
            parsed_temperature = _parse_float(temperature, field_name="temperature")
            if parsed_temperature < 0 or parsed_temperature > 1:
                raise AudioUnsupportedOptionError(
                    "Standalone Audio API temperature must be between 0 and 1.",
                    param="temperature",
                )
            effective_body["temperature"] = parsed_temperature

        if allow_include:
            include_values = _form_list(form, "include")
            if include_values:
                allowed = _csv_set(self._settings.AUDIO_TRANSCRIPTION_ALLOWED_INCLUDE_VALUES)
                unsupported = [value for value in include_values if value not in allowed]
                if unsupported:
                    raise AudioUnsupportedOptionError(
                        "Standalone Audio API transcription include values are not supported.",
                        param="include",
                    )
                effective_body["include"] = include_values

        if allow_timestamp_granularities:
            granularities = _form_list(form, "timestamp_granularities")
            if granularities:
                allowed = _csv_set(self._settings.AUDIO_ALLOWED_TIMESTAMP_GRANULARITIES)
                unsupported = [value for value in granularities if value not in allowed]
                if unsupported:
                    raise AudioUnsupportedOptionError(
                        "Standalone Audio API transcription timestamp granularities are not supported.",
                        param="timestamp_granularities",
                    )
                if effective_body.get("response_format") != "verbose_json":
                    raise AudioUnsupportedOptionError(
                        "Standalone Audio API transcription timestamp granularities require response_format=verbose_json.",
                        param="timestamp_granularities",
                    )
                effective_body["timestamp_granularities"] = granularities

        estimate_payload: dict[str, Any] = {
            "filename": validated_upload.filename,
            "content_type": validated_upload.content_type,
            "size_bytes": len(validated_upload.data),
        }
        if prompt is not None:
            estimate_payload["prompt"] = prompt

        return (
            AudioPolicyResult(
                effective_body=effective_body,
                estimated_input_tokens=estimate_serialized_json_input_tokens(estimate_payload),
                uploaded_file_bytes=len(validated_upload.data),
                content_type=_multipart_response_content_type(
                    endpoint_name=endpoint_name,
                    response_format=effective_body.get("response_format"),
                ),
            ),
            validated_upload,
        )


def _reject_unknown_fields(
    body: Mapping[str, Any] | Iterable[str],
    *,
    allowed_fields: frozenset[str],
) -> None:
    keys = set(body if not isinstance(body, Mapping) else body.keys())
    unknown_fields = sorted(keys - set(allowed_fields))
    if unknown_fields:
        raise AudioUnsupportedFieldError(
            "Standalone Audio API request contains unsupported fields.",
            param=str(unknown_fields[0]),
        )


def _required_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AudioInvalidMultipartError(
            f"Standalone Audio API field '{field_name}' must be a string.",
            param=field_name,
        )
    normalized = value.strip()
    if not normalized:
        raise AudioInvalidMultipartError(
            f"Standalone Audio API field '{field_name}' must not be empty.",
            param=field_name,
        )
    return normalized


def _csv_set(raw_value: str) -> set[str]:
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}


def _normalized_upload_content_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    normalized = content_type.strip().lower()
    return {
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "audio/x-pn-wav": "audio/wav",
        "audio/x-m4a": "audio/m4a",
    }.get(normalized, normalized)


def _parse_float(value: object, *, field_name: str) -> float:
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise AudioUnsupportedOptionError(
                f"Standalone Audio API field '{field_name}' must be numeric.",
                param=field_name,
            ) from exc
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AudioUnsupportedOptionError(
            f"Standalone Audio API field '{field_name}' must be numeric.",
            param=field_name,
        )
    return float(value)


def _speech_content_type(response_format: str | None) -> str:
    return {
        "aac": "audio/aac",
        "flac": "audio/flac",
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "pcm": "audio/L16",
        "wav": "audio/wav",
        None: "audio/mpeg",
    }[response_format]


def _multipart_response_content_type(
    *,
    endpoint_name: str,
    response_format: object,
) -> str:
    if response_format == "text":
        return "text/plain; charset=utf-8"
    if response_format == "srt":
        return "application/x-subrip"
    if response_format == "vtt":
        return "text/vtt; charset=utf-8"
    if response_format == "verbose_json":
        return "application/json"
    if response_format == "json" or response_format is None:
        return "application/json"
    raise AudioUnsupportedOptionError(
        f"The requested standalone Audio API {endpoint_name} response format is not supported.",
        param="response_format",
    )


async def _validated_upload(
    upload: UploadFile,
    *,
    settings: Settings,
) -> AudioUploadPayload:
    filename = upload.filename or "audio"
    if any(ch in filename for ch in ("/", "\\", "\x00")):
        raise AudioUnsupportedOptionError(
            "Standalone Audio API upload filename is not supported.",
            param="file",
        )
    if len(filename.encode("utf-8")) > settings.AUDIO_UPLOAD_MAX_FILENAME_BYTES:
        raise AudioUploadLimitExceededError(
            "Standalone Audio API upload filename exceeds the configured maximum length.",
            param="file",
        )

    extension = os.path.splitext(filename)[1].lower()
    if extension not in _csv_set(settings.AUDIO_UPLOAD_ALLOWED_EXTENSIONS):
        raise AudioUnsupportedOptionError(
            "Standalone Audio API upload file extension is not supported.",
            param="file",
        )

    content_type = _normalized_upload_content_type(upload.content_type)
    if content_type and content_type not in _csv_set(settings.AUDIO_UPLOAD_ALLOWED_MIME_TYPES):
        raise AudioUnsupportedOptionError(
            "Standalone Audio API upload content type is not supported.",
            param="file",
        )

    data = await upload.read(settings.AUDIO_UPLOAD_MAX_FILE_BYTES + 1)
    if len(data) > settings.AUDIO_UPLOAD_MAX_FILE_BYTES:
        raise AudioUploadLimitExceededError(
            "Standalone Audio API upload exceeds the configured maximum file size.",
            param="file",
        )

    return AudioUploadPayload(
        filename=filename,
        content_type=content_type,
        data=data,
    )


def _form_list(form: FormData, key: str) -> list[str]:
    values = form.getlist(key)
    if not values:
        values = form.getlist(f"{key}[]")
    parsed: list[str] = []
    for value in values:
        parsed.append(_required_str(value, field_name=key).lower())
    return parsed
