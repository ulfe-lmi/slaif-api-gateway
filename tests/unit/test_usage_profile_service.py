from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.usage_profile_service import (
    UsageProfileService,
    build_chat_completion_tool_metadata,
    sanitize_provider_url_parts,
    validate_cost_source,
)
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)

PROMPT_TEXT = "user prompt should not persist"
COMPLETION_TEXT = "assistant completion should not persist"
SECRET_VALUE = "sk-live-secret-should-not-persist"


class FakeUsageLedgerRepository:
    def __init__(self, row) -> None:
        self.row = row

    async def get_usage_record_by_id(self, usage_ledger_id):
        return self.row if self.row is not None and self.row.id == usage_ledger_id else None


class FakeUsageProfilesRepository:
    def __init__(self, *, existing=None, fail_create: bool = False) -> None:
        self.existing = existing
        self.fail_create = fail_create
        self.created: list[dict[str, object]] = []

    async def get_by_usage_ledger_id(self, usage_ledger_id):
        _ = usage_ledger_id
        return self.existing

    async def create_usage_profile(self, **kwargs):
        if self.fail_create:
            raise RuntimeError("insert failed with secret-looking context")
        self.created.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), **kwargs)


def test_usage_profile_service_creates_safe_chat_completion_profile() -> None:
    ledger = _ledger(
        cached_tokens=3,
        reasoning_tokens=2,
        response_metadata={
            "provider_reported_cost_native": "0.000123000",
            "provider_reported_currency": "USD",
        },
    )
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(ledger),
        usage_profiles_repository=profiles,
    )

    result = asyncio.run(_record(service, ledger))

    assert result is not None
    created = profiles.created[0]
    assert created["usage_ledger_id"] == ledger.id
    assert created["gateway_key_id"] == ledger.gateway_key_id
    assert created["endpoint_path"] == "/v1/chat/completions"
    assert created["provider"] == "openai"
    assert created["requested_model"] == "classroom-cheap"
    assert created["resolved_upstream_model"] == "gpt-4.1-mini"
    assert created["provider_host"] == "api.openai.com"
    assert created["provider_endpoint_path"] == "/v1/chat/completions"
    assert created["input_tokens"] == 5
    assert created["output_tokens"] == 6
    assert created["total_tokens"] == 11
    assert created["cached_tokens"] == 3
    assert created["reasoning_tokens"] == 2
    assert created["provider_reported_cost"] == Decimal("0.000123000")
    assert created["slaif_calculated_cost"] == Decimal("0.000456000")
    assert created["cost_source"] == "mixed"
    assert created["cost_currency"] == "EUR"
    assert created["gateway_request_id"] == ledger.request_id


def test_profile_metadata_drops_prompt_completion_raw_body_and_secret_values() -> None:
    ledger = _ledger()
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(ledger),
        usage_profiles_repository=profiles,
    )

    asyncio.run(
        _record(
            service,
            ledger,
            profile_metadata={
                "prompt": PROMPT_TEXT,
                "completion": COMPLETION_TEXT,
                "raw_request_body": {"message": PROMPT_TEXT},
                "raw_response_body": {"message": COMPLETION_TEXT},
                "safe": "kept",
                "source_url": f"https://example.test/?token={SECRET_VALUE}",
                "Authorization": f"Bearer {SECRET_VALUE}",
                "nested": {"session_token": SECRET_VALUE, "safe_count": 2},
            },
        )
    )

    payload = json.dumps(profiles.created[0]["profile_metadata"], sort_keys=True)
    assert "kept" in payload
    assert PROMPT_TEXT not in payload
    assert COMPLETION_TEXT not in payload
    assert SECRET_VALUE not in payload
    assert "Authorization" not in payload
    assert "session_token" not in payload


def test_provider_url_sanitization_strips_query_fragment_credentials_and_tokens() -> None:
    host, path = sanitize_provider_url_parts(
        f"https://user:pass@api.openai.com/v1/chat/completions?token={SECRET_VALUE}#frag"
    )

    assert host == "api.openai.com"
    assert path == "/v1/chat/completions"
    assert SECRET_VALUE not in f"{host}{path}"


def test_reasoning_and_cached_counts_are_nullable_not_guessed() -> None:
    ledger = _ledger(cached_tokens=0, reasoning_tokens=0)
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(ledger),
        usage_profiles_repository=profiles,
    )

    asyncio.run(_record(service, ledger))

    created = profiles.created[0]
    assert created["cached_tokens"] is None
    assert created["reasoning_tokens"] is None


def test_cost_fields_distinguish_provider_reported_and_slaif_calculated() -> None:
    provider_only = _ledger(actual_cost_eur=None, response_metadata={"provider_reported_cost_native": "1.25"})
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(provider_only),
        usage_profiles_repository=profiles,
    )

    asyncio.run(_record(service, provider_only))

    created = profiles.created[0]
    assert created["provider_reported_cost"] == Decimal("1.25")
    assert created["slaif_calculated_cost"] is None
    assert created["cost_source"] == "provider_reported"


def test_usage_profile_preserves_safe_cost_confidence_and_overrun_metadata() -> None:
    ledger = _ledger(
        response_metadata={
            "cost_source": "provider_reported",
            "cost_confidence": "provider_reported_with_slaif_comparison",
            "reservation_overrun": True,
            "token_reservation_overrun": True,
            "cost_reservation_overrun": False,
            "overrun_policy": "chat_completions_admit_then_finalize_v1",
            "provider_reported_cost_native": "0.05",
            "provider_reported_currency": "EUR",
        }
    )
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(ledger),
        usage_profiles_repository=profiles,
    )

    asyncio.run(_record(service, ledger))

    created = profiles.created[0]
    assert created["cost_source"] == "provider_reported"
    assert created["profile_metadata"]["cost_confidence"] == (
        "provider_reported_with_slaif_comparison"
    )
    assert created["profile_metadata"]["reservation_overrun"] is True
    assert created["profile_metadata"]["token_reservation_overrun"] is True
    assert created["profile_metadata"]["cost_reservation_overrun"] is False


def test_tool_metadata_stores_only_safe_counts_and_function_names() -> None:
    metadata = build_chat_completion_tool_metadata(
        {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_course",
                        "parameters": {"raw_schema": PROMPT_TEXT},
                    },
                },
                {"type": "web-search", "authorization": SECRET_VALUE},
                {"type": "function", "function": {"name": SECRET_VALUE}},
            ],
            "functions": [
                {"name": "legacy_lookup", "parameters": {"description": PROMPT_TEXT}},
            ],
        }
    )

    assert metadata.tool_call_counts == {"function": 3, "web_search": 1}
    assert metadata.function_tool_names == ["legacy_lookup", "lookup_course"]
    payload = json.dumps(
        {
            "tool_call_counts": metadata.tool_call_counts,
            "function_tool_names": metadata.function_tool_names,
        },
        sort_keys=True,
    )
    assert PROMPT_TEXT not in payload
    assert SECRET_VALUE not in payload


def test_invalid_ledger_state_does_not_create_profile() -> None:
    ledger = _ledger(success=False)
    profiles = FakeUsageProfilesRepository()
    service = UsageProfileService(
        usage_ledger_repository=FakeUsageLedgerRepository(ledger),
        usage_profiles_repository=profiles,
    )

    result = asyncio.run(_record(service, ledger))

    assert result is None
    assert profiles.created == []


def test_validate_cost_source_rejects_unknown_values() -> None:
    assert validate_cost_source("mixed") == "mixed"
    with pytest.raises(ValueError):
        validate_cost_source("invoice_grade")


def test_profile_insert_failure_is_logged_safely(monkeypatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    usage_ledger_id = uuid.uuid4()
    warnings: list[tuple[str, dict[str, object]]] = []

    class _Session:
        async def commit(self) -> None:
            raise AssertionError("commit should not run after profile insert failure")

    async def _dummy_db_session():
        yield _Session()

    def _warning(event, **kwargs):
        warnings.append((event, kwargs))

    monkeypatch.setattr(gateway_module, "_get_db_session_after_auth_header_check", _dummy_db_session)
    monkeypatch.setattr(gateway_module.logger, "warning", _warning)

    policy = SimpleNamespace(effective_body={"model": "classroom-cheap", "messages": []})

    asyncio.run(
        gateway_module._record_usage_profile_after_finalization(
            usage_ledger_id=usage_ledger_id,
            route=_route(),
            policy_result=policy,
            authenticated_key=_auth(),
            request=None,
        )
    )

    assert warnings
    event, payload = warnings[0]
    assert event == "usage_profile.record_failed"
    assert payload["reason"] == "profile_insert_failed"
    assert payload["usage_ledger_id"] == str(usage_ledger_id)
    serialized = json.dumps(payload, sort_keys=True)
    assert SECRET_VALUE not in serialized
    assert PROMPT_TEXT not in serialized
    assert COMPLETION_TEXT not in serialized


def test_calibration_usage_profile_metadata_is_safe() -> None:
    import slaif_gateway.services.chat_completion_gateway as gateway_module

    metadata = gateway_module._usage_profile_policy_metadata(
        authenticated_key=_auth(
            key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        ),
        effective_body={
            "model": "gpt-5-search-api",
            "messages": [{"role": "user", "content": PROMPT_TEXT}],
            "web_search_options": {"search_context_size": "low"},
            "tools": [
                {"type": "web_search_preview"},
                {"type": "vendor_unknown_tool"},
            ],
        },
    )

    serialized = json.dumps(metadata, sort_keys=True)
    assert metadata["key_purpose"] == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert "web_search_options" in metadata["observed_hosted_capability_types"]
    assert "vendor_unknown_tool" in metadata["unknown_hosted_capability_types"]
    assert PROMPT_TEXT not in serialized
    assert SECRET_VALUE not in serialized


async def _record(
    service: UsageProfileService,
    ledger,
    *,
    profile_metadata: dict[str, object] | None = None,
):
    return await service.record_from_usage_ledger(
        ledger.id,
        route=_route(),
        tool_metadata=build_chat_completion_tool_metadata(
            {
                "tools": [
                    {"type": "function", "function": {"name": "lookup"}},
                ],
            }
        ),
        profile_metadata=profile_metadata,
    )


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_base_url="https://api.openai.com/v1?ignored=true",
    )


def _auth(
    *,
    key_purpose: str = "standard",
    capability_policy_mode: str = "standard",
) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public",
        status="active",
        valid_from=now,
        valid_until=now,
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        key_purpose=key_purpose,
        capability_policy_mode=capability_policy_mode,
    )


def _ledger(
    *,
    success: bool = True,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    actual_cost_eur: Decimal | None = Decimal("0.000456000"),
    response_metadata: dict[str, object] | None = None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        request_id=f"gw-{uuid.uuid4()}",
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        institution_id=None,
        cohort_id=uuid.uuid4(),
        endpoint="/v1/chat/completions",
        provider="openai",
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        success=success,
        accounting_status="finalized" if success else "failed",
        prompt_tokens=5,
        completion_tokens=6,
        input_tokens=5,
        output_tokens=6,
        total_tokens=11,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        actual_cost_eur=actual_cost_eur,
        response_metadata=response_metadata or {},
        created_at=datetime.now(UTC),
    )
