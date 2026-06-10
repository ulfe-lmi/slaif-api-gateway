"""Standalone Audio API request-policy and forwarding schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AudioPolicyResult:
    """Safe normalized standalone Audio API request ready for routing/pricing."""

    effective_body: dict[str, Any]
    estimated_input_tokens: int
    effective_output_tokens: int = 0
    uploaded_file_bytes: int = 0
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class AudioUploadPayload:
    """Transient validated audio upload for provider forwarding."""

    filename: str
    content_type: str | None
    data: bytes = field(repr=False)
