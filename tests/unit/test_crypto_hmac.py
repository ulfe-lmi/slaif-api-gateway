import hmac as stdlib_hmac

import pytest

from slaif_gateway.utils.crypto import hmac_sha256_token, verify_hmac_sha256_token


def test_same_token_and_secret_give_same_digest() -> None:
    assert hmac_sha256_token("token-a", "secret-a") == hmac_sha256_token("token-a", "secret-a")


def test_different_secret_changes_digest() -> None:
    assert hmac_sha256_token("token-a", "secret-a") != hmac_sha256_token("token-a", "secret-b")


def test_different_token_changes_digest() -> None:
    assert hmac_sha256_token("token-a", "secret-a") != hmac_sha256_token("token-b", "secret-a")


def test_verification_success_and_failures() -> None:
    digest = hmac_sha256_token("token-a", "secret-a")

    assert verify_hmac_sha256_token("token-a", digest, "secret-a")
    assert not verify_hmac_sha256_token("token-b", digest, "secret-a")
    assert not verify_hmac_sha256_token("token-a", digest, "secret-b")


@pytest.mark.parametrize(
    "token,secret",
    [
        ("", "secret"),
        ("token", ""),
        ("token", b""),
    ],
)
def test_empty_token_or_secret_raises_value_error(token: str, secret: str | bytes) -> None:
    with pytest.raises(ValueError):
        hmac_sha256_token(token, secret)


def test_verify_uses_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False
    original_compare_digest = stdlib_hmac.compare_digest

    def _spy(left: str, right: str) -> bool:
        nonlocal called
        called = True
        return original_compare_digest(left, right)

    monkeypatch.setattr("slaif_gateway.utils.crypto.hmac.compare_digest", _spy)
    digest = hmac_sha256_token("token-a", "secret-a")

    assert verify_hmac_sha256_token("token-a", digest, "secret-a")
    assert called
