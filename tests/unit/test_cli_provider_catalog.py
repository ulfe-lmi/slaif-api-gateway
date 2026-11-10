from __future__ import annotations

import json
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.services.provider_catalog_proposal import ProviderCatalogProposalResult

runner = CliRunner()


def test_provider_catalog_cli_registers_command() -> None:
    result = runner.invoke(app, ["provider-catalog", "--help"])

    assert result.exit_code == 0
    assert "propose" in result.stdout


def test_provider_catalog_cli_json_summary_is_safe(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    result_payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=3,
        pricing_rows_ready=2,
        warnings_count=4,
        high_confidence=2,
        medium_confidence=1,
        low_confidence=0,
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        return result_payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["route_rows_ready"] == 3
    assert payload["pricing_rows_ready"] == 2
    assert payload["mutated_metadata"] is False
    assert "authorization" not in result.stdout.lower()
    assert "token_hash" not in result.stdout.lower()


def test_provider_catalog_cli_forwards_allow_zero_prices_flag(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    captured: dict[str, object] = {}
    result_payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=0,
        pricing_rows_ready=0,
        warnings_count=1,
        high_confidence=0,
        medium_confidence=0,
        low_confidence=0,
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        captured.update(kwargs)
        return result_payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--allow-zero-prices",
        ],
    )

    assert result.exit_code == 0
    assert captured["allow_zero_prices"] is True


def test_provider_catalog_cli_forwards_paired_and_ordinary_chat_flags(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    captured: dict[str, object] = {}
    result_payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=1,
        pricing_rows_ready=1,
        warnings_count=0,
        high_confidence=1,
        medium_confidence=0,
        low_confidence=0,
        paired_ready_only=True,
        ordinary_chat_only=True,
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        captured.update(kwargs)
        return result_payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--paired-ready-only",
            "--ordinary-chat-only",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured["paired_ready_only"] is True
    assert captured["ordinary_chat_only"] is True
    payload = json.loads(result.stdout)
    assert payload["paired_ready_only"] is True
    assert payload["ordinary_chat_only"] is True


def test_provider_catalog_cli_forwards_package_flags(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    captured: dict[str, object] = {}
    result_payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=2,
        pricing_rows_ready=2,
        warnings_count=0,
        high_confidence=2,
        medium_confidence=0,
        low_confidence=0,
        package_index_path=output_dir / "packages" / "package-index.json",
        package_index_markdown_path=output_dir / "packages" / "package-index.md",
        package_names=("openrouter-chat-text", "openrouter-chat-image"),
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        captured.update(kwargs)
        return result_payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--package",
            "chat-text",
            "--package",
            "openrouter-chat-image",
            "--all-packages",
            "--include-deprecated",
            "--include-ambiguous-capabilities",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured["package_names"] == ("chat-text", "openrouter-chat-image")
    assert captured["all_packages"] is True
    assert captured["include_deprecated"] is True
    assert captured["include_ambiguous_capabilities"] is True
    payload = json.loads(result.stdout)
    assert payload["package_names"] == ["openrouter-chat-text", "openrouter-chat-image"]
    assert payload["files"]["package_index_json"].endswith("package-index.json")


def test_provider_catalog_cli_rejects_unknown_package_name(tmp_path: Path) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--package",
            "not-a-real-package",
        ],
    )

    assert result.exit_code != 0
    assert "unknown package name" in result.stderr.lower()


def test_provider_catalog_cli_rejects_openai_package_request(tmp_path: Path) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openai",
            "--output-dir",
            str(output_dir),
            "--package",
            "chat-text",
        ],
    )

    assert result.exit_code != 0
    assert "implemented only for openrouter" in result.stderr.lower()


# --- FX capture boundary for --currency (non-USD needs ONE configured direct rate) ---


class _FakeEngine:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def dispose(self) -> None:
        self._events.append("disposed")


def _fake_fx_stack(monkeypatch, *, row):
    """Route the CLI's FX capture boundary to fakes; returns (events,
    lookups). Only the CLI module's own imported names are re-pointed."""
    import slaif_gateway.cli.provider_catalog as cli_mod

    events: list[str] = []
    lookups: list[dict[str, object]] = []
    monkeypatch.setattr(
        cli_mod,
        "get_settings",
        lambda: SimpleNamespace(
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/slaif_test"
        ),
    )
    monkeypatch.setattr(
        cli_mod,
        "create_engine_from_settings",
        lambda settings: _FakeEngine(events),
    )

    @asynccontextmanager
    async def _fake_session():
        yield SimpleNamespace()

    def _session_factory(engine):
        def factory():
            return _fake_session()
        return factory

    monkeypatch.setattr(cli_mod, "create_sessionmaker_from_engine", _session_factory)

    class _FakeFxRepository:
        def __init__(self, session) -> None:
            pass

        async def find_latest_rate(self, *, base_currency, quote_currency, at_time):
            lookups.append(
                {"base": base_currency, "quote": quote_currency, "at_time": at_time}
            )
            return row

    monkeypatch.setattr(cli_mod, "FxRatesRepository", _FakeFxRepository)
    return events, lookups


def test_cli_propose_usd_is_offline_and_never_touches_fx(
    tmp_path: Path, monkeypatch
) -> None:
    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    captured: dict[str, object] = {}
    payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=0,
        pricing_rows_ready=0,
        warnings_count=0,
        high_confidence=0,
        medium_confidence=0,
        low_confidence=0,
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        captured.update(kwargs)
        return payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )
    # USD must NEVER construct an FX database engine (offline capable)
    def _no_engine(settings):
        raise AssertionError("USD must not touch DB")

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.create_engine_from_settings",
        _no_engine,
    )
    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    assert captured["fx_capture"] is None


def test_cli_propose_non_usd_without_configured_rate_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    output_dir = tmp_path / "catalog"
    events, lookups = _fake_fx_stack(monkeypatch, row=None)
    generated = []

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        generated.append(kwargs)
        raise AssertionError("generation must not start without a configured rate")

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )
    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--currency",
            "EUR",
        ],
    )
    assert result.exit_code != 0
    assert "no active configured USD->EUR FX rate exists" in result.stderr
    # the synthetic DSN is never echoed either
    assert "postgresql+asyncpg" not in result.stdout + result.stderr
    # exactly one lookup on the DIRECT USD->EUR pair, at a capture time
    assert len(lookups) == 1
    assert lookups[0]["base"] == "USD" and lookups[0]["quote"] == "EUR"
    assert isinstance(lookups[0]["at_time"], datetime)
    assert generated == []
    assert "disposed" in events  # engine closed before any generation
    assert not output_dir.exists()


def test_cli_propose_non_usd_with_configured_rate_captures_once_and_closes(
    tmp_path: Path, monkeypatch
) -> None:
    from slaif_gateway.services.provider_catalog_proposal import ProposalFxCapture

    output_dir = tmp_path / "catalog"
    output_dir.mkdir()
    rate_id = "22222222-2222-4222-8222-222222222222"
    row = SimpleNamespace(
        id=rate_id,
        rate=Decimal("1.083"),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=None,
    )
    events, lookups = _fake_fx_stack(monkeypatch, row=row)
    captured: dict[str, object] = {}
    payload = ProviderCatalogProposalResult(
        output_dir=output_dir,
        routes_proposal_path=output_dir / "routes-proposal.tsv",
        pricing_proposal_path=output_dir / "pricing-proposal.tsv",
        normalized_path=output_dir / "provider-catalog-normalized.json",
        report_path=output_dir / "provider-catalog-report.md",
        warnings_path=output_dir / "warnings.json",
        manifest_path=output_dir / "source-manifest.json",
        route_rows_ready=0,
        pricing_rows_ready=0,
        warnings_count=0,
        high_confidence=0,
        medium_confidence=0,
        low_confidence=0,
    )

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        captured.update(kwargs)
        return payload

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )
    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--currency",
            "eur",  # normalized to the uppercase target
        ],
    )
    assert result.exit_code == 0
    assert captured["currency"] == "eur"
    fx = captured["fx_capture"]
    assert isinstance(fx, ProposalFxCapture)
    assert fx.base_currency == "USD" and fx.target_currency == "EUR"
    assert fx.rate == "1.083"
    assert fx.fx_rate_id == rate_id
    assert len(lookups) == 1
    assert events.count("disposed") == 1  # closed before generation


def test_cli_propose_credential_shaped_currency_is_refused_before_db(
    tmp_path: Path, monkeypatch
) -> None:
    """A credential-shaped --currency value is rejected by the shape
    guard BEFORE any settings/DB access and is never echoed verbatim
    (handle_cli_error renders BadParameter messages as-is)."""
    canary = "Bearer sk-test-canary-9f31"
    calls = {"settings": 0, "engine": 0}
    import slaif_gateway.cli.provider_catalog as cli_mod

    def _settings_counter():
        calls["settings"] += 1
        return SimpleNamespace(DATABASE_URL="postgresql+asyncpg://user:pw@localhost/db")

    monkeypatch.setattr(
        cli_mod,
        "get_settings",
        _settings_counter,
    )

    def _no_engine(settings):
        calls["engine"] += 1
        raise AssertionError("DB must not be reached")

    monkeypatch.setattr(cli_mod, "create_engine_from_settings", _no_engine)
    output_dir = tmp_path / "catalog"
    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--currency",
            canary,
        ],
    )
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert canary not in combined
    assert "sk-test-canary-9f31" not in combined
    assert "3-letter" in combined
    assert calls["settings"] == 0  # never reached settings/DB
    assert calls["engine"] == 0
    assert not output_dir.exists()


def test_cli_propose_fx_configuration_fault_never_echoes_credential(
    tmp_path: Path, monkeypatch
) -> None:
    """A fault raised from the NEW FX configuration boundary (settings
    carrying an untrusted DSN-shaped value) is wrapped into ONE fixed
    safe error - never reflected into the terminal output."""
    canary = "sk-canary-9f31"
    import slaif_gateway.cli.provider_catalog as cli_mod

    def _bad_settings():
        raise ValueError(f"bad DSN postgresql+asyncpg://user:{canary}@host/db")

    monkeypatch.setattr(cli_mod, "get_settings", _bad_settings)
    generated = []

    async def fake_generate(**kwargs) -> ProviderCatalogProposalResult:  # noqa: ANN003
        generated.append(kwargs)
        raise AssertionError("generation must not start on a configuration fault")

    monkeypatch.setattr(
        "slaif_gateway.cli.provider_catalog.generate_provider_catalog_proposal",
        fake_generate,
    )
    output_dir = tmp_path / "catalog"
    result = runner.invoke(
        app,
        [
            "provider-catalog",
            "propose",
            "openrouter",
            "--output-dir",
            str(output_dir),
            "--currency",
            "EUR",
        ],
    )
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert canary not in combined
    assert "FX configuration or database is unavailable" in combined
    assert generated == []
    assert not output_dir.exists()
