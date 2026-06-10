"""Route/model capability policy for standalone Embeddings API routes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.services.policy_errors import RequestPolicyError

EMBEDDINGS_CAPABILITIES_KEY = "embeddings"
EMBEDDINGS_CAPABILITY_ENABLED = "embeddings"
EMBEDDINGS_CAPABILITY_DIMENSIONS = "embeddings_dimensions"

KNOWN_EMBEDDINGS_CAPABILITIES = frozenset(
    {
        EMBEDDINGS_CAPABILITY_ENABLED,
        EMBEDDINGS_CAPABILITY_DIMENSIONS,
    }
)


def default_embeddings_capabilities() -> dict[str, bool]:
    return {
        EMBEDDINGS_CAPABILITY_ENABLED: True,
        EMBEDDINGS_CAPABILITY_DIMENSIONS: False,
    }


def ensure_default_embeddings_capabilities(
    capabilities: Mapping[str, object] | None,
    *,
    endpoint: str,
) -> dict[str, object]:
    normalized = dict(capabilities or {})
    if endpoint == "/v1/embeddings" and EMBEDDINGS_CAPABILITIES_KEY not in normalized:
        normalized[EMBEDDINGS_CAPABILITIES_KEY] = default_embeddings_capabilities()
    return normalized


@dataclass(frozen=True, slots=True)
class EmbeddingsRouteCapabilityFinding:
    capability: str
    field: str
    error_code: str
    safe_message: str


class EmbeddingsRouteCapabilityError(RequestPolicyError):
    def __init__(self, finding: EmbeddingsRouteCapabilityFinding) -> None:
        self.error_code = finding.error_code
        self.capability = finding.capability
        super().__init__(finding.safe_message, param=finding.field)


def enforce_embeddings_route_capabilities(
    *,
    route_capabilities: Mapping[str, object] | None,
    dimensions_requested: bool,
) -> None:
    capabilities = _parse_embeddings_route_capabilities(route_capabilities)
    if not capabilities.get(EMBEDDINGS_CAPABILITY_ENABLED, False):
        raise EmbeddingsRouteCapabilityError(
            EmbeddingsRouteCapabilityFinding(
                capability=EMBEDDINGS_CAPABILITY_ENABLED,
                field="model",
                error_code="embeddings_capability_not_supported",
                safe_message="This model route does not support the requested embeddings endpoint.",
            )
        )
    if dimensions_requested and not capabilities.get(EMBEDDINGS_CAPABILITY_DIMENSIONS, False):
        raise EmbeddingsRouteCapabilityError(
            EmbeddingsRouteCapabilityFinding(
                capability=EMBEDDINGS_CAPABILITY_DIMENSIONS,
                field="dimensions",
                error_code="embeddings_dimensions_not_supported",
                safe_message="This model route does not support configurable embeddings dimensions.",
            )
        )


def _parse_embeddings_route_capabilities(
    route_capabilities: Mapping[str, object] | None,
) -> dict[str, bool]:
    if not isinstance(route_capabilities, Mapping):
        return {}
    raw = route_capabilities.get(EMBEDDINGS_CAPABILITIES_KEY)
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, bool] = {}
    for name in KNOWN_EMBEDDINGS_CAPABILITIES:
        parsed[name] = raw.get(name) is True
    return parsed
