"""Unit tests for the 222 demo-copy sanitizer and independent verifier.

No database, network or provider is involved: the policy, remappings,
catalog fail-closed gates, JSONB shape validators, bounded pre-state and
the custody/manifest orchestration are exercised with fake connections.
The real PostgreSQL 16 source+target behavior is covered by
tests/integration/test_demo_snapshot_sanitize_postgres.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_sanitize as dsan

# ---------------------------------------------------------------------------
# Frozen 222 checkpoint catalog fixture (migration head
# 0027_demo_admin_accounts): 34 public tables, 507 columns. Verified
# against the owned PG16 source at activation; the runtime inventory must
# equal the policy and the reviewed column signature exactly.
# ---------------------------------------------------------------------------

_CHECKPOINT_CATALOG: dict[str, tuple[str, ...]] = {
    "admin_sessions": (
        "id",
        "admin_user_id",
        "session_token_hash",
        "csrf_token_hash",
        "ip_address",
        "user_agent",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_seen_at",
    ),
    "admin_users": (
        "id",
        "email",
        "display_name",
        "password_hash",
        "role",
        "is_active",
        "last_login_at",
        "created_at",
        "updated_at",
        "mfa_secret",
    ),
    "alembic_version": (
        "version_num",
    ),
    "approved_catalog_entries": (
        "id",
        "revision_id",
        "entry_kind",
        "provider",
        "name",
        "metadata_json",
        "created_at",
    ),
    "audit_log": (
        "id",
        "admin_user_id",
        "action",
        "entity_type",
        "entity_id",
        "old_values",
        "new_values",
        "ip_address",
        "user_agent",
        "request_id",
        "note",
        "created_at",
    ),
    "background_jobs": (
        "id",
        "celery_task_id",
        "job_type",
        "status",
        "created_by_admin_user_id",
        "payload_summary",
        "result_summary",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    ),
    "budget_periods": (
        "id",
        "organization_id",
        "team_id",
        "project_id",
        "owner_id",
        "service_account_id",
        "name",
        "period_type",
        "period_start",
        "period_end",
        "cost_limit_eur",
        "token_limit_total",
        "request_limit_total",
        "cost_used_eur",
        "tokens_used_total",
        "requests_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "requests_reserved_total",
        "carryover_policy",
        "created_at",
        "updated_at",
    ),
    "catalog_refresh_applications": (
        "id",
        "run_id",
        "bundle_sha256",
        "receipt_hmac_sha256",
        "plan_sha256",
        "mode",
        "operator_actor",
        "db_actor",
        "admin_user_id",
        "reason",
        "effective_at",
        "applied_provider_ids",
        "applied_route_ids",
        "applied_pricing_created_ids",
        "applied_pricing_superseded_old_ids",
        "applied_pricing_superseded_new_ids",
        "applied_fx_created_ids",
        "applied_fx_superseded_old_ids",
        "applied_fx_superseded_new_ids",
        "created_providers",
        "created_routes",
        "created_pricing",
        "created_fx",
        "superseded_pricing",
        "superseded_fx",
        "outcome",
        "created_at",
    ),
    "codex_replay_references": (
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
    ),
    "cohorts": (
        "id",
        "name",
        "description",
        "starts_at",
        "ends_at",
        "created_at",
        "updated_at",
        "project_id",
    ),
    "conversation_references": (
        "id",
        "provider_conversation_id",
        "gateway_key_id",
        "owner_id",
        "institution_id",
        "cohort_id",
        "provider",
        "endpoint",
        "route_id",
        "status",
        "provider_request_id",
        "deleted_at",
        "metadata",
        "created_at",
        "updated_at",
    ),
    "email_deliveries": (
        "id",
        "owner_id",
        "gateway_key_id",
        "one_time_secret_id",
        "recipient_email",
        "subject",
        "template_name",
        "status",
        "provider_message_id",
        "error_message",
        "created_at",
        "sent_at",
        "failed_at",
    ),
    "fx_rates": (
        "id",
        "base_currency",
        "quote_currency",
        "rate",
        "valid_from",
        "valid_until",
        "source",
        "created_at",
    ),
    "gateway_keys": (
        "id",
        "public_key_id",
        "key_prefix",
        "key_hint",
        "token_hash",
        "hash_algorithm",
        "hmac_key_version",
        "owner_id",
        "cohort_id",
        "status",
        "valid_from",
        "valid_until",
        "cost_limit_eur",
        "token_limit_total",
        "request_limit_total",
        "cost_used_eur",
        "tokens_used_total",
        "requests_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "requests_reserved_total",
        "rate_limit_requests_per_minute",
        "rate_limit_tokens_per_minute",
        "max_concurrent_requests",
        "allow_all_models",
        "allowed_models",
        "allow_all_endpoints",
        "allowed_endpoints",
        "metadata",
        "last_used_at",
        "last_quota_reset_at",
        "quota_reset_count",
        "created_by_admin_user_id",
        "created_at",
        "updated_at",
        "revoked_at",
        "revoked_reason",
        "key_purpose",
        "capability_policy_mode",
        "calibration_metadata",
        "template_id",
        "template_revision_id",
        "external_tool_fence_state",
        "external_tool_fence_reservation_id",
        "external_tool_fence_request_id",
        "external_tool_fence_acquired_at",
        "external_tool_fence_expires_at",
        "service_owner_id",
        "service_name",
        "rotated_at",
        "max_validity_days",
    ),
    "institutions": (
        "id",
        "name",
        "country",
        "notes",
        "created_at",
        "updated_at",
        "organization_id",
    ),
    "key_template_revisions": (
        "id",
        "template_id",
        "revision_number",
        "created_by_admin_id",
        "created_at",
        "source_type",
        "source_calibration_gateway_key_id",
        "source_time_window_start",
        "source_time_window_end",
        "source_multiplier",
        "allowed_endpoints",
        "allowed_models",
        "allowed_providers",
        "allowed_hosted_capabilities",
        "hosted_capabilities_requiring_review",
        "request_limit_total",
        "token_limit_total",
        "input_token_limit_total",
        "output_token_limit_total",
        "reasoning_token_limit_total",
        "cost_limit_eur",
        "max_input_tokens_per_request",
        "max_output_tokens_per_request",
        "max_total_tokens_per_request",
        "max_single_request_cost_eur",
        "rate_limit_policy",
        "validity_days_default",
        "email_delivery_mode_default",
        "template_snapshot",
        "created_audit_log_id",
    ),
    "key_templates": (
        "id",
        "name",
        "description",
        "status",
        "created_by_admin_id",
        "created_at",
        "updated_at",
        "archived_at",
        "archived_by_admin_id",
        "notes",
        "current_revision_id",
    ),
    "model_routes": (
        "id",
        "requested_model",
        "match_type",
        "endpoint",
        "provider",
        "upstream_model",
        "priority",
        "enabled",
        "visible_in_models",
        "supports_streaming",
        "capabilities",
        "notes",
        "created_at",
        "updated_at",
    ),
    "oidc_identities": (
        "id",
        "owner_id",
        "issuer_url",
        "subject",
        "email",
        "created_at",
    ),
    "one_time_secrets": (
        "id",
        "purpose",
        "owner_id",
        "gateway_key_id",
        "encrypted_payload",
        "nonce",
        "encryption_key_version",
        "expires_at",
        "consumed_at",
        "status",
        "created_at",
    ),
    "organizations": (
        "id",
        "name",
        "slug",
        "notes",
        "created_at",
        "updated_at",
    ),
    "owners": (
        "id",
        "name",
        "surname",
        "email",
        "institution_id",
        "external_id",
        "notes",
        "is_active",
        "anonymized_at",
        "created_at",
        "updated_at",
    ),
    "policy_bundle_revisions": (
        "id",
        "bundle_id",
        "revision",
        "policy_json",
        "created_at",
    ),
    "policy_bundles": (
        "id",
        "organization_id",
        "team_id",
        "project_id",
        "name",
        "created_at",
    ),
    "pricing_rules": (
        "id",
        "provider",
        "upstream_model",
        "endpoint",
        "currency",
        "input_price_per_1m",
        "cached_input_price_per_1m",
        "output_price_per_1m",
        "reasoning_price_per_1m",
        "request_price",
        "pricing_metadata",
        "valid_from",
        "valid_until",
        "enabled",
        "source_url",
        "notes",
        "created_at",
        "updated_at",
    ),
    "projects": (
        "id",
        "team_id",
        "name",
        "slug",
        "description",
        "starts_at",
        "ends_at",
        "created_at",
        "updated_at",
    ),
    "provider_configs": (
        "id",
        "provider",
        "display_name",
        "kind",
        "base_url",
        "api_key_env_var",
        "enabled",
        "timeout_seconds",
        "max_retries",
        "notes",
        "created_at",
        "updated_at",
        "governance_region",
        "retention_policy",
        "training_use",
        "zdr_claimed",
        "tool_destinations",
        "evidence_date",
        "reviewer",
    ),
    "quota_reservations": (
        "id",
        "gateway_key_id",
        "request_id",
        "endpoint",
        "requested_model",
        "reserved_cost_eur",
        "reserved_tokens",
        "reserved_requests",
        "status",
        "created_at",
        "expires_at",
        "finalized_at",
        "released_at",
        "quota_mode",
        "external_tool_capabilities",
        "external_tool_destination_ids",
        "external_tool_provider",
        "external_tool_route_id",
        "provider",
        "resolved_model",
        "streaming",
    ),
    "request_diagnostics": (
        "id",
        "gateway_request_id",
        "client_request_id",
        "client_id_unavailable_reason",
        "method",
        "endpoint_template",
        "occurred_at",
        "http_status",
        "stream_outcome",
        "source",
        "reason_code",
        "error_code",
        "error_param",
        "positions",
        "counts",
        "limits",
        "gateway_key_id",
        "route_id",
        "route_pattern",
        "deployment_revision",
        "estimated_input_tokens",
        "output_allowance_tokens",
        "context_window_tokens",
        "replay_error_code",
        "recorded_at",
    ),
    "response_references": (
        "id",
        "provider_response_id",
        "gateway_key_id",
        "owner_id",
        "institution_id",
        "cohort_id",
        "provider",
        "requested_model",
        "upstream_model",
        "endpoint",
        "route_id",
        "status",
        "provider_request_id",
        "expires_at",
        "deleted_at",
        "metadata",
        "created_at",
        "updated_at",
    ),
    "team_members": (
        "team_id",
        "owner_id",
        "role",
        "created_at",
    ),
    "teams": (
        "id",
        "organization_id",
        "name",
        "slug",
        "notes",
        "created_at",
        "updated_at",
    ),
    "usage_ledger": (
        "id",
        "request_id",
        "client_request_id",
        "idempotency_key",
        "quota_reservation_id",
        "gateway_key_id",
        "owner_id",
        "institution_id",
        "cohort_id",
        "owner_email_snapshot",
        "owner_name_snapshot",
        "owner_surname_snapshot",
        "institution_name_snapshot",
        "cohort_name_snapshot",
        "endpoint",
        "http_method",
        "provider",
        "requested_model",
        "resolved_model",
        "upstream_request_id",
        "streaming",
        "success",
        "accounting_status",
        "http_status",
        "error_type",
        "error_message",
        "prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "total_tokens",
        "estimated_cost_eur",
        "actual_cost_eur",
        "actual_cost_native",
        "native_currency",
        "usage_raw",
        "response_metadata",
        "started_at",
        "finished_at",
        "latency_ms",
        "created_at",
    ),
    "usage_profiles": (
        "id",
        "usage_ledger_id",
        "gateway_key_id",
        "owner_id",
        "institution_id",
        "cohort_id",
        "endpoint_path",
        "provider",
        "requested_model",
        "resolved_upstream_model",
        "provider_host",
        "provider_endpoint_path",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "tool_call_counts",
        "function_tool_names",
        "provider_reported_cost",
        "slaif_calculated_cost",
        "cost_currency",
        "cost_source",
        "gateway_request_id",
        "profile_metadata",
        "created_at",
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    base: dict[str, object] = {
        "DEMO_SNAPSHOT_ENABLED": True,
        "DEMO_SNAPSHOT_SOURCE_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_SOURCE_PORT": 5555,
        "DEMO_SNAPSHOT_SOURCE_DATABASE": "slaif_src",
        "DEMO_SNAPSHOT_SOURCE_USER": "snap_reader",
        "DEMO_SNAPSHOT_TARGET_HOST": "127.0.0.1",
        "DEMO_SNAPSHOT_TARGET_PORT": 5556,
        "DEMO_SNAPSHOT_TARGET_USER": "snap_target",
        "DEMO_SNAPSHOT_PGPASSFILE": str(Path("/tmp/never") / "pgpass"),
        "DEMO_SNAPSHOT_CUSTODY_DIR": str(Path("/tmp/never") / "custody"),
    }
    base.update(overrides)
    return Settings(**base)


def _passfile(tmp_path: Path, mode: int = 0o600) -> Path:
    passfile = tmp_path / "pgpass"
    passfile.write_text(
        "127.0.0.1:5555:slaif_src:snap_reader:canary-source-pw\n"
        "127.0.0.1:5556:*:snap_target:canary-target-pw\n",
        encoding="utf-8",
    )
    os.chmod(passfile, mode)
    return passfile


def _config(tmp_path: Path, **overrides) -> ds.DemoSnapshotConfig:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700, exist_ok=True)
    passfile = overrides.pop("passfile", None) or _passfile(tmp_path)
    settings = _settings(
        DEMO_SNAPSHOT_PGPASSFILE=str(passfile),
        DEMO_SNAPSHOT_CUSTODY_DIR=str(custody),
        **overrides,
    )
    return ds.config_from_settings(settings)


def _write_job(
    custody: Path,
    job_id: str,
    state: str,
    *,
    failure_code: str | None = None,
) -> Path:
    job_dir = custody / job_id
    job_dir.mkdir(mode=0o700)
    manifest = ds.SnapshotManifest(
        job_id=job_id,
        state=state,
        created_at=time.time() - 1,
        target_db="demo_snap_" + job_id[-20:],
        failure_code=failure_code,
    )
    ds._write_manifest(job_dir, manifest)
    return job_dir


class _FakeConn:
    """Minimal asyncpg stand-in: scripted fetchval/fetch, never used for
    real I/O. ``calls`` records every query for assertions."""

    def __init__(self, fetchval_results=(), fetch_results=()):
        self._fetchval_results = list(fetchval_results)
        self._fetch_results = list(fetch_results)
        self.calls: list[str] = []
        self.closed = False

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql))
        if not self._fetchval_results:
            raise AssertionError("unexpected fetchval: " + sql)
        value = self._fetchval_results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql))
        if not self._fetch_results:
            raise AssertionError("unexpected fetch: " + sql)
        value = self._fetch_results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def close(self):
        self.closed = True


class _Row(dict):
    """dict row supporting asyncpg-style row["column"] access."""


def _pk_rows() -> list:
    return [
        _Row(table_name=t, conname=f"pk_{t}", cols="id")
        for t in sorted(dsan.TABLE_POLICY)
    ]


def _fk_dict(fk: tuple) -> dict[str, str]:
    keys = (
        "conname", "table_name", "cols", "ref_table", "ref_cols",
        "confdeltype", "confupdtype", "confmatchtype",
        "condeferrable", "condeferred", "convalidated",
    )
    return dict(zip(keys, fk))


def _synthetic_inventory() -> dict[str, object]:
    """A catalog inventory derived from the reviewed policy itself: it
    passes _check_catalog for the non-constraint dimensions, and carries
    a small constraint list whose digest we pin via monkeypatch in the
    tests that need the digest dimension to pass."""
    tables: dict[str, dict[str, tuple[str, bool]]] = {}
    for table, cols in dsan.TABLE_POLICY.items():
        tables[table] = {
            col: dsan._COLUMN_SIGNATURE[f"{table}.{col}"] for col in cols
        }
    constraints = [
        ("public", "owners", "pk_dummy", "p", "PRIMARY KEY (id)"),
        ("public", "owners", "fk_dummy", "f", "FOREIGN KEY (institution_id) REFERENCES institutions(id)"),
    ]
    return {
        "tables": tables,
        "extensions": dsan._EXPECTED_EXTENSIONS,
        "public_types": (
            {t for t in dsan.TABLE_POLICY}
            | {"_" + t for t in dsan.TABLE_POLICY}
            | dsan._EXPECTED_EXTRA_PUBLIC_TYPES
        ),
        "constraints": constraints,
        "foreign_keys": [_fk_dict(fk) for fk in dsan._REVIEWED_FOREIGN_KEYS],
    }


def _pin_digest(monkeypatch: pytest.MonkeyPatch, inventory: dict[str, object]) -> None:
    monkeypatch.setattr(
        dsan, "_REVIEWED_CONSTRAINT_DIGEST",
        dsan._constraint_digest(list(inventory["constraints"])),
    )
    monkeypatch.setattr(
        dsan, "_REVIEWED_CONSTRAINT_TOTAL", len(inventory["constraints"])
    )
    counts: dict[str, int] = {}
    for record in inventory["constraints"]:
        counts[record[3]] = counts.get(record[3], 0) + 1
    monkeypatch.setattr(dsan, "_REVIEWED_CONSTRAINT_COUNTS", counts)


# ---------------------------------------------------------------------------
# Policy completeness and static invariants
# ---------------------------------------------------------------------------


def test_policy_equals_checkpoint_catalog() -> None:
    fixture_tables = set(_CHECKPOINT_CATALOG)
    assert set(dsan.TABLE_POLICY) == fixture_tables
    assert len(fixture_tables) == 34
    total = 0
    for table, columns in _CHECKPOINT_CATALOG.items():
        assert set(dsan.TABLE_POLICY[table]) == set(columns), table
        total += len(columns)
    assert total == 507


def test_column_signature_covers_policy_exactly() -> None:
    pairs = {
        (name.split(".", 1)[0], name.split(".", 1)[1])
        for name in dsan._COLUMN_SIGNATURE
    }
    policy_pairs = {
        (t, c) for t, cols in dsan.TABLE_POLICY.items() for c in cols
    }
    assert pairs == policy_pairs
    assert len(pairs) == 507


def test_reviewed_fk_inventory_shape() -> None:
    assert len(dsan._REVIEWED_FOREIGN_KEYS) == 64
    for fk in dsan._REVIEWED_FOREIGN_KEYS:
        assert len(fk) == 11
        assert fk[8] == "false" and fk[9] == "false" and fk[10] == "true"


def test_f_fc_keys_exist_in_shipped_data() -> None:
    data = dsan.load_demo_identities()
    for table, cols in dsan.TABLE_POLICY.items():
        for column, action in cols.items():
            if action.startswith("F:") or action.startswith("FC:"):
                key = action.split(":", 1)[1]
                assert data.get(key), (table, column, key)


def test_all_jj_columns_have_typed_validators() -> None:
    for table, cols in dsan.TABLE_POLICY.items():
        for column, action in cols.items():
            if action == dsan.JJ:
                assert (table, column) in dsan._JJ_VALIDATORS


def test_shipped_identity_data_is_reserved_and_complete() -> None:
    data = dsan.load_demo_identities()
    assert data["schema_version"] == 1
    for domain in data["email_domains"]:
        assert domain.endswith(".invalid"), domain
    for value in data.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item)
            assert all(ord(ch) < 128 for ch in text), text
    dsan._require_data_keys(data)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._require_data_keys({})


# ---------------------------------------------------------------------------
# Deterministic per-copy remappings
# ---------------------------------------------------------------------------


def test_remap_uuid_deterministic_seed_dependent() -> None:
    old = uuid.uuid4()
    a1 = dsan.remap_uuid(b"snap-a", old)
    a2 = dsan.remap_uuid(b"snap-a", old)
    b1 = dsan.remap_uuid(b"snap-b", old)
    assert a1 == a2
    assert a1 != b1
    assert a1 != old
    assert isinstance(a1, uuid.UUID)


def test_remap_str_id_shape_and_injective_sample() -> None:
    seen: set[str] = set()
    for i in range(200):
        value = dsan.remap_str_id(b"snap-a", f"id-{i}")
        assert value.startswith("demo")
        # 64-char cap: fits the narrowest reviewed S column (varchar(64)).
        assert len(value) == 4 + 60
        assert value not in seen
        seen.add(value)
    assert dsan.remap_str_id(b"snap-b", "id-0") != dsan.remap_str_id(b"snap-a", "id-0")


def test_remap_hex64_shape_and_determinism() -> None:
    old = "a" * 64
    a1 = dsan.remap_hex64(b"snap-a", b"item_id_hmac", old)
    a2 = dsan.remap_hex64(b"snap-a", b"item_id_hmac", old)
    b1 = dsan.remap_hex64(b"snap-b", b"item_id_hmac", old)
    c1 = dsan.remap_hex64(b"snap-a", b"call_id_hmac", old)
    # Bare 64 hex, NO prefix: the CHECK ^[0-9a-f]{64}$ forbids any prefix.
    assert re.fullmatch(r"^[0-9a-f]{64}$", a1)
    assert a1 == a2
    assert a1 != b1  # per-copy (seed-dependent)
    assert a1 != c1  # per-column (salt-dependent)
    assert a1 != old
    seen: set[str] = set()
    for i in range(200):
        value = dsan.remap_hex64(b"snap-a", b"item_id_hmac", f"{i:064x}")
        assert len(value) == 64 and value not in seen
        seen.add(value)


def test_h_column_digest_multiset_law() -> None:
    seed = b"copy-a"
    column = "item_id_hmac"
    raw = ["a" * 64, "b" * 64, "c" * 64, "a" * 64]  # duplicates allowed
    expected = [dsan.remap_hex64(seed, column.encode(), v) for v in raw]
    # Pre-state projection (raw -> expected) and verifier pass (stored
    # values hashed AS-IS, here stored == expected) must agree.
    assert dsan._h_column_digest(seed, column, expected) == dsan._h_column_digest(
        seed, column, list(reversed(expected))
    )
    # An un-remapped raw pass-through must NOT match: shape alone cannot
    # distinguish raw from remapped, the keyed aggregate can.
    assert dsan._h_column_digest(seed, column, raw) != dsan._h_column_digest(
        seed, column, expected
    )
    # Duplicate-sensitive multiset (dropping one duplicate changes it).
    assert dsan._h_column_digest(seed, column, expected[1:]) != dsan._h_column_digest(
        seed, column, expected
    )
    # Value-change sensitive.
    changed = list(expected)
    changed[0] = dsan.remap_hex64(seed, column.encode(), "d" * 64)
    assert dsan._h_column_digest(seed, column, changed) != dsan._h_column_digest(
        seed, column, expected
    )
    # Per-copy (seed-dependent).
    assert dsan._h_column_digest(b"copy-b", column, expected) != dsan._h_column_digest(
        seed, column, expected
    )


def test_h_action_only_reviewed_replay_hmac_columns() -> None:
    h_cols = sorted(
        f"{table}.{col}"
        for table, cols in dsan.TABLE_POLICY.items()
        for col, action in cols.items()
        if action == dsan.H
    )
    assert h_cols == [
        "codex_replay_references.call_id_hmac",
        "codex_replay_references.item_id_hmac",
    ]


def test_remap_preserves_fk_links() -> None:
    key = uuid.uuid4()
    owner = uuid.uuid4()
    seed = b"snap-a"
    # same old value remaps identically in every table -> links hold
    assert dsan.remap_uuid(seed, key) == dsan.remap_uuid(seed, key)
    assert dsan.remap_uuid(seed, owner) != dsan.remap_uuid(seed, key)


# ---------------------------------------------------------------------------
# Identity maps
# ---------------------------------------------------------------------------


def _identity_data() -> dict[str, object]:
    return dsan.load_demo_identities()


def test_owner_maps_overflow_is_injective() -> None:
    data = _identity_data()
    owner_ids = [str(uuid.uuid4()) for _ in range(60)]
    maps = dsan.build_identity_maps(
        b"snap-a", data,
        owner_ids=owner_ids,
        institution_ids=[], cohort_ids=[], org_ids=[],
        team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    emails = list(maps.owner_email.values())
    fulls = [
        (maps.owner_name[oid], maps.owner_surname[oid]) for oid in owner_ids
    ]
    assert len(set(emails)) == 60
    assert len(set(fulls)) == 60
    for email in emails:
        assert email.split("@", 1)[1].endswith(".invalid")


def test_entity_map_overflow_is_injective() -> None:
    data = _identity_data()
    inst_ids = [str(uuid.uuid4()) for _ in range(30)]
    maps = dsan.build_identity_maps(
        b"snap-a", data,
        owner_ids=[], institution_ids=inst_ids, cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    names = list(maps.institution_name.values())
    assert len(set(names)) == 30


def test_identity_maps_are_seed_dependent() -> None:
    data = _identity_data()
    owner_ids = [str(uuid.uuid4()) for _ in range(100)]
    a = dsan.build_identity_maps(
        b"snap-a", data, owner_ids=owner_ids, institution_ids=[],
        cohort_ids=[], org_ids=[], team_ids=[], project_ids=[],
        budget_ids=[], template_ids=[], admin_ids=[],
    )
    b = dsan.build_identity_maps(
        b"snap-b", data, owner_ids=owner_ids, institution_ids=[],
        cohort_ids=[], org_ids=[], team_ids=[], project_ids=[],
        budget_ids=[], template_ids=[], admin_ids=[],
    )
    assert a.owner_email != b.owner_email


# ---------------------------------------------------------------------------
# JSONB shape helpers
# ---------------------------------------------------------------------------


def test_remapped_uuid_array_keeps_shape_and_remaps() -> None:
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    seed = b"snap-a"
    out = dsan._remap_uuid_array(json.dumps([str(u1), str(u2)]), seed)
    parsed = json.loads(out)
    assert parsed == [str(dsan.remap_uuid(seed, u1)), str(dsan.remap_uuid(seed, u2))]
    assert dsan._ju_is_safe(out)


def test_uuid_array_refuses_wrong_shapes() -> None:
    seed = b"snap-a"
    with pytest.raises(ds.DemoSnapshotError) as exc1:
        dsan._remap_uuid_array(json.dumps(["not-a-uuid"]), seed)
    assert exc1.value.code == ds.CODE_SANITIZE_FAILED
    with pytest.raises(ds.DemoSnapshotError):
        dsan._remap_uuid_array(json.dumps({"a": 1}), seed)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._remap_uuid_array("not json", seed)
    assert dsan._remap_uuid_array(None, seed) is None
    assert not dsan._ju_is_safe("[]") or dsan._ju_is_safe(json.dumps([]))
    assert not dsan._ju_is_safe("null")


def test_jj_validators_accept_reject() -> None:
    ok_models = json.dumps(["gpt-4o", "demo-model/x"])
    assert dsan._jj_is_valid("gateway_keys", "allowed_models", ok_models)
    assert not dsan._jj_is_valid("gateway_keys", "allowed_models", json.dumps(["a b"]))
    assert not dsan._jj_is_valid("gateway_keys", "allowed_models", json.dumps({"m": 1}))

    ok_endpoints = json.dumps(["/v1/chat/completions"])
    assert dsan._jj_is_valid("gateway_keys", "allowed_endpoints", ok_endpoints)
    assert not dsan._jj_is_valid("gateway_keys", "allowed_endpoints", json.dumps(["chat"]))

    # model_routes.capabilities is NO LONGER a generic JJ boolean map:
    # the installed route capability grammar is handled by the RC action
    # (see the RC tests below).
    assert dsan.TABLE_POLICY["model_routes"]["capabilities"] == dsan.RC
    assert ("model_routes", "capabilities") not in dsan._JJ_VALIDATORS

    ok_rate = json.dumps({"requests_per_minute": 60, "window_seconds": 60})
    assert dsan._jj_is_valid("key_template_revisions", "rate_limit_policy", ok_rate)
    assert not dsan._jj_is_valid("key_template_revisions", "rate_limit_policy", json.dumps({"x": -1}))
    assert not dsan._jj_is_valid("key_template_revisions", "rate_limit_policy", json.dumps({"x": True}))

    ok_dotted = json.dumps(["functions.exec"])
    assert dsan._jj_is_valid("quota_reservations", "external_tool_capabilities", ok_dotted)
    assert not dsan._jj_is_valid("quota_reservations", "external_tool_capabilities", json.dumps(["my secret note"]))

    assert not dsan._jj_is_valid("no_such_table", "c", json.dumps([]))


# ---------------------------------------------------------------------------
# RC: installed route capability transform + independent re-proof
# ---------------------------------------------------------------------------

_RC_SEED = b"rc-seed-a"
_RC_SEED_B = b"rc-seed-b"
_RC_ROUTE_A = uuid.UUID("11111111-2222-3333-4444-555555555555")
_RC_ROUTE_B = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _rc_full_document() -> dict[str, object]:
    """A representative INSTALLED nested capability document (real
    product vocabulary)."""
    return {
        "chat_completions": {"chat_text": True, "chat_streaming": True},
        "responses": {"text": True, "compact": False, "codex_request_envelope": True},
        "codex_limits": {
            "context_window_tokens": 1050000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 128000,
        },
        "codex_compaction_compatible_route_ids": [
            str(_RC_ROUTE_A), str(_RC_ROUTE_B),
        ],
        "media_input_estimation": {
            "version": 1, "image_tokens": 50000, "video_tokens": 100000,
            "video_frames": 8,
        },
        "completion_service": {"version": 1, "profile": "my-canary-profile"},
        "external_tools": {
            "version": 1,
            "supported_capabilities": ["provider_remote_mcp"],
            "approved_destination_ids": ["remote_mcp:canary-dest-one"],
            "max_provider_tool_calls_per_request": 4,
            "call_limit_enforced": True,
            "final_usage_required": True,
            "final_cost_required": True,
        },
        "audio_endpoints": {"audio_speech": True},
        "embeddings": {"embeddings": True, "embeddings_dimensions": False},
        "realtime": {"audio": True},
    }


def _rc_copied_route_ids(seed: bytes) -> frozenset[str]:
    return frozenset(
        {
            str(dsan.remap_uuid(seed, _RC_ROUTE_A)),
            str(dsan.remap_uuid(seed, _RC_ROUTE_B)),
        }
    )


def test_rc_empty_document_supported() -> None:
    assert dsan._transform_route_capabilities(json.dumps({}), _RC_SEED) == "{}"
    assert dsan._verify_route_capabilities("{}", frozenset()) is True


def test_rc_representative_nested_document_preserved() -> None:
    doc = _rc_full_document()
    out = json.loads(dsan._transform_route_capabilities(json.dumps(doc), _RC_SEED))
    # Non-identifying booleans/numbers/finite codes are preserved exactly.
    assert out["chat_completions"] == doc["chat_completions"]
    assert out["responses"] == doc["responses"]
    assert out["codex_limits"] == doc["codex_limits"]
    assert out["media_input_estimation"] == doc["media_input_estimation"]
    assert out["audio_endpoints"] == doc["audio_endpoints"]
    assert out["embeddings"] == doc["embeddings"]
    assert out["realtime"] == doc["realtime"]
    assert out["external_tools"]["supported_capabilities"] == [
        "provider_remote_mcp"
    ]
    assert out["external_tools"]["max_provider_tool_calls_per_request"] == 4


def test_rc_completion_profile_fictionalized_per_copy() -> None:
    out_a = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED)
    )
    out_b = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED_B)
    )
    profile_a = out_a["completion_service"]["profile"]
    profile_b = out_b["completion_service"]["profile"]
    # Exactly demo-profile-<24 lowercase hex>.
    assert re.fullmatch(r"demo-profile-[0-9a-f]{24}", profile_a)
    # SAME per-copy derivation as the 223 completion-choices projection.
    assert profile_a == dsan.demo_profile_id(_RC_SEED, "my-canary-profile")
    assert profile_a != profile_b  # per-copy ids differ
    # The original operator profile id is absent from the transformed bytes.
    assert "my-canary-profile" not in dsan._transform_route_capabilities(
        json.dumps(_rc_full_document()), _RC_SEED
    )


def test_rc_compaction_ids_remapped_to_copied_routes() -> None:
    out = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED)
    )
    ids = out["codex_compaction_compatible_route_ids"]
    # Exact per-copy remap, list meaning (order) preserved.
    assert ids == [
        str(dsan.remap_uuid(_RC_SEED, _RC_ROUTE_A)),
        str(dsan.remap_uuid(_RC_SEED, _RC_ROUTE_B)),
    ]
    # Nonempty-list verifier positive: the transformed document re-proves
    # against the copied route id set.
    assert dsan._verify_route_capabilities(json.dumps(out), _rc_copied_route_ids(_RC_SEED))
    # Raw (un-remapped) source ids are NOT in the copied set -> violation.
    bad = dict(out)
    bad["codex_compaction_compatible_route_ids"] = [str(_RC_ROUTE_A)]
    assert not dsan._verify_route_capabilities(json.dumps(bad), _rc_copied_route_ids(_RC_SEED))
    # An id that is a valid UUID but belongs to no copied route -> violation.
    bad2 = dict(out)
    bad2["codex_compaction_compatible_route_ids"] = [str(uuid.uuid4())]
    assert not dsan._verify_route_capabilities(json.dumps(bad2), _rc_copied_route_ids(_RC_SEED))


def test_rc_destination_ids_remapped_per_copy() -> None:
    out_a = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED)
    )
    out_b = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED_B)
    )
    dest_a = out_a["external_tools"]["approved_destination_ids"][0]
    dest_b = out_b["external_tools"]["approved_destination_ids"][0]
    # Kind preserved; operator opaque name replaced by a per-copy digest.
    kind, opaque_a = dest_a.split(":", 1)
    assert kind == "remote_mcp"
    assert re.fullmatch(r"demo[0-9a-f]{44}", opaque_a)
    assert dest_a != dest_b
    assert "canary-dest-one" not in json.dumps(out_a)
    # Verifier accepts the fictional shape, rejects the raw operator name.
    assert dsan._verify_route_capabilities(json.dumps(out_a), _rc_copied_route_ids(_RC_SEED))
    raw = dict(out_a)
    raw["external_tools"] = dict(out_a["external_tools"])
    raw["external_tools"]["approved_destination_ids"] = ["remote_mcp:canary-dest-one"]
    assert not dsan._verify_route_capabilities(json.dumps(raw), _rc_copied_route_ids(_RC_SEED))


def test_rc_unknown_or_invalid_shapes_fail_closed() -> None:
    rejections = [
        {"local_coding": {"contract_version": "local-coding-v1"}},
        {"local_coding_vllm": {"contract_version": "vllm-chat-video-v1"}},
        {"upstream_llm": {"version": 1, "profile": "p", "revision": 1, "sha256": "x" * 64}},
        {"unknown_group": True},
        {"chat_completions": {"not_a_known_flag": True}},
        {"responses": {"text": "yes"}},
        {"codex_limits": {"context_window_tokens": "x", "default_max_output_tokens": 1, "max_output_tokens": 2}},
        {"codex_limits": {"context_window_tokens": 100, "default_max_output_tokens": 200, "max_output_tokens": 150}},
        {"codex_compaction_compatible_route_ids": ["not-a-uuid"]},
        {"codex_compaction_compatible_route_ids": [str(_RC_ROUTE_A), str(_RC_ROUTE_A)]},
        {"media_input_estimation": {"version": 2}},
        {"completion_service": {"version": 2, "profile": "p"}},
        {"streaming": True, "tools": False},  # legacy flat top-level booleans
        {"vllm_chat_video": {"version": 1}},  # missing media block
        {
            "completion_service": {"version": 1, "profile": "p"},
            "vllm_chat_video": {"version": 1},
            "media_input_estimation": {"version": 1, "video_frames": 4, "video_tokens": 50000},
        },  # installed conflict law
        # Secret-shaped value in a wrong position fails closed.
        {"chat_completions": {"chat_text": "Bearer secret-token-value"}},
    ]
    for doc in rejections:
        with pytest.raises(ds.DemoSnapshotError):
            dsan._transform_route_capabilities(json.dumps(doc), _RC_SEED)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._transform_route_capabilities(json.dumps([True]), _RC_SEED)
    # Oversized documents fail the bounded envelope.
    big = {"codex_compaction_compatible_route_ids": [str(uuid.uuid4()) for _ in range(33)]}
    with pytest.raises(ds.DemoSnapshotError):
        dsan._transform_route_capabilities(json.dumps(big), _RC_SEED)


def test_rc_verifier_rejects_tampered_stored_documents() -> None:
    out = json.loads(
        dsan._transform_route_capabilities(json.dumps(_rc_full_document()), _RC_SEED)
    )
    route_ids = _rc_copied_route_ids(_RC_SEED)
    # A tampered stored document that restores the RAW profile id fails.
    bad = dict(out)
    bad["completion_service"] = {"version": 1, "profile": "my-canary-profile"}
    assert not dsan._verify_route_capabilities(json.dumps(bad), route_ids)
    # A tampered document that injects a transport group fails.
    bad2 = dict(out)
    bad2["local_coding"] = {"contract_version": "local-coding-v1"}
    assert not dsan._verify_route_capabilities(json.dumps(bad2), route_ids)
    # A tampered document that flips a preserved boolean to a non-bool fails.
    bad3 = dict(out)
    bad3["realtime"] = {"audio": "yes"}
    assert not dsan._verify_route_capabilities(json.dumps(bad3), route_ids)
    # A tampered document that injects vllm_chat_video alongside the
    # completion selector violates the installed conflict law and fails,
    # even though each group alone would pass its per-group re-proof.
    bad4 = dict(out)
    bad4["vllm_chat_video"] = {"version": 1}
    assert not dsan._verify_route_capabilities(json.dumps(bad4), route_ids)
    # Non-JSON stored value fails.
    assert not dsan._verify_route_capabilities("not json", route_ids)


def test_rc_policy_wiring() -> None:
    assert dsan.TABLE_POLICY["model_routes"]["capabilities"] == dsan.RC
    assert ("model_routes", "capabilities") not in dsan._JJ_VALIDATORS


# ---------------------------------------------------------------------------
# Catalog fail-closed gate
# ---------------------------------------------------------------------------


def test_check_catalog_accepts_policy_derived_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    dsan._check_catalog(inv)  # must not raise


def test_check_catalog_rejects_table_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    extra = dict(inv)
    tables = {t: dict(c) for t, c in inv["tables"].items()}  # type: ignore[union-attr]
    tables["rogue_table"] = {"id": ("uuid", False)}
    extra["tables"] = tables
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._check_catalog(extra)
    assert exc.value.code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN


def test_check_catalog_rejects_column_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    tables = {t: dict(c) for t, c in inv["tables"].items()}  # type: ignore[union-attr]
    tables["owners"]["rogue_col"] = ("text", True)
    inv["tables"] = tables
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._check_catalog(inv)
    assert exc.value.code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN


def test_check_catalog_rejects_type_and_nullability_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    tables = {t: dict(c) for t, c in inv["tables"].items()}  # type: ignore[union-attr]
    tables["owners"]["name"] = ("character varying(128)", False)
    inv["tables"] = tables
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv)

    inv2 = _synthetic_inventory()
    _pin_digest(monkeypatch, inv2)
    tables2 = {t: dict(c) for t, c in inv2["tables"].items()}  # type: ignore[union-attr]
    tables2["owners"]["notes"] = ("text", False)  # was nullable
    inv2["tables"] = tables2
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv2)


def test_check_catalog_rejects_extension_and_type_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    inv["extensions"] = dsan._EXPECTED_EXTENSIONS | {"hstore"}
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv)

    inv2 = _synthetic_inventory()
    _pin_digest(monkeypatch, inv2)
    inv2["public_types"] = set(inv2["public_types"]) | {"rogue_type"}  # type: ignore[union-attr]
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv2)


def test_check_catalog_rejects_fk_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    fks = list(inv["foreign_keys"])
    fks = fks[:-1]  # one fewer FK
    inv["foreign_keys"] = fks
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._check_catalog(inv)
    assert exc.value.code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN

    inv2 = _synthetic_inventory()
    _pin_digest(monkeypatch, inv2)
    fks2 = [dict(fk) for fk in inv2["foreign_keys"]]  # type: ignore[union-attr]
    fks2[0]["condeferrable"] = "true"
    inv2["foreign_keys"] = fks2
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv2)


def test_check_catalog_rejects_constraint_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    constraints = list(inv["constraints"])
    constraints[0] = ("public", "owners", "pk_dummy", "p", "PRIMARY KEY (id, other)")
    inv["constraints"] = constraints
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._check_catalog(inv)
    assert exc.value.code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN


def test_check_catalog_rejects_constraint_count_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)
    inv["constraints"] = list(inv["constraints"])[:-1]
    with pytest.raises(ds.DemoSnapshotError):
        dsan._check_catalog(inv)


# ---------------------------------------------------------------------------
# Bounded pre-state
# ---------------------------------------------------------------------------


def test_prestate_refuses_oversized_table_before_id_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _entity_ids_must_not_run(*_a, **_k):
        raise AssertionError("entity id materialization must not run")

    monkeypatch.setattr(dsan, "_entity_id_lists", _entity_ids_must_not_run)
    conn = _FakeConn(
        fetchval_results=[dsan._MAX_ROWS_PER_TABLE + 1],
        fetch_results=[_pk_rows()],
    )
    inv = _synthetic_inventory()
    with pytest.raises(ds.DemoSnapshotError) as exc:
        import asyncio

        asyncio.run(
            dsan._capture_prestate(conn, inv, b"prestate", time.monotonic() + 60)
        )
    assert exc.value.code == ds.CODE_SANITIZE_FAILED


def test_prestate_refuses_total_row_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _entity_ids_must_not_run(*_a, **_k):
        raise AssertionError("entity id materialization must not run")

    monkeypatch.setattr(dsan, "_entity_id_lists", _entity_ids_must_not_run)
    n_tables = len(dsan.TABLE_POLICY)
    per_table = dsan._MAX_TOTAL_ROWS // n_tables + 1
    conn = _FakeConn(
        fetchval_results=[per_table] * n_tables,
        fetch_results=[_pk_rows()],
    )
    inv = _synthetic_inventory()
    with pytest.raises(ds.DemoSnapshotError) as exc:
        import asyncio

        asyncio.run(dsan._capture_prestate(conn, inv, b"prestate", time.monotonic() + 60))
    assert exc.value.code == ds.CODE_SANITIZE_FAILED


# ---------------------------------------------------------------------------
# FK DDL
# ---------------------------------------------------------------------------


def test_fk_recreate_sql_round_trip() -> None:
    fk = _fk_dict(dsan._REVIEWED_FOREIGN_KEYS[0])
    sql = dsan._fk_recreate_sql(fk)
    assert "ALTER TABLE public" in sql
    assert "ADD CONSTRAINT" in sql
    if fk["confdeltype"] != "a":
        assert f"ON DELETE {dsan._FK_ACTIONS[fk['confdeltype']]}" in sql
    if fk["confdeltype"] == "a":
        assert "ON DELETE" not in sql


def test_fk_recreate_sql_refuses_unsafe_identifier() -> None:
    fk = _fk_dict(dsan._REVIEWED_FOREIGN_KEYS[0])
    fk["table_name"] = 'evil"; DROP TABLE owners; --'
    with pytest.raises(ds.DemoSnapshotError):
        dsan._fk_recreate_sql(fk)


# ---------------------------------------------------------------------------
# Passfile credential handling
# ---------------------------------------------------------------------------


def test_target_password_reads_matching_line(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert dsan._target_password(config) == "canary-target-pw"


def test_target_password_refuses_world_readable(tmp_path: Path) -> None:
    passfile = _passfile(tmp_path, mode=0o644)
    config = _config(tmp_path, passfile=passfile)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._target_password(config)
    assert exc.value.code == ds.CODE_MISCONFIGURED
    assert str(tmp_path) not in exc.value.safe_message


def test_target_password_refuses_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real_pgpass"
    real.write_text("127.0.0.1:5556:*:snap_target:canary-target-pw\n", encoding="utf-8")
    os.chmod(real, 0o600)
    link = tmp_path / "link_pgpass"
    os.symlink(real, link)
    config = _config(tmp_path, passfile=link)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._target_password(config)
    assert exc.value.code == ds.CODE_MISCONFIGURED


def test_target_password_missing_credential(tmp_path: Path) -> None:
    passfile = tmp_path / "pgpass"
    passfile.write_text("127.0.0.1:9999:*:other:somepw\n", encoding="utf-8")
    os.chmod(passfile, 0o600)
    config = _config(tmp_path, passfile=passfile)
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._target_password(config)
    assert exc.value.code == ds.CODE_MISCONFIGURED


# ---------------------------------------------------------------------------
# Planning and value conversion
# ---------------------------------------------------------------------------


def _plan_columns(table: str) -> dict[str, tuple[str, bool]]:
    return {
        col: dsan._COLUMN_SIGNATURE[f"{table}.{col}"]
        for col in dsan.TABLE_POLICY[table]
    }


def test_build_plan_selects_non_preserved_and_refs() -> None:
    plan = dsan._build_plan("usage_ledger", ["id"], _plan_columns("usage_ledger"))
    assert "owner_email_snapshot" in plan.set_cols
    assert "prompt_tokens" not in plan.set_cols
    # the E_* snapshot needs the reference column fetched
    assert "owner_id" in plan.fetch_cols
    assert "id" in plan.pk


def test_build_plan_requires_primary_key() -> None:
    with pytest.raises(ds.DemoSnapshotError) as exc:
        dsan._build_plan("owners", [], _plan_columns("owners"))
    assert exc.value.code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN


def test_convert_value_actions() -> None:
    data = _identity_data()
    seed = b"snap-a"
    owner_id = str(uuid.uuid4())
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[owner_id], institution_ids=[],
        cohort_ids=[], org_ids=[], team_ids=[], project_ids=[],
        budget_ids=[], template_ids=[], admin_ids=[],
    )
    row = _Row(id=uuid.UUID(owner_id))

    u = uuid.uuid4()
    got = dsan._convert_value(dsan.U, u, seed=seed, data=data, maps=maps,
                              table="owners", column="id", row=row, row_index=0)
    assert got == dsan.remap_uuid(seed, u)
    assert dsan._convert_value(dsan.U, None, seed=seed, data=data, maps=maps,
                               table="owners", column="id", row=row, row_index=0) is None

    got_s = dsan._convert_value(dsan.S, "req-1", seed=seed, data=data, maps=maps,
                                table="usage_ledger", column="request_id", row=row, row_index=0)
    assert got_s == dsan.remap_str_id(seed, "req-1")

    hex64 = "f" * 64
    got_h = dsan._convert_value(dsan.H, hex64, seed=seed, data=data, maps=maps,
                                table="codex_replay_references",
                                column="item_id_hmac", row=row, row_index=0)
    # The column name is the per-column salt.
    assert got_h == dsan.remap_hex64(seed, b"item_id_hmac", hex64)
    assert dsan._convert_value(dsan.H, None, seed=seed, data=data, maps=maps,
                               table="codex_replay_references",
                               column="call_id_hmac", row=row, row_index=0) is None

    assert dsan._convert_value(dsan.N, "leak", seed=seed, data=data, maps=maps,
                               table="owners", column="notes", row=row, row_index=0) is None
    assert dsan._convert_value(dsan.J0, '{"a": 1}', seed=seed, data=data, maps=maps,
                               table="usage_ledger", column="usage_raw", row=row, row_index=0) == "{}"
    assert dsan._convert_value(dsan.JA, '["x"]', seed=seed, data=data, maps=maps,
                               table="usage_profiles", column="function_tool_names", row=row, row_index=0) == "[]"

    got_e = dsan._convert_value(dsan.E_OWNER_NAME, "Old Name", seed=seed, data=data,
                                maps=maps, table="owners", column="name", row=row, row_index=0)
    assert got_e == maps.owner_name[owner_id]
    assert got_e != "Old Name"

    # IP is deterministic per row index and from the fixed fictional set
    ips = data["fictional_ips"]
    got_ip = dsan._convert_value(dsan.IP, None, seed=seed, data=data, maps=maps,
                                 table="admin_sessions", column="ip_address", row=row, row_index=1)
    assert got_ip == ips[1 % len(ips)]
    got_ua = dsan._convert_value(dsan.UA, None, seed=seed, data=data, maps=maps,
                                 table="admin_sessions", column="user_agent", row=row, row_index=0)
    assert got_ua == data["user_agents"][0]


def test_convert_value_refuses_wrong_types() -> None:
    data = _identity_data()
    seed = b"snap-a"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    row = _Row()
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.U, "not-a-uuid", seed=seed, data=data, maps=maps,
                            table="owners", column="id", row=row, row_index=0)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.S, 123, seed=seed, data=data, maps=maps,
                            table="owners", column="external_id", row=row, row_index=0)
    for bad in ("f" * 63, "f" * 65, "g" * 64, "F" * 64, "f" * 62 + "-"):
        with pytest.raises(ds.DemoSnapshotError):
            dsan._convert_value(dsan.H, bad, seed=seed, data=data, maps=maps,
                                table="codex_replay_references",
                                column="item_id_hmac", row=row, row_index=0)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.H, 123, seed=seed, data=data, maps=maps,
                            table="codex_replay_references",
                            column="call_id_hmac", row=row, row_index=0)
    # The installed flat top-level boolean document is NOT the installed
    # capability grammar: the RC action refuses it fail closed.
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.RC, json.dumps({"chat": True, "streaming": False}),
                            seed=seed, data=data, maps=maps, table="model_routes",
                            column="capabilities", row=row, row_index=0)
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.RC, "not json", seed=seed,
                            data=data, maps=maps, table="model_routes",
                            column="capabilities", row=row, row_index=0)


def test_not_null_reason_maps_to_fixed_fictional_value() -> None:
    data = _identity_data()
    seed = b"snap-reason"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    row = _Row()
    action = dsan.TABLE_POLICY["catalog_refresh_applications"]["reason"]
    got = dsan._convert_value(
        action, "canary-operator-reason-leak", seed=seed, data=data,
        maps=maps, table="catalog_refresh_applications", column="reason",
        row=row, row_index=0,
    )
    # The column is NOT NULL, so the operator reason must be replaced by
    # the fixed fictional note, never nulled and never preserved.
    assert got == data["generic_note"]
    assert "canary-operator-reason-leak" not in str(got)
    # Regression guard: EVERY N action must target a nullable column,
    # otherwise the committed transaction would abort on NOT NULL.
    for table, columns in dsan.TABLE_POLICY.items():
        for column, act in columns.items():
            if act == dsan.N:
                _type, nullable = dsan._COLUMN_SIGNATURE[f"{table}.{column}"]
                assert nullable is True, f"N on NOT NULL {table}.{column}"


def test_orphan_recipient_email_deterministic_and_seed_dependent() -> None:
    data = _identity_data()
    delivery_id = uuid.uuid4()
    orphan_row = _Row(id=delivery_id, owner_id=None)
    domains = data["email_domains"]
    by_seed = {}
    for seed in (b"copy-a", b"copy-b"):
        maps = dsan.build_identity_maps(
            seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
            org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
            template_ids=[], admin_ids=[],
        )

        def orphan() -> str:
            return str(dsan._convert_value(
                dsan.E_OWNER_EMAIL, "real-recipient@corp.example",
                seed=seed, data=data, maps=maps,
                table="email_deliveries", column="recipient_email",
                row=orphan_row, row_index=0,
            ))

        value = orphan()
        # Deterministic within one copy, reserved non-delivering domain,
        # and the real recipient is gone.
        assert value == orphan()
        assert value.rsplit("@", 1)[1] in domains
        assert "real-recipient" not in value
        by_seed[seed] = value
    # Two copies never share the first copy's identity surface.
    assert by_seed[b"copy-a"] != by_seed[b"copy-b"]
    # A linked delivery keeps the shared fictional owner email.
    owner_id = str(uuid.uuid4())
    maps = dsan.build_identity_maps(
        b"copy-a", data, owner_ids=[owner_id], institution_ids=[],
        cohort_ids=[], org_ids=[], team_ids=[], project_ids=[],
        budget_ids=[], template_ids=[], admin_ids=[],
    )
    linked_row = _Row(id=delivery_id, owner_id=uuid.UUID(owner_id))
    got = dsan._convert_value(
        dsan.E_OWNER_EMAIL, "real-recipient@corp.example", seed=b"copy-a",
        data=data, maps=maps, table="email_deliveries",
        column="recipient_email", row=linked_row, row_index=0,
    )
    assert got == maps.owner_email[owner_id]


def test_verifier_linked_recipient_exact_join() -> None:
    data = _identity_data()
    seed = b"copy-a"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[str(uuid.uuid4())], institution_ids=[],
        cohort_ids=[], org_ids=[], team_ids=[], project_ids=[],
        budget_ids=[], template_ids=[], admin_ids=[],
    )
    # The verifier sees the STORED (already remapped) orphan id: the
    # expected value must derive from it directly, with no second remap.
    old_orphan_id = uuid.uuid4()
    stored_orphan_id = dsan.remap_uuid(seed, old_orphan_id)
    orphan_value = dsan._orphan_recipient_email(stored_orphan_id, data)
    # ...and the sanitizer side derives the SAME value from the old id.
    assert (
        dsan._orphan_recipient_email(
            dsan.remap_uuid(seed, old_orphan_id), data
        )
        == orphan_value
    )

    async def run(linked_bad: int, orphan_rows: list) -> int:
        conn = _FakeConn(
            fetchval_results=[linked_bad],
            fetch_results=[orphan_rows],
        )
        return await dsan._column_violations(
            conn, "email_deliveries", "recipient_email",
            dsan.E_OWNER_EMAIL, data, maps=maps,
        )

    # Linked mismatch: owner A's delivery carrying owner B's fake email is
    # caught by the exact owner JOIN, not mere set membership.
    assert asyncio.run(run(1, [])) == 1
    # Orphan mismatch: derived address not applied.
    assert asyncio.run(run(0, [_Row(id=stored_orphan_id, v="wrong@x.invalid")])) == 1
    # Clean copy: exact linked email + derived orphan address.
    assert asyncio.run(run(0, [_Row(id=stored_orphan_id, v=orphan_value)])) == 0


def test_column_violations_h_shape_only_no_global_uniqueness() -> None:
    # The H branch reports ONLY shape violations. The raw value already
    # matches the 64-hex pattern (shape cannot prove remapping; the keyed
    # pre-state aggregate does that), and the schema's unique law is the
    # COMPOSITE (gateway_key_id, item_kind, hmac) constraint, so the same
    # remapped value may legitimately recur across keys: no distinct-count
    # query may be issued.
    async def run(bad_shape: int) -> int:
        conn = _FakeConn(fetchval_results=[bad_shape])
        return await dsan._column_violations(
            conn, "codex_replay_references", "item_id_hmac", dsan.H,
            _identity_data(),
        )

    assert asyncio.run(run(2)) == 2
    assert asyncio.run(run(0)) == 0
    conn = _FakeConn(fetchval_results=[0])
    asyncio.run(
        dsan._column_violations(
            conn, "codex_replay_references", "item_id_hmac", dsan.H, _identity_data()
        )
    )
    assert len(conn.calls) == 1  # exactly the shape count, nothing else


def test_ftn_action_only_reviewed_tool_name_column() -> None:
    ftn_cols = sorted(
        f"{table}.{col}"
        for table, cols in dsan.TABLE_POLICY.items()
        for col, action in cols.items()
        if action == dsan.FTN
    )
    assert ftn_cols == ["codex_replay_references.tool_name"]


def test_convert_value_ftn_row_conditional() -> None:
    data = _identity_data()
    seed = b"snap-a"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    fixed = data["fictional_tool_name"]
    for kind in ("function_call", "custom_tool_call"):
        got = dsan._convert_value(dsan.FTN, "raw-tool-name", seed=seed,
                                  data=data, maps=maps,
                                  table="codex_replay_references",
                                  column="tool_name",
                                  row=_Row(item_kind=kind), row_index=0)
        assert got == fixed
    for kind in ("reasoning", "compaction"):
        assert dsan._convert_value(dsan.FTN, None, seed=seed, data=data,
                                   maps=maps, table="codex_replay_references",
                                   column="tool_name",
                                   row=_Row(item_kind=kind), row_index=0) is None
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.FTN, None, seed=seed, data=data, maps=maps,
                            table="codex_replay_references", column="tool_name",
                            row=_Row(item_kind="unknown_kind"), row_index=0)


def test_column_violations_ftn_row_conditional() -> None:
    # One SQL count covers both directions: fixed kinds must equal the
    # fixed fictional value; null kinds must be NULL.
    async def run(bad: int) -> int:
        conn = _FakeConn(fetchval_results=[bad])
        return await dsan._column_violations(
            conn, "codex_replay_references", "tool_name", dsan.FTN,
            _identity_data(),
        )

    assert asyncio.run(run(1)) == 1
    assert asyncio.run(run(0)) == 0
    conn = _FakeConn(fetchval_results=[0])
    asyncio.run(dsan._column_violations(
        conn, "codex_replay_references", "tool_name", dsan.FTN, _identity_data()
    ))
    assert len(conn.calls) == 1


def test_fn_action_only_reviewed_tool_namespace_column() -> None:
    fn_cols = sorted(
        f"{table}.{col}"
        for table, cols in dsan.TABLE_POLICY.items()
        for col, action in cols.items()
        if action == dsan.FN
    )
    assert fn_cols == ["codex_replay_references.tool_namespace"]


def test_key_prefix_policy_is_fixed_fictional_prefix() -> None:
    # A configurable source prefix may carry an organization slug and
    # renders verbatim in admin key pages; the copy must use the fixed
    # fictional prefix instead, and it must satisfy the configured
    # gateway key prefix shape (sk-...- lowercase alnum/hyphen body).
    action = dsan.TABLE_POLICY["gateway_keys"]["key_prefix"]
    assert action == dsan.F + "demo_key_prefix"
    data = _identity_data()
    value = str(data["demo_key_prefix"])
    assert re.fullmatch(r"sk-[a-z0-9-]+-", value)
    seed = b"snap-a"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    row = _Row()
    got = dsan._convert_value(action, "sk-canary-source-org-slug-", seed=seed,
                              data=data, maps=maps, table="gateway_keys",
                              column="key_prefix", row=row, row_index=0)
    assert got == value
    assert "canary" not in str(got)


def test_convert_value_fn_row_conditional() -> None:
    data = _identity_data()
    seed = b"snap-a"
    maps = dsan.build_identity_maps(
        seed, data, owner_ids=[], institution_ids=[], cohort_ids=[],
        org_ids=[], team_ids=[], project_ids=[], budget_ids=[],
        template_ids=[], admin_ids=[],
    )
    fixed = data["fictional_tool_namespace"]
    for kind in ("function_call", "custom_tool_call"):
        got = dsan._convert_value(dsan.FN, "raw-client-namespace", seed=seed,
                                  data=data, maps=maps,
                                  table="codex_replay_references",
                                  column="tool_namespace",
                                  row=_Row(item_kind=kind), row_index=0)
        assert got == fixed
    for kind in ("reasoning", "compaction"):
        assert dsan._convert_value(dsan.FN, None, seed=seed, data=data,
                                   maps=maps, table="codex_replay_references",
                                   column="tool_namespace",
                                   row=_Row(item_kind=kind), row_index=0) is None
    with pytest.raises(ds.DemoSnapshotError):
        dsan._convert_value(dsan.FN, None, seed=seed, data=data, maps=maps,
                            table="codex_replay_references", column="tool_namespace",
                            row=_Row(item_kind="unknown_kind"), row_index=0)


def test_column_violations_fn_row_conditional() -> None:
    # Same row-conditional law as FTN: fixed kinds must equal the fixed
    # fictional namespace; null kinds must be NULL.
    async def run(bad: int) -> int:
        conn = _FakeConn(fetchval_results=[bad])
        return await dsan._column_violations(
            conn, "codex_replay_references", "tool_namespace", dsan.FN,
            _identity_data(),
        )

    assert asyncio.run(run(1)) == 1
    assert asyncio.run(run(0)) == 0
    conn = _FakeConn(fetchval_results=[0])
    asyncio.run(dsan._column_violations(
        conn, "codex_replay_references", "tool_namespace", dsan.FN, _identity_data()
    ))
    assert len(conn.calls) == 1


def test_column_violations_ip_typed_inet_comparison() -> None:
    # Regression: the inet columns render host addresses with an explicit
    # /32 suffix (inet::text), which never string-matches the bare
    # fictional list. The verifier must compare TYPED inet values against
    # the fixed addresses cast as inet[] (address AND prefix checked).
    async def run(bad: int) -> int:
        conn = _FakeConn(fetchval_results=[bad])
        return await dsan._column_violations(
            conn, "admin_sessions", "ip_address", dsan.IP, _identity_data()
        )

    assert asyncio.run(run(1)) == 1
    assert asyncio.run(run(0)) == 0
    conn = _FakeConn(fetchval_results=[0])
    asyncio.run(dsan._column_violations(
        conn, "admin_sessions", "ip_address", dsan.IP, _identity_data()
    ))
    sql = conn.calls[0][1]
    assert "<> ALL($1::inet[])" in sql
    assert "::text" not in sql


# ---------------------------------------------------------------------------
# Orchestration: custody/manifest state machine (fake connections)
# ---------------------------------------------------------------------------


def _orchestration_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _config(tmp_path)
    fake = _FakeConn()

    async def _fake_connect(_config, _target_db, *, readonly=False):
        return fake

    monkeypatch.setattr(dsan, "_connect_copy", _fake_connect)
    return config, fake


def test_sanitize_skips_already_sanitized_without_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _fake = _orchestration_env(tmp_path, monkeypatch)
    _write_job(config.custody_dir, "snap-" + "a" * 32, ds.STATE_DB_SANITIZED_UNPUBLISHED)

    def _no_db(*_a, **_k):
        raise AssertionError("no database access for an idempotent skip")

    monkeypatch.setattr(dsan, "_inventory_catalog", _no_db)

    result = dsan.sanitize_copies(config)
    assert result.state == dsan.SANITIZE_STATE_SKIPPED
    assert result.copies_sanitized == 0 and result.copies_failed == 0


def test_sanitize_catalog_failure_keeps_raw_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, fake = _orchestration_env(tmp_path, monkeypatch)
    job_id = "snap-" + "b" * 32
    job_dir = _write_job(config.custody_dir, job_id, ds.STATE_RAW_UNVERIFIED)

    async def _bad_inventory(_conn):
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_SCHEMA_UNKNOWN, "Demo copy catalog tables differ from the reviewed policy."
        )

    monkeypatch.setattr(dsan, "_inventory_catalog", _bad_inventory)

    result = dsan.sanitize_copies(config)
    assert result.state == "FAILED"
    assert result.failure_code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN
    assert result.copies_failed == 1
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.state == ds.STATE_RAW_UNVERIFIED
    assert manifest.failure_code == ds.CODE_SANITIZE_SCHEMA_UNKNOWN
    assert fake.closed


def test_sanitize_tx_failure_keeps_raw_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _fake = _orchestration_env(tmp_path, monkeypatch)
    job_id = "snap-" + "c" * 32
    job_dir = _write_job(config.custody_dir, job_id, ds.STATE_RAW_UNVERIFIED)
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)

    async def _good_inventory(_conn):
        return inv

    pre = {
        "tables": inv["tables"], "pk": {"owners": ["id"]},
        "stats": {}, "foreign_keys": inv["foreign_keys"],
        "entity_ids": {k: [] for k in dsan._ENTITY_TABLE},
    }

    async def _good_prestate(_conn, _inventory, _seed, _deadline):
        return pre

    async def _boom(*_a, **_k):
        raise ds.DemoSnapshotError(ds.CODE_SANITIZE_FAILED, "Demo sanitization exceeded its bounded time budget.")

    monkeypatch.setattr(dsan, "_inventory_catalog", _good_inventory)
    monkeypatch.setattr(dsan, "_capture_prestate", _good_prestate)
    monkeypatch.setattr(dsan, "_run_sanitizer_tx", _boom)

    result = dsan.sanitize_copies(config)
    assert result.state == "FAILED"
    assert result.failure_code == ds.CODE_SANITIZE_FAILED
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.state == ds.STATE_RAW_UNVERIFIED
    assert manifest.failure_code == ds.CODE_SANITIZE_FAILED
    # the private pre-state artifact is kept for operator inspection
    assert (job_dir / dsan._PRESTATE_NAME).is_file()


def test_sanitize_verifier_failure_keeps_raw_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _fake = _orchestration_env(tmp_path, monkeypatch)
    job_id = "snap-" + "d" * 32
    job_dir = _write_job(config.custody_dir, job_id, ds.STATE_RAW_UNVERIFIED)
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)

    async def _good_inventory(_conn):
        return inv

    pre = {
        "tables": inv["tables"], "pk": {"owners": ["id"]},
        "stats": {}, "foreign_keys": inv["foreign_keys"],
        "entity_ids": {k: [] for k in dsan._ENTITY_TABLE},
    }

    async def _good_prestate(_conn, _inventory, _seed, _deadline):
        return pre

    async def _ok_tx(*_a, **_k):
        return None

    async def _bad_verify(*_a, **_k):
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_VERIFY_FAILED, "Demo copy row count changed during sanitization."
        )

    monkeypatch.setattr(dsan, "_inventory_catalog", _good_inventory)
    monkeypatch.setattr(dsan, "_capture_prestate", _good_prestate)
    monkeypatch.setattr(dsan, "_run_sanitizer_tx", _ok_tx)
    monkeypatch.setattr(dsan, "_run_verifier", _bad_verify)

    result = dsan.sanitize_copies(config)
    assert result.state == "FAILED"
    assert result.failure_code == ds.CODE_SANITIZE_VERIFY_FAILED
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.state == ds.STATE_RAW_UNVERIFIED
    assert manifest.failure_code == ds.CODE_SANITIZE_VERIFY_FAILED


def test_sanitize_success_promotes_to_sanitized_unpublished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _fake = _orchestration_env(tmp_path, monkeypatch)
    job_id = "snap-" + "e" * 32
    job_dir = _write_job(config.custody_dir, job_id, ds.STATE_RAW_UNVERIFIED)
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)

    async def _good_inventory(_conn):
        return inv

    pre = {
        "tables": inv["tables"], "pk": {"owners": ["id"]},
        "stats": {}, "foreign_keys": inv["foreign_keys"],
        "entity_ids": {k: [] for k in dsan._ENTITY_TABLE},
    }

    async def _good_prestate(_conn, _inventory, _seed, _deadline):
        return pre

    async def _ok_tx(*_a, **_k):
        return None

    async def _ok_verify(*_a, **_k):
        return None

    monkeypatch.setattr(dsan, "_inventory_catalog", _good_inventory)
    monkeypatch.setattr(dsan, "_capture_prestate", _good_prestate)
    monkeypatch.setattr(dsan, "_run_sanitizer_tx", _ok_tx)
    monkeypatch.setattr(dsan, "_run_verifier", _ok_verify)

    result = dsan.sanitize_copies(config)
    assert result.state == dsan.SANITIZE_STATE_SANITIZED
    assert result.copies_sanitized == 1 and result.copies_failed == 0
    manifest = ds._read_manifest(job_dir)
    assert manifest is not None
    assert manifest.state == ds.STATE_DB_SANITIZED_UNPUBLISHED
    assert manifest.failure_code is None

    # idempotent re-run: no eligible copies -> SKIPPED, no DB access
    result2 = dsan.sanitize_copies(config)
    assert result2.state == dsan.SANITIZE_STATE_SKIPPED


def test_sanitize_mixed_batch_reports_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _fake = _orchestration_env(tmp_path, monkeypatch)
    job_a = "snap-" + "1" * 32
    job_b = "snap-" + "2" * 32
    _write_job(config.custody_dir, job_a, ds.STATE_RAW_UNVERIFIED)
    _write_job(config.custody_dir, job_b, ds.STATE_RAW_UNVERIFIED)
    inv = _synthetic_inventory()
    _pin_digest(monkeypatch, inv)

    calls = {"n": 0}

    async def _good_inventory(_conn):
        return inv

    pre = {
        "tables": inv["tables"], "pk": {"owners": ["id"]},
        "stats": {}, "foreign_keys": inv["foreign_keys"],
        "entity_ids": {k: [] for k in dsan._ENTITY_TABLE},
    }

    async def _good_prestate(_conn, _inventory, _seed, _deadline):
        return pre

    async def _tx(_conn, _pre, _maps, _data, _seed, _deadline):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ds.DemoSnapshotError(ds.CODE_SANITIZE_FAILED, "boom")
        return None

    async def _ok_verify(*_a, **_k):
        return None

    monkeypatch.setattr(dsan, "_inventory_catalog", _good_inventory)
    monkeypatch.setattr(dsan, "_capture_prestate", _good_prestate)
    monkeypatch.setattr(dsan, "_run_sanitizer_tx", _tx)
    monkeypatch.setattr(dsan, "_run_verifier", _ok_verify)

    result = dsan.sanitize_copies(config)
    assert result.state == "FAILED"
    assert result.copies_sanitized == 1
    assert result.copies_failed == 1
    assert result.failure_code == ds.CODE_SANITIZE_FAILED


# ---------------------------------------------------------------------------
# 221 expiry now covers sanitized-but-unpublished copies
# ---------------------------------------------------------------------------


def _fake_ops(calls: list[str]):
    def create_database(name: str, deadline: float) -> None:
        calls.append(f"create:{name}")

    def drop_database(name: str) -> bool:
        calls.append(f"drop:{name}")
        return True

    def restore(archive, name: str, deadline: float) -> None:
        calls.append(f"restore:{name}")

    def database_exists(name: str):
        return True

    return ds.TargetOps(
        create_database=create_database,
        drop_database=drop_database,
        restore=restore,
        database_exists=database_exists,
    )


def test_expiry_covers_sanitized_unpublished_copies(tmp_path: Path) -> None:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    passfile = _passfile(tmp_path)
    settings = _settings(
        DEMO_SNAPSHOT_PGPASSFILE=str(passfile),
        DEMO_SNAPSHOT_CUSTODY_DIR=str(custody),
        DEMO_SNAPSHOT_RETENTION_SECONDS=3600,
        DEMO_SNAPSHOT_MAX_COPIES=8,
    )
    config = ds.config_from_settings(settings)

    old = time.time() - 7200
    raw = "snap-" + "f" * 32
    san = "snap-" + "0" * 32
    fresh_san = "snap-" + "3" * 32
    for job_id, state in ((raw, ds.STATE_RAW_UNVERIFIED),
                          (san, ds.STATE_DB_SANITIZED_UNPUBLISHED)):
        job_dir = custody / job_id
        job_dir.mkdir(mode=0o700)
        ds._write_manifest(job_dir, ds.SnapshotManifest(
            job_id=job_id, state=state, created_at=old,
            target_db="demo_snap_" + job_id[-20:],
        ))
    fresh_dir = custody / fresh_san
    fresh_dir.mkdir(mode=0o700)
    ds._write_manifest(fresh_dir, ds.SnapshotManifest(
        job_id=fresh_san, state=ds.STATE_DB_SANITIZED_UNPUBLISHED,
        created_at=time.time(), target_db="demo_snap_" + fresh_san[-20:],
    ))

    calls: list[str] = []
    removed = ds._expire_copies(config, _fake_ops(calls), now=time.time())
    assert removed == 2
    assert f"drop:demo_snap_{raw[-20:]}" in calls
    assert f"drop:demo_snap_{san[-20:]}" in calls
    assert f"drop:demo_snap_{fresh_san[-20:]}" not in calls


def test_fence_serializes_sanitize(tmp_path: Path) -> None:
    config = _config(tmp_path)
    ds._validate_custody_dir(config.custody_dir)
    fd = ds._acquire_fence(config.custody_dir)
    try:
        with pytest.raises(ds.DemoSnapshotError) as exc:
            dsan.sanitize_copies(config)
        assert exc.value.code == ds.CODE_FENCE_HELD
    finally:
        ds._release_fence(fd)
