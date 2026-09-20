from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _settings_fields() -> set[str]:
    tree = ast.parse((ROOT / "app/slaif_gateway/config.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and re.fullmatch(r"[A-Z][A-Z0-9_]+", item.target.id)
            }
    raise AssertionError("Settings class not found")


def test_every_setting_is_named_in_configuration_reference() -> None:
    configuration = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    missing = sorted(field for field in _settings_fields() if field not in configuration)
    assert missing == []


def test_every_sqlalchemy_table_is_named_in_schema_contract() -> None:
    models = (ROOT / "app/slaif_gateway/db/models.py").read_text(encoding="utf-8")
    tables = set(re.findall(r'__tablename__\s*=\s*["\x27]([^"\x27]+)', models))
    schema = (ROOT / "docs/database-schema.md").read_text(encoding="utf-8")
    missing = sorted(table for table in tables if table not in schema)
    assert missing == []
    assert f"contains {len(tables)} tables" in schema
    assert "`background_jobs` can be added" not in schema
    assert schema.index("## 5.22 `budget_periods`") < schema.index("## 6. Quota reservation algorithm")


def test_every_typer_subcommand_is_named_in_cli_reference() -> None:
    reference = (ROOT / "docs/cli-reference.md").read_text(encoding="utf-8")
    missing: list[str] = []
    for path in sorted((ROOT / "app/slaif_gateway/cli").glob("*.py")):
        group = path.stem.replace("_", "-")
        if group in {"__init__", "common"}:
            continue
        source = path.read_text(encoding="utf-8")
        nested = dict(
            re.findall(
                r'app\.add_typer\((\w+),\s*name=["\x27]([^"\x27]+)',
                source,
            )
        )
        for typer_name, command in re.findall(
            r'@(\w+)\.command\(["\x27]([^"\x27]+)',
            source,
        ):
            parts = [] if group == "main" else [group]
            if typer_name != "app":
                parts.append(nested[typer_name])
            parts.append(command)
            invocation = "slaif-gateway " + " ".join(parts)
            if invocation not in reference:
                missing.append(" ".join(parts))
    assert missing == []


def test_public_version_documents_distinguish_release_from_draft() -> None:
    releases = (ROOT / "docs/releases/README.md").read_text(encoding="utf-8")
    draft = (ROOT / "docs/release-notes.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "v0.1.0-rc.1" in releases
    assert "Untagged draft" in draft
    assert "## Unreleased" in changelog
    assert "[v0.1.0-rc.1]" in changelog


def test_foundation_docs_do_not_claim_runtime_wiring() -> None:
    expected = {
        "docs/dlp-policy.md": "not wired into Gateway egress",
        "docs/onboarding.md": "no wired onboarding page or CLI",
        "docs/observability.md": "SLO evaluation is a standalone foundation",
        "docs/provider-governance.md": "not part of ordinary route resolution",
    }
    for relative, phrase in expected.items():
        assert phrase in (ROOT / relative).read_text(encoding="utf-8")


def test_root_public_entry_points_exist_and_are_front_door() -> None:
    for name in ("QUICKSTART.md", "INSTALL.md", "CONTRIBUTING.md"):
        assert (ROOT / name).is_file(), name
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "QUICKSTART.md" in readme
    assert "INSTALL.md" in readme
    docs_home = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "../QUICKSTART.md" in docs_home
    assert "../INSTALL.md" in docs_home


def test_quickstart_stub_points_to_canonical_entry_points() -> None:
    stub = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    assert "../QUICKSTART.md" in stub
    assert "../INSTALL.md" in stub
    assert "first-time-operator-guide.md" in stub


def test_operator_guide_keeps_required_pricing_and_troubleshooting_sections() -> None:
    guide = (ROOT / "docs" / "first-time-operator-guide.md").read_text(encoding="utf-8")
    assert "## Pricing" in guide
    assert "## Troubleshooting" in guide


def test_real_provider_doc_does_not_overclaim_current_sql_evidence() -> None:
    content = (ROOT / "docs/real-provider-qualification.md").read_text(encoding="utf-8")
    assert "performs no SQL query" in content
    assert "real-provider accounting qualification: not complete" in content

    matrix = (ROOT / "docs/compatibility-matrix.md").read_text(encoding="utf-8")
    normalized_matrix = " ".join(matrix.split())
    assert "Complete current real-provider accounting qualification is not established" in normalized_matrix
    assert "passed with finalized PostgreSQL usage-ledger entries" not in matrix


def test_quickstart_milestone_two_documents_credentialed_model_call() -> None:
    quickstart = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
    # The model call is executable code in the root quickstart, not a deep link.
    assert "chat.completions.create(" in quickstart
    # The client example pins the repository's qualified SDK version.
    assert "openai==3.14.1" in quickstart
    # Local discovery and external inference are explicitly labeled.
    assert "**LOCAL**" in quickstart
    assert "**EXTERNAL**" in quickstart
    # The provider credential is configured at the milestone-2 boundary.
    assert "OPENAI_UPSTREAM_API_KEY" in quickstart
    # Milestone 2 no longer claims provider-free inference.
    assert "no live provider inference" not in quickstart.lower()


def test_operator_guide_places_grouping_flags_on_their_commands() -> None:
    guide = (ROOT / "docs/first-time-operator-guide.md").read_text(encoding="utf-8")
    assert "owners create --institution-id" in guide
    assert "keys create --cohort-id" in guide


def test_install_production_upgrade_is_fail_closed_and_proxy_refreshed() -> None:
    install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    start = install.index("### Production upgrade (controlled outline)")
    outline = install[start : install.index("## Interface exposure")]
    # The sequence is a fail-closed subshell, and the one-shot migration
    # exit-status gate precedes the API replacement.
    assert "set -euo pipefail" in outline
    gate = outline.index("run --rm --no-deps migrations")
    api = outline.index("up -d --force-recreate api")
    assert gate < api
    # The public proxy is refreshed after the API replacement (static
    # proxy_pass does not pick up the recreated container's address).
    assert outline.index("up -d --force-recreate nginx") > api
    # Stopped one-shots are only observable with ps --all.
    assert "ps --all" in outline
    # Optional async services have a concrete named command.
    assert (
        "--profile async up -d --force-recreate worker scheduler" in outline
    )
    # No metrics status is invented for the production proxy.
    assert "denies `/metrics`" not in install
    assert "does not expose or proxy `/metrics`" in install


def test_quickstart_links_refresh_race_to_install_recovery() -> None:
    quickstart = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
    assert "INSTALL.md#health-probe-after-recreation" in quickstart
    # The ten-row prerequisite stays; the speculative product recommendation
    # does not appear in the beginner prose.
    assert "requires a pricing row for **every** selected model" in quickstart
    assert "reasonable future improvement" not in quickstart
