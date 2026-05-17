from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.services.calibration_summary_service import (
    CalibrationSummaryError,
    CalibrationSummaryService,
)
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)

PROMPT_TEXT = "prompt text must not appear"
COMPLETION_TEXT = "completion text must not appear"
SECRET_VALUE = "sk-live-secret-must-not-appear"


class FakeKeyRepository:
    def __init__(self, key) -> None:
        self.key = key

    async def get_key_for_admin_detail(self, gateway_key_id):
        return self.key if self.key is not None and self.key.id == gateway_key_id else None


class FakeUsageProfilesRepository:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def list_for_gateway_key(self, gateway_key_id, **kwargs):
        self.calls.append({"gateway_key_id": gateway_key_id, **kwargs})
        return self.rows


def test_summarizes_trusted_calibration_usage_and_policy_proposal() -> None:
    key = _key()
    now = datetime.now(UTC)
    rows = [
        _profile(
            gateway_key_id=key.id,
            created_at=now - timedelta(minutes=10),
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            reasoning_tokens=3,
            cached_tokens=None,
            slaif_calculated_cost=Decimal("0.010000000"),
            provider_reported_cost=Decimal("0.011000000"),
            profile_metadata={
                "observed_hosted_capability_types": ["web_search_options"],
                "unknown_hosted_capability_types": ["custom_tool"],
                "denied_external_authority_markers": ["server_url"],
                "prompt": PROMPT_TEXT,
                "completion": COMPLETION_TEXT,
                "provider_key": SECRET_VALUE,
            },
        ),
        _profile(
            gateway_key_id=key.id,
            created_at=now,
            input_tokens=5,
            output_tokens=7,
            total_tokens=12,
            reasoning_tokens=None,
            cached_tokens=2,
            slaif_calculated_cost=Decimal("0.020000000"),
        ),
    ]
    service = _service(key=key, rows=rows)

    result = asyncio.run(
        service.summarize_calibration_key_usage(
            gateway_key_id=key.id,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            multiplier=Decimal("2"),
        )
    )

    summary = result.summary
    proposal = result.proposal
    assert summary.observed_request_count == 2
    assert summary.observed_endpoints == ("/v1/chat/completions",)
    assert summary.observed_providers == ("openai",)
    assert summary.observed_requested_models == ("gpt-4.1-mini",)
    assert summary.total_input_tokens == 15
    assert summary.total_output_tokens == 27
    assert summary.total_tokens == 42
    assert summary.total_reasoning_tokens == 3
    assert summary.total_cached_tokens == 2
    assert summary.total_slaif_calculated_cost == Decimal("0.030000000")
    assert summary.total_provider_reported_cost == Decimal("0.011000000")
    assert summary.cost_confidence == "mixed"
    assert summary.observed_hosted_capabilities == ("web_search_options",)
    assert summary.observed_unknown_hosted_capabilities == ("custom_tool",)
    assert summary.observed_denied_capabilities == ("server_url",)
    assert proposal.proposed_allowed_endpoints == ("/v1/chat/completions",)
    assert proposal.proposed_allowed_models == ("gpt-4.1-mini",)
    assert proposal.proposed_allowed_providers == ("openai",)
    assert proposal.proposed_allowed_hosted_capabilities == ()
    assert proposal.hosted_capabilities_requiring_review == ("web_search_options",)
    assert proposal.proposed_request_limit_total == 4
    assert proposal.proposed_token_limit_total == 84
    assert proposal.proposed_input_token_limit_total == 30
    assert proposal.proposed_output_token_limit_total == 54
    assert proposal.proposed_reasoning_token_limit_total == 6
    assert proposal.proposed_cost_limit_eur == Decimal("0.060000000")
    payload = json.dumps(result, default=str, sort_keys=True)
    assert PROMPT_TEXT not in payload
    assert COMPLETION_TEXT not in payload
    assert SECRET_VALUE not in payload


def test_rejects_standard_key_usage_summary() -> None:
    key = _key(key_purpose="standard", capability_policy_mode="standard")
    service = _service(key=key, rows=[])

    with pytest.raises(CalibrationSummaryError, match="trusted calibration"):
        asyncio.run(service.summarize_calibration_key_usage(gateway_key_id=key.id))


@pytest.mark.parametrize("multiplier", [Decimal("0.99"), Decimal("10.1")])
def test_rejects_invalid_multiplier(multiplier: Decimal) -> None:
    key = _key()
    service = _service(key=key, rows=[])

    with pytest.raises(CalibrationSummaryError, match="multiplier"):
        asyncio.run(
            service.summarize_calibration_key_usage(
                gateway_key_id=key.id,
                multiplier=multiplier,
            )
        )


def test_empty_usage_returns_not_enough_data_warning() -> None:
    key = _key()
    service = _service(key=key, rows=[])

    result = asyncio.run(service.summarize_calibration_key_usage(gateway_key_id=key.id))

    assert result.is_empty is True
    assert result.summary.observed_request_count == 0
    assert result.proposal.proposed_allowed_endpoints == ()
    assert result.proposal.proposed_request_limit_total == 1
    assert any("Not enough" in warning for warning in result.warnings)


def test_does_not_propose_unimplemented_endpoints() -> None:
    key = _key()
    service = _service(
        key=key,
        rows=[
            _profile(gateway_key_id=key.id, endpoint_path="/v1/responses"),
            _profile(gateway_key_id=key.id, endpoint_path="/v1/completions"),
            _profile(gateway_key_id=key.id, endpoint_path="/v1/chat/completions"),
        ],
    )

    result = asyncio.run(service.summarize_calibration_key_usage(gateway_key_id=key.id))

    assert "/v1/chat/completions" in result.proposal.proposed_allowed_endpoints
    assert "/v1/responses" not in result.proposal.proposed_allowed_endpoints
    assert "/v1/completions" not in result.proposal.proposed_allowed_endpoints
    assert any("unsupported endpoints" in warning for warning in result.warnings)


def _service(*, key, rows) -> CalibrationSummaryService:
    return CalibrationSummaryService(
        gateway_keys_repository=FakeKeyRepository(key),
        usage_profiles_repository=FakeUsageProfilesRepository(rows),
    )


def _key(
    *,
    key_purpose: str = KEY_PURPOSE_TRUSTED_CALIBRATION,
    capability_policy_mode: str = CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
):
    owner = SimpleNamespace(
        id=uuid.uuid4(),
        name="Ada",
        surname="Lovelace",
        email="ada@example.org",
        institution=SimpleNamespace(id=uuid.uuid4(), name="SLAIF University"),
    )
    cohort_id = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        public_key_id="public-calibration",
        owner_id=owner.id,
        owner=owner,
        cohort_id=cohort_id,
        cohort=SimpleNamespace(id=cohort_id, name="Workshop"),
        key_purpose=key_purpose,
        capability_policy_mode=capability_policy_mode,
    )


def _profile(
    *,
    gateway_key_id: uuid.UUID,
    endpoint_path: str = "/v1/chat/completions",
    provider: str = "openai",
    requested_model: str = "gpt-4.1-mini",
    resolved_upstream_model: str = "gpt-4.1-mini",
    provider_host: str = "api.openai.com",
    provider_endpoint_path: str = "/v1/chat/completions",
    input_tokens: int = 1,
    output_tokens: int = 2,
    total_tokens: int = 3,
    reasoning_tokens: int | None = None,
    cached_tokens: int | None = None,
    slaif_calculated_cost: Decimal | None = None,
    provider_reported_cost: Decimal | None = None,
    cost_currency: str | None = "EUR",
    cost_source: str = "slaif_calculated",
    profile_metadata: dict[str, object] | None = None,
    created_at: datetime | None = None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        gateway_key_id=gateway_key_id,
        endpoint_path=endpoint_path,
        provider=provider,
        requested_model=requested_model,
        resolved_upstream_model=resolved_upstream_model,
        provider_host=provider_host,
        provider_endpoint_path=provider_endpoint_path,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_tokens=cached_tokens,
        slaif_calculated_cost=slaif_calculated_cost,
        provider_reported_cost=provider_reported_cost,
        cost_currency=cost_currency,
        cost_source=cost_source,
        profile_metadata=profile_metadata or {},
        created_at=created_at or datetime.now(UTC),
    )
