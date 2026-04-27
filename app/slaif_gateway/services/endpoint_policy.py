"""Service-layer endpoint allow-list checks for authenticated gateway keys."""

from __future__ import annotations

from typing import Final

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.endpoint_policy_errors import EndpointNotAllowedError

MODELS_LIST: Final[str] = "models.list"
CHAT_COMPLETIONS: Final[str] = "chat.completions"

_ENDPOINT_ALIASES: Final[dict[str, frozenset[str]]] = {
    MODELS_LIST: frozenset(
        {
            "models.list",
            "get /v1/models",
            "/v1/models",
        }
    ),
    CHAT_COMPLETIONS: frozenset(
        {
            "chat.completions",
            "post /v1/chat/completions",
            "/v1/chat/completions",
        }
    ),
}


class EndpointPolicyService:
    """Checks whether an authenticated key may call a stable endpoint identifier."""

    def ensure_endpoint_allowed(
        self,
        authenticated_key: AuthenticatedGatewayKey,
        endpoint: str,
    ) -> None:
        if authenticated_key.allow_all_endpoints:
            return

        allowed = {_normalize_endpoint_entry(item) for item in authenticated_key.allowed_endpoints}
        if not allowed:
            raise EndpointNotAllowedError()

        requested_aliases = _ENDPOINT_ALIASES.get(endpoint, frozenset({_normalize_endpoint_entry(endpoint)}))
        if allowed.isdisjoint(requested_aliases):
            raise EndpointNotAllowedError()


def _normalize_endpoint_entry(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parts = normalized.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isalpha() and parts[1].startswith("/"):
        return f"{parts[0].lower()} {parts[1].lower()}"
    if normalized.startswith("/"):
        return normalized.lower()
    return normalized.lower()

