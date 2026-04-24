"""Helpers for redacting sensitive values in logs and CLI output."""

from sqlalchemy.engine import make_url

_REDACTED = "***"


def redact_database_url(database_url: str | None) -> str:
    """Return a redacted database URL safe for user-facing output."""
    if not database_url:
        return "<not set>"

    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return database_url.replace("//", f"//{_REDACTED}:", 1)
