"""Trust-limited client module protocol."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from slaif_gateway.modules.contracts import CanonicalClientRequest


class ClientModule(Protocol):
    """Decode one untrusted client dialect without Gateway authority."""

    module_id: str
    module_version: str

    def normalize(
        self,
        endpoint: str,
        body: Mapping[str, object],
    ) -> CanonicalClientRequest:
        """Return fresh canonical facts without side effects or retention."""
