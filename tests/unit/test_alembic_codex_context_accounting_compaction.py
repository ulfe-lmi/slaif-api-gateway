from __future__ import annotations

from pathlib import Path

from slaif_gateway.db.models import Base, KIND_VALUES_CODEX_REPLAY_REFERENCES


MIGRATION_PATH = Path("migrations/versions/0014_codex_context_accounting_compaction.py")


def test_0014_is_single_successor_and_changes_only_replay_kind_shape() -> None:
    content = MIGRATION_PATH.read_text()
    assert 'revision = "0014_codex_context_accounting_compaction"' in content
    assert 'down_revision = "0013_codex_replay_references"' in content
    assert "op.add_column" not in content
    assert "encrypted_content" not in content
    assert "compaction" in content


def test_model_allows_compaction_without_content_columns() -> None:
    table = Base.metadata.tables["codex_replay_references"]
    assert "compaction" in KIND_VALUES_CODEX_REPLAY_REFERENCES
    assert "encrypted_content" not in table.columns
    assert "content_hmac" not in table.columns
    kind_shape = next(
        constraint
        for constraint in table.constraints
        if str(constraint.name).endswith("codex_replay_references_kind_shape")
    )
    assert "compaction" in str(kind_shape.sqltext)
