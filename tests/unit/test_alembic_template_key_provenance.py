from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = Path("migrations/versions/0010_gateway_key_template_provenance.py")


def test_gateway_key_template_provenance_migration_is_narrow_and_safe() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "template_id" in source
    assert "template_revision_id" in source
    assert "gateway_keys" in source
    assert "key_templates" in source
    assert "key_template_revisions" in source
    assert "prompt" not in source
    assert "completion" not in source
    assert "raw_request" not in source
    assert "raw_response" not in source
