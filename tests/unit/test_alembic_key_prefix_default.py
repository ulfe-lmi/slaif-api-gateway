from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION_PATH = Path("migrations/versions/0005_fix_gateway_key_prefix_default.py")


def test_fifth_migration_exists_and_mentions_gateway_key_prefix() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    assert "gateway_keys" in content
    assert "key_prefix" in content
    assert "sk-slaif-" in content


def test_fifth_migration_down_revision_points_to_fourth_migration() -> None:
    content = MIGRATION_PATH.read_text()

    assert 'down_revision = "0004_email_secrets_and_background_jobs"' in content


def test_alembic_has_exactly_one_head_revision_after_fifth_migration() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["0006_email_delivery_attempt_state"]
