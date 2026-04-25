from __future__ import annotations

from pathlib import Path

from slaif_gateway.cli import keys as keys_cli


def test_cli_keys_module_does_not_import_out_of_scope_runtime_dependencies() -> None:
    source = Path(keys_cli.__file__).read_text()

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
    for forbidden in forbidden_imports:
        assert forbidden not in source


def test_cli_keys_module_does_not_log_or_persist_plaintext_key_material() -> None:
    source = Path(keys_cli.__file__).read_text()

    assert "logging" not in source
    assert "logger" not in source
    assert ".add(" not in source
    assert ".commit(" not in source
    assert "token_hash:" not in source
    assert "encrypted_payload:" not in source
    assert "nonce:" not in source


def test_safe_output_helper_rejects_secret_markers() -> None:
    assert keys_cli._safe_output_has_no_secrets("public metadata", ["token_hash"])
    assert not keys_cli._safe_output_has_no_secrets("contains token_hash", ["token_hash"])
