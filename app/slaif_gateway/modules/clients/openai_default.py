"""Default OpenAI-compatible client dialect module."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    DEFAULT_CLIENT_MODULE_ID,
    DEFAULT_CLIENT_MODULE_VERSION,
    ModuleSelectionError,
)

SUPPORTED_ENDPOINTS = frozenset({"/v1/chat/completions", "/v1/responses"})


class OpenAIDefaultClientModule:
    """Normalize ordinary OpenAI-compatible Chat and Responses requests."""

    module_id = DEFAULT_CLIENT_MODULE_ID
    module_version = DEFAULT_CLIENT_MODULE_VERSION
    fixture_sha256 = None
    policy_spec = None

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if endpoint not in SUPPORTED_ENDPOINTS:
            raise ModuleSelectionError(
                "The default client module does not support this endpoint",
                error_code="unsupported_client_endpoint",
            )
        if not isinstance(body, Mapping):
            raise ModuleSelectionError(
                "The client request body is not a mapping",
                error_code="client_request_invalid",
            )
        # A deep copy is deliberately returned so policy code cannot mutate the
        # caller-owned Pydantic mapping. The module stores no request state.
        canonical_body = copy.deepcopy(dict(body))
        return CanonicalClientRequest(
            module_id=self.module_id,
            module_version=self.module_version,
            endpoint=endpoint,
            body=canonical_body,
        )

    def normalize_responses(
        self,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        return self.normalize("/v1/responses", body)

    def stream_profile(self, body: Mapping[str, object]) -> str | None:
        _ = body
        return None

    def encrypted_reasoning_output_requested(self, body: Mapping[str, object]) -> bool:
        _ = body
        return False
