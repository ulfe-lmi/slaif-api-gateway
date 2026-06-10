"""Route/model capability policy for standalone Audio API endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.services.policy_errors import RequestPolicyError

AUDIO_ENDPOINT_CAPABILITIES_KEY = "audio_endpoints"

AUDIO_CAPABILITY_SPEECH = "audio_speech"
AUDIO_CAPABILITY_TRANSCRIPTIONS = "audio_transcriptions"
AUDIO_CAPABILITY_TRANSLATIONS = "audio_translations"

_ENDPOINT_TO_CAPABILITY = {
    "/v1/audio/speech": AUDIO_CAPABILITY_SPEECH,
    "/v1/audio/transcriptions": AUDIO_CAPABILITY_TRANSCRIPTIONS,
    "/v1/audio/translations": AUDIO_CAPABILITY_TRANSLATIONS,
}

KNOWN_AUDIO_ENDPOINT_CAPABILITIES = frozenset(_ENDPOINT_TO_CAPABILITY.values())


def default_audio_endpoint_capabilities(*, endpoint: str) -> dict[str, bool]:
    return {
        AUDIO_CAPABILITY_SPEECH: endpoint == "/v1/audio/speech",
        AUDIO_CAPABILITY_TRANSCRIPTIONS: endpoint == "/v1/audio/transcriptions",
        AUDIO_CAPABILITY_TRANSLATIONS: endpoint == "/v1/audio/translations",
    }


def ensure_default_audio_endpoint_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    endpoint: str,
) -> dict[str, object]:
    normalized = dict(capabilities or {})
    if endpoint in _ENDPOINT_TO_CAPABILITY and AUDIO_ENDPOINT_CAPABILITIES_KEY not in normalized:
        normalized[AUDIO_ENDPOINT_CAPABILITIES_KEY] = default_audio_endpoint_capabilities(
            endpoint=endpoint
        )
    return normalized


@dataclass(frozen=True, slots=True)
class AudioRouteCapabilityFinding:
    capability: str
    field: str
    error_code: str
    safe_message: str


class AudioRouteCapabilityError(RequestPolicyError):
    def __init__(self, finding: AudioRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        self.capability = finding.capability
        super().__init__(finding.safe_message, param=finding.field)


def enforce_audio_route_capabilities(
    *,
    endpoint: str,
    route_capabilities: Mapping[str, object] | None,
) -> None:
    required = _ENDPOINT_TO_CAPABILITY.get(endpoint)
    if required is None:
        raise AudioRouteCapabilityError(
            AudioRouteCapabilityFinding(
                capability="audio_endpoint_unknown",
                field="model",
                error_code="audio_capability_not_supported",
                safe_message="This model route does not support the requested standalone Audio API endpoint.",
            )
        )
    capabilities = _parse_audio_route_capabilities(route_capabilities)
    if not capabilities.get(required, False):
        raise AudioRouteCapabilityError(
            AudioRouteCapabilityFinding(
                capability=required,
                field="model",
                error_code="audio_capability_not_supported",
                safe_message="This model route does not support the requested standalone Audio API endpoint.",
            )
        )


def _parse_audio_route_capabilities(
    route_capabilities: Mapping[str, object] | None,
) -> dict[str, bool]:
    if not isinstance(route_capabilities, Mapping):
        return {}
    raw = route_capabilities.get(AUDIO_ENDPOINT_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, bool] = {}
    for name in KNOWN_AUDIO_ENDPOINT_CAPABILITIES:
        value = raw.get(name)
        parsed[name] = value is True
    return parsed
