"""Versioned, deterministic operator policy for catalog refresh review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from slaif_gateway.schemas.catalog_refresh import POLICY_VERSION, PolicyDocument


@dataclass(frozen=True, slots=True)
class RefreshPolicy:
    """Resolved policy thresholds (always recomputed, never caller-supplied)."""

    version: int
    price_change_review: Decimal
    fx_change_review: Decimal
    source_stale_review: timedelta
    source_stale_blocked: timedelta
    fx_stale_review: timedelta
    fx_stale_blocked: timedelta

    def source_age_state(self, age: timedelta) -> str:
        if age < self.source_stale_review:
            return "fresh"
        if age <= self.source_stale_blocked:
            return "review"
        return "blocked"

    def fx_age_state(self, age: timedelta) -> str:
        if age < self.fx_stale_review:
            return "fresh"
        if age <= self.fx_stale_blocked:
            return "review"
        return "blocked"


def policy_from_document(document: PolicyDocument) -> RefreshPolicy:
    """Resolve a validated policy document into deterministic thresholds."""
    return RefreshPolicy(
        version=document.version,
        price_change_review=Decimal(document.price_change_review),
        fx_change_review=Decimal(document.fx_change_review),
        source_stale_review=timedelta(hours=document.source_stale_review_hours),
        source_stale_blocked=timedelta(hours=document.source_stale_blocked_hours),
        fx_stale_review=timedelta(days=document.fx_stale_review_days),
        fx_stale_blocked=timedelta(days=document.fx_stale_blocked_days),
    )


DEFAULT_POLICY_VERSION = POLICY_VERSION
