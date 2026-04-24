import pytest
from cryptography.exceptions import InvalidTag

from slaif_gateway.utils.secrets import (
    EncryptedSecret,
    decrypt_secret,
    encrypt_secret,
    generate_secret_key,
)


def test_encrypt_then_decrypt_roundtrip() -> None:
    key = generate_secret_key()
    encrypted = encrypt_secret("hello-world", key)

    assert decrypt_secret(encrypted, key) == b"hello-world"


def test_encrypting_same_plaintext_twice_differs() -> None:
    key = generate_secret_key()

    encrypted_one = encrypt_secret("same-plaintext", key)
    encrypted_two = encrypt_secret("same-plaintext", key)

    assert encrypted_one.nonce != encrypted_two.nonce
    assert encrypted_one.ciphertext != encrypted_two.ciphertext


def test_wrong_master_key_fails_decryption() -> None:
    encrypted = encrypt_secret("top-secret", generate_secret_key())

    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, generate_secret_key())


def test_wrong_associated_data_fails_decryption() -> None:
    key = generate_secret_key()
    encrypted = encrypt_secret("top-secret", key, associated_data=b"a")

    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, key, associated_data=b"b")


def test_generated_master_key_works() -> None:
    key = generate_secret_key()
    encrypted = encrypt_secret(b"binary\x00payload", key)

    assert decrypt_secret(encrypted, key) == b"binary\x00payload"


def test_ciphertext_does_not_contain_plaintext() -> None:
    key = generate_secret_key()
    plaintext = "plain-text-content"
    encrypted = encrypt_secret(plaintext, key)

    assert plaintext not in encrypted.ciphertext


def test_invalid_algorithm_is_rejected() -> None:
    key = generate_secret_key()
    encrypted = encrypt_secret("hello", key)
    tampered = EncryptedSecret(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        algorithm="AES-128-GCM",
    )

    with pytest.raises(ValueError):
        decrypt_secret(tampered, key)
