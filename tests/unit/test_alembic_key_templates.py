from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = Path("migrations/versions/0009_key_templates.py")


def test_key_templates_migration_adds_safe_template_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "key_templates" in source
    assert "key_template_revisions" in source
    assert "calibration_proposal" in source
    assert "hosted_capabilities_requiring_review" in source
    assert "allowed_hosted_capabilities" in source
    assert "prompt" not in source
    assert "completion" not in source
    assert "raw_request" not in source
    assert "raw_response" not in source
