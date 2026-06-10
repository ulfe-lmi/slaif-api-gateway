from __future__ import annotations

import json
from pathlib import Path

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
