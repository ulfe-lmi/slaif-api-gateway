"""Migration-head tests for the request_diagnostics table (0026)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION_PATH = Path("migrations/versions/0026_request_diagnostics.py")


def test_request_diagnostics_migration_file_exists() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    assert "def upgrade() -> None:" in content
    assert "def downgrade() -> None:" in content
    assert 'op.create_table(\n        "request_diagnostics"' in content or (
        'op.create_table(' in content and '"request_diagnostics"' in content
    )
    # Stable unique server diagnostic ID + bounded content-free facts.
    assert "uq_request_diagnostics_gateway_request_id" in content
    assert "request_diagnostics_stream_outcome_allowed" in content
    assert "request_diagnostics_client_id_reason_allowed" in content
    assert "request_diagnostics_positions_bounded" in content
    assert "request_diagnostics_facts_payload_8kib" in content
    # PostgreSQL 16 compatibility: no jsonb_object_length (PG17+ only).
    assert "jsonb_object_length" not in content
    # Absent facts store SQL NULL, not JSON null.
    assert "none_as_null=True" in content


def test_request_diagnostics_down_revision_points_to_0025() -> None:
    content = MIGRATION_PATH.read_text()
    assert 'revision = "0026_request_diagnostics"' in content
    assert 'down_revision = "0025_catalog_refresh_applications"' in content


def test_alembic_has_exactly_one_head_after_request_diagnostics() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0026_request_diagnostics"]


def test_request_diagnostics_downgrade_drops_table_and_constraints() -> None:
    content = MIGRATION_PATH.read_text()
    downgrade = content.split("def downgrade() -> None:")[1]
    assert 'op.drop_table("request_diagnostics")' in downgrade
    assert "uq_request_diagnostics_gateway_request_id" in downgrade
    assert "ix_request_diagnostics_occurred_at" in downgrade
    assert "ix_request_diagnostics_client_request_id" in downgrade
