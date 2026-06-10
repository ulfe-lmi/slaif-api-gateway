"""Safe schemas for the Realtime client-secret foundation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RealtimePolicyResult:
    """Safe normalized Realtime client-secret request ready for routing/pricing."""

    effective_body: dict[str, Any]
    estimated_input_tokens: int
    effective_output_tokens: int
