"""Route/model capability policy for Realtime API client-secret routes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.services.policy_errors import RequestPolicyError

REALTIME_CAPABILITIES_KEY = "realtime"
REALTIME_CAPABILITY_AUDIO = "audio"
REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS = "webrtc_client_secrets"
REALTIME_CAPABILITY_TRANSCRIPTION = "transcription"

KNOWN_REALTIME_CAPABILITIES = frozenset(
    {
        REALTIME_CAPABILITY_AUDIO,
        REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS,
        REALTIME_CAPABILITY_TRANSCRIPTION,
    }
)


def default_realtime_capabilities() -> dict[str, bool]:
    return {
        REALTIME_CAPABILITY_AUDIO: True,
        REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS: True,
        REALTIME_CAPABILITY_TRANSCRIPTION: False,
    }


def ensure_default_realtime_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    endpoint: str,
) -> dict[str, object]:
    normalized = dict(capabilities or {})
    if endpoint == "/v1/realtime/client_secrets" and REALTIME_CAPABILITIES_KEY not in normalized:
        normalized[REALTIME_CAPABILITIES_KEY] = default_realtime_capabilities()
    return normalized


@dataclass(frozen=True, slots=True)
class RealtimeRouteCapabilityFinding:
    capability: str
    field: str
    error_code: str
    safe_message: str


class RealtimeRouteCapabilityError(RequestPolicyError):
    def __init__(self, finding: RealtimeRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        self.capability = finding.capability
        super().__init__(finding.safe_message, param=finding.field)


def enforce_realtime_route_capabilities(
    *,
    route_capabilities: Mapping[str, object] | None,
    transcription_requested: bool,
) -> None:
    capabilities = _parse_realtime_route_capabilities(route_capabilities)
    if not capabilities.get(REALTIME_CAPABILITY_AUDIO, False):
        raise RealtimeRouteCapabilityError(
            RealtimeRouteCapabilityFinding(
                capability=REALTIME_CAPABILITY_AUDIO,
                field="session.model",
                error_code="realtime_capability_not_supported",
                safe_message="This model route does not support the requested Realtime endpoint.",
            )
        )
    if not capabilities.get(REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS, False):
        raise RealtimeRouteCapabilityError(
            RealtimeRouteCapabilityFinding(
                capability=REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS,
                field="session.model",
                error_code="realtime_client_secret_not_supported",
                safe_message="This model route does not support Realtime client secrets.",
            )
        )
    if transcription_requested and not capabilities.get(REALTIME_CAPABILITY_TRANSCRIPTION, False):
        raise RealtimeRouteCapabilityError(
            RealtimeRouteCapabilityFinding(
                capability=REALTIME_CAPABILITY_TRANSCRIPTION,
                field="session.type",
                error_code="realtime_transcription_not_supported",
                safe_message="This model route does not support Realtime transcription sessions.",
            )
        )


def _parse_realtime_route_capabilities(
    route_capabilities: Mapping[str, object] | None,
) -> dict[str, bool]:
    if not isinstance(route_capabilities, Mapping):
        return {}
    raw = route_capabilities.get(REALTIME_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, bool] = {}
    for name in KNOWN_REALTIME_CAPABILITIES:
        parsed[name] = raw.get(name) is True
    return parsed
