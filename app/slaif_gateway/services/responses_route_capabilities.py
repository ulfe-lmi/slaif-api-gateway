"""Route/model capability policy for stateless text-only Responses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.services.policy_errors import RequestPolicyError

RESPONSES_CAPABILITIES_KEY = "responses"
RESPONSES_CAPABILITY_TEXT = "text"
RESPONSES_CAPABILITY_STATELESS = "stateless"
RESPONSES_CAPABILITY_STREAMING = "streaming"
RESPONSES_CAPABILITY_TOOLS = "tools"
RESPONSES_CAPABILITY_MULTIMODAL = "multimodal"
RESPONSES_CAPABILITY_STORAGE = "storage"
RESPONSES_CAPABILITY_BACKGROUND = "background"

KNOWN_RESPONSES_CAPABILITIES = frozenset(
    {
        RESPONSES_CAPABILITY_TEXT,
        RESPONSES_CAPABILITY_STATELESS,
        RESPONSES_CAPABILITY_STREAMING,
        RESPONSES_CAPABILITY_TOOLS,
        RESPONSES_CAPABILITY_MULTIMODAL,
        RESPONSES_CAPABILITY_STORAGE,
        RESPONSES_CAPABILITY_BACKGROUND,
    }
)


def default_responses_capabilities() -> dict[str, bool]:
    """Return conservative metadata for this first Responses slice."""

    return {
        RESPONSES_CAPABILITY_TEXT: True,
        RESPONSES_CAPABILITY_STATELESS: True,
        RESPONSES_CAPABILITY_STREAMING: False,
        RESPONSES_CAPABILITY_TOOLS: False,
        RESPONSES_CAPABILITY_MULTIMODAL: False,
        RESPONSES_CAPABILITY_STORAGE: False,
        RESPONSES_CAPABILITY_BACKGROUND: False,
    }


def ensure_default_responses_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    endpoint: str,
) -> dict[str, object]:
    """Add explicit Responses metadata only when creating Responses routes."""

    normalized = dict(capabilities or {})
    if endpoint == "/v1/responses" and RESPONSES_CAPABILITIES_KEY not in normalized:
        normalized[RESPONSES_CAPABILITIES_KEY] = default_responses_capabilities()
    return normalized


@dataclass(frozen=True, slots=True)
class ResponsesRouteCapabilityFinding:
    capability: str
    field: str
    error_code: str
    safe_message: str


class ResponsesRouteCapabilityError(RequestPolicyError):
    """Request-policy error for Responses route capability mismatches."""

    def __init__(self, finding: ResponsesRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        super().__init__(finding.safe_message, param=finding.field)


def enforce_responses_route_capabilities(
    *,
    route_capabilities: Mapping[str, object] | None,
) -> None:
    """Require explicit text+stateless Responses metadata and fail closed."""

    capabilities = _parse_route_capabilities(route_capabilities)
    required = (
        ResponsesRouteCapabilityFinding(
            capability=RESPONSES_CAPABILITY_TEXT,
            field="model",
            error_code="responses_route_capability_not_supported",
            safe_message="This model route does not support text Responses.",
        ),
        ResponsesRouteCapabilityFinding(
            capability=RESPONSES_CAPABILITY_STATELESS,
            field="model",
            error_code="responses_route_capability_not_supported",
            safe_message="This model route does not support stateless Responses.",
        ),
    )
    for finding in required:
        if capabilities.get(finding.capability) is not True:
            raise ResponsesRouteCapabilityError(finding)


def _parse_route_capabilities(route_capabilities: Mapping[str, object] | None) -> dict[str, bool]:
    if not route_capabilities or RESPONSES_CAPABILITIES_KEY not in route_capabilities:
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITIES_KEY,
                field="model",
                error_code="responses_route_capability_missing",
                safe_message="Responses route capability metadata is missing.",
            )
        )

    raw = route_capabilities.get(RESPONSES_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        raise ResponsesRouteCapabilityError(
            ResponsesRouteCapabilityFinding(
                capability=RESPONSES_CAPABILITIES_KEY,
                field="model",
                error_code="responses_route_capability_invalid",
                safe_message="Responses route capability metadata is invalid.",
            )
        )

    parsed: dict[str, bool] = {}
    for key, value in raw.items():
        capability = str(key)
        if capability not in KNOWN_RESPONSES_CAPABILITIES:
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="responses_route_capability_invalid",
                    safe_message="Responses route capability metadata contains an unknown flag.",
                )
            )
        if not isinstance(value, bool):
            raise ResponsesRouteCapabilityError(
                ResponsesRouteCapabilityFinding(
                    capability=capability,
                    field="model",
                    error_code="responses_route_capability_invalid",
                    safe_message="Responses route capability metadata must use boolean flags.",
                )
            )
        parsed[capability] = value
    return parsed
