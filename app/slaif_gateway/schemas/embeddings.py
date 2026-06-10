"""Safe schemas for the standalone Embeddings API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EmbeddingsPolicyResult:
    """Safe normalized embeddings request ready for routing/pricing."""

    effective_body: dict[str, Any]
    estimated_input_tokens: int
    effective_output_tokens: int = 0
