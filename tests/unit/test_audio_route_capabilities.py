from __future__ import annotations

import pytest

from slaif_gateway.services.audio_route_capabilities import (
    AUDIO_ENDPOINT_CAPABILITIES_KEY,
    ensure_default_audio_endpoint_capabilities,
    enforce_audio_route_capabilities,
)


def test_audio_route_defaults_enable_only_matching_endpoint() -> None:
    speech = ensure_default_audio_endpoint_capabilities({}, endpoint="/v1/audio/speech")
    transcription = ensure_default_audio_endpoint_capabilities(
        {},
        endpoint="/v1/audio/transcriptions",
    )

    assert speech[AUDIO_ENDPOINT_CAPABILITIES_KEY]["audio_speech"] is True
    assert speech[AUDIO_ENDPOINT_CAPABILITIES_KEY]["audio_transcriptions"] is False
    assert transcription[AUDIO_ENDPOINT_CAPABILITIES_KEY]["audio_transcriptions"] is True
    assert transcription[AUDIO_ENDPOINT_CAPABILITIES_KEY]["audio_speech"] is False


def test_audio_route_capability_absent_or_false_fails_closed() -> None:
    with pytest.raises(Exception) as absent_exc:
        enforce_audio_route_capabilities(endpoint="/v1/audio/speech", route_capabilities={})
    assert getattr(absent_exc.value, "error_code", None) == "audio_capability_not_supported"

    with pytest.raises(Exception) as false_exc:
        enforce_audio_route_capabilities(
            endpoint="/v1/audio/transcriptions",
            route_capabilities={
                AUDIO_ENDPOINT_CAPABILITIES_KEY: {
                    "audio_transcriptions": False,
                }
            },
        )
    assert getattr(false_exc.value, "error_code", None) == "audio_capability_not_supported"


def test_audio_route_capability_true_allows_endpoint() -> None:
    enforce_audio_route_capabilities(
        endpoint="/v1/audio/translations",
        route_capabilities={
            AUDIO_ENDPOINT_CAPABILITIES_KEY: {
                "audio_translations": True,
            }
        },
    )
