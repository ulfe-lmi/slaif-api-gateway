from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


_COMMAND_RE = re.compile(r'@(\w+)\.command\(\s*(?:name\s*=\s*)?["\x27]([^"\x27]+)["\x27]')
_REGISTRATION_RE = re.compile(r'app\.add_typer\((\w+),\s*name=["\x27]([^"\x27]+)')
_IMPORT_RE = re.compile(r"from\s+([\w.]+)\s+import\s+(\w+)(?:\s+as\s+(\w+))?")
_TYPER_LOCAL_RE = re.compile(r"^\s*(\w+)\s*=\s*typer\.Typer\(", re.M)


def _cli_module_sources(cli_dir: Path) -> dict[str, str]:
    """Scanned Typer CLI module sources keyed by module stem (pure read)."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(cli_dir.glob("*.py"))
        if path.stem not in {"__init__", "common"}
    }


def _resolve_cli_command_parts(cli_dir: Path) -> list[list[str]]:
    """Statically resolve registered Typer command invocation parts.

    Pure source scan (no production imports): each module's local
    ``typer.Typer`` instances are resolved against ``app.add_typer(
    <alias>, name=...)`` registrations in the same module or in
    importing modules.  A sub-app whose Typer object is IMPORTED from a
    separate module therefore resolves under its actual parent
    namespace (``codex_replay.py`` -> ``codex replay``) instead of its
    file stem; in-file nested apps and top-level groups keep their
    existing resolution.  Both positional and ``name=`` command
    declarations are detected.
    """
    sources = _cli_module_sources(cli_dir)
    local_typpers: dict[str, set[str]] = {
        stem: set(_TYPER_LOCAL_RE.findall(src)) for stem, src in sources.items()
    }
    import_aliases: dict[str, dict[str, tuple[str, str]]] = {}
    registrations: dict[str, list[tuple[str, str]]] = {}
    for stem, src in sources.items():
        import_aliases[stem] = {
            alias or name: (module_path.split(".")[-1], name)
            for module_path, name, alias in _IMPORT_RE.findall(src)
        }
        registrations[stem] = _REGISTRATION_RE.findall(src)

    stem_group = {stem: stem.replace("_", "-") for stem in sources}

    def parent_of(stem: str, typer_var: str) -> tuple[str, str] | None:
        for parent in sorted(sources):
            for alias, sub_name in registrations[parent]:
                if parent == stem:
                    if alias == typer_var and alias in local_typpers[stem]:
                        return (parent, sub_name)
                elif import_aliases[parent].get(alias) == (stem, typer_var):
                    return (parent, sub_name)
        return None

    prefix_cache: dict[tuple[str, str], list[str]] = {}

    def command_prefix(stem: str, typer_var: str) -> list[str]:
        key = (stem, typer_var)
        if key in prefix_cache:
            return prefix_cache[key]
        prefix_cache[key] = []  # deterministic cycle guard
        parent = parent_of(stem, typer_var)
        if parent is None:
            prefix = [] if stem == "main" else [stem_group[stem]]
        elif parent[0] == "main":
            prefix = [parent[1]]
        else:
            prefix = command_prefix(parent[0], "app") + [parent[1]]
        prefix_cache[key] = prefix
        return prefix

    parts: list[list[str]] = []
    for stem, src in sources.items():
        for typer_var, command in _COMMAND_RE.findall(src):
            parts.append(command_prefix(stem, typer_var) + [command])
    return parts


def test_every_typer_subcommand_is_named_in_cli_reference() -> None:
    reference = (ROOT / "docs/cli-reference.md").read_text(encoding="utf-8")
    missing = [
        " ".join(parts)
        for parts in _resolve_cli_command_parts(ROOT / "app/slaif_gateway/cli")
        if "slaif-gateway " + " ".join(parts) not in reference
    ]
    assert missing == []


def test_codex_replay_commands_documented_under_real_invocations() -> None:
    reference = (ROOT / "docs/cli-reference.md").read_text(encoding="utf-8")
    parts = [
        " ".join(parts)
        for parts in _resolve_cli_command_parts(ROOT / "app/slaif_gateway/cli")
    ]
    # The registered separate-file sub-app resolves to its real parent
    # namespace, never a fabricated file-stem alias.
    assert "codex replay inspect" in parts
    assert "codex replay extend" in parts
    assert "codex-replay inspect" not in parts
    assert "codex-replay extend" not in parts
    assert "slaif-gateway codex replay inspect" in reference
    assert "slaif-gateway codex replay extend" in reference


def _write_nested_subapp_fixture(tmp_path: Path) -> None:
    (tmp_path / "gamma.py").write_text(
        "import typer\n"
        "\n"
        "app = typer.Typer()\n"
        "\n"
        "\n"
        '@app.command("solo")\n'
        "def solo() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "import typer\n"
        "\n"
        "from fake.cli.beta import app as beta_app\n"
        "\n"
        "app = typer.Typer()\n"
        "\n"
        'app.add_typer(beta_app, name="beta")\n'
        "\n"
        "\n"
        '@app.command("root-cmd")\n'
        "def root_cmd() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "alpha.py").write_text(
        "import typer\n"
        "\n"
        "app = typer.Typer()\n"
        "\n"
        "\n"
        '@app.command("run")\n'
        "def run() -> None:\n"
        "    pass\n"
        "\n"
        "\n"
        '@app.command(name="named")\n'
        "def named() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "beta.py").write_text(
        "import typer\n"
        "\n"
        "from fake.cli.alpha import app as alpha_app\n"
        "\n"
        "app = typer.Typer()\n"
        "\n"
        'app.add_typer(alpha_app, name="sub")\n'
        "\n"
        "\n"
        '@app.command("own")\n'
        "def own() -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )


def test_registered_separate_file_nested_app_resolves_to_parent(tmp_path: Path) -> None:
    _write_nested_subapp_fixture(tmp_path)
    parts = [" ".join(p) for p in _resolve_cli_command_parts(tmp_path)]
    # alpha's imported app resolves under beta's real parent namespace,
    # never its file stem; beta's root app is a top-level group; gamma
    # is unregistered and keeps its stem group; both command-name
    # spellings are detected.
    assert parts == [
        "beta sub run",
        "beta sub named",
        "beta own",
        "gamma solo",
        "root-cmd",
    ]


def test_undocumented_nested_command_is_reported_missing(tmp_path: Path) -> None:
    _write_nested_subapp_fixture(tmp_path)
    resolved = _resolve_cli_command_parts(tmp_path)
    reference = "\n".join(
        "slaif-gateway " + " ".join(p)
        for p in resolved
        if " ".join(p) != "beta sub run"
    )
    missing = [
        " ".join(p) for p in resolved if "slaif-gateway " + " ".join(p) not in reference
    ]
    assert missing == ["beta sub run"]


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

    # The canonical block is the fenced bash block that opens a subshell.
    blocks = [
        b
        for b in re.findall(r"```bash\n(.*?)```", outline, flags=re.S)
        if b.startswith("(",)
    ]
    assert len(blocks) == 1
    block = blocks[0]

    # No unquoted angle-bracket placeholders may occur in executable
    # shell, and the published block must pass a real bash syntax check.
    assert "<" not in block
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available for the syntax check")
    proc = subprocess.run(
        [bash, "-n"], input=block, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr

    # Ingress and the runtime users are quiesced before the migration
    # gate, and the gate precedes the API replacement.
    quiesce = block.index("stop nginx api")
    gate = block.index("run --rm --no-deps migrations")
    api = block.index(
        "up -d --no-deps --force-recreate --wait --wait-timeout 120 api"
    )
    assert quiesce < gate < api
    # API health wait plus the in-container readyz probe precede the
    # proxy refresh, which precedes the public HTTPS check.
    readyz = block.index("exec -T api python")
    proxy = block.index("up -d --no-deps --force-recreate nginx")
    assert api < readyz < proxy
    curl = block.index(
        "curl --fail --silent --show-error --retry 10 --retry-all-errors"
    )
    assert proxy < curl
    # TLS verification is never weakened in the public check.
    assert "-k" not in block
    assert "--insecure" not in block
    # Optional async services are branch-gated, never an unconditional
    # line, and the default copy/paste starts no async jobs.
    assert 'if [ "$upgrade_async" = yes ]' in block
    assert "--profile async up -d --force-recreate worker scheduler" not in block
    # Abandoned 178-c command strings and claims are gone.
    assert "<checkout" not in outline
    assert "remove this line otherwise" not in outline
    assert "ps --all" not in outline
    assert "two brief, bounded windows" not in outline
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
