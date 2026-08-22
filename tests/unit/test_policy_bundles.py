import pytest

from slaif_gateway.services.policy_bundles import PolicyBundleService, PolicyDriftError


def test_check_drift_fails_closed_on_unknown_model_or_tool():
    with pytest.raises(PolicyDriftError) as caught:
        PolicyBundleService.check_drift(
            preview={"models": ["m1"], "tools": ["p:t1"]},
            requested_models=["m1", "missing"],
            requested_tools=["p:t1", "p:missing"],
        )
    assert caught.value.missing_models == ["missing"]
    assert caught.value.missing_tools == ["p:missing"]


def test_check_drift_passes_when_resources_are_approved():
    PolicyBundleService.check_drift(
        preview={"models": ["m1"], "tools": ["p:t1"]},
        requested_models=["m1"],
        requested_tools=["p:t1"],
    )
