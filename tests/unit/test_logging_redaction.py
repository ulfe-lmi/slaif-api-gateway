from __future__ import annotations

import json

import structlog

from slaif_gateway.config import Settings
from slaif_gateway.logging import configure_logging
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


def test_redacts_sensitive_assignments_in_free_text() -> None:
    text = (
        "plaintext_key=sk-slaif-public.secretsecret provider_key=sk-or-providersecret123 "
        "Authorization=Bearer session-token-secret csrf_token=csrf-secret "
        "session_token=session-secret encrypted_payload=payload-secret nonce=nonce-secret"
    )

    redacted = redact_text(text)

    for forbidden in (
        "secretsecret",
        "providersecret",
        "session-token-secret",
        "csrf-secret",
        "session-secret",
        "payload-secret",
        "nonce-secret",
    ):
        assert forbidden not in redacted


def test_debug_log_level_allows_debug_events(capsys) -> None:
    configure_logging(Settings(APP_ENV="test", DATABASE_URL=None, LOG_LEVEL="DEBUG", STRUCTURED_LOGS=True))

    structlog.get_logger("tests.logging").debug("debug.visible", marker="debug-marker")

    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["event"] == "debug.visible"
    assert event["level"] == "debug"
    assert event["marker"] == "debug-marker"


def test_info_log_level_filters_debug_but_allows_info(capsys) -> None:
    configure_logging(Settings(APP_ENV="test", DATABASE_URL=None, LOG_LEVEL="INFO", STRUCTURED_LOGS=True))

    log = structlog.get_logger("tests.logging")
    log.debug("debug.hidden")
    log.info("info.visible")

    output = capsys.readouterr().out
    assert "debug.hidden" not in output
    event = json.loads(output.strip().splitlines()[-1])
    assert event["event"] == "info.visible"
    assert event["level"] == "info"
