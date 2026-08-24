from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION = Path("migrations/versions/0024_quota_reservation_accounting_facts.py")
REVISION = "0024_quota_reservation_accounting_facts"
DOWN_REVISION = "0023_module_provider_foundation"


def test_quota_reservation_accounting_facts_is_a_single_nullable_upgrade() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }
    assert assignments == {"revision": REVISION, "down_revision": DOWN_REVISION}
    assert source.count("op.add_column(\"quota_reservations\"") == 3
    assert source.count("op.drop_column(\"quota_reservations\"") == 3
    assert source.count("nullable=True") == 3
    assert "op.drop_table" not in source


def test_alembic_chain_has_one_head_and_0024_downgrades_to_0023() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == DOWN_REVISION
