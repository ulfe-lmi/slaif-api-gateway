"""Content-free schemas for the first OpenAI Responses web-search contract."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class WebSearchRequestFacts:
    """Validated, policy-bound facts for one provider web-search request."""

    search_context_size: str | None
    max_tool_calls: int
    effective_tool_call_cap: int
    provider: str
    capability: str
    quota_mode: str
    decision_reason_code: str
    _provider_body: Mapping[str, Any]
    admission_decision: Any = None

    @property
    def provider_body(self) -> dict[str, Any]:
        """Rebuild the exact approved provider fragment without gateway state."""
        return {
            "tools": [dict(self._provider_body["tools"][0])],
            "max_tool_calls": self._provider_body["max_tool_calls"],
        }


@dataclass(frozen=True, slots=True)
class WebSearchAccountingEvidence:
    """Safe, low-cardinality evidence used by a future accounting boundary."""

    provider: str
    capability: str
    admitted_call_cap: int
    completed_call_count: int
    pricing_source: str | None
    unit_tool_fee_native: Decimal | None
    total_tool_fee_native: Decimal | None
    authoritative: bool
    reason_code: str

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "admitted_call_cap": self.admitted_call_cap,
            "completed_call_count": self.completed_call_count,
            "pricing_source": self.pricing_source,
            "unit_tool_fee_native": self.unit_tool_fee_native,
            "total_tool_fee_native": self.total_tool_fee_native,
            "authoritative": self.authoritative,
            "reason_code": self.reason_code,
        }


def frozen_provider_body(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """Keep the canonical body private and immutable at the schema boundary."""
    return MappingProxyType(
        {
            "tools": (MappingProxyType(dict(body["tools"][0])),),
            "max_tool_calls": body["max_tool_calls"],
        }
    )
