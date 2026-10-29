"""Shared typed inspection and reviewed expiry extension for retained Codex
replay references (objective 200).

Administrative maintenance only: it is NOT a replay authorization bypass,
a new runtime replay mode, or a key-policy migration. Inspection is
read-only. The reviewed extension locks the exact scope keys, revalidates
the scope membership AFTER the blocking locks, re-derives the reviewed
counts from the locked state, and monotonically extends ONLY
``expires_at`` of exactly the eligible reviewed rows with one bounded
audit; the caller owns the transaction (no inner commit). Target
expiry is ALWAYS the ORIGINAL stored ``created_at`` plus the selected
lifetime (never execution-now plus lifetime); ``created_at`` is never
rewritten and no expiry is shortened.

Privacy: aggregate counts, gateway key/cohort/route UUIDs, and bounded
timestamps are safe administration metadata. Provider item/call IDs, raw
HMAC digests, compaction ciphertext, raw stored JSON, secrets, prompts,
arguments/results, tool payloads, and individual replay-row UUIDs are never
serialized, printed, logged, or audited. The plan carries three public
optimistic fingerprints computed from the exact reviewed key-set, stable row
identities, pre-expiry, and eligibility dependencies (source, state, and the
exact expected post-state); they are not authentication or replay authority.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Sequence

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import (
    CodexReplayReferencesRepository,
    ReplayMaintenanceKeyState,
    ReplayMaintenanceRow,
)
from slaif_gateway.schemas.codex_replay_maintenance import (
    EXCLUSION_REASON_EXPIRED_NOT_INCLUDED,
    EXCLUSION_REASON_HMAC_VERSION_UNAVAILABLE,
    EXCLUSION_REASON_KEY_NOT_ACTIVE_OR_VALID,
    EXCLUSION_REASON_LEDGER_NOT_FINALIZED,
    EXCLUSION_REASON_OUTSIDE_LIFETIME,
    EXCLUSION_REASON_UNSUPPORTED_KIND,
    ReplayExtendPlan,
    ReplayMaintenanceError,
    ReplayMaintenanceStaleError,
    ReplayScope,
    parse_replay_extend_plan_document,
    render_replay_extend_plan,
)
from slaif_gateway.services.codex_replay_service import CODEX_REPLAY_ITEM_KINDS
from slaif_gateway.services.provider_route_configuration import (
    contains_known_secret_shape,
)

# Named documented maintenance ceilings: large enough for the encountered
# scale (20,451 references across 26 keys) and bounded for memory/selection.
MAX_SELECTED_KEYS = 1_000
MAX_INSPECTED_REFERENCES = 50_000
MAX_ROUTE_MODEL_GROUPS = 100
MIN_REFERENCE_TTL_SECONDS = 1
MAX_REFERENCE_TTL_SECONDS = 31_536_000

EXTEND_ACTION = "codex_replay_references_extended"
EXTEND_ENTITY_TYPE = "codex_replay_references"

INSPECTION_READINESS_NOTE = (
    "Expiry eligibility is maintenance state, not client or model "
    "readiness; replay use still requires the normal runtime "
    "authorization, route, and policy checks."
)

_OVERSIZE_MESSAGE = (
    "The maintenance scope exceeds the bounded ceiling "
    f"({MAX_SELECTED_KEYS} keys / {MAX_INSPECTED_REFERENCES} references). "
    "Narrow the scope or creation-time bounds and preview again."
)


def _reason_codes() -> list[str]:
    return [
        EXCLUSION_REASON_KEY_NOT_ACTIVE_OR_VALID,
        EXCLUSION_REASON_LEDGER_NOT_FINALIZED,
        EXCLUSION_REASON_UNSUPPORTED_KIND,
        EXCLUSION_REASON_HMAC_VERSION_UNAVAILABLE,
        EXCLUSION_REASON_OUTSIDE_LIFETIME,
        EXCLUSION_REASON_EXPIRED_NOT_INCLUDED,
    ]


def _oversize_error() -> ReplayMaintenanceError:
    return ReplayMaintenanceError(_OVERSIZE_MESSAGE, error_code="replay_maintenance_oversize")


def _stale_error() -> ReplayMaintenanceStaleError:
    return ReplayMaintenanceStaleError(
        "The reviewed replay maintenance pre-state no longer matches the "
        "live rows.",
        error_code="replay_maintenance_stale",
    )


def validate_ttl_seconds(ttl_seconds: int) -> int:
    """Respect 1..31,536,000 seconds even for direct shared-service calls."""
    if type(ttl_seconds) is not int:
        raise ReplayMaintenanceError(
            "ttl_seconds must be a positive integer.",
            error_code="replay_maintenance_ttl",
        )
    if ttl_seconds < MIN_REFERENCE_TTL_SECONDS or ttl_seconds > MAX_REFERENCE_TTL_SECONDS:
        raise ReplayMaintenanceError(
            "ttl_seconds must be within 1..31536000 seconds.",
            error_code="replay_maintenance_ttl",
        )
    return ttl_seconds


@dataclass(frozen=True, slots=True)
class ReplayKeySummary:
    key_id: uuid.UUID
    key_status: str
    references: int
    active_references: int
    expired_references: int
    created_min: datetime | None
    created_max: datetime | None
    expiry_min: datetime | None
    expiry_max: datetime | None


@dataclass(frozen=True, slots=True)
class ReplayRouteModelGroup:
    route_id: uuid.UUID
    requested_model: str | None
    references: int


@dataclass(frozen=True, slots=True)
class ReplayExclusionReasons:
    key_not_active_or_valid: int
    ledger_not_finalized: int
    unsupported_kind: int
    hmac_version_unavailable: int
    outside_lifetime: int
    expired_not_included: int

    def as_counts(self) -> dict[str, int]:
        return {
            "key_not_active_or_valid": self.key_not_active_or_valid,
            "ledger_not_finalized": self.ledger_not_finalized,
            "unsupported_kind": self.unsupported_kind,
            "hmac_version_unavailable": self.hmac_version_unavailable,
            "outside_lifetime": self.outside_lifetime,
            "expired_not_included": self.expired_not_included,
        }


@dataclass(frozen=True, slots=True)
class ReplayInspectionSummary:
    scope_text: str
    now: datetime
    configured_ttl_seconds: int
    keys: int
    keys_active_or_valid: int
    references: int
    active_references: int
    expired_references: int
    created_min: datetime | None
    created_max: datetime | None
    expiry_min: datetime | None
    expiry_max: datetime | None
    per_key: tuple[ReplayKeySummary, ...]
    route_model_groups: tuple[ReplayRouteModelGroup, ...]
    route_model_groups_total: int
    route_model_groups_truncated: bool
    reasons: ReplayExclusionReasons
    note: str


@dataclass(frozen=True, slots=True)
class ReplayExtendResult:
    applied: bool
    already_applied: bool
    updated_references: int
    selected_keys: int
    eligible_references: int
    exclusion_counts: dict[str, int]


def _key_active_or_valid(key: ReplayMaintenanceKeyState, now: datetime) -> bool:
    return key.status == "active" and key.valid_from <= now < key.valid_until


def _available_hmac_versions(settings: Settings, versions: Sequence[int]) -> frozenset[int]:
    """Read-only availability check; the secret is never returned or logged."""
    return frozenset(
        version for version in versions if settings.get_hmac_secret(str(version))
    )


def _classify_row(
    *,
    row: ReplayMaintenanceRow,
    key_ok: bool,
    version_available: frozenset[int],
    now: datetime,
    ttl_seconds: int,
    include_expired: bool,
) -> tuple[str, str]:
    """Deterministic first-matched eligibility classification (fixed law)."""
    if not key_ok:
        return "excluded", EXCLUSION_REASON_KEY_NOT_ACTIVE_OR_VALID
    if row.item_kind not in CODEX_REPLAY_ITEM_KINDS:
        return "excluded", EXCLUSION_REASON_UNSUPPORTED_KIND
    if not row.ledger_finalized:
        return "excluded", EXCLUSION_REASON_LEDGER_NOT_FINALIZED
    if row.hmac_key_version not in version_available:
        return "excluded", EXCLUSION_REASON_HMAC_VERSION_UNAVAILABLE
    if row.created_at + timedelta(seconds=ttl_seconds) <= now:
        return "excluded", EXCLUSION_REASON_OUTSIDE_LIFETIME
    if row.expires_at <= now and not include_expired:
        return "excluded", EXCLUSION_REASON_EXPIRED_NOT_INCLUDED
    return "eligible", ""


def _entry_tuple(*, row: ReplayMaintenanceRow, expiry: datetime, state: str, reason: str) -> list[str]:
    # Full stable row identity + reviewed state. Raw digests and row UUIDs
    # remain internal to the fingerprint input; only the SHA-256 of the
    # canonical serialization is ever carried by the plan.
    return [
        str(row.id),
        str(row.gateway_key_id),
        row.item_kind,
        row.item_id_hmac,
        str(row.usage_ledger_id),
        str(row.hmac_key_version),
        row.created_at.isoformat(),
        expiry.isoformat(),
        state,
        reason,
    ]


def _fingerprint(entries: list[list[str]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fingerprint_without_expiry(
    markers: list[list[str]], entries: list[list[str]]
) -> str:
    # State digest: key-set + full row identity, original creation, and
    # eligibility state only (the expiry position is the reviewed variable).
    stripped = [
        [part[0], part[1], part[2], part[3], part[4], part[5], part[6], part[8], part[9]]
        for part in entries
    ]
    canonical = json.dumps(markers + stripped, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _key_markers(keys: Sequence[ReplayMaintenanceKeyState]) -> list[list[str]]:
    """Bind the exact reviewed key-set (scope membership) into the digests."""
    return [
        ["key", str(key.id)] for key in sorted(keys, key=lambda item: str(item.id))
    ]


def _expected_post_entries(
    rows: Sequence[ReplayMaintenanceRow],
    states: Sequence[tuple[str, str]],
    ttl_seconds: int,
) -> list[list[str]]:
    """Exact reviewed post-state: eligible rows at max(old, created + TTL)."""
    entries: list[list[str]] = []
    for row, (state, reason) in zip(rows, states):
        expiry = row.expires_at
        if state == "eligible":
            target = row.created_at + timedelta(seconds=ttl_seconds)
            if target > expiry:
                expiry = target
        entries.append(_entry_tuple(row=row, expiry=expiry, state=state, reason=reason))
    return entries


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


class CodexReplayMaintenanceService:
    """Bounded read-only inspection and reviewed monotonic expiry extension."""

    def __init__(
        self,
        *,
        repository: CodexReplayReferencesRepository,
        audit_repository: AuditRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository
        self._settings = settings

    # --- shared scope helpers -------------------------------------------------

    async def _resolve_scope_keys(
        self,
        *,
        scope: ReplayScope,
        limit: int,
    ) -> list[ReplayMaintenanceKeyState]:
        keys = await self._repository.list_maintenance_key_states(
            key_id=scope.key_id,
            cohort_id=scope.cohort_id,
            all_active=scope.all_active,
            limit=limit,
        )
        if len(keys) > MAX_SELECTED_KEYS:
            raise _oversize_error()
        return keys

    async def _fetch_rows(
        self,
        *,
        key_ids: Sequence[uuid.UUID],
        created_from: datetime | None,
        created_until: datetime | None,
        lock: bool,
    ) -> list[ReplayMaintenanceRow]:
        rows = await self._repository.list_maintenance_rows(
            key_ids=list(key_ids),
            created_from=created_from,
            created_until=created_until,
            limit=MAX_INSPECTED_REFERENCES + 1,
            for_update=lock,
        )
        if len(rows) > MAX_INSPECTED_REFERENCES:
            raise _oversize_error()
        return rows

    async def _available_versions(self, key_ids: Sequence[uuid.UUID]) -> frozenset[int]:
        versions = await self._repository.list_maintenance_hmac_versions(
            key_ids=list(key_ids)
        )
        return _available_hmac_versions(self._settings, versions)

    # --- inspection (read-only) ------------------------------------------------

    async def inspect_replay_references(
        self,
        *,
        scope: ReplayScope,
        created_from: datetime | None = None,
        created_until: datetime | None = None,
        now: datetime | None = None,
    ) -> ReplayInspectionSummary:
        checked_now = now or datetime.now(UTC)
        ttl = self._settings.CODEX_REPLAY_REFERENCE_TTL_SECONDS
        keys = await self._resolve_scope_keys(scope=scope, limit=MAX_SELECTED_KEYS + 1)
        key_ids = [key.id for key in keys]
        key_by_id = {key.id: key for key in keys}

        totals = await self._repository.inspect_reference_aggregates(
            key_ids=key_ids,
            created_from=created_from,
            created_until=created_until,
            now=checked_now,
        )
        per_key_rows = await self._repository.inspect_reference_per_key(
            key_ids=key_ids,
            created_from=created_from,
            created_until=created_until,
            now=checked_now,
        )
        group_rows, groups_total = await self._repository.inspect_reference_route_groups(
            key_ids=key_ids,
            created_from=created_from,
            created_until=created_until,
            limit=MAX_ROUTE_MODEL_GROUPS + 1,
        )
        rows = await self._fetch_rows(
            key_ids=key_ids,
            created_from=created_from,
            created_until=created_until,
            lock=False,
        )
        versions = await self._available_versions(key_ids)
        reasons = {code: 0 for code in _reason_codes()}
        for row in rows:
            key = key_by_id.get(row.gateway_key_id)
            key_ok = _key_active_or_valid(key, checked_now) if key is not None else False
            _state, reason = _classify_row(
                row=row,
                key_ok=key_ok,
                version_available=versions,
                now=checked_now,
                ttl_seconds=ttl,
                include_expired=False,
            )
            if reason:
                reasons[reason] += 1

        per_key = tuple(
            ReplayKeySummary(
                key_id=key_id,
                key_status=key_by_id[key_id].status if key_id in key_by_id else "",
                references=references,
                active_references=active,
                expired_references=references - active,
                created_min=created_min,
                created_max=created_max,
                expiry_min=expiry_min,
                expiry_max=expiry_max,
            )
            for (
                key_id,
                references,
                active,
                created_min,
                created_max,
                expiry_min,
                expiry_max,
            ) in per_key_rows
        )
        groups = tuple(
            ReplayRouteModelGroup(
                route_id=route_id,
                requested_model=requested_model,
                references=references,
            )
            for route_id, requested_model, references in group_rows[:MAX_ROUTE_MODEL_GROUPS]
        )
        return ReplayInspectionSummary(
            scope_text=scope.scope_text,
            now=checked_now,
            configured_ttl_seconds=ttl,
            keys=len(keys),
            keys_active_or_valid=sum(
                1 for key in keys if _key_active_or_valid(key, checked_now)
            ),
            references=totals.references,
            active_references=totals.active_references,
            expired_references=totals.references - totals.active_references,
            created_min=totals.created_min,
            created_max=totals.created_max,
            expiry_min=totals.expiry_min,
            expiry_max=totals.expiry_max,
            per_key=per_key,
            route_model_groups=groups,
            route_model_groups_total=groups_total,
            route_model_groups_truncated=len(group_rows) > MAX_ROUTE_MODEL_GROUPS,
            reasons=ReplayExclusionReasons(**reasons),
            note=INSPECTION_READINESS_NOTE,
        )

    # --- preview (read-only, renders the reviewed plan) ------------------------

    async def preview_replay_extend(
        self,
        *,
        scope: ReplayScope,
        ttl_seconds: int | None = None,
        include_expired: bool = False,
        created_from: datetime | None = None,
        created_until: datetime | None = None,
        now: datetime | None = None,
    ) -> ReplayExtendPlan:
        checked_now = now or datetime.now(UTC)
        selected_ttl = (
            self._settings.CODEX_REPLAY_REFERENCE_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        )
        validate_ttl_seconds(selected_ttl)
        keys = await self._resolve_scope_keys(scope=scope, limit=MAX_SELECTED_KEYS + 1)
        key_ids = [key.id for key in keys]
        key_by_id = {key.id: key for key in keys}
        rows = await self._fetch_rows(
            key_ids=key_ids,
            created_from=created_from,
            created_until=created_until,
            lock=False,
        )
        versions = await self._available_versions(key_ids)

        entries: list[list[str]] = []
        states: list[tuple[str, str]] = []
        reasons = {code: 0 for code in _reason_codes()}
        eligible_old: list[datetime] = []
        eligible_new: list[datetime] = []
        for row in rows:
            key = key_by_id.get(row.gateway_key_id)
            key_ok = _key_active_or_valid(key, checked_now) if key is not None else False
            state, reason = _classify_row(
                row=row,
                key_ok=key_ok,
                version_available=versions,
                now=checked_now,
                ttl_seconds=selected_ttl,
                include_expired=include_expired,
            )
            if state == "eligible":
                target = row.created_at + timedelta(seconds=selected_ttl)
                eligible_old.append(row.expires_at)
                # Actual post-expiry: an already-later (or equal) stored
                # expiry is NOT shortened, so the advertised range must
                # agree with expected_post_state_fingerprint and apply.
                eligible_new.append(max(row.expires_at, target))
            elif reason:
                reasons[reason] += 1
            entries.append(
                _entry_tuple(row=row, expiry=row.expires_at, state=state, reason=reason)
            )
            states.append((state, reason))

        plan = ReplayExtendPlan(
            schema_version=1,
            operation="extend",
            scope=scope,
            created_from=created_from,
            created_until=created_until,
            ttl_seconds=selected_ttl,
            configured_ttl_seconds=self._settings.CODEX_REPLAY_REFERENCE_TTL_SECONDS,
            include_expired=include_expired,
            previewed_at=checked_now,
            selected_keys=len(keys),
            eligible_references=len(eligible_new),
            exclusion_counts=reasons,
            old_expiry_min=min(eligible_old) if eligible_old else None,
            old_expiry_max=max(eligible_old) if eligible_old else None,
            new_expiry_min=min(eligible_new) if eligible_new else None,
            new_expiry_max=max(eligible_new) if eligible_new else None,
            expected_source_fingerprint=_fingerprint(_key_markers(keys) + entries),
            expected_source_state_fingerprint=_fingerprint_without_expiry(
                _key_markers(keys), entries
            ),
            expected_post_state_fingerprint=_fingerprint(
                _key_markers(keys) + _expected_post_entries(rows, states, selected_ttl)
            ),
        )
        # Strict round-trip gate BEFORE any file write: the rendered
        # document must carry the exact reviewed bindings.
        parse_replay_extend_plan_document(render_replay_extend_plan(plan))
        return plan

    # --- apply (caller-owned transaction, no inner commit) ---------------------

    async def apply_replay_extend(
        self,
        *,
        plan: ReplayExtendPlan,
        reason: str,
        actor_admin_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> ReplayExtendResult:
        if not (reason or "").strip():
            raise ReplayMaintenanceError(
                "reason: A nonblank audit reason is required.",
                error_code="replay_maintenance_reason",
            )
        if contains_known_secret_shape(reason):
            raise ReplayMaintenanceError(
                "reason: value must not contain recognized credential patterns.",
                error_code="replay_maintenance_reason",
            )
        validate_ttl_seconds(plan.ttl_seconds)

        # Deterministic lock order: the exact scope keys (FOR UPDATE, by
        # id) first, then the retained rows (FOR UPDATE, by key/kind/
        # digest). The fresh time is taken AFTER the locks, never the
        # transaction-start time.
        resolved = await self._resolve_scope_keys(
            scope=plan.scope, limit=MAX_SELECTED_KEYS + 1
        )
        locked_keys = await self._repository.lock_maintenance_keys(
            key_ids=[key.id for key in resolved]
        )
        if {key.id for key in locked_keys} != {key.id for key in resolved}:
            raise _stale_error()
        # Revalidate the scope membership AFTER the blocking key lock: a
        # concurrent committed scope change (a key leaving or entering the
        # cohort, or an all-active key leaving the active state) while the
        # lock was being acquired must make the reviewed plan stale.
        rechecked = await self._resolve_scope_keys(
            scope=plan.scope, limit=MAX_SELECTED_KEYS + 1
        )
        if {key.id for key in rechecked} != {key.id for key in locked_keys}:
            raise _stale_error()
        rows = await self._fetch_rows(
            key_ids=[key.id for key in resolved],
            created_from=plan.created_from,
            created_until=plan.created_until,
            lock=True,
        )
        # Revalidate the EXACT reviewed membership AFTER the blocking
        # reference-row locks as well: a key entering or leaving the
        # cohort (or leaving the active set) while the row locks were
        # acquired is invisible to the post-key-lock recheck and must
        # still make the reviewed plan stale before any mutation.
        final_rechecked = await self._resolve_scope_keys(
            scope=plan.scope, limit=MAX_SELECTED_KEYS + 1
        )
        if {key.id for key in final_rechecked} != {key.id for key in locked_keys}:
            raise _stale_error()
        # The fresh time is taken only AFTER all locks (keys + rows), never
        # the transaction-start time and never the pre-row-lock time.
        fresh_now = now or datetime.now(UTC)
        key_by_id = {key.id: key for key in locked_keys}
        versions = await self._available_versions([key.id for key in locked_keys])

        entries: list[list[str]] = []
        states: list[tuple[str, str]] = []
        reasons = {code: 0 for code in _reason_codes()}
        updates: list[tuple[uuid.UUID, datetime]] = []
        for row in rows:
            key = key_by_id.get(row.gateway_key_id)
            key_ok = _key_active_or_valid(key, fresh_now) if key is not None else False
            state, why = _classify_row(
                row=row,
                key_ok=key_ok,
                version_available=versions,
                now=fresh_now,
                ttl_seconds=plan.ttl_seconds,
                include_expired=plan.include_expired,
            )
            if state == "eligible":
                target = row.created_at + timedelta(seconds=plan.ttl_seconds)
                if target > row.expires_at:
                    updates.append((row.id, target))
            elif why:
                reasons[why] += 1
            entries.append(_entry_tuple(row=row, expiry=row.expires_at, state=state, reason=why))
            states.append((state, why))

        markers = _key_markers(locked_keys)
        actual_full = _fingerprint(markers + entries)
        actual_state = _fingerprint_without_expiry(markers, entries)

        # The saved plan is a public optimistic guard, not signed authority:
        # the live scope size and eligibility count are re-derived from the
        # locked state and must agree with the reviewed plan metadata
        # (an edited count in a strictly parsed plan is refused here).
        fresh_eligible = sum(1 for state, _why in states if state == "eligible")
        if (
            len(locked_keys) != plan.selected_keys
            or fresh_eligible != plan.eligible_references
        ):
            raise _stale_error()

        # The expected post-state RECOMPUTED from the fresh locked rows,
        # the actual classification, and the SELECTED TTL. A consistent
        # plan carries it as expected_post_state_fingerprint; it guards
        # BOTH decision paths: the first apply (before any mutation) and
        # the already-applied repeat (a TTL-only edit that would require
        # a different post-state cannot be reported as already applied).
        fresh_post = _fingerprint(
            markers + _expected_post_entries(rows, states, plan.ttl_seconds)
        )

        if actual_full == plan.expected_source_fingerprint:
            # Reviewed pre-state confirmed: first apply path. BEFORE any
            # mutation, the reviewed plan must agree with the FRESH
            # locked state under the SELECTED TTL (a TTL-only edit of an
            # otherwise valid plan is refused here, not only on the
            # already-applied repeat path):
            if fresh_post != plan.expected_post_state_fingerprint:
                raise _stale_error()
            # And, for a first apply only, the saved report descriptors
            # (old/new expiry ranges and exclusion counts) must agree
            # with the freshly derived eligible-row ranges/reasons,
            # using the same max(old, created + TTL) formula as the
            # preview - including a zero-diff first apply. A plan whose
            # descriptors do not describe THIS operation is refused
            # before any write or audit.
            fresh_old = [
                row.expires_at
                for row, (state, _why) in zip(rows, states)
                if state == "eligible"
            ]
            fresh_new = [
                max(
                    row.expires_at,
                    row.created_at + timedelta(seconds=plan.ttl_seconds),
                )
                for row, (state, _why) in zip(rows, states)
                if state == "eligible"
            ]
            if (
                (min(fresh_old) if fresh_old else None) != plan.old_expiry_min
                or (max(fresh_old) if fresh_old else None) != plan.old_expiry_max
                or (min(fresh_new) if fresh_new else None) != plan.new_expiry_min
                or (max(fresh_new) if fresh_new else None) != plan.new_expiry_max
                or any(
                    plan.exclusion_counts.get(code, 0) != count
                    for code, count in reasons.items()
                )
            ):
                raise _stale_error()
            if not updates:
                # No-op under the reviewed pre-state: zero writes, zero audits.
                return ReplayExtendResult(
                    applied=False,
                    already_applied=False,
                    updated_references=0,
                    selected_keys=len(locked_keys),
                    eligible_references=fresh_eligible,
                    exclusion_counts=reasons,
                )
            updated = await self._repository.extend_reference_expiries(updates=updates)
            if updated != len(updates):
                raise _stale_error()
            updated_ids = {item_id for item_id, _new in updates}
            old_values = [row.expires_at for row in rows if row.id in updated_ids]
            new_values = [new for _item_id, new in updates]
            await self._audit_repository.add_audit_log(
                action=EXTEND_ACTION,
                entity_type=EXTEND_ENTITY_TYPE,
                admin_user_id=actor_admin_id,
                entity_id=None,
                old_values={
                    "operation": "extend",
                    "scope": plan.scope.scope_text,
                    "ttl_seconds": plan.ttl_seconds,
                    "configured_ttl_seconds": plan.configured_ttl_seconds,
                    "include_expired": plan.include_expired,
                    "created_from": _iso(plan.created_from),
                    "created_until": _iso(plan.created_until),
                    "selected_keys": len(locked_keys),
                    "eligible_references": fresh_eligible,
                    "extended_references": len(updates),
                    "exclusion_counts": reasons,
                    "old_expiry_range": [min(old_values), max(old_values)],
                    "operation_fingerprint": plan.expected_source_fingerprint,
                },
                new_values={
                    "new_expiry_range": [min(new_values), max(new_values)],
                },
                note=reason,
            )
            return ReplayExtendResult(
                applied=True,
                already_applied=False,
                updated_references=updated,
                selected_keys=len(locked_keys),
                eligible_references=fresh_eligible,
                exclusion_counts=reasons,
            )

        # Already-applied post-state: the SAME reviewed key-set and rows
        # (full identity, original creation, and eligibility state
        # unchanged) now carry EXACTLY the reviewed target (max(old,
        # created + TTL)) for every eligible row. No writes, no duplicate
        # audit. The RECOMPUTED post-state under the selected TTL must
        # also agree with the saved post-state fingerprint, so a TTL-only
        # edit of an applied plan that would require a DIFFERENT
        # post-state fails stale instead of reporting already applied
        # (an edit with no actual post-state effect still reports the
        # honest no-op). A key-set, row/ledger/version identity, or
        # eligibility state change (for example an expiry boundary
        # crossed while waiting for the row lock), or an unrelated
        # extension landing beyond the reviewed target, fails stale
        # instead. An external change landing on exactly the reviewed
        # target is indistinguishable from a prior apply and is reported
        # as already applied (safe: zero writes, zero audit, identical
        # final state).
        if (
            actual_state == plan.expected_source_state_fingerprint
            and actual_full == plan.expected_post_state_fingerprint
            and fresh_post == plan.expected_post_state_fingerprint
        ):
            return ReplayExtendResult(
                applied=False,
                already_applied=True,
                updated_references=0,
                selected_keys=len(locked_keys),
                eligible_references=fresh_eligible,
                exclusion_counts=reasons,
            )
        raise _stale_error()
