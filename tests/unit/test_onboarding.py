import pytest

from slaif_gateway.services.onboarding import OnboardingService


@pytest.mark.asyncio
async def test_clean_operator_is_blocked_until_prerequisites_are_met():
    service = OnboardingService()
    rows = await service.build_setup_model(facts={})
    by_key = {row["key"]: row for row in rows}
    assert by_key["organization"]["status"] == "blocked"
    assert by_key["oidc"]["status"] == "held"
    assert by_key["strict-key"]["status"] == "blocked"


@pytest.mark.asyncio
async def test_completed_path_reports_usable_strict_key():
    facts = {key: True for key in (
        "organization", "oidc", "provider_configured", "catalog_imported",
        "policy_assigned", "budget_defined", "service_account", "strict_key_issued",
    )}
    rows = await OnboardingService().build_setup_model(facts=facts)
    assert all(row["status"] == "implemented" for row in rows)
    assert rows[-1]["key"] == "strict-key"


@pytest.mark.asyncio
async def test_no_secret_values_appear_in_status_model():
    facts = {key: True for key in ("organization", "oidc", "provider_configured")}
    text = repr(await OnboardingService().build_setup_model(facts=facts)).lower()
    assert "api-key" not in text
    assert "secret" not in text
