import pytest

from slaif_gateway.services.security import (
    AbuseTracker, SECURITY_HEADERS, provider_base_url_is_safe,
    safe_admin_redirect, validate_secret_strength,
)


def test_security_headers_are_complete():
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in SECURITY_HEADERS["Content-Security-Policy"]


def test_abuse_tracker_locks_after_threshold():
    tracker = AbuseTracker(max_attempts=3)
    for _ in range(2):
        tracker.record_failure("user")
    assert tracker.is_blocked("user") is False
    tracker.record_failure("user")
    assert tracker.is_blocked("user") is True
    tracker.clear("user")
    assert tracker.is_blocked("user") is False


def test_admin_redirect_rejects_open_redirects():
    assert safe_admin_redirect("//evil.example/path", set()) == "/"
    assert safe_admin_redirect("https://evil.example", set()) == "/"
    assert safe_admin_redirect("/admin/keys", set()) == "/admin/keys"


@pytest.mark.parametrize("value,expected", [
    ("https://provider.example.com", True),
    ("http://127.0.0.1", True),
    ("http://192.168.1.10/v1", False),
    ("http://user:pass@example.com", False),
])
def test_provider_base_url_boundary(value, expected):
    assert provider_base_url_is_safe(value) is expected


def test_secret_validation_fails_closed_and_rejects_defaults_in_production():
    with pytest.raises(ValueError):
        validate_secret_strength({"SECRET_A": None})
    with pytest.raises(ValueError):
        validate_secret_strength({"SECRET_B": "short"})
    with pytest.raises(ValueError):
        validate_secret_strength(
            {"SECRET_C": "a" * 40 + " example"}, production=True
        )
    assert validate_secret_strength({"GOOD": "x" * 40}) is True
