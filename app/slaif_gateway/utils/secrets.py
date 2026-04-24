"""Symmetric encryption utilities for temporary one-time secret payloads."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ALGORITHM = "AES-256-GCM"
_KEY_BYTES = 32
_NONCE_BYTES = 12


@dataclass(frozen=True, slots=True)
class EncryptedSecret:
    """Serialized encrypted secret material for temporary storage."""

    ciphertext: str
    nonce: str
    algorithm: str = _ALGORITHM
    key_version: str = "v1"


def _to_base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _from_base64url(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _derive_key(master_key: str | bytes) -> bytes:
    if isinstance(master_key, str):
        if not master_key:
            raise ValueError("master_key must be non-empty")
        try:
            raw = _from_base64url(master_key)
        except Exception:
            raw = master_key.encode("utf-8")
    else:
        raw = master_key

    if not raw:
        raise ValueError("master_key must be non-empty")

    if len(raw) == _KEY_BYTES:
        return raw

    return hashlib.sha256(raw).digest()


def generate_secret_key() -> str:
    """Generate URL-safe base64-encoded 256-bit key material."""
    return _to_base64url(secrets.token_bytes(_KEY_BYTES))


def encrypt_secret(
    plaintext: str | bytes,
    master_key: str | bytes,
    associated_data: bytes | None = None,
) -> EncryptedSecret:
    """Encrypt plaintext using AES-256-GCM with a fresh random nonce."""
    if isinstance(plaintext, str):
        plaintext_bytes = plaintext.encode("utf-8")
    else:
        plaintext_bytes = plaintext

    if not plaintext_bytes:
        raise ValueError("plaintext must be non-empty")

    key = _derive_key(master_key)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, associated_data)
    return EncryptedSecret(ciphertext=_to_base64url(ciphertext), nonce=_to_base64url(nonce))


def decrypt_secret(
    encrypted: EncryptedSecret,
    master_key: str | bytes,
    associated_data: bytes | None = None,
) -> bytes:
    """Decrypt an EncryptedSecret; cryptography exceptions signal auth/decryption failures."""
    if encrypted.algorithm != _ALGORITHM:
        raise ValueError(f"unsupported algorithm: {encrypted.algorithm}")

    key = _derive_key(master_key)
    nonce = _from_base64url(encrypted.nonce)
    ciphertext = _from_base64url(encrypted.ciphertext)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data)
