from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_head_revision() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads


def test_first_migration_mentions_foundational_tables_only() -> None:
    migration_file = Path("migrations/versions/0001_foundational_identity_and_keys.py")
    content = migration_file.read_text()

    for table_name in (
        "institutions",
        "cohorts",
        "owners",
        "admin_users",
        "admin_sessions",
        "gateway_keys",
        "audit_log",
    ):
        assert table_name in content

    for table_name in (
        "quota_reservations",
        "usage_ledger",
        "pricing_rules",
        "model_pricing",
    ):
        assert table_name not in content
