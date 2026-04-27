from slaif_gateway.utils.crypto import generate_gateway_key
from slaif_gateway.utils.redaction import redact_text


def test_redaction_recognizes_configured_custom_gateway_prefix() -> None:
    generated = generate_gateway_key(prefix="sk-acme-prod-")
    redacted = redact_text(
        f"created {generated.plaintext_key}",
        accepted_gateway_key_prefixes=("sk-acme-prod-",),
    )
    secret = generated.plaintext_key.split(".", 1)[1]

    assert f"sk-acme-prod-{generated.public_key_id}.***" in redacted
    assert secret not in redacted
    assert secret[:4] not in redacted
    assert secret[-4:] not in redacted


def test_generic_gateway_key_fallback_redacts_unknown_prefix() -> None:
    generated = generate_gateway_key(prefix="sk-lab-")
    redacted = redact_text(f"created {generated.plaintext_key}")
    secret = generated.plaintext_key.split(".", 1)[1]

    assert f"sk-lab-{generated.public_key_id}.***" in redacted
    assert secret not in redacted
