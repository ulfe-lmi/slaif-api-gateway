"""Request policy for the narrow Realtime client-secret RC2 subset."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.schemas.realtime import RealtimePolicyResult
from slaif_gateway.services.input_token_estimation import estimate_serialized_json_input_tokens
from slaif_gateway.services.policy_errors import (
    RealtimeInputLimitExceededError,
    RealtimeUnsupportedFieldError,
    RealtimeUnsupportedOptionError,
)

_TOP_LEVEL_FIELDS = frozenset({"expires_after", "session"})
_EXPIRES_AFTER_FIELDS = frozenset({"anchor", "seconds"})
_SESSION_FIELDS = frozenset(
    {
        "type",
        "model",
        "output_modalities",
        "audio",
        "instructions",
        "max_output_tokens",
    }
)
_AUDIO_FIELDS = frozenset({"input", "output"})
_AUDIO_INPUT_FIELDS = frozenset({"format"})
_AUDIO_OUTPUT_FIELDS = frozenset({"format", "voice"})
_FORMAT_FIELDS = frozenset({"type", "rate"})
_SUPPORTED_MODALITIES = frozenset({"audio"})


class RealtimeRequestPolicy:
    """Apply bounded Realtime client-secret request validation and normalization."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply_client_secret_create(self, body: Mapping[str, Any]) -> RealtimePolicyResult:
        effective_body = dict(body)
        _reject_unknown_fields(effective_body, allowed_fields=_TOP_LEVEL_FIELDS)

        session_value = effective_body.get("session")
        if not isinstance(session_value, Mapping):
            raise RealtimeUnsupportedOptionError(
                "Realtime client-secret requests require a session object.",
                param="session",
            )

        session = self._normalize_session(dict(session_value))
        expires_after = self._normalize_expires_after(effective_body.get("expires_after"))

        effective_body["session"] = session
        effective_body["expires_after"] = expires_after

        estimate_payload = {
            "session": {
                "type": session["type"],
                "model": session["model"],
                "output_modalities": session["output_modalities"],
                "audio": session["audio"],
                "max_output_tokens": session["max_output_tokens"],
            },
            "expires_after": expires_after,
        }
        if "instructions" in session:
            estimate_payload["session"]["instructions"] = session["instructions"]

        return RealtimePolicyResult(
            effective_body=effective_body,
            estimated_input_tokens=estimate_serialized_json_input_tokens(estimate_payload),
            effective_output_tokens=int(session["max_output_tokens"]),
        )

    def _normalize_session(self, session: dict[str, Any]) -> dict[str, Any]:
        _reject_unknown_fields(session, allowed_fields=_SESSION_FIELDS, param_prefix="session")

        session_type = _required_str(session.get("type"), field_name="session.type").lower()
        if session_type != "realtime":
            raise RealtimeUnsupportedOptionError(
                "This Realtime foundation supports only session.type='realtime'.",
                param="session.type",
            )

        model = _required_str(session.get("model"), field_name="session.model")

        output_modalities = session.get("output_modalities", ["audio"])
        normalized_modalities = _normalize_output_modalities(output_modalities)

        audio_value = session.get("audio")
        if not isinstance(audio_value, Mapping):
            raise RealtimeUnsupportedOptionError(
                "Realtime sessions require an audio configuration object.",
                param="session.audio",
            )
        audio = self._normalize_audio(dict(audio_value))

        instructions = session.get("instructions")
        normalized_instructions: str | None = None
        if instructions is not None:
            normalized_instructions = _required_str(instructions, field_name="session.instructions")
            if len(normalized_instructions.encode("utf-8")) > self._settings.REALTIME_MAX_INSTRUCTIONS_BYTES:
                raise RealtimeInputLimitExceededError(
                    "Realtime instructions exceed the configured gateway limit.",
                    param="session.instructions",
                )

        max_output_tokens = session.get(
            "max_output_tokens",
            self._settings.REALTIME_DEFAULT_MAX_OUTPUT_TOKENS,
        )
        normalized_max_output_tokens = _normalize_max_output_tokens(
            max_output_tokens,
            settings=self._settings,
        )

        normalized: dict[str, Any] = {
            "type": session_type,
            "model": model,
            "output_modalities": normalized_modalities,
            "audio": audio,
            "max_output_tokens": normalized_max_output_tokens,
        }
        if normalized_instructions is not None:
            normalized["instructions"] = normalized_instructions
        return normalized

    def _normalize_audio(self, audio: dict[str, Any]) -> dict[str, Any]:
        _reject_unknown_fields(audio, allowed_fields=_AUDIO_FIELDS, param_prefix="session.audio")

        output_value = audio.get("output")
        if not isinstance(output_value, Mapping):
            raise RealtimeUnsupportedOptionError(
                "Realtime audio output configuration is required.",
                param="session.audio.output",
            )

        output = self._normalize_audio_output(dict(output_value))
        normalized: dict[str, Any] = {"output": output}

        input_value = audio.get("input")
        if input_value is not None:
            if not isinstance(input_value, Mapping):
                raise RealtimeUnsupportedOptionError(
                    "Realtime audio input configuration must be an object.",
                    param="session.audio.input",
                )
            normalized["input"] = self._normalize_audio_input(dict(input_value))
        return normalized

    def _normalize_audio_input(self, audio_input: dict[str, Any]) -> dict[str, Any]:
        _reject_unknown_fields(
            audio_input,
            allowed_fields=_AUDIO_INPUT_FIELDS,
            param_prefix="session.audio.input",
        )
        input_format = audio_input.get("format")
        if input_format is None:
            raise RealtimeUnsupportedOptionError(
                "Realtime audio input format is required when input audio is configured.",
                param="session.audio.input.format",
            )
        return {
            "format": _normalize_audio_format(
                input_format,
                field_name="session.audio.input.format",
                settings=self._settings,
            )
        }

    def _normalize_audio_output(self, audio_output: dict[str, Any]) -> dict[str, Any]:
        _reject_unknown_fields(
            audio_output,
            allowed_fields=_AUDIO_OUTPUT_FIELDS,
            param_prefix="session.audio.output",
        )
        output_format = audio_output.get("format")
        if output_format is None:
            raise RealtimeUnsupportedOptionError(
                "Realtime audio output format is required.",
                param="session.audio.output.format",
            )
        voice = audio_output.get("voice")
        if not isinstance(voice, str):
            raise RealtimeUnsupportedOptionError(
                "Realtime audio output requires a supported built-in voice string.",
                param="session.audio.output.voice",
            )
        normalized_voice = voice.strip().lower()
        if normalized_voice not in _csv_set(self._settings.REALTIME_ALLOWED_VOICES):
            raise RealtimeUnsupportedOptionError(
                "The requested Realtime voice is not supported.",
                param="session.audio.output.voice",
            )
        return {
            "format": _normalize_audio_format(
                output_format,
                field_name="session.audio.output.format",
                settings=self._settings,
            ),
            "voice": normalized_voice,
        }

    def _normalize_expires_after(self, value: object) -> dict[str, Any]:
        if value is None:
            return {
                "anchor": "created_at",
                "seconds": self._settings.REALTIME_CLIENT_SECRET_DEFAULT_TTL_SECONDS,
            }
        if not isinstance(value, Mapping):
            raise RealtimeUnsupportedOptionError(
                "Realtime expires_after must be an object.",
                param="expires_after",
            )
        payload = dict(value)
        _reject_unknown_fields(payload, allowed_fields=_EXPIRES_AFTER_FIELDS, param_prefix="expires_after")
        anchor = _required_str(payload.get("anchor"), field_name="expires_after.anchor").lower()
        if anchor != "created_at":
            raise RealtimeUnsupportedOptionError(
                "Realtime expires_after.anchor must be 'created_at'.",
                param="expires_after.anchor",
            )
        seconds = payload.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise RealtimeUnsupportedOptionError(
                "Realtime expires_after.seconds must be an integer.",
                param="expires_after.seconds",
            )
        if seconds < self._settings.REALTIME_CLIENT_SECRET_MIN_TTL_SECONDS:
            raise RealtimeUnsupportedOptionError(
                "Realtime expires_after.seconds is below the configured minimum.",
                param="expires_after.seconds",
            )
        if seconds > self._settings.REALTIME_CLIENT_SECRET_MAX_TTL_SECONDS:
            raise RealtimeUnsupportedOptionError(
                "Realtime expires_after.seconds exceeds the configured maximum.",
                param="expires_after.seconds",
            )
        return {"anchor": anchor, "seconds": seconds}


def _reject_unknown_fields(
    body: Mapping[str, Any],
    *,
    allowed_fields: frozenset[str],
    param_prefix: str | None = None,
) -> None:
    unknown_fields = sorted(set(body) - set(allowed_fields))
    if not unknown_fields:
        return
    param = unknown_fields[0]
    if param_prefix:
        param = f"{param_prefix}.{param}"
    raise RealtimeUnsupportedFieldError(
        "Realtime requests may include only the supported GA client-secret fields.",
        param=param,
    )


def _required_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise RealtimeUnsupportedOptionError(
            f"Realtime field '{field_name}' must be a string.",
            param=field_name,
        )
    normalized = value.strip()
    if not normalized:
        raise RealtimeUnsupportedOptionError(
            f"Realtime field '{field_name}' must not be empty.",
            param=field_name,
        )
    return normalized


def _normalize_output_modalities(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise RealtimeUnsupportedOptionError(
            "Realtime output_modalities must be an array of supported modality strings.",
            param="session.output_modalities",
        )
    modalities = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise RealtimeUnsupportedOptionError(
                "Realtime output_modalities entries must be strings.",
                param=f"session.output_modalities[{index}]",
            )
        normalized = item.strip().lower()
        if normalized not in _SUPPORTED_MODALITIES:
            raise RealtimeUnsupportedOptionError(
                "This Realtime foundation supports only audio output modality.",
                param=f"session.output_modalities[{index}]",
            )
        modalities.append(normalized)
    if modalities != ["audio"]:
        raise RealtimeUnsupportedOptionError(
            "This Realtime foundation supports only output_modalities=['audio'].",
            param="session.output_modalities",
        )
    return modalities


def _normalize_audio_format(
    value: object,
    *,
    field_name: str,
    settings: Settings,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RealtimeUnsupportedOptionError(
            "Realtime audio format must be an object.",
            param=field_name,
        )
    payload = dict(value)
    _reject_unknown_fields(payload, allowed_fields=_FORMAT_FIELDS, param_prefix=field_name)
    format_type = _required_str(payload.get("type"), field_name=f"{field_name}.type").lower()
    allowed_types = _csv_set(settings.REALTIME_ALLOWED_AUDIO_FORMAT_TYPES)
    if format_type not in allowed_types:
        raise RealtimeUnsupportedOptionError(
            "The requested Realtime audio format is not supported.",
            param=f"{field_name}.type",
        )
    if format_type == "audio/pcm":
        rate = payload.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, int):
            raise RealtimeUnsupportedOptionError(
                "Realtime PCM audio format requires an integer rate.",
                param=f"{field_name}.rate",
            )
        if rate != settings.REALTIME_PCM_AUDIO_RATE:
            raise RealtimeUnsupportedOptionError(
                "The requested Realtime PCM audio rate is not supported.",
                param=f"{field_name}.rate",
            )
        return {"type": format_type, "rate": rate}
    if "rate" in payload:
        raise RealtimeUnsupportedOptionError(
            "Realtime non-PCM audio formats must not include rate.",
            param=f"{field_name}.rate",
        )
    return {"type": format_type}


def _normalize_max_output_tokens(value: object, *, settings: Settings) -> int:
    if isinstance(value, str):
        if value.strip().lower() == "inf":
            raise RealtimeUnsupportedOptionError(
                "Realtime max_output_tokens must be bounded for RC2.",
                param="session.max_output_tokens",
            )
        raise RealtimeUnsupportedOptionError(
            "Realtime max_output_tokens must be an integer.",
            param="session.max_output_tokens",
        )
    if isinstance(value, bool) or not isinstance(value, int):
        raise RealtimeUnsupportedOptionError(
            "Realtime max_output_tokens must be an integer.",
            param="session.max_output_tokens",
        )
    if value <= 0:
        raise RealtimeUnsupportedOptionError(
            "Realtime max_output_tokens must be positive.",
            param="session.max_output_tokens",
        )
    if value > settings.REALTIME_MAX_OUTPUT_TOKENS:
        raise RealtimeInputLimitExceededError(
            "Realtime max_output_tokens exceeds the configured gateway limit.",
            param="session.max_output_tokens",
        )
    return value


def _csv_set(raw_value: str) -> set[str]:
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}
