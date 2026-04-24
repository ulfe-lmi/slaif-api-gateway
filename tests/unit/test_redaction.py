from slaif_gateway.utils.redaction import redact_database_url


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url("postgresql+asyncpg://alice:supersecret@localhost:5432/slaif")

    assert "supersecret" not in redacted
    assert "***" in redacted


def test_redact_database_url_handles_missing_value() -> None:
    assert redact_database_url(None) == "<not set>"
