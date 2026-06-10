from __future__ import annotations

import pytest

from slaif_gateway.services.realtime_route_capabilities import (
    REALTIME_CAPABILITIES_KEY,
    ensure_default_realtime_capabilities,
    enforce_realtime_route_capabilities,
)


def test_realtime_route_defaults_enable_audio_client_secret_subset() -> None:
    capabilities = ensure_default_realtime_capabilities({}, endpoint="/v1/realtime/client_secrets")

    assert capabilities[REALTIME_CAPABILITIES_KEY]["audio"] is True
    assert capabilities[REALTIME_CAPABILITIES_KEY]["webrtc_client_secrets"] is True
    assert capabilities[REALTIME_CAPABILITIES_KEY]["transcription"] is False
    assert capabilities[REALTIME_CAPABILITIES_KEY]["client_secret_direct_provider_exposure_accepted"] is False


def test_realtime_route_capabilities_fail_closed_when_missing_or_invalid() -> None:
    with pytest.raises(Exception) as absent_exc:
        enforce_realtime_route_capabilities(
            route_capabilities={},
            transcription_requested=False,
            direct_provider_exposure_required=False,
        )
    assert getattr(absent_exc.value, "error_code", None) == "realtime_capability_not_supported"

    with pytest.raises(Exception) as invalid_shape_exc:
        enforce_realtime_route_capabilities(
            route_capabilities={REALTIME_CAPABILITIES_KEY: "invalid"},
            transcription_requested=False,
            direct_provider_exposure_required=False,
        )
    assert getattr(invalid_shape_exc.value, "error_code", None) == "realtime_capability_not_supported"


def test_realtime_route_capability_true_allows_audio_client_secret_subset() -> None:
    enforce_realtime_route_capabilities(
        route_capabilities={
            REALTIME_CAPABILITIES_KEY: {
                "audio": True,
                "webrtc_client_secrets": True,
                "transcription": False,
                "client_secret_direct_provider_exposure_accepted": True,
            }
        },
        transcription_requested=False,
        direct_provider_exposure_required=True,
    )


def test_realtime_direct_provider_exposure_acceptance_is_required_when_requested() -> None:
    with pytest.raises(Exception) as exc_info:
        enforce_realtime_route_capabilities(
            route_capabilities={
                REALTIME_CAPABILITIES_KEY: {
                    "audio": True,
                    "webrtc_client_secrets": True,
                    "transcription": False,
                    "client_secret_direct_provider_exposure_accepted": False,
                }
            },
            transcription_requested=False,
            direct_provider_exposure_required=True,
        )

    assert getattr(exc_info.value, "error_code", None) == "realtime_direct_provider_exposure_not_accepted"
