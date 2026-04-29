from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION_PATH = Path("migrations/versions/0004_email_secrets_and_background_jobs.py")


def test_fourth_migration_file_exists_and_targets_email_jobs_tables() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    for table_name in ("one_time_secrets", "email_deliveries", "background_jobs"):
        assert table_name in content

    for forbidden_name in (
        "op.create_table(\"provider_configs\"",
        "op.create_table(\"model_routes\"",
        "op.create_table(\"pricing_rules\"",
        "op.create_table(\"fx_rates\"",
        "op.create_table(\"quota_reservations\"",
        "op.create_table(\"usage_ledger\"",
    ):
        assert forbidden_name not in content


def test_fourth_migration_down_revision_points_to_third_migration() -> None:
    content = MIGRATION_PATH.read_text()

    assert 'down_revision = "0003_provider_routing_pricing_fx"' in content


def test_alembic_has_exactly_one_head_revision_after_fourth_migration() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["0006_email_delivery_attempt_state"]
