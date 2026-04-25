from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION_PATH = Path("migrations/versions/0002_quota_reservations_and_usage_ledger.py")


def test_second_migration_file_exists_and_targets_only_accounting_tables() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    assert "quota_reservations" in content
    assert "usage_ledger" in content

    for table_name in (
        "provider_configs",
        "model_routes",
        "pricing_rules",
        "fx_rates",
        "one_time_secrets",
        "email_deliveries",
        "background_jobs",
    ):
        assert table_name not in content


def test_second_migration_down_revision_points_to_first_migration() -> None:
    content = MIGRATION_PATH.read_text()

    assert 'down_revision = "0001_foundational_identity_and_keys"' in content


def test_alembic_has_exactly_one_head_revision() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["0005_fix_gateway_key_prefix_default"]
