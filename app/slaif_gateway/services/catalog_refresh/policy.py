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
    fx_stale_review_days: int
    fx_stale_blocked_days: int

    def source_age_state(self, age: timedelta) -> str:
        """Source freshness with exact documented boundaries.

        - ``fresh``   when age <= review threshold (default 24h, inclusive)
        - ``review``  when review threshold < age <= blocked threshold
        - ``blocked`` when age > blocked threshold (default 72h)

        The reference time for offline review is the bundle's
        ``generated_at`` (a deterministic, replayable clock); a future live
        apply re-checks freshness against its own current clock.
        """
        if age <= self.source_stale_review:
            return "fresh"
        if age <= self.source_stale_blocked:
            return "review"
        return "blocked"

    def fx_age_state(self, calendar_age_days: int) -> str:
        """FX publication-age state on a CALENDAR-DAY basis (defaults 3d / 7d).

        ``calendar_age_days`` is the whole-day difference between the UTC
        publication date and the UTC review reference date
        (``review_date - publication_date``); the time-of-day never changes
        the state.

        - ``fresh``   when calendar age <= review days (default 3, inclusive)
        - ``review``  when review days < calendar age <= blocked days
        - ``blocked`` when calendar age > blocked days (default 7)
        """
        if calendar_age_days <= self.fx_stale_review_days:
            return "fresh"
        if calendar_age_days <= self.fx_stale_blocked_days:
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
        fx_stale_review_days=document.fx_stale_review_days,
        fx_stale_blocked_days=document.fx_stale_blocked_days,
    )


DEFAULT_POLICY_VERSION = POLICY_VERSION
