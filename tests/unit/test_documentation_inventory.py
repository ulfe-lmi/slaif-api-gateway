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


def test_real_provider_doc_does_not_overclaim_current_sql_evidence() -> None:
    content = (ROOT / "docs/real-provider-qualification.md").read_text(encoding="utf-8")
    assert "performs no SQL query" in content
    assert "real-provider accounting qualification: not complete" in content

    matrix = (ROOT / "docs/compatibility-matrix.md").read_text(encoding="utf-8")
    normalized_matrix = " ".join(matrix.split())
    assert "Complete current real-provider accounting qualification is not established" in normalized_matrix
    assert "passed with finalized PostgreSQL usage-ledger entries" not in matrix
