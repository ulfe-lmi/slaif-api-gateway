"""Safe error types for catalog refresh tooling.

Messages are operator-facing and must never embed key material, raw source
text, or caller-supplied payloads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import ValidationError


class CatalogRefreshError(Exception):
    """Base error for catalog refresh tooling."""


class CatalogRefreshBlockedError(CatalogRefreshError):
    """A safe, reportable blocking condition (code + detail only)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class CatalogRefreshSealError(CatalogRefreshError):
    """Sealing/verification failure; never includes key material."""


def safe_schema_error_text(exc: "ValidationError") -> str:
    """Bounded, privacy-safe rendering of a Pydantic ValidationError.

    String locations are dropped (they may be untrusted input: unknown
    extra field names, dictionary keys); only integer positions are kept.
    Custom value-error messages may embed input values and are replaced
    with fixed text. Standard Pydantic message templates are retained,
    each bounded. The result never contains arbitrary raw input.
    """
    parts: list[str] = []
    for error in exc.errors()[:8]:
        loc = ".".join(
            str(part) for part in error.get("loc", ()) if isinstance(part, int)
        )
        if error.get("type") == "value_error":
            msg = "custom validation failed"
        else:
            msg = str(error.get("msg", "invalid"))[:300]
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)[:4000]
