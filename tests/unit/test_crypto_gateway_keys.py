import pytest

from slaif_gateway.utils.crypto import (
    generate_gateway_key,
    is_plausible_gateway_key,
    parse_gateway_key_public_id,
    redact_gateway_key,
)


def test_generate_gateway_key_format_and_parse() -> None:
    generated = generate_gateway_key()

    assert generated.plaintext_key.startswith("sk-ulfe-")
    assert "." in generated.plaintext_key
    assert parse_gateway_key_public_id(generated.plaintext_key) == generated.public_key_id


def test_generate_gateway_key_uniqueness() -> None:
    keys = {generate_gateway_key().plaintext_key for _ in range(200)}

    assert len(keys) == 200


@pytest.mark.parametrize(
    "key",
    [
        "",
        "sk-ulfe-no-dot",
        "sk-ulfe-.nosecret",
        "sk-ulfe-public.",
        "sk-wrong-public.secret",
        "sk-ulfe-public.abc",
    ],
)
def test_malformed_keys_are_rejected(key: str) -> None:
    assert not is_plausible_gateway_key(key)

    with pytest.raises(ValueError):
        parse_gateway_key_public_id(key)


def test_redacted_key_hides_full_secret() -> None:
    generated = generate_gateway_key()
    redacted = redact_gateway_key(generated.plaintext_key)

    secret = generated.plaintext_key.split(".", 1)[1]
    assert secret not in redacted
    assert redacted.startswith(f"sk-ulfe-{generated.public_key_id}.")
