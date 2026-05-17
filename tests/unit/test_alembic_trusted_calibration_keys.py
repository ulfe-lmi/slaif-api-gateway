from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = Path("migrations/versions/0008_trusted_calibration_keys.py")


def test_trusted_calibration_key_migration_adds_safe_policy_columns() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "key_purpose" in source
    assert "capability_policy_mode" in source
    assert "calibration_metadata" in source
    assert "trusted_calibration" in source
    assert "trusted_calibration_discovery" in source
    assert "prompt" not in source
    assert "completion" not in source
    assert "raw_request" not in source
    assert "raw_response" not in source
