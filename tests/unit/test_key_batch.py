"""Native unit evidence for 203-a reviewed key-configuration batches.

Covers the strict plan schema/IO boundaries (safe fixed errors, derived
diff/count re-derivation, tamper refusal, known-shape refusal, bounded
exclusive write) and the shared KeyBatchService selection/preview/apply
laws (read-only preview, bounded selection, stale/membership/drift
refusal with ZERO writes, repeat no-op law, usage-only non-staleness,
deterministic lock order, reason bounds) using honest fakes. Real
PostgreSQL evidence lives in tests/integration/test_cli_key_batch_postgres.py.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_MAX_KEYS,
    KeyBatchError,
    KeyBatchStaleError,
    key_batch_document_changes,
    key_batch_state_fingerprint,
    parse_key_batch_plan,
    parse_key_batch_plan_file,
    render_key_batch_plan,
    write_key_batch_plan_file,
)
from slaif_gateway.schemas.key_configuration import parse_key_configuration
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.key_batch_service import (
    APPLY_STATUS_ALREADY_AT_TARGET,
    APPLY_STATUS_APPLIED,
    APPLY_STATUS_NO_CHANGE,
    KeyBatchService,
)
from tests.unit.key_management_fakes import (
    FakeAuditRepository,
    FakeGatewayKeyRow,
    FakeGatewayKeysRepository,
    make_key_service,
)

NOW = datetime(2026, 10, 29, 7, 0, 0, tzinfo=UTC)

CANARY = "sk-slaif-canary203a00000000000"


# ---------------------------------------------------------------------------
# fakes: batch selection + deterministic lock-order observation
# ---------------------------------------------------------------------------


class BatchKeysRepository(FakeGatewayKeysRepository):
    """Honest fake with the additive batch reads and lock-order recording.

    The limit writer quantizes a non-None cost to the exact
    ``Numeric(18, 9)`` storage scale the real column enforces (an honest
    column emulation; the owned-PostgreSQL suite proves the same law
    natively - the fake alone is not storage proof).
    """

    def __init__(self, rows: list[FakeGatewayKeyRow] | None = None) -> None:
        super().__init__(rows[0] if rows else None)
        for row in rows or []:
            self.rows[row.id] = row
        self.lock_order: list[uuid.UUID] = []
        self.selection_calls: list[dict[str, object]] = []
        self._stored_cost: dict[uuid.UUID, Decimal] = {}

    async def update_gateway_key_limits(
        self,
        gateway_key_id: uuid.UUID,
        *,
        cost_limit_eur: Decimal | None = None,
        token_limit_total: int | None = None,
        request_limit_total: int | None = None,
    ) -> bool:
        if cost_limit_eur is not None:
            cost_limit_eur = cost_limit_eur.quantize(Decimal("0.000000001"))
        result = await super().update_gateway_key_limits(
            gateway_key_id,
            cost_limit_eur=cost_limit_eur,
            token_limit_total=token_limit_total,
            request_limit_total=request_limit_total,
        )
        # The durable value (what a fresh SELECT returns) is at the
        # storage scale; the ORM attribute may still hold the Python value.
        if result and cost_limit_eur is not None:
            self._stored_cost[gateway_key_id] = cost_limit_eur
        return result

    async def get_gateway_key_for_update(self, gateway_key_id: uuid.UUID):
        self.lock_order.append(gateway_key_id)
        row = self.rows.get(gateway_key_id)
        # populate_existing emulation: a fresh locked read observes the
        # coerced column value.
        if row is not None and gateway_key_id in self._stored_cost:
            row.cost_limit_eur = self._stored_cost[gateway_key_id]
        return row

    async def list_key_batch_selection(
        self, *, cohort_id: uuid.UUID, statuses, limit: int
    ) -> list[FakeGatewayKeyRow]:
        self.selection_calls.append(
            {"cohort_id": cohort_id, "statuses": tuple(statuses), "limit": limit}
        )
        rows = [
            row
            for row in self.rows.values()
            if row.cohort_id == cohort_id and row.status in tuple(statuses)
        ]
        return sorted(rows, key=lambda r: r.id)[:limit]

    async def get_gateway_keys_by_ids(self, *, key_ids) -> list[FakeGatewayKeyRow]:
        wanted = set(key_ids)
        return [row for row in sorted(self.rows.values(), key=lambda r: r.id) if row.id in wanted]


class FakeCohortsRepository:
    def __init__(self, cohorts: dict[uuid.UUID, object] | None = None) -> None:
        self.cohorts = cohorts or {}

    async def get_cohort_by_id(self, cohort_id: uuid.UUID):
        return self.cohorts.get(cohort_id)


def _make_rows(
    count: int = 2,
    *,
    cohort_id: uuid.UUID | None = None,
    status: str = "active",
) -> list[FakeGatewayKeyRow]:
    cohort = cohort_id if cohort_id is not None else uuid.uuid4()
    return [
        FakeGatewayKeyRow(
            cohort_id=cohort,
            status=status,
            cost_limit_eur=Decimal("5.000000000"),
            token_limit_total=1000,
            request_limit_total=100,
        )
        for _ in range(count)
    ]


def _make_batch_service(
    rows: list[FakeGatewayKeyRow],
    *,
    cohort_id: uuid.UUID | None = None,
) -> tuple[KeyBatchService, BatchKeysRepository, FakeAuditRepository, KeyBatchService]:
    keys_repo = BatchKeysRepository(rows)
    _, _, one_time_repo, audit_repo, _ = make_key_service(rows[0] if rows else None)
    # Rebuild the KeyService bound to the BATCH repository (multi-row).
    from slaif_gateway.config import Settings
    from slaif_gateway.utils.secrets import generate_secret_key
    from slaif_gateway.services.key_service import KeyService

    settings = Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ONE_TIME_SECRET_KEY_VERSION="v1",
        GATEWAY_KEY_PREFIX="sk-slaif-",
    )
    key_service = KeyService(
        settings=settings,
        gateway_keys_repository=keys_repo,
        one_time_secrets_repository=one_time_repo,
        audit_repository=audit_repo,
    )
    service = KeyBatchService(
        gateway_keys_repository=keys_repo,
        cohorts_repository=FakeCohortsRepository({cohort_id: object()} if cohort_id else {}),
        key_service=key_service,
        now_factory=lambda: NOW,
    )
    return service, keys_repo, audit_repo, key_service


POLICY = {"schema_version": 1, "request_limit_total": 2000}


def _policy() -> object:
    return parse_key_configuration(POLICY)


# ---------------------------------------------------------------------------
# schema: fingerprint + diff helpers
# ---------------------------------------------------------------------------


def test_fingerprint_excludes_usage_and_covers_identity_context() -> None:
    doc = {"schema_version": 1, "request_limit_total": 100}
    owner = uuid.uuid4()
    cohort = uuid.uuid4()
    base = dict(
        config_document=doc,
        owner_id=owner,
        cohort_id=cohort,
        status="active",
        key_purpose="standard",
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
    )
    first = key_batch_state_fingerprint(**base)
    assert key_batch_state_fingerprint(**base) == first
    assert len(first) == 64
    # status drift changes the fingerprint
    assert key_batch_state_fingerprint(**{**base, "status": "suspended"}) != first
    # config drift changes the fingerprint
    assert key_batch_state_fingerprint(**{**base, "config_document": {**doc, "request_limit_total": 2}}) != first
    # validity drift changes the fingerprint
    assert key_batch_state_fingerprint(**{**base, "valid_until": NOW + timedelta(days=2)}) != first


def test_document_changes_derived_and_deterministic() -> None:
    before = {"schema_version": 1, "request_limit_total": 1, "cost_limit_eur": None}
    after = {"schema_version": 1, "request_limit_total": 2, "cost_limit_eur": "3.000000000"}
    changes = key_batch_document_changes(before, after)
    assert [c["field"] for c in changes] == ["cost_limit_eur", "request_limit_total"]
    assert key_batch_document_changes(after, before) != changes
    assert key_batch_document_changes(before, before) == ()


# ---------------------------------------------------------------------------
# schema: strict parse boundaries
# ---------------------------------------------------------------------------


def _valid_plan_document() -> dict[str, object]:
    kid = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
    before = {"schema_version": 1, "request_limit_total": 100}
    after = {"schema_version": 1, "request_limit_total": 2000}
    changes = [dict(c) for c in key_batch_document_changes(before, after)]
    context = dict(
        config_document=before,
        owner_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        cohort_id=None,
        status="active",
        key_purpose="standard",
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
    )
    return {
        "schema_version": 1,
        "operation": "apply",
        "selection_kind": "keys",
        "cohort_id": None,
        "key_ids": [kid],
        "statuses": ["active"],
        "policy": {"schema_version": 1, "request_limit_total": 2000},
        "keys": [
            {
                "key_id": kid,
                "source_fingerprint": key_batch_state_fingerprint(**context),
                "post_fingerprint": key_batch_state_fingerprint(
                    **{**context, "config_document": after}
                ),
                "before": before,
                "after": after,
                "changes": changes,
            }
        ],
        "selected_count": 1,
        "changed_count": 1,
        "unchanged_count": 0,
        "excluded_by_status": [],
        "planned_at": NOW.isoformat(),
    }


def test_valid_plan_round_trips() -> None:
    doc = _valid_plan_document()
    plan = parse_key_batch_plan(doc)
    assert plan.key_ids == (doc["key_ids"][0],)
    assert plan.selected_count == 1 and plan.changed_count == 1
    assert render_key_batch_plan(plan) == doc


def test_missing_top_level_fields_are_safe_errors() -> None:
    doc = _valid_plan_document()
    del doc["planned_at"]
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "missing required fields" in str(exc.value)
    assert exc.value.error_code == "key_batch_plan"


def test_non_object_documents_are_safe_errors() -> None:
    with pytest.raises(KeyBatchError):
        parse_key_batch_plan([1, 2, 3])  # type: ignore[arg-type]
    with pytest.raises(KeyBatchError):
        parse_key_batch_plan("nope")  # type: ignore[arg-type]
    doc = _valid_plan_document()
    doc["keys"] = "not-a-list"
    with pytest.raises(KeyBatchError):
        parse_key_batch_plan(doc)


def test_unknown_nested_snapshot_fields_are_refused() -> None:
    doc = _valid_plan_document()
    doc["keys"][0]["before"]["rogue_field"] = 1
    doc["keys"][0]["after"]["rogue_field"] = 1
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "before" in str(exc.value)


def test_known_secret_shape_is_refused_at_parse_and_write() -> None:
    doc = _valid_plan_document()
    doc["keys"][0]["before"]["allowed_models"] = [CANARY]
    doc["keys"][0]["after"]["allowed_models"] = [CANARY]
    doc["keys"][0]["changes"] = []
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "credential shape" in str(exc.value)
    # The bounded writer re-validates through the SAME parse gate, so a
    # recognized shape can never be produced or persisted through it.
    plan = parse_key_batch_plan(_valid_plan_document())
    assert "credential" not in json.dumps(render_key_batch_plan(plan))


def _parse_raw(raw: str) -> None:
    from slaif_gateway.schemas.key_batch import _load_strict_object, parse_key_batch_plan

    document = _load_strict_object(raw.encode("utf-8"), 8 * 1024 * 1024)
    parse_key_batch_plan(document)


def test_duplicate_json_keys_refused_in_file() -> None:
    raw = json.dumps(_valid_plan_document()).replace(
        '"planned_at":', '"planned_at": "x", "planned_at":', 1
    )
    with pytest.raises(KeyBatchError) as exc:
        _parse_raw(raw)
    assert "duplicate" in str(exc.value)


def test_unsorted_or_repeated_key_ids_refused() -> None:
    doc = _valid_plan_document()
    kid = doc["key_ids"][0]
    doc["key_ids"] = [kid, kid]
    doc["keys"] = doc["keys"] * 2
    doc["selected_count"] = 2
    with pytest.raises(KeyBatchError):
        parse_key_batch_plan(doc)
    doc = _valid_plan_document()
    smaller = "00000000-0000-0000-0000-000000000000"  # sorts before the original
    doc["key_ids"] = [doc["key_ids"][0], smaller]  # unsorted (larger first)
    doc["keys"][0]["key_id"] = doc["key_ids"][0]
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "sorted" in str(exc.value)


def test_tampered_counts_and_diffs_refused() -> None:
    doc = _valid_plan_document()
    doc["changed_count"] = 0
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "changed_count" in str(exc.value)

    doc = _valid_plan_document()
    doc["keys"][0]["changes"] = []
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "changes" in str(exc.value)

    doc = _valid_plan_document()
    doc["selected_count"] = 2
    with pytest.raises(KeyBatchError):
        parse_key_batch_plan(doc)


def test_selected_plus_excluded_combined_bound() -> None:
    doc = _valid_plan_document()
    doc["excluded_by_status"] = [
        {"key_id": str(uuid.uuid4()), "status": "suspended"} for _ in range(1000)
    ]
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "1000" in str(exc.value)


def test_excluded_status_must_be_outside_filter() -> None:
    doc = _valid_plan_document()
    doc["excluded_by_status"] = [
        {"key_id": str(uuid.uuid4()), "status": "active"}
    ]
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan(doc)
    assert "outside the selected status filter" in str(exc.value)


def test_plan_file_oversize_and_exclusive_write(tmp_path: Path) -> None:
    # Oversize file is refused by the bounded read (max+1 bytes read).
    big = tmp_path / "big.json"
    big.write_bytes(b"{" + b" " * (8 * 1024 * 1024) + b"}")
    with pytest.raises(KeyBatchError) as exc:
        parse_key_batch_plan_file(big)
    assert "exceeds" in str(exc.value)

    plan = parse_key_batch_plan(_valid_plan_document())
    out = tmp_path / "plan.json"
    write_key_batch_plan_file(out, plan)
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert parse_key_batch_plan_file(out) == plan
    # O_EXCL: existing file is never overwritten.
    with pytest.raises(KeyBatchError) as exc:
        write_key_batch_plan_file(out, plan)
    assert "new writable file" in str(exc.value)


# ---------------------------------------------------------------------------
# service: plan (read-only preview)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_cohort_read_only_exact_preview() -> None:
    cohort_id = uuid.uuid4()
    rows = _make_rows(3, cohort_id=cohort_id)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows, cohort_id=cohort_id)

    plan = await service.plan(
        cohort_id=cohort_id, key_ids=(), statuses=["active"], policy=_policy()
    )
    assert plan.selection_kind == "cohort"
    assert plan.cohort_id == str(cohort_id)
    assert list(plan.key_ids) == [str(r.id) for r in sorted(rows, key=lambda r: r.id)]
    assert plan.selected_count == 3 and plan.changed_count == 3
    for entry in plan.keys:
        assert entry.before["request_limit_total"] == 100
        assert entry.after["request_limit_total"] == 2000
        assert entry.changes == key_batch_document_changes(entry.before, entry.after)
    # Read-only: no writes, no audits, no limit/policy/metadata calls.
    assert audit_repo.calls == []
    assert keys_repo.limit_calls == [] and keys_repo.policy_calls == []
    assert keys_repo.metadata_calls == [] and keys_repo.rate_limit_calls == []
    # Deterministic sorted-UUID lock order.
    assert keys_repo.lock_order == sorted(r.id for r in rows)
    # Bounded selection read (cap+1) with the finite status filter.
    assert keys_repo.selection_calls == [
        {"cohort_id": cohort_id, "statuses": ("active",), "limit": KEY_BATCH_MAX_KEYS + 1}
    ]


@pytest.mark.asyncio
async def test_plan_explicit_keys_mixed_statuses_and_duplicates() -> None:
    rows = _make_rows(3)
    rows[1].status = "suspended"
    rows[2].status = "revoked"
    service, _, _, _ = _make_batch_service(rows)

    plan = await service.plan(
        cohort_id=None,
        key_ids=[r.id for r in rows],
        statuses=["active", "suspended"],
        policy=_policy(),
    )
    assert plan.selection_kind == "keys"
    assert plan.cohort_id is None
    assert plan.selected_count == 2
    assert plan.excluded_by_status == ((str(rows[2].id), "revoked"),)

    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=None,
            key_ids=[rows[0].id, rows[0].id],
            statuses=["active"],
            policy=_policy(),
        )
    assert "duplicate" in str(exc.value)


@pytest.mark.asyncio
async def test_plan_missing_keys_fail_whole_request_safely() -> None:
    rows = _make_rows(1)
    service, _, _, _ = _make_batch_service(rows)
    missing = uuid.uuid4()
    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=None,
            key_ids=[rows[0].id, missing],
            statuses=["active"],
            policy=_policy(),
        )
    message = str(exc.value)
    assert "1 requested keys were not found" in message
    assert str(missing) not in message
    assert exc.value.error_code == "key_batch_key_not_found"


@pytest.mark.asyncio
async def test_plan_cohort_overflow_refused() -> None:
    cohort_id = uuid.uuid4()
    rows = _make_rows(KEY_BATCH_MAX_KEYS + 1, cohort_id=cohort_id)
    service, _, _, _ = _make_batch_service(rows, cohort_id=cohort_id)
    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=cohort_id, key_ids=(), statuses=["active"], policy=_policy()
        )
    assert exc.value.error_code == "key_batch_selection_overflow"


@pytest.mark.asyncio
async def test_plan_empty_eligible_selection_is_explicit_no_change() -> None:
    cohort_id = uuid.uuid4()
    rows = [FakeGatewayKeyRow(cohort_id=cohort_id, status="revoked")]
    service, _, _, _ = _make_batch_service(rows, cohort_id=cohort_id)
    plan = await service.plan(
        cohort_id=cohort_id, key_ids=(), statuses=["active"], policy=_policy()
    )
    assert plan.selected_count == 0 and plan.keys == ()
    assert plan.changed_count == 0 and plan.unchanged_count == 0


@pytest.mark.asyncio
async def test_plan_requires_exactly_one_selection_source_and_finite_statuses() -> None:
    rows = _make_rows(1)
    cohort_id = rows[0].cohort_id
    service, _, _, _ = _make_batch_service(rows, cohort_id=cohort_id)
    with pytest.raises(KeyBatchError):
        await service.plan(
            cohort_id=cohort_id, key_ids=[rows[0].id], statuses=["active"], policy=_policy()
        )
    with pytest.raises(KeyBatchError):
        await service.plan(
            cohort_id=None, key_ids=(), statuses=["active"], policy=_policy()
        )
    with pytest.raises(KeyBatchError):
        await service.plan(
            cohort_id=cohort_id, key_ids=(), statuses=["expired"], policy=_policy()
        )
    with pytest.raises(KeyBatchError):
        await service.plan(
            cohort_id=cohort_id, key_ids=(), statuses=["active"],
            policy=parse_key_configuration({"schema_version": 1}),
        )


@pytest.mark.asyncio
async def test_plan_cohort_not_found() -> None:
    rows = _make_rows(1)
    service, _, _, _ = _make_batch_service(rows)
    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=uuid.uuid4(), key_ids=(), statuses=["active"], policy=_policy()
        )
    assert exc.value.error_code == "key_batch_cohort_not_found"


# ---------------------------------------------------------------------------
# service: apply (atomic law on honest fakes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_happy_path_per_key_service_and_audit() -> None:
    rows = _make_rows(2)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    result = await service.apply(
        plan=plan, reason="batch window", actor_admin_id=uuid.uuid4()
    )
    assert result.status == APPLY_STATUS_APPLIED
    assert result.selected_count == 2 and result.changed_count == 2
    assert keys_repo.limit_calls == [
        {
            "gateway_key_id": r.id,
            "cost_limit_eur": r.cost_limit_eur,
            "token_limit_total": 1000,
            "request_limit_total": 2000,
        }
        for r in sorted(rows, key=lambda r: r.id)
    ]
    # Existing per-key audit law: one audit per key, exact reason/actor.
    actor = audit_repo.calls[0]["admin_user_id"]
    assert len(audit_repo.calls) == 2
    for call in audit_repo.calls:
        assert call["action"] == "update_key_configuration"
        assert call["note"] == "batch window"
        assert call["admin_user_id"] == actor
        assert "token_hash" not in str(call)
    for row in rows:
        assert row.request_limit_total == 2000


@pytest.mark.asyncio
async def test_apply_repeat_whole_set_is_already_at_target_zero_writes() -> None:
    rows = _make_rows(2)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    first = await service.apply(plan=plan, reason="first apply")
    assert first.status == APPLY_STATUS_APPLIED
    limit_calls_after_first = len(keys_repo.limit_calls)
    audits_after_first = len(audit_repo.calls)
    second = await service.apply(plan=plan, reason="repeat apply")
    assert second.status == APPLY_STATUS_ALREADY_AT_TARGET
    assert second.changed_count == 0 and second.unchanged_count == 2
    assert len(keys_repo.limit_calls) == limit_calls_after_first
    assert len(audit_repo.calls) == audits_after_first


@pytest.mark.asyncio
async def test_apply_initial_no_effect_rows_count_unchanged() -> None:
    rows = _make_rows(2)
    rows[1].request_limit_total = 2000  # already at the reviewed target value
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    assert plan.changed_count == 1 and plan.unchanged_count == 1
    result = await service.apply(plan=plan, reason="partial no-op")
    assert result.status == APPLY_STATUS_APPLIED
    assert result.changed_count == 1 and result.unchanged_count == 1
    assert len(keys_repo.limit_calls) == 1
    assert keys_repo.limit_calls[0]["gateway_key_id"] == rows[0].id
    assert len(audit_repo.calls) == 1


@pytest.mark.asyncio
async def test_apply_usage_only_changes_do_not_stale_repeat() -> None:
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    await service.apply(plan=plan, reason="apply once")
    # Usage-only counter movement between preview/apply must NOT stale.
    for row in rows:
        row.cost_used_eur = Decimal("42.000000000")
        row.tokens_used_total = 999
        row.requests_used_total = 9
        row.last_used_at = NOW + timedelta(minutes=5)
        row.updated_at = NOW + timedelta(minutes=5)
    result = await service.apply(plan=plan, reason="repeat after usage")
    assert result.status == APPLY_STATUS_ALREADY_AT_TARGET
    assert result.unchanged_count == 1
    assert row.cost_used_eur == Decimal("42.000000000")  # usage preserved


@pytest.mark.asyncio
async def test_apply_mixed_partial_state_refused_zero_writes() -> None:
    rows = _make_rows(2)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    # Foreign writer finished one key of the reviewed set already.
    rows[0].request_limit_total = 2000
    with pytest.raises(KeyBatchStaleError) as exc:
        await service.apply(plan=plan, reason="mixed")
    assert exc.value.error_code == "key_batch_stale"
    assert keys_repo.limit_calls == [] and audit_repo.calls == []
    assert rows[1].request_limit_total == 100  # untouched


@pytest.mark.asyncio
async def test_apply_config_drift_refused_zero_writes() -> None:
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    rows[0].request_limit_total = 777  # drift after review
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=plan, reason="drift")
    assert keys_repo.limit_calls == [] and audit_repo.calls == []


@pytest.mark.asyncio
async def test_apply_status_drift_and_deletion_refused() -> None:
    rows = _make_rows(1)
    service, keys_repo, _, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    rows[0].status = "suspended"
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=plan, reason="status drift")
    assert keys_repo.limit_calls == []

    rows[0].status = "active"
    keys_repo.rows.pop(rows[0].id)
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=plan, reason="deleted")
    assert keys_repo.limit_calls == []


@pytest.mark.asyncio
async def test_apply_cohort_membership_change_after_review_refused() -> None:
    cohort_id = uuid.uuid4()
    rows = _make_rows(2, cohort_id=cohort_id)
    service, keys_repo, _, _ = _make_batch_service(rows, cohort_id=cohort_id)
    plan = await service.plan(
        cohort_id=cohort_id, key_ids=(), statuses=["active"], policy=_policy()
    )
    # A new eligible cohort member joins after the review.
    newcomer = FakeGatewayKeyRow(cohort_id=cohort_id, status="active")
    keys_repo.rows[newcomer.id] = newcomer
    with pytest.raises(KeyBatchStaleError) as exc:
        await service.apply(plan=plan, reason="membership changed")
    assert exc.value.error_code == "key_batch_stale"
    assert keys_repo.limit_calls == []


@pytest.mark.asyncio
async def test_apply_edited_after_document_refused() -> None:
    rows = _make_rows(1)
    service, keys_repo, _, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    document = render_key_batch_plan(plan)
    # Semantically edited target that still passes field syntax.
    for key in document["keys"]:
        key["after"]["request_limit_total"] = 5000
        key["changes"][0]["after"] = 5000
    edited = parse_key_batch_plan(document)
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=edited, reason="edited target")
    assert keys_repo.limit_calls == []


@pytest.mark.asyncio
async def test_apply_edited_larger_target_after_prior_apply_refused() -> None:
    rows = _make_rows(1)
    service, keys_repo, _, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    await service.apply(plan=plan, reason="first")
    document = render_key_batch_plan(plan)
    for key in document["keys"]:
        key["after"]["request_limit_total"] = 9000
        key["changes"][0]["after"] = 9000
    document["policy"]["request_limit_total"] = 9000
    edited = parse_key_batch_plan(document)
    # The re-derived target matches the edited plan, but the reviewed
    # source fingerprint no longer matches: NOT a false already-at-target.
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=edited, reason="bigger repeat")
    assert rows[0].request_limit_total == 2000  # original target preserved


@pytest.mark.asyncio
async def test_apply_coherent_edit_stale_post_fingerprint_refused_on_first() -> None:
    """FIRST-apply state of the coherent edit: a fresh source (100)
    reviewed at 2000, then a coherently edited patch+after+diff to 9000
    still carrying the recorded 2000 post digest, is refused BEFORE any
    write on the very first apply (the semantic post-fingerprint
    relationship the strict parser cannot see).
    """
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[rows[0].id], statuses=["active"], policy=_policy()
    )
    document = render_key_batch_plan(plan)
    for key in document["keys"]:
        key["after"]["request_limit_total"] = 9000
        key["changes"][0]["after"] = 9000
    document["policy"]["request_limit_total"] = 9000
    edited = parse_key_batch_plan(document)
    with pytest.raises(KeyBatchStaleError):
        await service.apply(plan=edited, reason="coherent first edit")
    assert keys_repo.limit_calls == [] and audit_repo.calls == []
    assert rows[0].request_limit_total == 100


FENCED_POLICY_DOC = {
    "schema_version": 1,
    "request_limit_total": 500,
    "token_limit_total": 100_000,
    "cost_limit_eur": "10.000000000",
    "external_tool_policy": {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": ["provider_web_search"],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": 1,
        "single_request_overrun_acknowledged": True,
    },
    "confirm_external_tool_fenced": True,
}


@pytest.mark.asyncio
async def test_apply_fenced_target_requires_fresh_confirmation() -> None:
    """A SAVED plan confirmation is never authority (item 8)."""
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None,
        key_ids=[r.id for r in rows],
        statuses=["active"],
        policy=parse_key_configuration(FENCED_POLICY_DOC),
    )
    # The preview input is recorded INFORMATIONALLY in the saved plan.
    assert render_key_batch_plan(plan)["policy"]["confirm_external_tool_fenced"] is True

    # No fresh apply-time flag: refused BEFORE any write or audit.
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.apply(plan=plan, reason="fenced without fresh flag")
    assert exc.value.param == "confirm_external_tool_fenced"
    assert keys_repo.limit_calls == [] and audit_repo.calls == []
    assert rows[0].request_limit_total == 100

    # Fresh explicit flag: applies with one per-key audit.
    result = await service.apply(
        plan=plan, reason="fenced with fresh flag", confirm_external_tool_fenced=True
    )
    assert result.status == APPLY_STATUS_APPLIED
    assert len(audit_repo.calls) == 1
    assert rows[0].metadata_json["external_tool_policy"]["mode"] == "external_tool_fenced"

    # Repeated decisions retain the CURRENT guard: no fresh flag refuses
    # with zero new audits; the fresh flag is explicit already-at-target.
    with pytest.raises(InvalidGatewayKeyPolicyError):
        await service.apply(plan=plan, reason="fenced repeat without flag")
    assert len(audit_repo.calls) == 1
    repeat = await service.apply(
        plan=plan, reason="fenced repeat with flag", confirm_external_tool_fenced=True
    )
    assert repeat.status == APPLY_STATUS_ALREADY_AT_TARGET
    assert repeat.unchanged_count == 1
    assert len(audit_repo.calls) == 1


@pytest.mark.asyncio
async def test_plan_input_policy_canary_refused_before_projection() -> None:
    """New-batch boundary: known shape in the typed INPUT policy."""
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    bad = parse_key_configuration({"schema_version": 1, "allowed_models": [CANARY]})
    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=None, key_ids=[rows[0].id], statuses=["active"], policy=bad
        )
    assert exc.value.error_code == "key_batch_policy"
    assert CANARY not in str(exc.value)
    assert keys_repo.lock_order == [] and keys_repo.limit_calls == []
    assert audit_repo.calls == []
    assert rows[0].request_limit_total == 100


@pytest.mark.asyncio
async def test_plan_stored_current_config_canary_refused_before_projection() -> None:
    """New-batch boundary: known shape in the RETAINED current config."""
    row = FakeGatewayKeyRow(
        allowed_models=[CANARY], request_limit_total=100
    )
    service, keys_repo, audit_repo, _ = _make_batch_service([row])
    with pytest.raises(KeyBatchError) as exc:
        await service.plan(
            cohort_id=None, key_ids=[row.id], statuses=["active"], policy=_policy()
        )
    assert exc.value.error_code == "key_batch_policy"
    assert CANARY not in str(exc.value)
    assert keys_repo.limit_calls == [] and audit_repo.calls == []
    assert row.request_limit_total == 100 and row.allowed_models == [CANARY]


@pytest.mark.asyncio
async def test_apply_edited_plan_input_canary_refused() -> None:
    """The saved plan is an artifact: a parsed plan object carrying a
    known shape in its input policy is re-guarded by the SERVICE before
    projection (the strict parser already refuses such documents at
    parse/write time; the service never trusts the object either).
    """
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[rows[0].id], statuses=["active"], policy=_policy()
    )
    edited = dataclasses.replace(
        plan,
        policy={"schema_version": 1, "request_limit_total": 2000,
                "allowed_models": [CANARY]},
    )
    with pytest.raises(KeyBatchError) as exc:
        await service.apply(plan=edited, reason="edited canary")
    assert exc.value.error_code == "key_batch_policy"
    assert CANARY not in str(exc.value)
    assert keys_repo.limit_calls == [] and audit_repo.calls == []
    assert rows[0].request_limit_total == 100


@pytest.mark.asyncio
async def test_apply_empty_selection_is_no_change() -> None:
    rows = [FakeGatewayKeyRow(status="revoked")]
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    result = await service.apply(plan=plan, reason="nothing eligible")
    assert result.status == APPLY_STATUS_NO_CHANGE
    assert result.selected_count == 0
    assert keys_repo.limit_calls == [] and audit_repo.calls == []


@pytest.mark.asyncio
async def test_apply_reason_bounds_and_credential_refusal_no_echo() -> None:
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=_policy()
    )
    with pytest.raises(KeyBatchError) as exc:
        await service.apply(plan=plan, reason="   ")
    assert exc.value.error_code == "key_batch_reason"
    with pytest.raises(KeyBatchError):
        await service.apply(plan=plan, reason="x" * 513)
    credential_reason = f"rotate {CANARY} now"
    with pytest.raises(KeyBatchError) as exc:
        await service.apply(plan=plan, reason=credential_reason)
    assert exc.value.error_code == "key_batch_reason"
    assert CANARY not in str(exc.value)
    assert keys_repo.limit_calls == [] and audit_repo.calls == []


@pytest.mark.asyncio
async def test_apply_money_target_normalization_and_repeat() -> None:
    rows = _make_rows(1)
    service, keys_repo, audit_repo, _ = _make_batch_service(rows)
    money = parse_key_configuration({"schema_version": 1, "cost_limit_eur": 2})
    plan = await service.plan(
        cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=money
    )
    # NEW projection boundary: target renders the exact 9-decimal storage
    # scale (the existing setter law accepts plain decimals too).
    assert plan.keys[0].after["cost_limit_eur"] == "2.000000000"
    result = await service.apply(plan=plan, reason="money batch")
    assert result.status == APPLY_STATUS_APPLIED
    repeat = await service.apply(plan=plan, reason="money repeat")
    assert repeat.status == APPLY_STATUS_ALREADY_AT_TARGET
    assert repeat.unchanged_count == 1
    assert rows[0].cost_limit_eur == Decimal("2.000000000")

    over = parse_key_configuration({"schema_version": 1, "cost_limit_eur": "1.1234567891"})
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.plan(
            cohort_id=None, key_ids=[r.id for r in rows], statuses=["active"], policy=over
        )
    assert "9-decimal" in str(exc.value)
