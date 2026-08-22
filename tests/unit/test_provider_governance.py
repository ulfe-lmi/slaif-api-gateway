from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.services.provider_governance import (
    ProviderGovernanceError,
    route_allowed,
)


def _facts(*, age_days=0):
    return {
        "region": "eu-central-1",
        "retention_policy": "30d",
        "training_use": False,
        "zdr_claimed": True,
        "tool_destinations": ["https://search.invalid"],
        "evidence_date": datetime.now(UTC) - timedelta(days=age_days),
    }


def test_allows_matching_region_and_zdr():
    assert route_allowed(_facts(), required_regions={"eu-central-1"}, require_zdr=True)


def test_denies_wrong_region_or_training():
    assert route_allowed(_facts(), required_regions={"us"}) is False
    assert route_allowed({"**": None} | _facts() | {"training_use": True}, deny_training_use=True) is False


def test_stale_or_invalid_evidence_fails_closed():
    with pytest.raises(ProviderGovernanceError):
        route_allowed(_facts(age_days=181))
    bad = _facts()
    bad["evidence_date"] = datetime.now(UTC).replace(tzinfo=None)
    with pytest.raises(ProviderGovernanceError):
        route_allowed(bad)
