import pytest

from slaif_gateway.utils.crypto import (
    generate_gateway_key,
    is_plausible_gateway_key,
    parse_gateway_key_public_id,
    redact_gateway_key,
)


def test_generate_gateway_key_uses_supplied_prefix() -> None:
    generated = generate_gateway_key(prefix="sk-slaif-")

    assert generated.plaintext_key.startswith("sk-slaif-")
    assert "." in generated.plaintext_key
    assert parse_gateway_key_public_id(generated.plaintext_key, ("sk-slaif-",)) == generated.public_key_id


def test_generate_gateway_key_uniqueness() -> None:
    keys = {generate_gateway_key(prefix="sk-slaif-").plaintext_key for _ in range(200)}

    assert len(keys) == 200


@pytest.mark.parametrize(
    "key",
    [
        "",
        "sk-slaif-no-dot",
        "sk-slaif-.nosecret",
        "sk-slaif-public.",
        "sk-wrong-public.secret",
        "sk-slaif-public.abc",
    ],
)
def test_malformed_keys_are_rejected(key: str) -> None:
    assert not is_plausible_gateway_key(key, ("sk-slaif-",))

    with pytest.raises(ValueError):
        parse_gateway_key_public_id(key, ("sk-slaif-",))


def test_parser_rejects_unconfigured_prefix() -> None:
    key = f"{generate_gateway_key(prefix='sk-ulfe-').plaintext_key}"

    assert not is_plausible_gateway_key(key, ("sk-slaif-",))
    with pytest.raises(ValueError):
        parse_gateway_key_public_id(key, ("sk-slaif-",))


def test_parser_accepts_legacy_prefix_when_configured() -> None:
    generated = generate_gateway_key(prefix="sk-ulfe-")

    assert parse_gateway_key_public_id(generated.plaintext_key, ("sk-slaif-", "sk-ulfe-")) == generated.public_key_id


def test_redacted_key_hides_full_secret_for_custom_prefix() -> None:
    generated = generate_gateway_key(prefix="sk-custom-")
    redacted = redact_gateway_key(generated.plaintext_key, accepted_prefixes=("sk-custom-",))

    secret = generated.plaintext_key.split(".", 1)[1]
    assert secret not in redacted
    assert secret[:4] not in redacted
    assert secret[-4:] not in redacted
    assert redacted.endswith(".***")
    assert redacted.startswith(f"sk-custom-{generated.public_key_id}.")


def test_redacted_key_uses_generic_fallback_for_unknown_prefix() -> None:
    generated = generate_gateway_key(prefix="sk-acme-prod-")
    redacted = redact_gateway_key(generated.plaintext_key)
    secret = generated.plaintext_key.split(".", 1)[1]

    assert redacted == f"sk-acme-prod-{generated.public_key_id}.***"
    assert secret not in redacted
    assert secret[:4] not in redacted
    assert secret[-4:] not in redacted


def test_redacted_key_accepts_legacy_prefix_when_configured() -> None:
    generated = generate_gateway_key(prefix="sk-ulfe-")
    redacted = redact_gateway_key(
        generated.plaintext_key,
        accepted_prefixes=("sk-slaif-", "sk-ulfe-"),
    )
    secret = generated.plaintext_key.split(".", 1)[1]

    assert redacted == f"sk-ulfe-{generated.public_key_id}.***"
    assert secret not in redacted
