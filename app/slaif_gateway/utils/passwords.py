"""Password hashing helpers for admin credentials."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError

_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


def hash_admin_password(password: str) -> str:
    """Hash an admin password with Argon2id."""
    if not password:
        raise ValueError("Admin password cannot be empty")
    return _PASSWORD_HASHER.hash(password)


def verify_admin_password(password: str, password_hash: str) -> bool:
    """Verify an admin password against an Argon2id hash."""
    if not password:
        raise ValueError("Admin password cannot be empty")
    if not password_hash:
        raise ValueError("Admin password hash cannot be empty")
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except VerificationError:
        return False
