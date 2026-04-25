from __future__ import annotations

from pathlib import Path

from slaif_gateway.cli import admin as admin_cli
from slaif_gateway.cli import cohorts as cohorts_cli
from slaif_gateway.cli import common as cli_common
from slaif_gateway.cli import institutions as institutions_cli
from slaif_gateway.cli import owners as owners_cli


CLI_MODULES = (admin_cli, institutions_cli, cohorts_cli, owners_cli)


def test_cli_record_modules_do_not_import_out_of_scope_runtime_dependencies() -> None:
    forbidden_imports = (
        "from slaif_gateway.providers",
        "import openai",
        "import openrouter",
        "import aiosmtplib",
        "import celery",
        "from fastapi",
        "import fastapi",
        "import redis",
        "dashboard",
    )

    for module in CLI_MODULES:
        source = Path(module.__file__).read_text()
        for forbidden in forbidden_imports:
            assert forbidden not in source


def test_cli_record_modules_do_not_log_secrets() -> None:
    forbidden_terms = (
        "logging",
        "logger",
        "token_hash:",
        "encrypted_payload:",
        "nonce:",
    )

    for module in CLI_MODULES:
        source = Path(module.__file__).read_text()
        for forbidden in forbidden_terms:
            assert forbidden not in source


def test_safe_output_helper_rejects_secret_markers() -> None:
    assert cli_common.safe_output_has_no_secrets("public metadata", ("password_hash",))
    assert not cli_common.safe_output_has_no_secrets(
        "contains password_hash",
        ("password_hash",),
    )
