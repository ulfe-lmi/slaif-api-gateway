"""PostgreSQL qualification evidence for the bounded facial scoring module."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.keys import CreateGatewayKeyInput, RevokeGatewayKeyInput
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse, ProviderUsage
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting import AccountingService
from slaif_gateway.services.auth_service import (
    GatewayAuthService,
    GatewayKeyExpiredError,
    GatewayKeyRevokedError,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    facial_scoring_chat_completion_capabilities,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.quota_errors import (
    ExternalToolFenceActiveError,
    KeyNotReservableError,
    QuotaLimitExceededError,
)
from slaif_gateway.services.quota_service import QuotaService
from slaif_gateway.utils.secrets import generate_secret_key


MODEL = "facial-manipulation-scoring"
PROVIDER = "facial_scoring"
ENDPOINT = "/v1/chat/completions"

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; skipping optional PostgreSQL qualification tests.",
)


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={
            "model": MODEL,
            "messages": [{"role": "user", "content": [{"type": "image_url"}]}],
            "max_completion_tokens": 1,
        },
        requested_output_tokens=1,
        effective_output_tokens=1,
        estimated_input_tokens=4096,
        injected_default_output_tokens=False,
    )


def _route(*, provider_config, route_row) -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model=route_row.requested_model,
        resolved_model=route_row.upstream_model,
        provider=route_row.provider,
        route_id=route_row.id,
        route_match_type=route_row.match_type,
        route_pattern=route_row.requested_model,
        priority=route_row.priority,
        provider_kind=provider_config.kind,
        provider_base_url=provider_config.base_url,
        provider_api_key_env_var=provider_config.api_key_env_var,
        provider_timeout_seconds=provider_config.timeout_seconds,
        provider_max_retries=provider_config.max_retries,
        supports_streaming=route_row.supports_streaming,
        capabilities=route_row.capabilities,
    )


async def _qualification_objects(session: AsyncSession):
    now = datetime.now(UTC).replace(microsecond=0)
    provider_config = await ProviderConfigsRepository(session).create_provider_config(
        provider=PROVIDER,
        display_name="Facial scoring qualification module",
        kind="module",
        base_url="https://facial-module.test",
        api_key_env_var="FACIAL_SCORING_API_KEY",
        timeout_seconds=17,
        max_retries=0,
        notes="mocked qualification metadata only",
    )
    route_row = await ModelRoutesRepository(session).create_model_route(
        requested_model=MODEL,
        provider=PROVIDER,
        upstream_model=MODEL,
        endpoint=ENDPOINT,
        priority=100,
        enabled=True,
        visible_in_models=True,
        supports_streaming=False,
        capabilities={"chat_completions": facial_scoring_chat_completion_capabilities()},
        notes="mocked qualification route only",
    )
    pricing_row = await PricingRulesRepository(session).create_pricing_rule(
        provider=PROVIDER,
        upstream_model=MODEL,
        endpoint=ENDPOINT,
        currency="EUR",
        input_price_per_1m=Decimal("0"),
        output_price_per_1m=Decimal("0"),
        request_price=Decimal("0"),
        valid_from=now - timedelta(minutes=1),
        enabled=True,
        notes="fixed request price for mocked qualification",
    )

    owner = await OwnersRepository(session).create_owner(
        name="Qualification",
        surname="Owner",
        email=f"facial-qualification-{uuid.uuid4().hex}@example.org",
    )
    settings = Settings(
        APP_ENV="test",
        TOKEN_HMAC_SECRET="facial-scoring-qualification-hmac",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
    )
    keys = GatewayKeysRepository(session)
    audit = AuditRepository(session)
    created = await KeyService(
        settings=settings,
        gateway_keys_repository=keys,
        one_time_secrets_repository=OneTimeSecretsRepository(session),
        audit_repository=audit,
    ).create_gateway_key(
        CreateGatewayKeyInput(
            owner_id=owner.id,
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(hours=1),
            cost_limit_eur=Decimal("0.01"),
            token_limit_total=1,
            request_limit_total=2,
            allowed_models=[MODEL],
            allowed_endpoints=[ENDPOINT],
            allowed_providers=[PROVIDER],
            rate_limit_policy={
                "requests_per_minute": 5,
                "tokens_per_minute": 5,
                "max_concurrent_requests": 1,
                "window_seconds": 60,
            },
            note="mocked PostgreSQL qualification",
        )
    )
    gateway_key = await session.get(GatewayKey, created.gateway_key_id)
    assert gateway_key is not None
    return now, settings, provider_config, route_row, pricing_row, created, gateway_key


@pytest.mark.asyncio
async def test_postgres_facial_scoring_fixed_pricing_reservation_accounting_and_release(
    async_test_session: AsyncSession,
) -> None:
    now, settings, provider_config, route_row, pricing_row, created, gateway_key = (
        await _qualification_objects(async_test_session)
    )
    route = _route(provider_config=provider_config, route_row=route_row)
    policy = _policy()
    pricing = PricingService(
        pricing_rules_repository=PricingRulesRepository(async_test_session),
        fx_rates_repository=FxRatesRepository(async_test_session),
    )
    estimate = await pricing.estimate_chat_completion_cost(
        route=route,
        policy=policy,
        endpoint="chat.completions",
        at=now,
    )
    assert estimate.pricing_rule_id == pricing_row.id
    assert estimate.request_price == Decimal("0")
    assert estimate.estimated_input_tokens == 0
    assert estimate.estimated_output_tokens == 0
    assert estimate.estimated_total_cost_eur == Decimal("0")

    keys = GatewayKeysRepository(async_test_session)
    auth_service = GatewayAuthService(settings=settings, gateway_keys_repository=keys)
    authenticated = await auth_service.authenticate_authorization_header(
        f"Bearer {created.plaintext_key}", now=now
    )
    quota = QuotaService(
        gateway_keys_repository=keys,
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    )
    first = await quota.reserve_for_chat_completion(
        authenticated_key=authenticated,
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=f"facial-success-{uuid.uuid4().hex}",
        now=now,
    )
    assert first.reserved_tokens == 0
    assert first.reserved_cost_eur == Decimal("0E-9")
    first_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        first.reservation_id
    )
    assert first_row is not None
    assert first_row.reserved_requests == 1

    finalized = await AccountingService(async_test_session).finalize_successful_response(
        first.reservation_id,
        authenticated,
        route,
        policy,
        estimate,
        ProviderResponse(
            provider=PROVIDER,
            upstream_model=MODEL,
            status_code=200,
            json_body={"status": "scored"},
            usage=ProviderUsage(prompt_tokens=51, completion_tokens=7, total_tokens=58),
        ),
        request_id=first.request_id,
        finished_at=now,
    )
    await async_test_session.refresh(gateway_key)
    ledger = await UsageLedgerRepository(async_test_session).get_usage_record_by_request_id(
        first.request_id
    )
    assert finalized.estimated_cost_eur == Decimal("0")
    assert finalized.actual_cost_eur == Decimal("0E-9")
    assert finalized.total_tokens == 0
    assert gateway_key.cost_used_eur == Decimal("0E-9")
    assert gateway_key.tokens_used_total == 0
    assert gateway_key.requests_used_total == 1
    assert ledger is not None
    assert ledger.total_tokens == 0
    assert ledger.actual_cost_eur == Decimal("0E-9")
    assert ledger.usage_raw == {}

    failed_downstream = await quota.reserve_for_chat_completion(
        authenticated_key=authenticated,
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=f"facial-failed-{uuid.uuid4().hex}",
        now=now,
    )
    released = await quota.release_reservation(failed_downstream.reservation_id, now=now)
    released_row = await QuotaReservationsRepository(async_test_session).get_reservation_by_id(
        released.reservation_id
    )
    await async_test_session.refresh(gateway_key)
    assert released_row is not None
    assert released_row.status == "released"
    assert gateway_key.requests_reserved_total == 0
    assert gateway_key.tokens_reserved_total == 0
    assert gateway_key.cost_reserved_eur == Decimal("0E-9")

    await keys.set_external_tool_fence(
        gateway_key,
        state="active",
        reservation_id=failed_downstream.reservation_id,
        request_id="qualification-fence",
        acquired_at=now,
        expires_at=now + timedelta(minutes=1),
    )
    with pytest.raises(ExternalToolFenceActiveError):
        await quota.reserve_for_chat_completion(
            authenticated_key=authenticated,
            route=route,
            policy=policy,
            cost_estimate=estimate,
            request_id=f"facial-fenced-{uuid.uuid4().hex}",
            now=now,
        )
    await keys.set_external_tool_fence(
        gateway_key,
        state="none",
        reservation_id=None,
        request_id=None,
        acquired_at=None,
        expires_at=None,
    )

    second_success = await quota.reserve_for_chat_completion(
        authenticated_key=authenticated,
        route=route,
        policy=policy,
        cost_estimate=estimate,
        request_id=f"facial-second-{uuid.uuid4().hex}",
        now=now,
    )
    await AccountingService(async_test_session).finalize_successful_response(
        second_success.reservation_id,
        authenticated,
        route,
        policy,
        estimate,
        ProviderResponse(
            provider=PROVIDER,
            upstream_model=MODEL,
            status_code=200,
            json_body={"status": "unscorable"},
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        request_id=second_success.request_id,
        finished_at=now,
    )
    with pytest.raises(QuotaLimitExceededError):
        await quota.reserve_for_chat_completion(
            authenticated_key=authenticated,
            route=route,
            policy=policy,
            cost_estimate=estimate,
            request_id=f"facial-over-limit-{uuid.uuid4().hex}",
            now=now,
        )


@pytest.mark.asyncio
async def test_postgres_facial_scoring_revocation_expiry_and_audit_boundaries(
    async_test_session: AsyncSession,
) -> None:
    now, settings, provider_config, route_row, _, created, gateway_key = (
        await _qualification_objects(async_test_session)
    )
    route = _route(provider_config=provider_config, route_row=route_row)
    policy = _policy()
    estimate = ChatCostEstimate(
        provider=PROVIDER,
        requested_model=MODEL,
        resolved_model=MODEL,
        native_currency="EUR",
        estimated_input_tokens=0,
        estimated_output_tokens=0,
        estimated_input_cost_native=Decimal("0"),
        estimated_output_cost_native=Decimal("0"),
        estimated_total_cost_native=Decimal("0"),
        estimated_total_cost_eur=Decimal("0"),
        pricing_rule_id=None,
        fx_rate_id=None,
        request_price=Decimal("0"),
    )
    keys = GatewayKeysRepository(async_test_session)
    auth_service = GatewayAuthService(settings=settings, gateway_keys_repository=keys)
    authenticated = await auth_service.authenticate_authorization_header(
        f"Bearer {created.plaintext_key}", now=now
    )
    quota = QuotaService(
        gateway_keys_repository=keys,
        quota_reservations_repository=QuotaReservationsRepository(async_test_session),
    )

    await KeyService(
        settings=settings,
        gateway_keys_repository=keys,
        one_time_secrets_repository=OneTimeSecretsRepository(async_test_session),
        audit_repository=AuditRepository(async_test_session),
    ).revoke_gateway_key(
        RevokeGatewayKeyInput(
            gateway_key_id=created.gateway_key_id,
            reason="qualification revocation boundary",
        )
    )
    with pytest.raises(GatewayKeyRevokedError):
        await auth_service.authenticate_authorization_header(
            f"Bearer {created.plaintext_key}", now=now
        )
    with pytest.raises(KeyNotReservableError):
        await quota.reserve_for_chat_completion(
            authenticated_key=authenticated,
            route=route,
            policy=policy,
            cost_estimate=estimate,
            request_id=f"facial-revoked-{uuid.uuid4().hex}",
            now=now,
        )

    await keys.update_gateway_key_status(
        gateway_key.id,
        status="active",
        revoked_at=None,
        revoked_reason=None,
    )
    await keys.update_gateway_key_validity(
        gateway_key.id,
        valid_until=now - timedelta(seconds=1),
    )
    with pytest.raises(GatewayKeyExpiredError):
        await auth_service.authenticate_authorization_header(
            f"Bearer {created.plaintext_key}", now=now
        )
    with pytest.raises(KeyNotReservableError):
        await quota.reserve_for_chat_completion(
            authenticated_key=authenticated,
            route=route,
            policy=policy,
            cost_estimate=estimate,
            request_id=f"facial-expired-{uuid.uuid4().hex}",
            now=now,
        )

    audits = await AuditRepository(async_test_session).list_audit_logs(entity_type="gateway_key")
    actions = {row.action for row in audits}
    assert "gateway_key_created" in actions
    assert "revoke_key" in actions
    audit_text = " ".join(str(row.new_values or {}) for row in audits)
    assert created.plaintext_key not in audit_text
    assert "FACIAL_SCORING_API_KEY" not in audit_text
