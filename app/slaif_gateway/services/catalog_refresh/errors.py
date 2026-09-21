"""Safe error types for catalog refresh tooling.

Messages are operator-facing and must never embed key material, raw source
text, or caller-supplied payloads.
"""

from __future__ import annotations


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
