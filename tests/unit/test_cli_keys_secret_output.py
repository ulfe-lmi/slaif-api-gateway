from __future__ import annotations

import pytest

from slaif_gateway.cli.common import CliSecretFileError, write_secret_file


def test_write_secret_file_creates_0600_file(tmp_path) -> None:
    path = tmp_path / "gateway-key.txt"

    write_secret_file(path, "sk-slaif-public.secret")

    assert path.read_text(encoding="utf-8") == "sk-slaif-public.secret\n"
    assert path.stat().st_mode & 0o777 == 0o600


def test_write_secret_file_fails_if_file_exists(tmp_path) -> None:
    path = tmp_path / "gateway-key.txt"
    path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(CliSecretFileError):
        write_secret_file(path, "sk-slaif-public.secret")

    assert path.read_text(encoding="utf-8") == "existing\n"
