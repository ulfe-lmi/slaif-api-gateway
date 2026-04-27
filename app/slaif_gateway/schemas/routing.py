"""Service-layer schemas for safe model route resolution results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RouteResolutionResult:
    """Safe route resolution output used by /v1 validation and later forwarding."""

    requested_model: str
    resolved_model: str
    provider: str
    route_id: uuid.UUID
    route_match_type: str
    route_pattern: str
    priority: int
    provider_base_url: str | None = None
    provider_api_key_env_var: str | None = None
    provider_timeout_seconds: int | None = None
    provider_max_retries: int | None = None
    visible_model_id: str | None = None
