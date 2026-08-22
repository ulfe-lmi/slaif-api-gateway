"""Provider governance routing constraints with stale-evidence fail-closed checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GovernanceFacts:
    region: str | None
    retention_policy: str | None
    training_use: bool
    zdr_claimed: bool
    tool_destinations: tuple[str, ...]
    evidence_date: datetime | None


class ProviderGovernanceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def route_allowed(
    facts: Mapping[str, object],
    *,
    required_regions: set[str] | None = None,
    deny_training_use: bool = False,
    require_zdr: bool = False,
    max_destination_count: int | None = None,
    now: datetime | None = None,
    evidence_max_age_days: int = 180,
) -> bool:
    """Return whether governance facts satisfy explicit policy constraints."""
    check_now = _aware(now)
    raw_date = facts.get("evidence_date")
    if not isinstance(raw_date, datetime):
        raise ProviderGovernanceError("provider_evidence_missing")
    if raw_date.tzinfo is None:
        raise ProviderGovernanceError("provider_evidence_invalid")
    if check_now - raw_date > timedelta(days=evidence_max_age_days):
        raise ProviderGovernanceError("provider_evidence_stale")

    region = facts.get("region")
    if required_regions is not None and (not isinstance(region, str) or region not in required_regions):
        return False

    if deny_training_use and facts.get("training_use") is True:
        return False
    if require_zdr and facts.get("zdr_claimed") is not True:
        return False

    destinations = facts.get("tool_destinations")
    if not isinstance(destinations, list):
        raise ProviderGovernanceError("provider_destinations_invalid")
    if any(not isinstance(item, str) or not item for item in destinations):
        raise ProviderGovernanceError("provider_destinations_invalid")
    if max_destination_count is not None and len(destinations) > max_destination_count:
        return False
    return True


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ProviderGovernanceError("provider_evidence_invalid")
    return value.astimezone(UTC)
