"""Trust-limited client module protocol."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from slaif_gateway.modules.contracts import CanonicalClientRequest


class ClientModule(Protocol):
    """Decode one untrusted client dialect without Gateway authority."""

    module_id: str
    module_version: str
    fixture_sha256: str | None

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        """Return fresh canonical facts without side effects or retention."""

    def normalize_responses(
        self,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        """Classify a Responses request using pure client-dialect logic."""

    def stream_profile(self, body: Mapping[str, object]) -> str | None:
        """Return a bounded client stream-profile fact, never authority."""
