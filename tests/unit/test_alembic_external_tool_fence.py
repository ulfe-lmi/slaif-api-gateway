from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from slaif_gateway.db.models import Base

MIGRATION_PATH = Path("migrations/versions/0015_external_tool_exclusive_fence.py")


def test_migration_file_exists_and_targets_only_fence_foundation() -> None:
    assert MIGRATION_PATH.exists()
    content = MIGRATION_PATH.read_text()

    assert 'revision = "0015_external_tool_exclusive_fence"' in content
    assert 'down_revision = "0014_codex_context_accounting_compaction"' in content

    for table_name in (
        "provider_configs",
        "pricing_rules",
        "fx_rates",
        "one_time_secrets",
        "email_deliveries",
        "background_jobs",
        "codex_replay_references",
    ):
        assert table_name not in content

    # ``model_routes`` may only appear as the RESTRICT target of the fence
    # reservation route pointer, never as a modified table.
    assert 'sa.ForeignKey("model_routes.id", ondelete="RESTRICT")' in content
    assert '"model_routes",' not in content

    # The 012 stored-policy JSON field name must not appear: 0015 adds only the
    # fence foundation columns, not a new external_tool_policy column.
    assert "external_tool_policy" not in content


def test_alembic_has_exactly_one_head_revision_after_fence_migration() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["0023_module_provider_foundation"]


def test_fence_migration_adds_only_the_fence_foundation_columns() -> None:
    content = MIGRATION_PATH.read_text()

    for column in (
        "external_tool_fence_state",
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
        "quota_mode",
        "external_tool_capabilities",
        "external_tool_destination_ids",
        "external_tool_provider",
        "external_tool_route_id",
    ):
        assert f'"{column}"' in content

    assert "server_default=sa.text(\"'none'\")" in content
    assert "server_default=sa.text(\"'strict_bounded'\")" in content
    assert "sa.text(\"'[]'::jsonb\")" in content
    assert 'sa.ForeignKey("quota_reservations.id", ondelete="RESTRICT")' in content
    assert 'sa.ForeignKey("model_routes.id", ondelete="RESTRICT")' in content

    for constraint in (
        "quota_reservations_external_tool_facts_array_shape",
        "quota_reservations_strict_mode_empty_external_facts",
        "quota_reservations_fenced_mode_bound_facts",
    ):
        assert constraint in content

    assert "ix_gateway_keys_external_tool_fence_reservation_id_unique" in content
    assert "unique=True" in content


def test_fence_migration_downgrade_drops_only_new_objects() -> None:
    content = MIGRATION_PATH.read_text()
    downgrade = content.split("def downgrade() -> None:", 1)[1]

    assert "op.drop_index(" in downgrade
    assert "ix_gateway_keys_external_tool_fence_state_expires_at" in downgrade
    for object_name in (
        "gateway_keys_external_tool_fence_state_allowed_values",
        "gateway_keys_external_tool_fence_none_shape",
        "gateway_keys_external_tool_fence_bound_shape",
        "quota_reservations_quota_mode_allowed_values",
        "quota_reservations_external_tool_facts_array_shape",
        "quota_reservations_strict_mode_empty_external_facts",
        "quota_reservations_fenced_mode_bound_facts",
    ):
        assert object_name in downgrade
    assert "ix_gateway_keys_external_tool_fence_reservation_id_unique" in downgrade
    # Each index/constraint must be dropped before the columns it references.
    assert downgrade.index("op.drop_constraint(") < downgrade.index("op.drop_column(")
    assert downgrade.index('"ix_gateway_keys_external_tool_fence_reservation_id_unique"') < (
        downgrade.index('"external_tool_fence_reservation_id"')
    )
    assert downgrade.index('"ix_gateway_keys_external_tool_fence_state_expires_at"') < (
        downgrade.index('"external_tool_fence_state"')
    )
    for column in (
        "external_tool_fence_state",
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
        "quota_mode",
        "external_tool_capabilities",
        "external_tool_destination_ids",
        "external_tool_provider",
        "external_tool_route_id",
    ):
        assert "op.drop_column(" in downgrade
        assert f'"{column}"' in downgrade
    # No destructive statements targeting other tables.
    assert "op.drop_table(" not in downgrade


def test_gateway_key_model_carries_exact_fence_contract() -> None:
    table = Base.metadata.tables["gateway_keys"]
    for column in (
        "external_tool_fence_state",
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
    ):
        assert column in table.columns, column
    assert table.c.external_tool_fence_state.nullable is False
    for column in (
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
    ):
        assert table.c[column].nullable is True, column

    constraint_names = {
        str(name) for name in (constraint.name for constraint in table.constraints) if name
    }
    for required in (
        "gateway_keys_external_tool_fence_state_allowed_values",
        "gateway_keys_external_tool_fence_none_shape",
        "gateway_keys_external_tool_fence_bound_shape",
    ):
        assert any(name.endswith(required) for name in constraint_names), required

    index_names = {str(index.name) for index in table.indexes}
    assert any(
        name.endswith("ix_gateway_keys_external_tool_fence_state_expires_at")
        for name in index_names
    )
    unique_index = next(
        (
            index
            for index in table.indexes
            if str(index.name).endswith("ix_gateway_keys_external_tool_fence_reservation_id_unique")
        ),
        None,
    )
    assert unique_index is not None
    assert unique_index.unique is True
    assert [column.name for column in unique_index.columns] == ["external_tool_fence_reservation_id"]

    reservation_fk = table.c.external_tool_fence_reservation_id.foreign_keys
    assert len(reservation_fk) == 1
    assert next(iter(reservation_fk)).ondelete == "RESTRICT"


def test_quota_reservation_model_carries_exact_fence_contract() -> None:
    table = Base.metadata.tables["quota_reservations"]
    for column in (
        "quota_mode",
        "external_tool_capabilities",
        "external_tool_destination_ids",
        "external_tool_provider",
        "external_tool_route_id",
    ):
        assert column in table.columns, column
    assert table.c.quota_mode.nullable is False
    assert table.c.external_tool_capabilities.nullable is False
    assert table.c.external_tool_destination_ids.nullable is False
    assert table.c.external_tool_provider.nullable is True
    assert table.c.external_tool_route_id.nullable is True

    route_fk = table.c.external_tool_route_id.foreign_keys
    assert len(route_fk) == 1
    assert next(iter(route_fk)).ondelete == "RESTRICT"

    constraint_names = {
        str(name) for name in (constraint.name for constraint in table.constraints) if name
    }
    for required in (
        "quota_reservations_quota_mode_allowed_values",
        "quota_reservations_external_tool_facts_array_shape",
        "quota_reservations_strict_mode_empty_external_facts",
        "quota_reservations_fenced_mode_bound_facts",
    ):
        assert any(name.endswith(required) for name in constraint_names), required
    assert "quota_reservations_fenced_mode_nonempty_capabilities" not in constraint_names


def test_models_module_no_longer_imports_remote() -> None:
    """The 014-a string primaryjoin did not resolve `remote` from the module namespace;
    The explicit foreign_keys disambiguation removes the dead import entirely.
    """
    source = Path(__file__).resolve().parents[2] / "app/slaif_gateway/db/models.py"
    content = source.read_text()
    assert "remote(" not in content
    assert "    remote" not in content
