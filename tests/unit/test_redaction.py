from slaif_gateway.utils.redaction import (
    redact_authorization_header,
    redact_database_url,
    redact_mapping,
    redact_text,
)


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url("postgresql+asyncpg://alice:supersecret@localhost:5432/slaif")

    assert "supersecret" not in redacted
    assert "***" in redacted


def test_redact_database_url_handles_missing_value() -> None:
    assert redact_database_url(None) == "<not set>"


def test_redact_authorization_header_hides_bearer_token() -> None:
    redacted = redact_authorization_header("Bearer sk-slaif-public.secret-value")

    assert redacted == "Bearer ***"
    assert "secret-value" not in redacted


def test_redact_mapping_hides_secret_like_fields_and_keeps_safe_fields() -> None:
    payload = {
        "Authorization": "Bearer sk-slaif-public.secret-value",
        "api_key": "abc1234567890",
        "password": "supersecret",
        "name": "alice",
        "nested": {
            "csrf_token": "csrf-secret",
            "count": 3,
        },
    }

    redacted = redact_mapping(payload)

    assert "secret-value" not in redacted["Authorization"]
    assert redacted["name"] == "alice"
    assert redacted["nested"]["count"] == 3
    assert "csrf-secret" not in redacted["nested"]["csrf_token"]


def test_redact_mapping_handles_nested_sensitive_key_variants() -> None:
    payload = {
        "providerApiKey": "sk-proj-providersecret123456789",
        "nested": {
            "authorization-header": "Bearer sk-slaif-public123.secretsecretsecret",
            "token_hash": "hash-secret",
            "encryptedPayload": "payload-secret",
            "sessionCookie": "session-secret",
            "safe": "provider=openai",
        },
        "list": [
            {"csrfToken": "csrf-secret"},
            "gateway key sk-acme-prod-public123.secretsecretsecret",
        ],
    }

    redacted = redact_mapping(payload, accepted_gateway_key_prefixes=("sk-acme-prod-",))
    serialized = str(redacted)

    assert "providersecret" not in serialized
    assert "secretsecretsecret" not in serialized
    assert "hash-secret" not in serialized
    assert "payload-secret" not in serialized
    assert "session-secret" not in serialized
    assert "csrf-secret" not in serialized
    assert redacted["nested"]["safe"] == "provider=openai"


def test_redact_text_redacts_gateway_keys_provider_keys_and_query_params() -> None:
    text = (
        "url=https://example.test/path?api_key=secret-token&safe=ok "
        "gateway=sk-acme-prod-public123.secretsecretsecret "
        "provider=sk-or-providersecret123 "
        "password=plain-secret"
    )

    redacted = redact_text(text, accepted_gateway_key_prefixes=("sk-acme-prod-",))

    assert "secret-token" not in redacted
    assert "secretsecretsecret" not in redacted
    assert "providersecret" not in redacted
    assert "plain-secret" not in redacted
    assert "safe=ok" in redacted
