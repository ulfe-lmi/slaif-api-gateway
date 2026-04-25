from __future__ import annotations

import pytest

from slaif_gateway.utils.passwords import hash_admin_password, verify_admin_password


def test_hash_admin_password_uses_argon2id_and_verifies() -> None:
    password = "correct horse battery staple"

    password_hash = hash_admin_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_admin_password(password, password_hash)
    assert not verify_admin_password("wrong password", password_hash)


def test_hash_admin_password_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        hash_admin_password("")


def test_verify_admin_password_rejects_empty_inputs() -> None:
    password_hash = hash_admin_password("not empty")

    with pytest.raises(ValueError, match="cannot be empty"):
        verify_admin_password("", password_hash)
    with pytest.raises(ValueError, match="cannot be empty"):
        verify_admin_password("not empty", "")
