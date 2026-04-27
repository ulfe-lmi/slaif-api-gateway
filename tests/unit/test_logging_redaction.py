from __future__ import annotations

from slaif_gateway.logging import _redact_event
from slaif_gateway.utils.redaction import redact_mapping, redact_text


def test_redacts_authorization_and_secret_fields() -> None:
    payload = {
        "Authorization": "Bearer sk-slaif-public.secretvalue",
        "password": "correct-horse-battery-staple",
        "cookie": "session=secret",
        "csrf_token": "csrf-secret",
        "session_token": "session-secret",
        "token_hash": "hash-secret",
        "encrypted_payload": "payload-secret",
        "nonce": "nonce-secret",
        "safe": "ordinary value",
    }

    redacted = redact_mapping(payload)

    assert "sk-slaif-public.secretvalue" not in str(redacted)
    assert "correct-horse-battery-staple" not in str(redacted)
    assert "session=secret" not in str(redacted)
    assert "csrf-secret" not in str(redacted)
    assert "hash-secret" not in str(redacted)
    assert redacted["safe"] == "ordinary value"


def test_redacts_bearer_tokens_and_gateway_keys_in_text() -> None:
    text = "Authorization: Bearer sk-slaif-public.secretvalue provider sk-or-secretvalue"

    redacted = redact_text(text)

    assert "sk-slaif-public.secretvalue" not in redacted
    assert "sk-or-secretvalue" not in redacted
    assert "***" in redacted


def test_structlog_redaction_processor_redacts_event_dict() -> None:
    event = _redact_event(
        None,
        "info",
        {
            "event": "forwarding with Bearer sk-slaif-public.secretvalue",
            "api_key": "provider-secret",
            "model": "gpt-test-mini",
        },
    )

    assert "sk-slaif-public.secretvalue" not in str(event)
    assert "provider-secret" not in str(event)
    assert event["model"] == "gpt-test-mini"


def test_structlog_redaction_processor_redacts_custom_prefix_and_nested_fields() -> None:
    event = _redact_event(
        None,
        "info",
        {
            "event": "forwarding sk-acme-prod-public123.secretsecretsecret",
            "request_id": "req_123",
            "provider": "openrouter",
            "nested": {
                "providerApiKey": "sk-or-providersecret123",
                "sessionCookie": "session-secret",
            },
        },
        accepted_gateway_key_prefixes=("sk-acme-prod-",),
    )
    serialized = str(event)

    assert "secretsecretsecret" not in serialized
    assert "providersecret" not in serialized
    assert "session-secret" not in serialized
    assert event["request_id"] == "req_123"
    assert event["provider"] == "openrouter"
