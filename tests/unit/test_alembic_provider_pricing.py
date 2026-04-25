from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION_PATH = Path("migrations/versions/0003_provider_routing_pricing_fx.py")


def test_third_migration_file_exists_and_targets_provider_pricing_tables() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    for table_name in ("provider_configs", "model_routes", "pricing_rules", "fx_rates"):
        assert table_name in content

    for forbidden_name in (
        "one_time_secrets",
        "email_deliveries",
        "background_jobs",
        "op.create_table(\"quota_reservations\"",
        "op.create_table(\"usage_ledger\"",
    ):
        assert forbidden_name not in content


def test_third_migration_down_revision_points_to_second_migration() -> None:
    content = MIGRATION_PATH.read_text()

    assert 'down_revision = "0002_quota_reservations_and_usage_ledger"' in content


def test_alembic_has_exactly_one_head_revision_after_third_migration() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["0005_fix_gateway_key_prefix_default"]
