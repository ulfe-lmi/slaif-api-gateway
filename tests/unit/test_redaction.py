from slaif_gateway.utils.redaction import (
    redact_authorization_header,
    redact_database_url,
    redact_mapping,
)


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url("postgresql+asyncpg://alice:supersecret@localhost:5432/slaif")

    assert "supersecret" not in redacted
    assert "***" in redacted


def test_redact_database_url_handles_missing_value() -> None:
    assert redact_database_url(None) == "<not set>"


def test_redact_authorization_header_hides_bearer_token() -> None:
    redacted = redact_authorization_header("Bearer sk-slaif-public.secret-value")

    assert redacted.startswith("Bearer ")
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
