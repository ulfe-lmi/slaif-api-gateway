"""PostgreSQL-backed integration tests for routing/pricing metadata CLI commands."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.db.models import FxRate, ModelRoute, PricingRule, ProviderConfig
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.services.model_catalog import ModelCatalogService
from slaif_gateway.services.pricing import PricingService
from slaif_gateway.services.pricing_errors import FxRateNotFoundError, PricingRuleNotFoundError
from slaif_gateway.services.route_resolution import RouteResolutionService
from slaif_gateway.services.routing_errors import ModelRouteDisabledError, ProviderDisabledError
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for routing/pricing CLI PostgreSQL integration tests",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-routing-pricing-cli-integration-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-routing-pricing-cli-integration-123456"
TEST_OPENAI_SECRET_VALUE = "sk-test-openai-provider-secret-value"
TEST_OPENROUTER_SECRET_VALUE = "sk-or-test-openrouter-provider-secret-value"
TEST_GATEWAY_KEY_VALUE = "sk-slaif-testgatewaysecret"
FORBIDDEN_OUTPUT_MARKERS = (
    TEST_OPENAI_SECRET_VALUE,
    TEST_OPENROUTER_SECRET_VALUE,
    TEST_GATEWAY_KEY_VALUE,
    "token_hash",
    "encrypted_payload",
    "nonce",
    "password_hash",
)


@pytest.fixture(scope="session")
def cli_metadata_postgres_url() -> str:
    database_url = os.environ["TEST_DATABASE_URL"]
    run_alembic_upgrade_head(database_url)
    return database_url


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, cli_metadata_postgres_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", cli_metadata_postgres_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", TEST_OPENAI_SECRET_VALUE)
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_OPENROUTER_SECRET_VALUE)

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    return cli_metadata_postgres_url


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(coro):
    return asyncio.run(coro)


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _load_json(output: str) -> dict[str, Any]:
    return json.loads(output)


def _assert_safe_output(output: str) -> None:
    lowered = output.lower()
    for marker in FORBIDDEN_OUTPUT_MARKERS:
        assert marker.lower() not in lowered


def _invoke_ok(runner: CliRunner, args: list[str]) -> dict[str, Any]:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    _assert_safe_output(result.output)
    if "--json" in args:
        return _load_json(result.stdout)
    return {}


def _invoke_fail(runner: CliRunner, args: list[str]) -> str:
    result = runner.invoke(app, args)
    assert result.exit_code != 0, result.output
    _assert_safe_output(result.output)
    return result.output


async def _with_session(database_url: str) -> AsyncSession:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    session.info["_integration_engine"] = engine
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session.info["_integration_engine"]
    await session.close()
    await engine.dispose()


async def _get_provider(database_url: str, provider: str) -> ProviderConfig:
    session = await _with_session(database_url)
    try:
        row = (
            await session.execute(select(ProviderConfig).where(ProviderConfig.provider == provider))
        ).scalar_one()
        return row
    finally:
        await _close_session(session)


async def _get_route(database_url: str, route_id: str) -> ModelRoute:
    session = await _with_session(database_url)
    try:
        row = await session.get(ModelRoute, uuid.UUID(route_id))
        assert row is not None
        return row
    finally:
        await _close_session(session)


async def _get_pricing_rule(database_url: str, pricing_rule_id: str) -> PricingRule:
    session = await _with_session(database_url)
    try:
        row = await session.get(PricingRule, uuid.UUID(pricing_rule_id))
        assert row is not None
        return row
    finally:
        await _close_session(session)


async def _get_fx_rate(database_url: str, fx_rate_id: str) -> FxRate:
    session = await _with_session(database_url)
    try:
        row = await session.get(FxRate, uuid.UUID(fx_rate_id))
        assert row is not None
        return row
    finally:
        await _close_session(session)


async def _count_pricing_rows(database_url: str, *, provider: str, model: str) -> int:
    session = await _with_session(database_url)
    try:
        statement = (
            select(func.count())
            .select_from(PricingRule)
            .where(PricingRule.provider == provider, PricingRule.upstream_model == model)
        )
        return int((await session.execute(statement)).scalar_one())
    finally:
        await _close_session(session)


def _ensure_provider(
    runner: CliRunner,
    *,
    provider: str,
    api_key_env_var: str,
) -> dict[str, Any]:
    result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "--provider",
            provider,
            "--api-key-env-var",
            api_key_env_var,
            "--json",
        ],
    )
    _assert_safe_output(result.output)
    if result.exit_code == 0:
        return _load_json(result.stdout)

    assert "duplicate" in result.output.lower() or "already exists" in result.output.lower()
    return _invoke_ok(runner, ["providers", "show", provider, "--json"])


def _disable_existing_routes(runner: CliRunner, requested_model: str) -> None:
    payload = _invoke_ok(runner, ["routes", "list", "--json", "--limit", "1000"])
    for row in payload["routes"]:
        if row["requested_model"] == requested_model and row["enabled"] is True:
            _invoke_ok(runner, ["routes", "disable", str(row["id"]), "--json"])


def _auth_key() -> AuthenticatedGatewayKey:
    now = datetime.now(UTC) - timedelta(minutes=1)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={
            "requests_per_minute": None,
            "tokens_per_minute": None,
            "max_concurrent_requests": None,
        },
    )


def _policy() -> ChatCompletionPolicyResult:
    return ChatCompletionPolicyResult(
        effective_body={"model": "gpt-test-mini", "messages": [{"role": "user", "content": "hi"}]},
        requested_output_tokens=2000,
        effective_output_tokens=2000,
        estimated_input_tokens=1000,
        injected_default_output_tokens=False,
    )


async def _list_visible_model_ids(database_url: str) -> list[str]:
    session = await _with_session(database_url)
    try:
        service = ModelCatalogService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        models = await service.list_visible_models(_auth_key())
        return [model.id for model in models]
    finally:
        await _close_session(session)


async def _resolve_model(database_url: str, model: str):
    session = await _with_session(database_url)
    try:
        service = RouteResolutionService(
            model_routes_repository=ModelRoutesRepository(session),
            provider_configs_repository=ProviderConfigsRepository(session),
        )
        return await service.resolve_model(model, _auth_key())
    finally:
        await _close_session(session)


async def _pricing_service_checks(database_url: str, *, usd_model: str) -> None:
    at = datetime.now(UTC)
    session = await _with_session(database_url)
    try:
        service = PricingService(
            pricing_rules_repository=PricingRulesRepository(session),
            fx_rates_repository=FxRatesRepository(session),
        )

        openai = await service.find_active_pricing_rule(
            provider="openai",
            model="gpt-test-mini",
            endpoint="chat.completions",
            at=at,
        )
        assert openai.currency == "EUR"
        assert openai.input_price_per_1m == Decimal("0.100000000")

        openrouter = await service.find_active_pricing_rule(
            provider="openrouter",
            model="anthropic/claude-test",
            endpoint="chat.completions",
            at=at,
        )
        assert openrouter.currency == "EUR"
        assert openrouter.output_price_per_1m == Decimal("0.700000000")

        usd = await service.find_active_pricing_rule(
            provider="openai",
            model=usd_model,
            endpoint="chat.completions",
            at=at,
        )
        assert usd.currency == "USD"

        converted, fx = await service.convert_to_eur(Decimal("2.500000000"), "USD", at=at)
        assert converted == Decimal("2.300000000000000000")
        assert fx.rate == Decimal("0.920000000")

        route = await _resolve_model(database_url, "gpt-test-mini")
        estimate = await service.estimate_chat_completion_cost(
            route=route,
            policy=_policy(),
            at=at,
        )
        assert estimate.estimated_total_cost_eur == Decimal("0.001300000000")

        with pytest.raises(PricingRuleNotFoundError):
            await service.find_active_pricing_rule(
                provider="openai",
                model="missing-pricing-model",
                endpoint="chat.completions",
                at=at,
            )
        with pytest.raises(FxRateNotFoundError):
            await service.convert_to_eur(Decimal("1"), "GBP", at=at)
    finally:
        await _close_session(session)


def test_provider_cli_commands_persist_and_are_safe(
    runner: CliRunner,
    cli_env: str,
) -> None:
    openai = _ensure_provider(
        runner,
        provider="openai",
        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
    )
    openrouter = _ensure_provider(
        runner,
        provider="openrouter",
        api_key_env_var="OPENROUTER_API_KEY",
    )

    assert openai["api_key_env_var"] == "OPENAI_UPSTREAM_API_KEY"
    assert openrouter["api_key_env_var"] == "OPENROUTER_API_KEY"

    openai_row = _run(_get_provider(cli_env, "openai"))
    openrouter_row = _run(_get_provider(cli_env, "openrouter"))
    assert openai_row.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert openrouter_row.api_key_env_var == "OPENROUTER_API_KEY"

    listed = _invoke_ok(runner, ["providers", "list", "--json", "--limit", "100"])
    assert {"openai", "openrouter"}.issubset({row["provider"] for row in listed["providers"]})

    shown_by_name = _invoke_ok(runner, ["providers", "show", "openai", "--json"])
    shown_by_id = _invoke_ok(runner, ["providers", "show", str(shown_by_name["id"]), "--json"])
    assert shown_by_id["provider"] == "openai"

    disabled = _invoke_ok(runner, ["providers", "disable", "openai", "--json"])
    assert disabled["enabled"] is False
    assert _run(_get_provider(cli_env, "openai")).enabled is False

    enabled = _invoke_ok(runner, ["providers", "enable", "openai", "--json"])
    assert enabled["enabled"] is True
    assert _run(_get_provider(cli_env, "openai")).enabled is True

    duplicate_output = _invoke_fail(
        runner,
        [
            "providers",
            "add",
            "--provider",
            "openai",
            "--api-key-env-var",
            "OPENAI_UPSTREAM_API_KEY",
        ],
    )
    assert "duplicate" in duplicate_output.lower() or "already exists" in duplicate_output.lower()

    secret_provider = _unique_label("secret-provider")
    _invoke_fail(
        runner,
        [
            "providers",
            "add",
            "--provider",
            secret_provider,
            "--base-url",
            "https://provider.example/v1",
            "--api-key-env-var",
            TEST_OPENAI_SECRET_VALUE,
        ],
    )


def test_route_cli_commands_persist_and_are_safe(
    runner: CliRunner,
    cli_env: str,
) -> None:
    _ensure_provider(runner, provider="openai", api_key_env_var="OPENAI_UPSTREAM_API_KEY")
    _ensure_provider(runner, provider="openrouter", api_key_env_var="OPENROUTER_API_KEY")
    _invoke_ok(runner, ["providers", "enable", "openai", "--json"])
    _invoke_ok(runner, ["providers", "enable", "openrouter", "--json"])

    exact_route = _invoke_ok(
        runner,
        [
            "routes",
            "add",
            "--requested-model",
            "gpt-test-mini",
            "--match-type",
            "exact",
            "--provider",
            "openai",
            "--upstream-model",
            "gpt-test-mini",
            "--priority",
            "10",
            "--visible",
            "--enabled",
            "--json",
        ],
    )
    glob_route = _invoke_ok(
        runner,
        [
            "routes",
            "add",
            "--pattern",
            "anthropic/*",
            "--match-type",
            "glob",
            "--provider",
            "openrouter",
            "--upstream-model",
            "anthropic/claude-test",
            "--priority",
            "20",
            "--visible",
            "--enabled",
            "--json",
        ],
    )

    assert _run(_get_route(cli_env, exact_route["id"])).requested_model == "gpt-test-mini"
    assert _run(_get_route(cli_env, glob_route["id"])).match_type == "glob"

    listed = _invoke_ok(runner, ["routes", "list", "--json", "--limit", "200"])
    listed_ids = {row["id"] for row in listed["routes"]}
    assert exact_route["id"] in listed_ids
    assert glob_route["id"] in listed_ids

    shown = _invoke_ok(runner, ["routes", "show", str(exact_route["id"]), "--json"])
    assert shown["provider"] == "openai"

    disabled = _invoke_ok(runner, ["routes", "disable", str(exact_route["id"]), "--json"])
    assert disabled["enabled"] is False
    assert _run(_get_route(cli_env, exact_route["id"])).enabled is False

    enabled = _invoke_ok(runner, ["routes", "enable", str(exact_route["id"]), "--json"])
    assert enabled["enabled"] is True
    assert _run(_get_route(cli_env, exact_route["id"])).enabled is True

    _invoke_fail(
        runner,
        [
            "routes",
            "add",
            "--requested-model",
            _unique_label("bad-route"),
            "--match-type",
            "regex",
            "--provider",
            "openai",
            "--upstream-model",
            "gpt-test-mini",
        ],
    )
    _invoke_fail(runner, ["routes", "show", "not-a-uuid"])

    _invoke_ok(runner, ["routes", "disable", str(exact_route["id"]), "--json"])
    _invoke_ok(runner, ["routes", "disable", str(glob_route["id"]), "--json"])


def test_pricing_cli_commands_and_import_persist_and_are_safe(
    runner: CliRunner,
    cli_env: str,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC) - timedelta(minutes=1)
    openai_valid_from = now.isoformat()
    openrouter_valid_from = (now + timedelta(seconds=1)).isoformat()
    usd_model = _unique_label("gpt-test-usd")
    import_model = _unique_label("gpt-imported")
    dry_run_model = _unique_label("gpt-dry-run")

    openai_rule = _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--endpoint",
            "chat.completions",
            "--currency",
            "EUR",
            "--input-price-per-1m",
            "0.100000000",
            "--output-price-per-1m",
            "0.600000000",
            "--valid-from",
            openai_valid_from,
            "--source-url",
            "https://pricing.example.local/openai",
            "--json",
        ],
    )
    openrouter_rule = _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openrouter",
            "--model",
            "anthropic/claude-test",
            "--endpoint",
            "chat.completions",
            "--currency",
            "EUR",
            "--input-price-per-1m",
            "0.300000000",
            "--output-price-per-1m",
            "0.700000000",
            "--valid-from",
            openrouter_valid_from,
            "--json",
        ],
    )
    usd_rule = _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            usd_model,
            "--endpoint",
            "chat.completions",
            "--currency",
            "USD",
            "--input-price-per-1m",
            "1.000000000",
            "--output-price-per-1m",
            "2.000000000",
            "--valid-from",
            (now + timedelta(seconds=2)).isoformat(),
            "--json",
        ],
    )

    assert openai_rule["input_price_per_1m"] == "0.100000000"
    assert openrouter_rule["output_price_per_1m"] == "0.700000000"
    assert usd_rule["currency"] == "USD"
    assert _run(_get_pricing_rule(cli_env, openai_rule["id"])).input_price_per_1m == Decimal(
        "0.100000000"
    )

    listed = _invoke_ok(runner, ["pricing", "list", "--provider", "openai", "--json", "--limit", "200"])
    assert openai_rule["id"] in {row["id"] for row in listed["pricing_rules"]}

    shown = _invoke_ok(runner, ["pricing", "show", str(openai_rule["id"]), "--json"])
    assert shown["model"] == "gpt-test-mini"
    assert shown["output_price_per_1m"] == "0.600000000"

    disabled = _invoke_ok(
        runner,
        [
            "pricing",
            "disable-model",
            "--provider",
            "openrouter",
            "--model",
            "anthropic/claude-test",
            "--endpoint",
            "chat.completions",
            "--json",
        ],
    )
    assert disabled["disabled_count"] >= 1
    assert _run(_get_pricing_rule(cli_env, openrouter_rule["id"])).enabled is False

    reenabled_rule = _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openrouter",
            "--model",
            "anthropic/claude-test",
            "--endpoint",
            "chat.completions",
            "--currency",
            "EUR",
            "--input-price-per-1m",
            "0.300000000",
            "--output-price-per-1m",
            "0.700000000",
            "--valid-from",
            (now + timedelta(seconds=3)).isoformat(),
            "--json",
        ],
    )
    assert reenabled_rule["enabled"] is True

    _invoke_fail(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            _unique_label("negative-price"),
            "--input-price-per-1m",
            "-0.1",
            "--output-price-per-1m",
            "0.2",
        ],
    )
    _invoke_fail(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            _unique_label("bad-validity"),
            "--input-price-per-1m",
            "0.1",
            "--output-price-per-1m",
            "0.2",
            "--valid-from",
            "2026-01-02T00:00:00Z",
            "--valid-until",
            "2026-01-01T00:00:00Z",
        ],
    )
    _invoke_fail(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            _unique_label("bad-decimal"),
            "--input-price-per-1m",
            "not-decimal",
            "--output-price-per-1m",
            "0.2",
        ],
    )
    _invoke_fail(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--input-price-per-1m",
            "0.100000000",
            "--output-price-per-1m",
            "0.600000000",
            "--valid-from",
            openai_valid_from,
        ],
    )

    import_file = tmp_path / "pricing-import.json"
    import_file.write_text(
        json.dumps(
            [
                {
                    "provider": "openai",
                    "model": import_model,
                    "endpoint": "chat.completions",
                    "currency": "EUR",
                    "input_price_per_1m": "0.110000000",
                    "output_price_per_1m": "0.220000000",
                    "valid_from": (now + timedelta(seconds=4)).isoformat(),
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    imported = _invoke_ok(runner, ["pricing", "import", "--file", str(import_file), "--json"])
    assert imported["imported_count"] == 1
    assert _run(_count_pricing_rows(cli_env, provider="openai", model=import_model)) == 1

    dry_run_file = tmp_path / "pricing-dry-run.json"
    dry_run_file.write_text(
        json.dumps(
            [
                {
                    "provider": "openai",
                    "model": dry_run_model,
                    "endpoint": "chat.completions",
                    "currency": "EUR",
                    "input_price_per_1m": "0.120000000",
                    "output_price_per_1m": "0.240000000",
                    "valid_from": (now + timedelta(seconds=5)).isoformat(),
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    dry_run = _invoke_ok(
        runner,
        ["pricing", "import", "--file", str(dry_run_file), "--dry-run", "--json"],
    )
    assert dry_run["dry_run"] is True
    assert dry_run["imported_count"] == 0
    assert _run(_count_pricing_rows(cli_env, provider="openai", model=dry_run_model)) == 0

    invalid_file = tmp_path / "pricing-invalid.json"
    invalid_file.write_text(
        json.dumps(
            [
                {
                    "provider": "openai",
                    "model": _unique_label("invalid-import"),
                    "input_price_per_1m": "not-decimal",
                    "output_price_per_1m": "0.200000000",
                    "unknown_field": "rejected",
                }
            ]
        ),
        encoding="utf-8",
    )
    _invoke_fail(runner, ["pricing", "import", "--file", str(invalid_file)])


def test_fx_cli_commands_persist_and_are_safe(
    runner: CliRunner,
    cli_env: str,
) -> None:
    valid_from = datetime.now(UTC).isoformat()
    created = _invoke_ok(
        runner,
        [
            "fx",
            "add",
            "--base-currency",
            "USD",
            "--quote-currency",
            "EUR",
            "--rate",
            "0.920000000",
            "--valid-from",
            valid_from,
            "--source",
            "integration-test",
            "--json",
        ],
    )
    assert created["rate"] == "0.920000000"
    assert _run(_get_fx_rate(cli_env, created["id"])).rate == Decimal("0.920000000")

    listed = _invoke_ok(
        runner,
        ["fx", "list", "--base-currency", "USD", "--quote-currency", "EUR", "--json"],
    )
    assert created["id"] in {row["id"] for row in listed["fx_rates"]}

    latest = _invoke_ok(
        runner,
        ["fx", "latest", "--base-currency", "USD", "--quote-currency", "EUR", "--json"],
    )
    assert latest["id"] == created["id"]
    assert latest["rate"] == "0.920000000"

    _invoke_fail(
        runner,
        ["fx", "add", "--base-currency", "USD", "--quote-currency", "EUR", "--rate", "0"],
    )
    _invoke_fail(
        runner,
        ["fx", "add", "--base-currency", "USD", "--quote-currency", "EUR", "--rate", "-0.1"],
    )
    _invoke_fail(
        runner,
        [
            "fx",
            "add",
            "--base-currency",
            "USD",
            "--quote-currency",
            "EUR",
            "--rate",
            "not-decimal",
        ],
    )
    _invoke_fail(
        runner,
        [
            "fx",
            "add",
            "--base-currency",
            "USD",
            "--quote-currency",
            "EUR",
            "--rate",
            "0.9",
            "--valid-from",
            "not-a-date",
        ],
    )


def test_persisted_rows_support_catalog_routing_and_pricing_services(
    runner: CliRunner,
    cli_env: str,
) -> None:
    _ensure_provider(runner, provider="openai", api_key_env_var="OPENAI_UPSTREAM_API_KEY")
    _ensure_provider(runner, provider="openrouter", api_key_env_var="OPENROUTER_API_KEY")
    _invoke_ok(runner, ["providers", "enable", "openai", "--json"])
    _invoke_ok(runner, ["providers", "enable", "openrouter", "--json"])

    now = datetime.now(UTC) - timedelta(minutes=1)
    _disable_existing_routes(runner, "gpt-test-mini")
    exact_route = _invoke_ok(
        runner,
        [
            "routes",
            "add",
            "--requested-model",
            "gpt-test-mini",
            "--match-type",
            "exact",
            "--provider",
            "openai",
            "--upstream-model",
            "gpt-test-mini",
            "--priority",
            "5",
            "--visible",
            "--enabled",
            "--json",
        ],
    )
    glob_route = _invoke_ok(
        runner,
        [
            "routes",
            "add",
            "--pattern",
            "anthropic/*",
            "--match-type",
            "glob",
            "--provider",
            "openrouter",
            "--upstream-model",
            "anthropic/claude-test",
            "--priority",
            "15",
            "--visible",
            "--enabled",
            "--json",
        ],
    )
    usd_model = _unique_label("gpt-service-usd")
    _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--endpoint",
            "chat.completions",
            "--currency",
            "EUR",
            "--input-price-per-1m",
            "0.100000000",
            "--output-price-per-1m",
            "0.600000000",
            "--valid-from",
            now.isoformat(),
            "--json",
        ],
    )
    _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openrouter",
            "--model",
            "anthropic/claude-test",
            "--endpoint",
            "chat.completions",
            "--currency",
            "EUR",
            "--input-price-per-1m",
            "0.300000000",
            "--output-price-per-1m",
            "0.700000000",
            "--valid-from",
            (now + timedelta(seconds=1)).isoformat(),
            "--json",
        ],
    )
    _invoke_ok(
        runner,
        [
            "pricing",
            "add",
            "--provider",
            "openai",
            "--model",
            usd_model,
            "--endpoint",
            "chat.completions",
            "--currency",
            "USD",
            "--input-price-per-1m",
            "1.000000000",
            "--output-price-per-1m",
            "2.000000000",
            "--valid-from",
            (now + timedelta(seconds=2)).isoformat(),
            "--json",
        ],
    )
    _invoke_ok(
        runner,
        [
            "fx",
            "add",
            "--base-currency",
            "USD",
            "--quote-currency",
            "EUR",
            "--rate",
            "0.920000000",
            "--valid-from",
            now.isoformat(),
            "--source",
            "integration-test",
            "--json",
        ],
    )

    visible = _run(_list_visible_model_ids(cli_env))
    assert "gpt-test-mini" in visible
    assert "anthropic/*" in visible

    openai_route = _run(_resolve_model(cli_env, "gpt-test-mini"))
    assert openai_route.provider == "openai"
    assert openai_route.resolved_model == "gpt-test-mini"

    openrouter_route = _run(_resolve_model(cli_env, "anthropic/claude-test"))
    assert openrouter_route.provider == "openrouter"
    assert openrouter_route.resolved_model == "anthropic/claude-test"

    _invoke_ok(runner, ["routes", "disable", str(exact_route["id"]), "--json"])
    visible_without_route = _run(_list_visible_model_ids(cli_env))
    assert "gpt-test-mini" not in visible_without_route
    with pytest.raises(ModelRouteDisabledError):
        _run(_resolve_model(cli_env, "gpt-test-mini"))
    _invoke_ok(runner, ["routes", "enable", str(exact_route["id"]), "--json"])

    _invoke_ok(runner, ["providers", "disable", "openrouter", "--json"])
    visible_without_provider = _run(_list_visible_model_ids(cli_env))
    assert "anthropic/*" not in visible_without_provider
    with pytest.raises(ProviderDisabledError):
        _run(_resolve_model(cli_env, "anthropic/claude-test"))
    _invoke_ok(runner, ["providers", "enable", "openrouter", "--json"])
    _invoke_ok(runner, ["routes", "enable", str(glob_route["id"]), "--json"])

    _run(_pricing_service_checks(cli_env, usd_model=usd_model))


def test_cli_failures_are_safe_for_missing_database_url(
    runner: CliRunner,
    cli_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = cli_env
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    output = _invoke_fail(runner, ["providers", "list"])
    assert "DATABASE_URL is not configured" in output
