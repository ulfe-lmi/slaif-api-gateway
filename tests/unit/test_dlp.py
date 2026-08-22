import pytest

from slaif_gateway.services.dlp import scan


def test_block_mode_blocks_email_and_reports_only_redacted_finding():
    decision = scan("contact user@example.com", action="block")
    assert decision.blocked is True
    assert decision.findings[0].detector == "email"
    assert "user@example.com" not in repr(decision.findings)


@pytest.mark.parametrize("payload,detector", [
    ("call +1 555 123 4567", "phone"),
    ("card 4111 1111 1111 1111", "credit_card"),
    ("ssn 123-45-6789", "ssn"),
])
def test_detectors_identify_safe_test_patterns(payload, detector):
    decision = scan(payload, action="flag")
    assert detector in {finding.detector for finding in decision.findings}


def test_flag_allows_but_reports_findings():
    decision = scan("mail a@b.co", action="flag")
    assert decision.blocked is False
    assert decision.findings


def test_monitor_has_no_match_without_findings():
    decision = scan("safe text", action="monitor")
    assert decision.blocked is False
    assert decision.findings == ()


def test_invalid_payload_is_rejected():
    with pytest.raises(TypeError):
        scan(b"bytes", action="block")  # type: ignore[arg-type]
