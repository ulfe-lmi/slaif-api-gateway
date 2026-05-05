from __future__ import annotations

import base64
import os
import re
import unicodedata
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import Settings, get_settings

runner = CliRunner()


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _env_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.partition("=")[2]
    raise AssertionError(f"{key} not found")


def setup_function() -> None:
    get_settings.cache_clear()


def test_hmac_generation_prints_value_by_default() -> None:
    result = runner.invoke(app, ["secrets", "generate", "hmac", "--version", "1"])

    assert result.exit_code == 0
    value = result.stdout.strip()
    assert len(value) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", value)


def test_admin_session_generation_prints_value_by_default() -> None:
    result = runner.invoke(app, ["secrets", "generate", "admin-session"])

    assert result.exit_code == 0
    value = result.stdout.strip()
    assert len(value) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", value)


def test_one_time_generation_prints_base64url_32_byte_value() -> None:
    result = runner.invoke(app, ["secrets", "generate", "one-time"])

    assert result.exit_code == 0
    value = result.stdout.strip()
    assert re.fullmatch(r"[A-Za-z0-9_-]+", value)
    assert len(_decode_base64url(value)) == 32
    Settings(ONE_TIME_SECRET_ENCRYPTION_KEY=value)


def test_write_updates_only_requested_variable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "# local env",
                "TOKEN_HMAC_SECRET_V1=change-me",
                "ADMIN_SESSION_SECRET=change-me",
                "OTHER_SETTING=keep-me",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "hmac",
            "--version",
            "1",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    text = env_file.read_text(encoding="utf-8")
    assert "# local env" in text
    assert "ADMIN_SESSION_SECRET=change-me" in text
    assert "OTHER_SETTING=keep-me" in text
    assert "TOKEN_HMAC_SECRET_V1=change-me" not in text
    assert len(_env_value(env_file, "TOKEN_HMAC_SECRET_V1")) >= 32


def test_write_does_not_print_secret_by_default(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ONE_TIME_SECRET_ENCRYPTION_KEY=\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "one-time",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    written_value = _env_value(env_file, "ONE_TIME_SECRET_ENCRYPTION_KEY")
    assert written_value
    assert written_value not in result.stdout
    assert written_value not in result.stderr
    assert result.stdout.strip() == f"Updated ONE_TIME_SECRET_ENCRYPTION_KEY in {env_file}"


def test_write_does_not_print_generated_secret_values_for_any_secret(tmp_path: Path) -> None:
    cases = (
        (
            ["secrets", "generate", "hmac", "--version", "1"],
            "TOKEN_HMAC_SECRET_V1",
        ),
        (
            ["secrets", "generate", "admin-session"],
            "ADMIN_SESSION_SECRET",
        ),
        (
            ["secrets", "generate", "one-time"],
            "ONE_TIME_SECRET_ENCRYPTION_KEY",
        ),
    )

    for command, env_var in cases:
        env_file = tmp_path / f"{env_var}.env"
        env_file.write_text(f"{env_var}=\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [*command, "--env-file", str(env_file), "--write"],
        )

        assert result.exit_code == 0
        written_value = _env_value(env_file, env_var)
        assert written_value
        assert written_value not in result.stdout
        assert written_value not in result.stderr


def test_write_preserves_comments_and_unrelated_lines(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# before\nADMIN_SESSION_SECRET=placeholder\n\n# after\nDATABASE_URL=postgresql://x\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    text = env_file.read_text(encoding="utf-8")
    assert text.startswith("# before\n")
    assert "\n\n# after\nDATABASE_URL=postgresql://x\n" in text
    assert "ADMIN_SESSION_SECRET=placeholder" not in text


def test_missing_target_variable_is_appended(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# local env\nAPP_ENV=development\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    text = env_file.read_text(encoding="utf-8")
    assert text.startswith("# local env\nAPP_ENV=development\n")
    assert "\nADMIN_SESSION_SECRET=" in text


def test_placeholder_value_is_replaced_without_force(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_SESSION_SECRET=dummy-value\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    assert "dummy-value" not in env_file.read_text(encoding="utf-8")


def test_non_placeholder_value_is_rejected_without_force(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    existing = "existing-live-runtime-secret-value-123456789"
    env_file.write_text(f"ADMIN_SESSION_SECRET={existing}\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 1
    assert "already has a non-placeholder value" in result.stderr
    assert existing in env_file.read_text(encoding="utf-8")
    assert existing not in result.stdout
    assert existing not in result.stderr


def test_non_placeholder_value_is_replaced_with_force(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    existing = "existing-live-runtime-secret-value-123456789"
    env_file.write_text(f"ADMIN_SESSION_SECRET={existing}\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
            "--force",
        ],
    )

    assert result.exit_code == 0
    written_value = _env_value(env_file, "ADMIN_SESSION_SECRET")
    assert written_value != existing
    assert existing not in result.stdout
    assert existing not in result.stderr
    assert written_value not in result.stdout
    assert written_value not in result.stderr


def test_write_refuses_env_example(tmp_path: Path) -> None:
    env_example = tmp_path / ".env.example"
    env_example.write_text("ADMIN_SESSION_SECRET=change-me\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_example),
            "--write",
        ],
    )

    assert result.exit_code == 1
    assert "Refusing to modify .env.example" in result.stderr
    assert env_example.read_text(encoding="utf-8") == "ADMIN_SESSION_SECRET=change-me\n"


def test_write_missing_env_file_fails_without_creating_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 1
    assert "Env file not found" in result.stderr
    assert not env_file.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode warning only")
def test_write_warns_when_env_file_is_group_or_world_readable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_SESSION_SECRET=\n", encoding="utf-8")
    env_file.chmod(0o644)

    result = runner.invoke(
        app,
        [
            "secrets",
            "generate",
            "admin-session",
            "--env-file",
            str(env_file),
            "--write",
        ],
    )

    assert result.exit_code == 0
    assert "is readable by other users; consider chmod 600" in result.stderr


def test_force_warnings_are_safe_for_each_secret_type(tmp_path: Path) -> None:
    cases = (
        (
            ["secrets", "generate", "hmac", "--version", "1"],
            "TOKEN_HMAC_SECRET_V1",
            "invalidates existing gateway keys",
        ),
        (
            ["secrets", "generate", "admin-session"],
            "ADMIN_SESSION_SECRET",
            "invalidates active admin sessions",
        ),
        (
            ["secrets", "generate", "one-time"],
            "ONE_TIME_SECRET_ENCRYPTION_KEY",
            "encrypted one-time secrets undecryptable",
        ),
    )

    for command, env_var, warning in cases:
        env_file = tmp_path / f"{env_var}.env"
        old_secret = f"old-live-secret-for-{env_var.lower()}-123456789"
        env_file.write_text(f"{env_var}={old_secret}\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [*command, "--env-file", str(env_file), "--write", "--force"],
        )

        assert result.exit_code == 0
        new_secret = _env_value(env_file, env_var)
        assert warning in result.stderr
        assert old_secret not in result.stdout
        assert old_secret not in result.stderr
        assert new_secret not in result.stdout
        assert new_secret not in result.stderr


def test_validate_env_succeeds_for_generated_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "APP_ENV=development",
                "ACTIVE_HMAC_KEY_VERSION=1",
                "TOKEN_HMAC_SECRET_V1=valid-hmac-secret-value-123456789012",
                "ADMIN_SESSION_SECRET=valid-admin-secret-value-123456789012",
                "ONE_TIME_SECRET_ENCRYPTION_KEY=",
                "",
            )
        ),
        encoding="utf-8",
    )
    one_time_result = runner.invoke(app, ["secrets", "generate", "one-time"])
    assert one_time_result.exit_code == 0
    with env_file.open("a", encoding="utf-8") as file:
        file.write(f"ONE_TIME_SECRET_ENCRYPTION_KEY={one_time_result.stdout.strip()}\n")

    result = runner.invoke(
        app,
        ["secrets", "validate-env", "--env-file", str(env_file)],
    )

    assert result.exit_code == 0
    assert "OK: TOKEN_HMAC_SECRET_V1 configured" in result.stdout
    assert "OK: ADMIN_SESSION_SECRET configured" in result.stdout
    assert "OK: ONE_TIME_SECRET_ENCRYPTION_KEY decodes to 32 bytes" in result.stdout


def test_validate_env_fails_when_one_time_key_has_wrong_length(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    wrong_length = base64.urlsafe_b64encode(b"short").decode("ascii").rstrip("=")
    env_file.write_text(
        "\n".join(
            (
                "TOKEN_HMAC_SECRET_V1=valid-hmac-secret-value-123456789012",
                "ADMIN_SESSION_SECRET=valid-admin-secret-value-123456789012",
                f"ONE_TIME_SECRET_ENCRYPTION_KEY={wrong_length}",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["secrets", "validate-env", "--env-file", str(env_file)],
    )

    assert result.exit_code == 1
    assert "must decode to exactly 32 bytes" in result.stderr
    assert wrong_length not in result.stdout
    assert wrong_length not in result.stderr


def test_validate_env_fails_when_hmac_secret_is_placeholder(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "TOKEN_HMAC_SECRET_V1=change-me",
                "ADMIN_SESSION_SECRET=valid-admin-secret-value-123456789012",
                "ONE_TIME_SECRET_ENCRYPTION_KEY=",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["secrets", "validate-env", "--env-file", str(env_file)],
    )

    assert result.exit_code == 1
    assert "TOKEN_HMAC_SECRET_V1 must be configured" in result.stderr
    assert "change-me" not in result.stdout
    assert "change-me" not in result.stderr


def test_validate_env_does_not_print_configured_secret_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    hmac_secret = "valid-hmac-secret-value-123456789012"
    admin_secret = "valid-admin-secret-value-123456789012"
    one_time_secret = runner.invoke(app, ["secrets", "generate", "one-time"]).stdout.strip()
    env_file.write_text(
        "\n".join(
            (
                f"TOKEN_HMAC_SECRET_V1={hmac_secret}",
                f"ADMIN_SESSION_SECRET={admin_secret}",
                f"ONE_TIME_SECRET_ENCRYPTION_KEY={one_time_secret}",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["secrets", "validate-env", "--env-file", str(env_file)],
    )

    assert result.exit_code == 0
    for secret in (hmac_secret, admin_secret, one_time_secret):
        assert secret not in result.stdout
        assert secret not in result.stderr


def test_env_example_contains_placeholders_only() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "TOKEN_HMAC_SECRET_V1=change-me-generate-long-random-secret-at-least-32-chars" in (
        env_example
    )
    assert "ADMIN_SESSION_SECRET=change-me-generate-long-random-secret-at-least-32-chars" in (
        env_example
    )
    assert "ONE_TIME_SECRET_ENCRYPTION_KEY=\n" in env_example


def test_cli_secrets_source_has_no_hidden_or_bidi_format_controls() -> None:
    source_path = Path("app/slaif_gateway/cli/secrets.py")
    text = source_path.read_text(encoding="utf-8")
    bidi_controls = {
        *range(0x202A, 0x202F),
        *range(0x2066, 0x206A),
        0x200E,
        0x200F,
        0x061C,
    }

    bad_chars: list[str] = []
    for index, char in enumerate(text):
        codepoint = ord(char)
        if unicodedata.category(char) == "Cf" or codepoint in bidi_controls:
            bad_chars.append(
                f"offset {index}: U+{codepoint:04X} {unicodedata.name(char, 'UNKNOWN')}"
            )

    assert bad_chars == []
