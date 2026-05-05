from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import bootstrap as bootstrap_cli
from slaif_gateway.cli.main import app
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.model_catalog import ModelCatalogService
from slaif_gateway.services.openai_completions_catalog import (
    OPENAI_PROVIDER,
    BootstrapRowStatus,
    OpenAICompletionsBootstrapResult,
    _PricingInput,
    bootstrap_openai_completions_catalog,
    load_openai_chat_completions_catalog,
    load_pricing_file,
)

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PRICING_CSV = REPO_ROOT / "docs" / "examples" / "openai-completions-pricing.example.csv"


@dataclass
class _Store:
    providers: dict[str, SimpleNamespace] = field(default_factory=dict)
    routes: list[SimpleNamespace] = field(default_factory=list)
    pricing: list[SimpleNamespace] = field(default_factory=list)
    audit_rows: list[dict[str, object]] = field(default_factory=list)


class _ProviderRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def get_provider_config_by_provider(self, provider: str):
        return self.store.providers.get(provider)

    async def create_provider_config(self, **kwargs):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **kwargs,
        )
        self.store.providers[row.provider] = row
        return row

    async def list_provider_configs(self, *, enabled=None, limit=100, offset=0):
        _ = (limit, offset)
        rows = list(self.store.providers.values())
        if enabled is not None:
            rows = [row for row in rows if row.enabled == enabled]
        return rows


class _RouteRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def list_model_routes(self, *, endpoint=None, provider=None, limit=100, offset=0):
        _ = (limit, offset)
        rows = self.store.routes
        if endpoint is not None:
            rows = [row for row in rows if row.endpoint == endpoint]
        if provider is not None:
            rows = [row for row in rows if row.provider == provider]
        return rows

    async def list_visible_model_routes(self, *, endpoint=None):
        rows = [
            row for row in self.store.routes if row.enabled is True and row.visible_in_models is True
        ]
        if endpoint is not None:
            rows = [row for row in rows if row.endpoint == endpoint]
        return rows

    async def create_model_route(self, **kwargs):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **kwargs,
        )
        self.store.routes.append(row)
        return row


class _PricingRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def list_pricing_rules(self, *, provider=None, upstream_model=None, endpoint=None, limit=100, offset=0):
        _ = (limit, offset)
        rows = self.store.pricing
        if provider is not None:
            rows = [row for row in rows if row.provider == provider]
        if upstream_model is not None:
            rows = [row for row in rows if row.upstream_model == upstream_model]
        if endpoint is not None:
            rows = [row for row in rows if row.endpoint == endpoint]
        return rows

    async def create_pricing_rule(self, **kwargs):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **kwargs,
        )
        self.store.pricing.append(row)
        return row


class _AuditRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def add_audit_log(self, **kwargs):
        self.store.audit_rows.append(kwargs)


def _pricing_rows(*, include_legacy_models: bool = False) -> dict[tuple[str, str, str], _PricingInput]:
    rows: dict[tuple[str, str, str], _PricingInput] = {}
    for entry in load_openai_chat_completions_catalog(include_legacy_models=include_legacy_models):
        rows[(OPENAI_PROVIDER, entry.upstream_model, entry.normalized_endpoint)] = _PricingInput(
            provider=OPENAI_PROVIDER,
            model=entry.upstream_model,
            endpoint=entry.normalized_endpoint,
            currency="EUR",
            input_price_per_1m=Decimal("0.10"),
            output_price_per_1m=Decimal("0.20"),
        )
    return rows


async def _run_bootstrap(
    store: _Store,
    *,
    dry_run: bool,
    pricing_mode: str = "require-file",
    pricing_rows: dict[tuple[str, str, str], _PricingInput] | None = None,
    include_legacy_models: bool = False,
) -> OpenAICompletionsBootstrapResult:
    return await bootstrap_openai_completions_catalog(
        provider_configs_repository=_ProviderRepo(store),
        model_routes_repository=_RouteRepo(store),
        pricing_rules_repository=_PricingRepo(store),
        audit_repository=_AuditRepo(store),
        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
        currency="EUR",
        pricing_mode=pricing_mode,  # type: ignore[arg-type]
        pricing_file_rows=pricing_rows if pricing_rows is not None else _pricing_rows(),
        include_legacy_completions=False,
        include_legacy_models=include_legacy_models,
        dry_run=dry_run,
    )


@pytest.mark.asyncio
async def test_dry_run_reports_provider_routes_and_pricing_without_mutation() -> None:
    store = _Store()

    result = await _run_bootstrap(store, dry_run=True)

    assert result.dry_run is True
    assert result.provider.status == "created"
    assert {row.status for row in result.chat_routes} == {"created"}
    assert {row.status for row in result.pricing} == {"created"}
    assert store.providers == {}
    assert store.routes == []
    assert store.pricing == []


@pytest.mark.asyncio
async def test_apply_creates_provider_exact_chat_routes_and_pricing_for_catalog_models() -> None:
    store = _Store()
    catalog = load_openai_chat_completions_catalog(include_legacy_models=False)

    result = await _run_bootstrap(store, dry_run=False)

    assert result.has_blockers is False
    assert store.providers["openai"].api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert len(store.routes) == len(catalog)
    assert all(row.match_type == "exact" for row in store.routes)
    assert all(row.endpoint == "/v1/chat/completions" for row in store.routes)
    assert {row.requested_model for row in store.routes} == {entry.model_id for entry in catalog}
    assert len(store.pricing) == len(catalog)
    assert all(row.currency == "EUR" for row in store.pricing)


@pytest.mark.asyncio
async def test_apply_twice_is_idempotent() -> None:
    store = _Store()

    first = await _run_bootstrap(store, dry_run=False)
    second = await _run_bootstrap(store, dry_run=False)

    assert first.has_blockers is False
    assert second.provider.status == "exists"
    assert {row.status for row in second.chat_routes} == {"exists"}
    assert {row.status for row in second.pricing} == {"exists"}
    assert len(store.providers) == 1
    assert len(store.routes) == len(second.chat_routes)
    assert len(store.pricing) == len(second.pricing)


def test_missing_pricing_file_in_require_file_mode_fails_safely(tmp_path) -> None:
    missing = tmp_path / "missing.csv"

    result = runner.invoke(
        app,
        [
            "bootstrap",
            "openai-completions-catalog",
            "--pricing-file",
            str(missing),
        ],
    )

    assert result.exit_code != 0
    assert "pricing-file" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.asyncio
async def test_pricing_file_missing_catalog_model_blocks_without_mutation(tmp_path) -> None:
    catalog = load_openai_chat_completions_catalog(include_legacy_models=False)
    csv_path = tmp_path / "pricing.csv"
    first = catalog[0]
    csv_path.write_text(
        "provider,model,endpoint,currency,input_price_per_1m,output_price_per_1m\n"
        f"openai,{first.upstream_model},chat.completions,EUR,0.10,0.20\n",
        encoding="utf-8",
    )
    store = _Store()

    result = await _run_bootstrap(
        store,
        dry_run=False,
        pricing_rows=load_pricing_file(csv_path, currency="EUR"),
    )

    assert result.has_blockers is True
    assert any(row.status == "missing" for row in result.pricing)
    assert store.providers == {}
    assert store.routes == []
    assert store.pricing == []


def test_placeholder_mode_without_confirmation_fails_safely() -> None:
    result = runner.invoke(
        app,
        [
            "bootstrap",
            "openai-completions-catalog",
            "--pricing-mode",
            "placeholder",
        ],
    )

    assert result.exit_code != 0
    assert "confirm-placeholder-pricing" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.asyncio
async def test_placeholder_mode_with_confirmation_creates_marked_placeholder_pricing() -> None:
    store = _Store()

    result = await _run_bootstrap(
        store,
        dry_run=False,
        pricing_mode="placeholder",
        pricing_rows={},
    )

    assert result.placeholder_pricing is True
    assert store.pricing
    assert all(row.pricing_metadata["placeholder"] is True for row in store.pricing)
    assert all("not real" in row.notes for row in store.pricing)


@pytest.mark.asyncio
async def test_provider_config_stores_api_key_env_var_only_not_provider_key_value() -> None:
    store = _Store()

    await _run_bootstrap(store, dry_run=False)

    provider = store.providers["openai"]
    assert provider.api_key_env_var == "OPENAI_UPSTREAM_API_KEY"
    assert not provider.api_key_env_var.startswith("sk-")


def test_command_output_does_not_contain_provider_key_env_value(monkeypatch) -> None:
    async def fake_bootstrap(**kwargs):
        assert kwargs["api_key_env_var"] == "OPENAI_UPSTREAM_API_KEY"
        return OpenAICompletionsBootstrapResult(
            dry_run=True,
            provider=BootstrapRowStatus(status="exists", message="ok"),
            chat_routes=(BootstrapRowStatus(status="exists", model_id="gpt-4o-mini"),),
            completions_routes=(
                BootstrapRowStatus(status="not_implemented", endpoint="/v1/completions"),
            ),
            pricing=(BootstrapRowStatus(status="exists", model_id="gpt-4o-mini"),),
            selected_models=("gpt-4o-mini",),
            placeholder_pricing=False,
        )

    monkeypatch.setattr(bootstrap_cli, "_bootstrap_openai_completions_catalog", fake_bootstrap)

    result = runner.invoke(
        app,
        [
            "bootstrap",
            "openai-completions-catalog",
            "--pricing-file",
            "unused.csv",
        ],
        env={"OPENAI_UPSTREAM_API_KEY": "provider-secret-value-not-printed"},
    )

    assert result.exit_code == 0
    assert "provider-secret-value-not-printed" not in result.output


def test_catalog_excludes_obvious_non_completions_model_categories() -> None:
    catalog = load_openai_chat_completions_catalog(include_legacy_models=True)
    forbidden = ("embedding", "image", "audio", "realtime", "moderation", "tts", "whisper")

    assert catalog
    for entry in catalog:
        assert entry.endpoint == "chat.completions"
        assert not any(marker in entry.model_id.lower() for marker in forbidden)


def test_openai_completions_pricing_example_csv_covers_default_catalog() -> None:
    required_columns = {
        "provider",
        "model",
        "endpoint",
        "currency",
        "input_price_per_1m",
        "output_price_per_1m",
    }

    with EXAMPLE_PRICING_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert required_columns.issubset(rows[0])
    assert all(row["provider"] == "openai" for row in rows)
    assert all(row["endpoint"] == "chat.completions" for row in rows)
    assert all("placeholder" in row["notes"].lower() for row in rows)
    assert all("not real" in row["notes"].lower() for row in rows)
    assert all("production" in row["notes"].lower() for row in rows)

    catalog = load_openai_chat_completions_catalog(include_legacy_models=False)
    assert {row["model"] for row in rows} == {entry.upstream_model for entry in catalog}


def test_include_legacy_completions_rejected_safely() -> None:
    result = runner.invoke(
        app,
        [
            "bootstrap",
            "openai-completions-catalog",
            "--include-legacy-completions",
        ],
    )

    assert result.exit_code != 0
    assert "/v1/completions legacy endpoint is not implemented" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.asyncio
async def test_conflicting_existing_route_is_not_silently_overwritten() -> None:
    store = _Store()
    first = load_openai_chat_completions_catalog(include_legacy_models=False)[0]
    store.routes.append(
        SimpleNamespace(
            requested_model=first.model_id,
            match_type="exact",
            endpoint=first.normalized_endpoint,
            provider="openrouter",
            upstream_model=f"openai/{first.upstream_model}",
            enabled=True,
            visible_in_models=True,
            supports_streaming=True,
        )
    )

    result = await _run_bootstrap(store, dry_run=False)

    assert result.has_blockers is True
    assert any(row.status == "conflict" and row.model_id == first.model_id for row in result.chat_routes)
    assert len(store.routes) == 1
    assert store.providers == {}
    assert store.pricing == []


@pytest.mark.asyncio
async def test_v1_models_visibility_uses_local_route_metadata_and_key_policy() -> None:
    store = _Store()
    await _run_bootstrap(store, dry_run=False)
    service = ModelCatalogService(
        model_routes_repository=_RouteRepo(store),
        provider_configs_repository=_ProviderRepo(store),
    )
    now = datetime.now(UTC)
    key = AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now,
        valid_until=now,
        allow_all_models=False,
        allowed_models=("gpt-4o-mini",),
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

    models = await service.list_visible_models(key)

    assert [model.id for model in models] == ["gpt-4o-mini"]
    assert json.dumps([model.model_dump() for model in models])
