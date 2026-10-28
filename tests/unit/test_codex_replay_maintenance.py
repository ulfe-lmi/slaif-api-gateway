"""Pure-layer evidence for the shared Codex replay maintenance service (200).

Fakes the administrative repository surface and the audit repository;
proves the eligibility law, the original-age target (created + TTL), the
monotonic no-shorten rule, the fingerprint pre-state/post-state decision
logic (first apply / already-applied no-op / stale), scope isolation,
bounded ceilings, and that no digest, row UUID, or secret ever reaches the
plan document or the audit payload.
"""

from __future__ import annotations

import copy
import json
import os
import stat
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.codex_replay import (
    ReplayMaintenanceKeyState,
    ReplayMaintenanceRow,
    ReplayReferenceTotals,
)
from slaif_gateway.schemas.codex_replay_maintenance import (
    REPLAY_PLAN_MAX_BYTES,
    parse_replay_extend_plan_document,
    parse_replay_extend_plan_file,
    parse_scope_uuid,
    render_replay_extend_plan,
    write_replay_extend_plan_file,
)
from slaif_gateway.services.codex_replay_maintenance import (
    EXTEND_ACTION,
    CodexReplayMaintenanceService,
    ReplayMaintenanceError,
    ReplayMaintenanceStaleError,
)
from slaif_gateway.schemas.codex_replay_maintenance import ReplayScope

KEY_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
KEY_B = uuid.UUID("22222222-3333-4444-8555-666666666666")
LEDGER_1 = uuid.UUID("44444444-5555-4666-8777-888888888888")
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
TTL_365 = 31_536_000


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "APP_ENV": "development",
        "ACTIVE_HMAC_KEY_VERSION": "1",
        "TOKEN_HMAC_SECRET": "unit-maintenance-secret",
        "CODEX_REPLAY_REFERENCE_TTL_SECONDS": TTL_365,
    }
    base.update(overrides)
    return Settings(**base)


def _key_state(
    key_id: uuid.UUID = KEY_A,
    status: str = "active",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> ReplayMaintenanceKeyState:
    return ReplayMaintenanceKeyState(
        id=key_id,
        status=status,
        valid_from=valid_from or (NOW - timedelta(days=10)),
        valid_until=valid_until or (NOW + timedelta(days=3650)),
    )


def _row(
    *,
    row_id: uuid.UUID | None = None,
    key_id: uuid.UUID = KEY_A,
    digest: str = DIGEST_A,
    kind: str = "function_call",
    ledger: uuid.UUID = LEDGER_1,
    version: int = 1,
    created: datetime | None = None,
    expires: datetime | None = None,
    ledger_finalized: bool = True,
) -> ReplayMaintenanceRow:
    created = created or (NOW - timedelta(days=10))
    return ReplayMaintenanceRow(
        id=row_id or uuid.uuid4(),
        gateway_key_id=key_id,
        item_kind=kind,
        item_id_hmac=digest,
        usage_ledger_id=ledger,
        hmac_key_version=version,
        created_at=created,
        # Default retained expiry: active but shorter than the 365d target
        # (created + 365d), so a default row is eligible for extension.
        expires_at=expires or (created + timedelta(days=90)),
        ledger_finalized=ledger_finalized,
    )


class FakeMaintenanceRepository:
    def __init__(self) -> None:
        self.key_states: list[ReplayMaintenanceKeyState] = []
        self.rows: list[ReplayMaintenanceRow] = []
        self.versions: list[int] = [1]
        self.totals = ReplayReferenceTotals(0, 0, None, None, None, None)
        self.per_key: list[tuple] = []
        self.route_groups: list[tuple] = []
        self.route_groups_total = 0
        self.extend_calls: list[list[tuple[uuid.UUID, datetime]]] = []
        self.locked_keys: list[ReplayMaintenanceKeyState] | None = None
        self.for_update_seen: list[bool] = []
        self.scope_calls: list[dict[str, Any]] = []

    async def list_maintenance_key_states(
        self,
        *,
        key_id: uuid.UUID | None,
        cohort_id: uuid.UUID | None,
        all_active: bool,
        limit: int,
    ) -> list[ReplayMaintenanceKeyState]:
        self.scope_calls.append(
            {"key_id": key_id, "cohort_id": cohort_id, "all_active": all_active}
        )
        if key_id is not None:
            return [k for k in self.key_states if k.id == key_id][:limit]
        if cohort_id is not None:
            return list(self.key_states)[:limit]
        if all_active:
            return [k for k in self.key_states if k.status == "active"][:limit]
        return []

    async def lock_maintenance_keys(
        self, *, key_ids: list[uuid.UUID]
    ) -> list[ReplayMaintenanceKeyState]:
        if self.locked_keys is not None:
            return self.locked_keys
        return [k for k in self.key_states if k.id in set(key_ids)]

    async def list_maintenance_rows(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        limit: int | None,
        for_update: bool,
    ) -> list[ReplayMaintenanceRow]:
        self.for_update_seen.append(for_update)
        rows = [
            row
            for row in self.rows
            if row.gateway_key_id in set(key_ids)
            and (created_from is None or row.created_at >= created_from)
            and (created_until is None or row.created_at < created_until)
        ]
        return rows[:limit] if limit is not None else rows

    async def list_maintenance_hmac_versions(
        self, *, key_ids: list[uuid.UUID]
    ) -> list[int]:
        return list(self.versions)

    async def inspect_reference_aggregates(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        now: datetime,
    ) -> ReplayReferenceTotals:
        return self.totals

    async def inspect_reference_per_key(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        now: datetime,
    ) -> list[tuple]:
        return list(self.per_key)

    async def inspect_reference_route_groups(
        self,
        *,
        key_ids: list[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        limit: int,
    ) -> tuple[list[tuple], int]:
        return list(self.route_groups)[:limit], self.route_groups_total

    async def extend_reference_expiries(
        self, *, updates: list[tuple[uuid.UUID, datetime]]
    ) -> int:
        self.extend_calls.append(list(updates))
        return len(updates)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def add_audit_log(self, **kwargs: Any) -> Any:
        self.entries.append(kwargs)
        return None


def _service(
    repository: FakeMaintenanceRepository | None = None,
    audit: FakeAuditRepository | None = None,
    **settings_kwargs: Any,
) -> tuple[CodexReplayMaintenanceService, FakeMaintenanceRepository, FakeAuditRepository]:
    repository = repository or FakeMaintenanceRepository()
    audit = audit or FakeAuditRepository()
    service = CodexReplayMaintenanceService(
        repository=repository,
        audit_repository=audit,  # type: ignore[arg-type]
        settings=_settings(**settings_kwargs),
    )
    return service, repository, audit


def _plan(service: CodexReplayMaintenanceService, **kwargs: Any):
    defaults: dict[str, Any] = {
        "scope": ReplayScope(key_id=KEY_A),
        "now": NOW,
    }
    defaults.update(kwargs)
    return service.preview_replay_extend(**defaults)


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


class TestInspection:
    def test_summary_counts_ranges_groups_and_note(self) -> None:
        repository = FakeMaintenanceRepository()
        repository.key_states = [_key_state()]
        repository.rows = [
            _row(expires=NOW + timedelta(days=10)),
            _row(digest=DIGEST_B, expires=NOW - timedelta(days=1)),
        ]
        created_a = repository.rows[0].created_at
        created_b = repository.rows[1].created_at
        repository.totals = ReplayReferenceTotals(
            2,
            1,
            min(created_a, created_b),
            max(created_a, created_b),
            NOW - timedelta(days=1),
            NOW + timedelta(days=10),
        )
        repository.per_key = [
            (KEY_A, 2, 1, created_a, created_b, NOW - timedelta(days=1), NOW + timedelta(days=10))
        ]
        repository.route_groups = [
            (uuid.UUID("99999999-0000-4000-8000-000000000001"), "zap-it-1", 2)
        ]
        repository.route_groups_total = 1
        service, _repo, _audit = _service(repository)
        summary = _run(
            service.inspect_replay_references(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert summary.scope_text == f"key:{KEY_A}"
        assert summary.references == 2
        assert summary.active_references == 1
        assert summary.expired_references == 1
        assert summary.keys == 1
        assert summary.keys_active_or_valid == 1
        assert summary.per_key[0].expired_references == 1
        assert summary.route_model_groups[0].requested_model == "zap-it-1"
        assert summary.route_model_groups_truncated is False
        assert "readiness" in summary.note
        assert _audit.entries == []

    def test_scope_oversize_refused_with_fixed_narrowing(self) -> None:
        repository = FakeMaintenanceRepository()
        repository.key_states = [_key_state(uuid.UUID(f"3{i:07d}-0000-4000-8000-000000000001")) for i in range(1001)]
        service, _repo, _audit = _service(repository)
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            _run(service.inspect_replay_references(scope=ReplayScope(cohort_id=uuid.uuid4()), now=NOW))
        assert "bounded ceiling" in str(excinfo.value)
        assert excinfo.value.error_code == "replay_maintenance_oversize"

    def test_reason_counts_under_configured_ttl(self) -> None:
        repository = FakeMaintenanceRepository()
        repository.key_states = [
            _key_state(KEY_A, status="revoked"),
            _key_state(KEY_B),
        ]
        # KEY_A rows: key excluded first (deterministic first-match law).
        repository.rows = [
            _row(key_id=KEY_A),
            _row(key_id=KEY_B, digest=DIGEST_B, ledger_finalized=False),
            _row(key_id=KEY_B, digest="c" * 64, version=2),
            _row(key_id=KEY_B, digest="d" * 64, created=NOW - timedelta(days=400)),
        ]
        service, _repo, _audit = _service(repository)
        summary = _run(
            service.inspect_replay_references(scope=ReplayScope(cohort_id=uuid.uuid4()), now=NOW)
        )
        assert summary.reasons.key_not_active_or_valid == 1
        assert summary.reasons.ledger_not_finalized == 1
        assert summary.reasons.hmac_version_unavailable == 1
        assert summary.reasons.outside_lifetime == 1
        assert summary.reasons.expired_not_included == 0


class TestPreview:
    def test_omitted_ttl_uses_configured_default_and_shows_it(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.ttl_seconds == TTL_365
        assert plan.configured_ttl_seconds == TTL_365
        assert plan.eligible_references == 1

    def test_explicit_ttl_differs_from_configured(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(
                scope=ReplayScope(key_id=KEY_A), ttl_seconds=86_400, now=NOW
            )
        )
        assert plan.ttl_seconds == 86_400
        assert plan.configured_ttl_seconds == TTL_365

    def test_target_is_original_created_plus_ttl_never_now_plus_ttl(self) -> None:
        created = NOW - timedelta(days=100)
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        # Active (expiry in the future) but well before the original-age
        # target: the extension must land on created + TTL, not now + TTL.
        repository.rows = [_row(created=created, expires=created + timedelta(days=105))]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        expected = created + timedelta(seconds=TTL_365)
        assert plan.new_expiry_min == expected
        assert plan.new_expiry_max == expected
        assert plan.old_expiry_min == created + timedelta(days=105)
        assert expected > NOW + timedelta(days=200)

    def test_exclusion_reasons_are_bounded_and_fixed(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state(KEY_A, status="suspended")]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.eligible_references == 0
        assert plan.exclusion_counts["key_not_active_or_valid"] == 1

    def test_expired_requires_explicit_include(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        created = NOW - timedelta(days=10)
        expired = _row(created=created, expires=NOW - timedelta(days=1))
        repository.rows = [expired]
        default_plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert default_plan.eligible_references == 0
        assert default_plan.exclusion_counts["expired_not_included"] == 1
        included_plan = _run(
            service.preview_replay_extend(
                scope=ReplayScope(key_id=KEY_A), include_expired=True, now=NOW
            )
        )
        assert included_plan.eligible_references == 1
        assert included_plan.new_expiry_min == created + timedelta(seconds=TTL_365)

    def test_not_yet_valid_and_expired_keys_are_excluded(self) -> None:
        for valid_until, valid_from in (
            (NOW - timedelta(days=1), None),  # key expired
            (None, NOW + timedelta(days=1)),  # not yet valid
        ):
            service, repository, _audit = _service()
            repository.key_states = [
                _key_state(valid_from=valid_from, valid_until=valid_until)
            ]
            repository.rows = [_row()]
            plan = _run(
                service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
            )
            assert plan.exclusion_counts["key_not_active_or_valid"] == 1

    def test_rows_oversize_refused(self) -> None:
        from slaif_gateway.services.codex_replay_maintenance import MAX_INSPECTED_REFERENCES

        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row(digest=f"{i:064x}") for i in range(MAX_INSPECTED_REFERENCES + 1)]
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            _run(
                service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
            )
        assert excinfo.value.error_code == "replay_maintenance_oversize"

    def test_plan_document_never_serializes_digests_or_row_uuids(self) -> None:
        service, repository, _audit = _service()
        row = _row()
        repository.key_states = [_key_state()]
        repository.rows = [row]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        document = render_replay_extend_plan(plan)
        payload = json.dumps(document)
        assert DIGEST_A not in payload
        assert str(row.id) not in payload
        assert "unit-maintenance-secret" not in payload
        # The round-trip gate accepts the rendered document, including the
        # three public optimistic digests (the only row-derived bytes).
        reparsed = parse_replay_extend_plan_document(document)
        assert reparsed.expected_source_fingerprint == plan.expected_source_fingerprint
        assert (
            reparsed.expected_source_state_fingerprint
            == plan.expected_source_state_fingerprint
        )
        assert reparsed.expected_post_state_fingerprint == plan.expected_post_state_fingerprint


class TestApply:
    def test_first_apply_updates_only_eligible_rows_and_audits_once(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state(KEY_A), _key_state(KEY_B)]
        row_a = _row(key_id=KEY_A)
        row_b = _row(key_id=KEY_B, digest=DIGEST_B)
        # Row already later than the target: monotonic no-op for it.
        row_late = _row(
            key_id=KEY_A,
            digest="e" * 64,
            created=NOW - timedelta(days=10),
            expires=NOW + timedelta(days=999),
        )
        repository.rows = [row_a, row_b, row_late]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(cohort_id=uuid.uuid4()), now=NOW)
        )
        repository.locked_keys = [
            _key_state(KEY_A),
            _key_state(KEY_B),
        ]
        result = _run(
            service.apply_replay_extend(
                plan=plan, reason="resume long-running conversation", now=NOW
            )
        )
        assert result.applied is True
        assert result.already_applied is False
        assert result.updated_references == 2
        target = (NOW - timedelta(days=10)) + timedelta(seconds=TTL_365)
        updated_ids = {item_id for item_id, _new in repository.extend_calls[0]}
        assert updated_ids == {row_a.id, row_b.id}
        assert all(new == target for _item_id, new in repository.extend_calls[0])
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry["action"] == EXTEND_ACTION
        assert entry["entity_id"] is None
        assert entry["old_values"]["extended_references"] == 2
        assert entry["old_values"]["scope"] == "cohort:None" or entry["old_values"]["scope"].startswith("cohort:")
        payload = json.dumps(entry, default=str)
        assert DIGEST_A not in payload
        assert DIGEST_B not in payload
        assert str(row_a.id) not in payload
        assert "unit-maintenance-secret" not in payload

    def test_no_op_prestate_makes_zero_writes_and_zero_audits(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        # Everything already beyond the target: eligible, but no update.
        repository.rows = [
            _row(created=NOW - timedelta(days=10), expires=NOW + timedelta(days=999))
        ]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        result = _run(
            service.apply_replay_extend(plan=plan, reason="reviewed", now=NOW)
        )
        assert result.applied is False
        assert result.already_applied is False
        assert result.updated_references == 0
        assert repository.extend_calls == []
        assert audit.entries == []

    def test_repeat_same_plan_is_safe_idempotent_noop(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        row = _row()
        repository.rows = [row]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        first = _run(service.apply_replay_extend(plan=plan, reason="r1", now=NOW))
        assert first.applied is True
        # The apply landed: the row now carries the reviewed target.
        row = _row(
            row_id=row.id,
            created=row.created_at,
            expires=(row.created_at + timedelta(seconds=TTL_365)),
        )
        repository.rows = [row]
        second = _run(service.apply_replay_extend(plan=plan, reason="r2", now=NOW))
        assert second.applied is False
        assert second.already_applied is True
        assert second.updated_references == 0
        assert len(repository.extend_calls) == 1
        assert len(audit.entries) == 1  # no duplicate audit

    def test_unrelated_change_fails_stale_not_idempotent(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        row = _row()
        repository.rows = [row]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        # An unrelated operator edit leaves an eligible row below target.
        row = _row(row_id=row.id, created=row.created_at, expires=row.created_at + timedelta(days=20))
        repository.rows = [row]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert audit.entries == []

    def test_membership_addition_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        repository.rows = [_row(), _row(digest=DIGEST_B)]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert audit.entries == []

    def test_key_revoked_after_preview_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        repository.locked_keys = [_key_state(status="revoked")]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert audit.entries == []

    def test_eligibility_boundary_crossed_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        # Created just inside the TTL at preview time.
        created = NOW - timedelta(seconds=TTL_365 - 100)
        # Actively retained (expiry in the future) but about to cross the
        # original-age target boundary.
        repository.rows = [_row(created=created, expires=NOW + timedelta(days=1))]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.eligible_references == 1
        # Time passes beyond the original-age target: it must be refused,
        # never revived by refreshing the age.
        later = NOW + timedelta(seconds=200)
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="r", now=later))
        assert audit.entries == []

    def test_scope_isolation_no_cross_key_update(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state(KEY_A), _key_state(KEY_B)]
        repository.rows = [_row(key_id=KEY_A)]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        result = _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert result.updated_references == 1
        updated_keys = {row.gateway_key_id for row in repository.rows}
        assert updated_keys == {KEY_A}

    def test_reason_laws(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            _run(service.apply_replay_extend(plan=plan, reason="   ", now=NOW))
        assert excinfo.value.error_code == "replay_maintenance_reason"
        with pytest.raises(ReplayMaintenanceError):
            _run(
                service.apply_replay_extend(
                    plan=plan,
                    reason="key sk-proj-abcdef1234567890abcdef1234567890",
                    now=NOW,
                )
            )

    def test_direct_service_ttl_out_of_range_refused(self) -> None:
        service, repository, _audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        with pytest.raises(ReplayMaintenanceError):
            _run(
                service.preview_replay_extend(
                    scope=ReplayScope(key_id=KEY_A), ttl_seconds=0, now=NOW
                )
            )
        with pytest.raises(ReplayMaintenanceError):
            _run(
                service.preview_replay_extend(
                    scope=ReplayScope(key_id=KEY_A),
                    ttl_seconds=31_536_001,
                    now=NOW,
                )
            )


class TestDraftBoundaryRegressions:
    """Fingerprint-binding regressions for the 2026-10-28 draft boundary probe.

    Each case mutates the live world between preview and apply in a way the
    reviewed plan must detect: a scope key-set change (even a zero-reference
    key), a row/ledger/HMAC-version identity replacement, or an
    eligibility-state crossing while waiting for the row lock. Every case
    must fail stale BEFORE any write or audit; the safe already-applied
    indistinguishable case is asserted explicitly.
    """

    def test_scope_key_added_without_references_fails_stale_before_audit(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(all_active=True), now=NOW)
        )
        assert plan.selected_keys == 1
        # A zero-reference active key joins the reviewed scope after review.
        repository.key_states.append(_key_state(key_id=KEY_B))
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(
                service.apply_replay_extend(
                    plan=plan, reason="root draft review", now=NOW
                )
            )
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_replaced_row_uuid_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        # Same content, different retained row identity.
        repository.rows = [replace(repository.rows[0], id=uuid.uuid4())]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(
                service.apply_replay_extend(
                    plan=plan, reason="root draft review", now=NOW
                )
            )
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_changed_ledger_uuid_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        repository.rows = [replace(repository.rows[0], usage_ledger_id=uuid.uuid4())]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(
                service.apply_replay_extend(
                    plan=plan, reason="root draft review", now=NOW
                )
            )
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_changed_hmac_version_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        # The replacement version is AVAILABLE, so only identity binding
        # can detect this change.
        repository.rows = [replace(repository.rows[0], hmac_key_version=2)]
        repository.versions = [1, 2]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(
                service.apply_replay_extend(
                    plan=plan, reason="root draft review", now=NOW
                )
            )
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_expiry_crossed_during_row_lock_fails_stale(self) -> None:
        from slaif_gateway.services import codex_replay_maintenance as service_module

        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        # Eligible at preview; the row expires while the apply waits for
        # the row lock, and the fresh now is taken AFTER that lock.
        repository.rows = [_row(expires=NOW + timedelta(seconds=30))]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.eligible_references == 1
        clock = {"now": NOW}
        original_rows = repository.list_maintenance_rows

        async def delayed_rows(**kwargs: Any) -> Any:
            if kwargs.get("for_update"):
                clock["now"] = NOW + timedelta(seconds=60)
            return await original_rows(**kwargs)

        repository.list_maintenance_rows = delayed_rows

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None) -> datetime:  # type: ignore[override]
                return clock["now"]

        with pytest.MonkeyPatch.context() as monkey:
            monkey.setattr(service_module, "datetime", _Clock)
            with pytest.raises(ReplayMaintenanceStaleError):
                _run(
                    service.apply_replay_extend(
                        plan=plan, reason="post row-lock clock review"
                    )
                )
        assert audit.entries == []
        assert repository.extend_calls == []
        # The fresh now really was taken after the row-lock wait.
        assert clock["now"] == NOW + timedelta(seconds=60)

    def test_unrelated_extension_beyond_reviewed_target_fails_stale(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        row = _row()
        repository.rows = [row]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        target = row.created_at + timedelta(seconds=TTL_365)
        # An unrelated operator extension landing BEYOND the reviewed target.
        repository.rows = [
            _row(row_id=row.id, created=row.created_at, expires=target + timedelta(days=1))
        ]
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_external_extension_to_exactly_target_is_safe_noop(self) -> None:
        # Documented indistinguishable case: an external change landing on
        # exactly the reviewed target is reported as already applied with
        # zero writes and zero duplicate audit (identical final state).
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        row = _row()
        repository.rows = [row]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        target = row.created_at + timedelta(seconds=TTL_365)
        repository.rows = [_row(row_id=row.id, created=row.created_at, expires=target)]
        result = _run(service.apply_replay_extend(plan=plan, reason="r", now=NOW))
        assert result.applied is False
        assert result.already_applied is True
        assert result.updated_references == 0
        assert repository.extend_calls == []
        assert audit.entries == []


class TestScopeCountRegressions:
    """Scope revalidation + derived-count regressions (2026-10-28 scope/count probe).

    The saved plan is a public optimistic guard, not signed authority: a
    scope membership change that commits while the blocking key lock is
    acquired, and a strictly parsed plan file with edited counts, must both
    fail stale before any write or audit, and the audit must report counts
    derived from the locked state.
    """

    def test_cohort_key_move_during_key_lock_fails_stale(self) -> None:
        class _MovedCohortRepository(FakeMaintenanceRepository):
            def __init__(self) -> None:
                super().__init__()
                self.moved = False

            async def list_maintenance_key_states(self, **kwargs: Any) -> Any:
                if kwargs.get("cohort_id") is not None and self.moved:
                    return []
                return await super().list_maintenance_key_states(**kwargs)

            async def lock_maintenance_keys(self, *, key_ids: list[uuid.UUID]) -> Any:
                locked = await super().lock_maintenance_keys(key_ids=key_ids)
                # The cohort move commits while the blocking key lock is
                # being acquired (visible to post-lock reads only).
                self.moved = True
                return locked

        repository = _MovedCohortRepository()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        audit = FakeAuditRepository()
        service = CodexReplayMaintenanceService(
            repository=repository,  # type: ignore[arg-type]
            audit_repository=audit,  # type: ignore[arg-type]
            settings=_settings(),
        )
        scope = ReplayScope(cohort_id=KEY_B)
        plan = _run(service.preview_replay_extend(scope=scope, now=NOW))
        assert plan.selected_keys == 1
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="root scope recheck", now=NOW))
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_edited_plan_counts_fail_stale_and_audit_uses_derived_counts(self) -> None:
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(all_active=True), now=NOW)
        )
        # A strictly parsed (round-trip valid) plan with inflated counts.
        edited = parse_replay_extend_plan_document(
            render_replay_extend_plan(
                replace(plan, selected_keys=2, eligible_references=2)
            )
        )
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(
                service.apply_replay_extend(
                    plan=edited, reason="root count review", now=NOW
                )
            )
        assert audit.entries == []
        assert repository.extend_calls == []
        # The unedited reviewed plan applies; audit/result report the
        # derived fresh counts, never the preview metadata.
        result = _run(
            service.apply_replay_extend(plan=plan, reason="derived counts", now=NOW)
        )
        assert result.selected_keys == 1
        assert result.eligible_references == 1
        assert result.updated_references == 1
        assert audit.entries[0]["old_values"]["selected_keys"] == 1
        assert audit.entries[0]["old_values"]["eligible_references"] == 1


def _valid_plan():
    service, repository, _audit = _service()
    repository.key_states = [_key_state()]
    repository.rows = [_row()]
    return _run(
        service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
    )


def _valid_document() -> dict[str, Any]:
    return render_replay_extend_plan(_valid_plan())


class TestPlanFileBoundaryRegressions:
    """200-c plan-file boundary regressions (safe-domain parse/write law).

    Every malformed file/JSON/scope form becomes a fixed no-echo
    ReplayMaintenanceError - never a raw ValueError, TypeError,
    AttributeError, or RecursionError; the plan file read is bounded at
    cap+1 before any parsing.
    """

    def test_oversize_file_refused_with_bounded_stream_read(
        self, tmp_path, monkeypatch
    ) -> None:
        import pathlib

        plan_path = tmp_path / "plan.json"
        canary = "OversizeCanary200c"
        # Far beyond the 32 KiB cap; the canary sits BEYOND the cap so a
        # full-file read could have seen it (and only a bounded read
        # request of cap+1 proves the finite read).
        plan_path.write_bytes(b"x" * (REPLAY_PLAN_MAX_BYTES + 100) + canary.encode())

        read_requests: list[int | None] = []
        real_open = pathlib.Path.open

        class _CountingStream:
            def __init__(self, stream) -> None:
                self._stream = stream

            def read(self, size=None):
                read_requests.append(size)
                return self._stream.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                self._stream.close()
                return False

        def _counting_open(self, mode="r", *args, **kwargs):
            return _CountingStream(real_open(self, mode, *args, **kwargs))

        monkeypatch.setattr(pathlib.Path, "open", _counting_open)
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            parse_replay_extend_plan_file(plan_path)
        assert excinfo.value.error_code == "replay_maintenance_plan"
        assert "bounded size" in excinfo.value.safe_message
        assert read_requests == [REPLAY_PLAN_MAX_BYTES + 1]
        assert canary not in excinfo.value.safe_message

    def test_deep_json_document_refused_with_fixed_error(self, tmp_path) -> None:
        plan_path = tmp_path / "deep.json"
        # 10,000 levels: under the 32 KiB cap, deep enough that the
        # bounded parser raises RecursionError.
        plan_path.write_text("[" * 10000 + "]" * 10000, encoding="utf-8")
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            parse_replay_extend_plan_file(plan_path)
        assert excinfo.value.error_code == "replay_maintenance_plan"
        assert "bounded structure depth" in excinfo.value.safe_message

    def test_deep_nested_secret_walk_refused_with_fixed_error(self) -> None:
        # 600 nested lists parse fine (below the parser limit) but
        # exhaust the recursive secret-shape walk; fixed domain error.
        document = _valid_document()
        document["scope"] = {"key_id": json.loads("[" * 600 + "1" + "]" * 600)}
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            parse_replay_extend_plan_document(document)
        assert "bounded structure depth" in excinfo.value.safe_message

    def test_giant_integer_literal_refused_with_fixed_error(self, tmp_path) -> None:
        plan_path = tmp_path / "bigint.json"
        digits = "7" * 5000
        plan_path.write_text(
            '{"schema_version": ' + digits + "}", encoding="utf-8"
        )
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            parse_replay_extend_plan_file(plan_path)
        assert excinfo.value.error_code == "replay_maintenance_plan"
        assert "not valid JSON" in excinfo.value.safe_message
        assert digits[:32] not in excinfo.value.safe_message

    def test_scope_value_types_refused_in_safe_domain(self) -> None:
        for bad in (123, ["x"], None, "not-a-uuid"):
            document = copy.deepcopy(_valid_document())
            document["scope"] = {"key_id": bad}
            with pytest.raises(ReplayMaintenanceError):
                parse_replay_extend_plan_document(document)
        document = copy.deepcopy(_valid_document())
        document["scope"] = {"key_id": str(KEY_A), "all_active": 1}
        with pytest.raises(ReplayMaintenanceError):
            parse_replay_extend_plan_document(document)

    def test_parse_scope_uuid_safe_domain_and_no_echo(self) -> None:
        for bad in (123, None, ["x"], 12.5, "not-a-uuid"):
            with pytest.raises(ReplayMaintenanceError):
                parse_scope_uuid(bad, field="--key-id")
        assert parse_scope_uuid(str(KEY_A), field="--key-id") == KEY_A
        canary = "CanaryScopeValue991"
        try:
            parse_scope_uuid(canary, field="--key-id")
        except ReplayMaintenanceError as exc:
            assert canary not in str(exc)
        else:
            raise AssertionError("expected ReplayMaintenanceError")


class TestPlanWriterBoundaryRegressions:
    """200-c writer law: serialize/validate/bound BEFORE any descriptor;
    reliable context-managed closure; honest static partial-file failure;
    existing files never overwritten."""

    def test_oversize_render_refused_before_descriptor_open(
        self, tmp_path, monkeypatch
    ) -> None:
        import slaif_gateway.schemas.codex_replay_maintenance as schema_module

        monkeypatch.setattr(schema_module, "REPLAY_PLAN_MAX_BYTES", 10)
        opened: list[Any] = []

        def _forbidden_open(*args, **kwargs):
            opened.append((args, kwargs))
            return -1

        monkeypatch.setattr(os, "open", _forbidden_open)
        plan_path = tmp_path / "plan.json"
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            write_replay_extend_plan_file(plan_path, _valid_plan())
        assert "bounded size" in excinfo.value.safe_message
        assert opened == []
        assert not plan_path.exists()

    def test_write_failure_closes_and_leaves_partial_honestly(
        self, tmp_path, monkeypatch
    ) -> None:
        sentinel = tmp_path / "sibling.json"
        sentinel.write_text("sibling", encoding="utf-8")
        plan_path = tmp_path / "plan.json"
        closed: list[bool] = []

        class _FailingStream:
            def __init__(self, fd: int) -> None:
                self._fd = fd

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                closed.append(True)
                os.close(self._fd)
                return False

            def write(self, payload):
                raise OSError("injected write failure")

        def _fake_fdopen(fd, mode):
            return _FailingStream(fd)

        monkeypatch.setattr(os, "fdopen", _fake_fdopen)
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            write_replay_extend_plan_file(plan_path, _valid_plan())
        assert "could not be written" in excinfo.value.safe_message
        assert closed == [True]
        # Honest static semantics: the newly created file may remain
        # (partial/empty); nothing is removed; sibling untouched.
        assert plan_path.exists()
        assert sentinel.read_text(encoding="utf-8") == "sibling"

    def test_existing_file_never_overwritten_and_0600(self, tmp_path) -> None:
        plan_path = tmp_path / "plan.json"
        plan1 = _valid_plan()
        write_replay_extend_plan_file(plan_path, plan1)
        assert stat.S_IMODE(os.stat(plan_path).st_mode) == 0o600
        original = plan_path.read_bytes()
        plan2 = replace(plan1, include_expired=True)
        with pytest.raises(ReplayMaintenanceError) as excinfo:
            write_replay_extend_plan_file(plan_path, plan2)
        assert "new writable file" in excinfo.value.safe_message
        assert plan_path.read_bytes() == original


class TestPreviewPostExpiryRanges:
    """200-c: preview ranges advertise the ACTUAL post-expiry.

    new_expiry range = max(existing expiry, original created + selected
    TTL) per eligible row: an already-later or equal stored expiry is
    never advertised as a shortening, and the ranges agree with the
    post-state fingerprint and the actual monotonic apply.
    """

    def test_later_expiry_not_advertised_as_shortening(self) -> None:
        created = NOW - timedelta(days=10)
        later = created + timedelta(days=400)  # beyond the 365d target
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row(created=created, expires=later)]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.eligible_references == 1
        assert plan.old_expiry_min == later
        assert plan.new_expiry_min == later
        assert plan.new_expiry_max == later
        # The actual apply agrees: monotonic no-op, zero writes, zero audit.
        result = _run(
            service.apply_replay_extend(plan=plan, reason="no shorten", now=NOW)
        )
        assert result.applied is False and result.already_applied is False
        assert result.updated_references == 0
        assert audit.entries == []

    def test_equal_expiry_no_update_and_honest_range(self) -> None:
        created = NOW - timedelta(days=10)
        target = created + timedelta(seconds=TTL_365)
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        repository.rows = [_row(created=created, expires=target)]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.new_expiry_min == target and plan.new_expiry_max == target
        result = _run(service.apply_replay_extend(plan=plan, reason="equal", now=NOW))
        assert result.updated_references == 0 and audit.entries == []

    def test_mixed_ranges_agree_with_actual_apply_and_repeat(self) -> None:
        created_a = NOW - timedelta(days=10)
        created_b = NOW - timedelta(days=20)
        extended = created_a + timedelta(seconds=TTL_365)  # row A moves
        unchanged = created_b + timedelta(days=400)  # row B stays
        service, repository, audit = _service()
        repository.key_states = [_key_state()]
        row_a = _row(created=created_a, expires=created_a + timedelta(days=90))
        row_b = _row(created=created_b, expires=unchanged, digest=DIGEST_B)
        repository.rows = [row_a, row_b]
        plan = _run(
            service.preview_replay_extend(scope=ReplayScope(key_id=KEY_A), now=NOW)
        )
        assert plan.eligible_references == 2
        assert plan.new_expiry_min == extended
        assert plan.new_expiry_max == unchanged
        result = _run(
            service.apply_replay_extend(plan=plan, reason="mixed", now=NOW)
        )
        assert result.updated_references == 1
        assert audit.entries[0]["new_values"]["new_expiry_range"] == [extended, extended]
        # The committed post-state: the SAME plan repeats as already-
        # applied (zero writes, no duplicate audit).
        repository.rows = [replace(row_a, expires_at=extended), row_b]
        repeat = _run(
            service.apply_replay_extend(plan=plan, reason="repeat", now=NOW)
        )
        assert repeat.already_applied is True
        assert repeat.updated_references == 0
        assert len(audit.entries) == 1


class TestFinalScopeRecheckRegressions:
    """200-c: exact membership revalidated AFTER the reference-row locks.

    A key entering or leaving the cohort while the blocking reference-
    row lock is acquired (invisible to the post-key-lock recheck) must
    refuse stale with zero expiry writes and zero audits.
    """

    def _repository(self, *, join_key=None, leave_key=None) -> FakeMaintenanceRepository:
        class _RowLockCohortRepository(FakeMaintenanceRepository):
            def __init__(self) -> None:
                super().__init__()
                self._row_lock_taken = False

            async def list_maintenance_rows(self, **kwargs: Any) -> Any:
                if kwargs.get("for_update") and not self._row_lock_taken:
                    self._row_lock_taken = True
                    # The cohort membership change commits while the
                    # blocking reference-row lock is being acquired.
                    if join_key is not None:
                        self.key_states.append(join_key)
                    if leave_key is not None:
                        self.key_states = [
                            k for k in self.key_states if k.id != leave_key.id
                        ]
                return await super().list_maintenance_rows(**kwargs)

        return _RowLockCohortRepository()

    def _service_for(self, repository, audit: FakeAuditRepository):
        return CodexReplayMaintenanceService(
            repository=repository,  # type: ignore[arg-type]
            audit_repository=audit,  # type: ignore[arg-type]
            settings=_settings(),
        )

    def test_zero_ref_key_joins_cohort_during_reference_lock_wait_fails_stale(self) -> None:
        repository = self._repository(join_key=_key_state(key_id=KEY_B))
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        audit = FakeAuditRepository()
        service = self._service_for(repository, audit)
        scope = ReplayScope(cohort_id=KEY_B)
        plan = _run(service.preview_replay_extend(scope=scope, now=NOW))
        assert plan.selected_keys == 1
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="final scope", now=NOW))
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_key_leaves_cohort_during_reference_lock_wait_fails_stale(self) -> None:
        leaver = _key_state(key_id=KEY_B)
        repository = self._repository(leave_key=leaver)
        repository.key_states = [_key_state(), leaver]
        repository.rows = [_row()]  # only the survivor carries references
        audit = FakeAuditRepository()
        service = self._service_for(repository, audit)
        scope = ReplayScope(cohort_id=KEY_B)
        plan = _run(service.preview_replay_extend(scope=scope, now=NOW))
        assert plan.selected_keys == 2
        with pytest.raises(ReplayMaintenanceStaleError):
            _run(service.apply_replay_extend(plan=plan, reason="final scope", now=NOW))
        assert audit.entries == []
        assert repository.extend_calls == []

    def test_stable_membership_passes_final_recheck(self) -> None:
        repository = self._repository()
        repository.key_states = [_key_state()]
        repository.rows = [_row()]
        audit = FakeAuditRepository()
        service = self._service_for(repository, audit)
        scope = ReplayScope(cohort_id=KEY_B)
        plan = _run(service.preview_replay_extend(scope=scope, now=NOW))
        result = _run(
            service.apply_replay_extend(plan=plan, reason="stable", now=NOW)
        )
        assert result.applied is True
        assert result.updated_references == 1
        assert len(audit.entries) == 1
