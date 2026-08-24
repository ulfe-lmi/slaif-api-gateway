"""Qualified Codex CLI 0.147 Responses client dialect."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from types import MappingProxyType

from slaif_gateway.modules.contracts import (
    CanonicalClientRequest,
    ModuleSelectionError,
)
from slaif_gateway.modules.clients.codex_0148 import CODEX_0148_CLIENT_TOOL_TAXONOMY
from slaif_gateway.modules.clients.codex_support import (
    CODEX_0147_INCLUDE_VALUE,
    build_codex_0147_policy_spec,
)

CODEX_0147_CLIENT_MODULE_ID = "codex-0.147-responses-v1"
CODEX_0147_CLIENT_MODULE_VERSION = "1"
CODEX_0147_CLI_VERSION = "0.147.0"
CODEX_0147_PROFILE_ID = "openai-gpt-5.6-sol-codex-0.147-v1"
CODEX_0147_FIXTURE_SHA256 = (
    "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432"
)

_PROFILE_FACTS = MappingProxyType(
    {
        "client_module_id": CODEX_0147_CLIENT_MODULE_ID,
        "client_module_version": CODEX_0147_CLIENT_MODULE_VERSION,
        "fixture_sha256": CODEX_0147_FIXTURE_SHA256,
    }
)
CODEX_0147_POLICY_SPEC = build_codex_0147_policy_spec(
    taxonomy_0148=CODEX_0148_CLIENT_TOOL_TAXONOMY,
)


class Codex0147ResponsesClientModule:
    """Expose only the already-qualified 0.147 client facts to Gateway core."""

    module_id = CODEX_0147_CLIENT_MODULE_ID
    module_version = CODEX_0147_CLIENT_MODULE_VERSION
    fixture_sha256 = CODEX_0147_FIXTURE_SHA256
    policy_spec = CODEX_0147_POLICY_SPEC

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        if endpoint not in {"/v1/responses", "/v1/responses/compact"}:
            raise ModuleSelectionError(
                "The Codex 0.147 client module does not support this endpoint",
                error_code="unsupported_client_endpoint",
            )
        if not isinstance(body, Mapping):
            raise ModuleSelectionError(
                "The client request body is not a mapping",
                error_code="client_request_invalid",
            )
        return CanonicalClientRequest(
            module_id=self.module_id,
            module_version=self.module_version,
            endpoint=endpoint,
            body=copy.deepcopy(dict(body)),
            stream_profile=self.module_id,
            profile_facts=_PROFILE_FACTS,
        )

    def normalize_responses(
        self,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        return self.normalize("/v1/responses", body)

    def stream_profile(self, body: Mapping[str, object]) -> str:
        _ = body
        return self.module_id

    def encrypted_reasoning_output_requested(self, body: Mapping[str, object]) -> bool:
        include = body.get("include")
        return isinstance(include, list) and CODEX_0147_INCLUDE_VALUE in include
