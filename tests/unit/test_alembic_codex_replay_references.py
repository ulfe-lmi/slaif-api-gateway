from __future__ import annotations

from pathlib import Path

from slaif_gateway.db.models import Base


MIGRATION_PATH = Path("migrations/versions/0013_codex_replay_references.py")


def test_codex_replay_model_has_exact_hmac_only_contract() -> None:
    table = Base.metadata.tables["codex_replay_references"]
    assert set(table.columns.keys()) == {
        "id",
        "gateway_key_id",
        "usage_ledger_id",
        "source_request_id",
        "provider",
        "route_id",
        "upstream_model",
        "item_kind",
        "item_id_hmac",
        "call_id_hmac",
        "hmac_key_version",
        "tool_namespace",
        "tool_name",
        "created_at",
        "expires_at",
    }
    assert table.c.item_id_hmac.type.length == 64
    assert table.c.call_id_hmac.type.length == 64
    assert table.c.item_id_hmac.nullable is False
    assert table.c.call_id_hmac.nullable is True
    assert {
        foreign_key.ondelete
        for column in (table.c.gateway_key_id, table.c.usage_ledger_id, table.c.route_id)
        for foreign_key in column.foreign_keys
    } == {"RESTRICT"}
    assert "encrypted_content" not in table.columns
    assert "summary" not in table.columns
    assert "arguments" not in table.columns
    assert "output" not in table.columns


def test_codex_replay_model_constraints_and_indexes_match_schema_contract() -> None:
    table = Base.metadata.tables["codex_replay_references"]
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}
    required_constraint_suffixes = {
        "uq_codex_replay_references_key_kind_item",
        "uq_codex_replay_references_key_kind_call",
        "codex_replay_references_item_kind_allowed_values",
        "codex_replay_references_item_hmac_format",
        "codex_replay_references_call_hmac_format",
        "codex_replay_references_kind_shape",
        "codex_replay_references_expiry_after_creation",
    }
    assert all(
        any(str(name).endswith(suffix) for name in constraint_names)
        for suffix in required_constraint_suffixes
    )
    assert index_names == {
        "ix_codex_replay_references_key_kind_item_expiry",
        "ix_codex_replay_references_key_kind_call_expiry",
        "ix_codex_replay_references_usage_ledger_id",
        "ix_codex_replay_references_expires_at",
    }


def test_codex_replay_migration_is_single_narrow_successor() -> None:
    content = MIGRATION_PATH.read_text()
    assert 'revision = "0013_codex_replay_references"' in content
    assert 'down_revision = "0012_conversation_references"' in content
    assert '"codex_replay_references"' in content
    assert 'ondelete="RESTRICT"' in content
    assert "encrypted_content" not in content
    assert "reasoning_text" not in content
    assert "tool_output" not in content
