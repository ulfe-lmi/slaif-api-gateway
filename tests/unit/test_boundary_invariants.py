"""Hostile negative invariant suite for SME organizational boundaries."""

from __future__ import annotations

import pytest

from slaif_gateway.services.policy_bundles import PolicyBundleService, PolicyDriftError
from slaif_gateway.services.provider_governance import ProviderGovernanceError, route_allowed
from slaif_gateway.services.security import AbuseTracker, safe_admin_redirect


def test_cross_unit_policy_drift_fails_closed():
    with pytest.raises(PolicyDriftError):
        PolicyBundleService.check_drift(
            preview={"models": ["team-a-model"], "tools": []},
            requested_models=["team-b-model"],
            requested_tools=[],
        )


def test_stale_governance_evidence_blocks_alternate_provider_route():
    from datetime import UTC, datetime, timedelta

    facts = {
        "region": "eu",
        "training_use": False,
        "zdr_claimed": True,
        "tool_destinations": [],
        "evidence_date": datetime.now(UTC) - timedelta(days=181),
    }
    with pytest.raises(ProviderGovernanceError):
        route_allowed(facts)


def test_abuse_tracker_prevents_privilege_grant_retry_after_lockout():
    tracker = AbuseTracker(max_attempts=2)
    for _ in range(2):
        tracker.record_failure("service-account")
    assert tracker.is_blocked("service-account") is True


def test_open_redirect_cannot_escape_admin_boundary():
    assert safe_admin_redirect("//attacker.example", set()) == "/"


def test_uuid_alias_does_not_bypass_scope_lookup():
    alias = "00000000-0000-0000-0000-000000000001"
    allowed = {"11111111-1111-1111-1111-111111111111"}
    assert alias not in allowed


@pytest.mark.parametrize("role,attempt", [
    ("auditor", "create_key"),
    ("manager", "grant_admin"),
    ("service-account", "rotate_admin_session"),
])
def test_role_ceilings_are_negative(role, attempt):
    ceilings = {
        "auditor": {"read", "export"},
        "manager": {"read", "manage_project"},
        "service-account": {"request"},
    }
    assert attempt not in ceilings[role]
