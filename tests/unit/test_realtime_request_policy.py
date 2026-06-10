from __future__ import annotations

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.realtime_request_policy import RealtimeRequestPolicy


def _settings(**overrides: object) -> Settings:
    values = {
        "REALTIME_ALLOWED_AUDIO_FORMAT_TYPES": "audio/pcm,audio/pcmu,audio/pcma",
        "REALTIME_ALLOWED_VOICES": "alloy,cedar,marin",
        "REALTIME_PCM_AUDIO_RATE": 24000,
        "REALTIME_CLIENT_SECRET_DEFAULT_TTL_SECONDS": 600,
        "REALTIME_CLIENT_SECRET_MIN_TTL_SECONDS": 10,
        "REALTIME_CLIENT_SECRET_MAX_TTL_SECONDS": 7200,
        "REALTIME_MAX_INSTRUCTIONS_BYTES": 256,
        "REALTIME_DEFAULT_MAX_OUTPUT_TOKENS": 512,
        "REALTIME_MAX_OUTPUT_TOKENS": 4096,
    }
    values.update(overrides)
    return Settings(**values)


def _policy(**settings_overrides: object) -> RealtimeRequestPolicy:
    return RealtimeRequestPolicy(_settings(**settings_overrides))


def _minimal_body() -> dict[str, object]:
    return {
        "session": {
            "type": "realtime",
            "model": "classroom-realtime",
            "output_modalities": ["audio"],
            "audio": {
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": "cedar",
                }
            },
        }
    }


def test_valid_minimal_realtime_request_is_accepted() -> None:
    result = _policy().apply_client_secret_create(_minimal_body())

    assert result.effective_body["expires_after"] == {"anchor": "created_at", "seconds": 600}
    assert result.effective_body["session"]["output_modalities"] == ["audio"]
    assert result.effective_output_tokens == 512
    assert result.estimated_input_tokens > 0


def test_supported_input_and_output_formats_are_accepted() -> None:
    body = _minimal_body()
    body["session"]["audio"] = {  # type: ignore[index]
        "input": {"format": {"type": "audio/pcm", "rate": 24000}},
        "output": {"format": {"type": "audio/pcma"}, "voice": "alloy"},
    }
    result = _policy().apply_client_secret_create(body)

    assert result.effective_body["session"]["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert result.effective_body["session"]["audio"]["output"]["format"] == {"type": "audio/pcma"}
    assert result.effective_body["session"]["audio"]["output"]["voice"] == "alloy"


def test_instructions_and_bounded_max_output_tokens_are_accepted() -> None:
    body = _minimal_body()
    body["session"]["instructions"] = "Speak briefly."  # type: ignore[index]
    body["session"]["max_output_tokens"] = 1024  # type: ignore[index]
    body["expires_after"] = {"anchor": "created_at", "seconds": 120}

    result = _policy().apply_client_secret_create(body)

    assert result.effective_body["session"]["instructions"] == "Speak briefly."
    assert result.effective_body["session"]["max_output_tokens"] == 1024
    assert result.effective_body["expires_after"]["seconds"] == 120


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda body: body.update({"unknown": True}), "realtime_field_not_supported"),
        (lambda body: body["session"].update({"tools": []}), "realtime_field_not_supported"),  # type: ignore[index]
        (lambda body: body["session"].update({"type": "transcription"}), "realtime_option_not_supported"),  # type: ignore[index]
        (lambda body: body["session"].update({"output_modalities": ["text"]}), "realtime_option_not_supported"),  # type: ignore[index]
        (lambda body: body["session"]["audio"]["output"].update({"voice": {"name": "custom"}}), "realtime_option_not_supported"),  # type: ignore[index]
        (lambda body: body["session"]["audio"]["output"].update({"format": {"type": "audio/mpeg"}}), "realtime_option_not_supported"),  # type: ignore[index]
        (lambda body: body["session"].update({"max_output_tokens": "inf"}), "realtime_option_not_supported"),  # type: ignore[index]
        (lambda body: body.update({"expires_after": {"anchor": "created_at", "seconds": 7201}}), "realtime_option_not_supported"),
    ],
)
def test_unsupported_realtime_shapes_fail_closed(mutator, expected_code: str) -> None:
    body = _minimal_body()
    mutator(body)

    with pytest.raises(RequestPolicyError) as exc:
        _policy().apply_client_secret_create(body)

    assert getattr(exc.value, "error_code", None) == expected_code


def test_overlong_instructions_are_rejected() -> None:
    body = _minimal_body()
    body["session"]["instructions"] = "x" * 257  # type: ignore[index]

    with pytest.raises(RequestPolicyError) as exc:
        _policy().apply_client_secret_create(body)

    assert getattr(exc.value, "error_code", None) == "realtime_input_limit_exceeded"


def test_pcm_rate_must_match_gateway_cap() -> None:
    body = _minimal_body()
    body["session"]["audio"] = {  # type: ignore[index]
        "output": {"format": {"type": "audio/pcm", "rate": 16000}, "voice": "cedar"},
    }

    with pytest.raises(RequestPolicyError) as exc:
        _policy().apply_client_secret_create(body)

    assert getattr(exc.value, "error_code", None) == "realtime_option_not_supported"
