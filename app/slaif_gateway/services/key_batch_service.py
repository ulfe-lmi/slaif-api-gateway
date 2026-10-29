"""Shared orchestration for reviewed key-configuration batches.

The service owns selection, preview, consistency, and transaction
orchestration for ``keys batch plan`` / ``keys batch apply``. The CLI
parses and formats only.

Laws implemented here (all enforced BEFORE any committed effect):

- Exactly one explicit selection source (one cohort OR an exact UUID
  list); finite persisted-status filter (default exactly ``active``);
  both requested and selected sets bounded to ``KEY_BATCH_MAX_KEYS``
  unique keys (overflow refused, never silently truncated).
- Preview is READ ONLY: strict policy parse, bounded locked preview in
  deterministic sorted-UUID order, canonical per-key before/after
  documents, derived diffs and bounded fingerprints. No writes, no
  audits, no secrets, no provider/crypto/mail/broker calls.
- Apply re-derives EVERYTHING from the strict typed policy plus the
  live locked rows: it locks/refetches all exact selected rows in
  sorted UUID order, re-resolves current filtered membership AFTER the
  last potentially blocking selected-key lock (honest READ COMMITTED
  linearization point; later cohort joins after that check are
  untouched), refuses any membership/status/config drift, re-derives
  the target through the SAME shared KeyService preparation law, and
  compares it with the reviewed target. Saved-plan coherence is
  verified BEFORE any first/repeat/no-op decision: the recorded
  source/post digests must still describe the advertised before/after
  documents under the key's current stable identity/lifecycle context,
  and a first-apply candidate's actual before must equal the advertised
  canonical before (an edited plan is refused, never re-trusted).
  Repeat/no-op decisions use
  recomputed state, never saved display metadata: a whole set already
  at the re-derived target is an explicit no-write/no-new-audit
  ``already_at_target`` (state equality, NOT historical proof); a
  partially changed or foreign state fails stale.
- Writes go through the EXISTING per-key
  ``KeyService.update_gateway_key_configuration`` law (same validation,
  same per-key audit) inside ONE caller-owned transaction: no internal
  commits/rollbacks, a late failure at a later key rolls back ALL keys
  and ALL provisional audits. A post-update canonical-state check
  inside the same transaction refuses any mismatch with the reviewed
  target.
- A saved plan is an editable operator review artifact: it is NOT a
  signature and grants no authority. The apply command carries the
  fresh bounded audit reason (credential shapes refused), the FRESH
  explicit fenced-external-tool confirmation (the only value the
  shared fenced law sees; any confirmation recorded in the plan's
  policy document is informational and stripped), and optional actor.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_APPLY_REASON_MAX_BYTES,
    KEY_BATCH_MAX_KEYS,
    KEY_BATCH_SELECTION_COHORT,
    KEY_BATCH_SELECTION_KEYS,
    KEY_BATCH_STATUS_VALUES,
    KeyBatchError,
    KeyBatchPlan,
    KeyBatchPlanKey,
    KeyBatchStaleError,
    key_batch_document_changes,
    key_batch_state_fingerprint,
)
from slaif_gateway.schemas.key_configuration import (
    KeyConfiguration,
    key_configuration_export,
    parse_key_configuration,
)
from slaif_gateway.schemas.keys import UpdateGatewayKeyConfigurationInput
from slaif_gateway.services.key_service import KeyService

# Finite recognized credential shapes reused from the existing redaction
# contract (known-shape protection for the audit reason, not DLP).
from slaif_gateway.utils.redaction import (  # noqa: E402
    _BEARER_PATTERN,
    _GATEWAY_KEY_TEXT_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

_REASON_SECRET_SHAPE_PATTERNS = (
    _GATEWAY_KEY_TEXT_PATTERN,
    _BEARER_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

# Internal nonblank reason for plan-time validation only: the fenced
# external-tool preparation law requires a nonblank audit reason. It is
# never persisted (preview writes zero audits); the fresh operator
# reason is validated and carried by the apply command.
_PLAN_INTERNAL_REASON = "key-batch-plan"

APPLY_STATUS_APPLIED = "applied"
APPLY_STATUS_ALREADY_AT_TARGET = "already_at_target"
APPLY_STATUS_NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class KeyBatchApplyResult:
    """Safe result of one reviewed batch apply (never a partial count).

    ``status`` is exactly one of ``applied`` (some keys written with
    their existing per-key audits), ``already_at_target`` (whole set
    already equals the re-derived target: zero writes, zero new
    audits), or ``no_change`` (empty eligible selection).
    """

    status: str
    selected_count: int
    changed_count: int
    unchanged_count: int
    key_ids: tuple[str, ...]


def _validate_apply_reason(reason: str | None) -> str:
    cleaned = (reason or "").strip()
    if not cleaned:
        raise KeyBatchError(
            "Enter an audit reason before applying a key batch.",
            error_code="key_batch_reason",
        )
    if len(cleaned.encode("utf-8")) > KEY_BATCH_APPLY_REASON_MAX_BYTES:
        raise KeyBatchError(
            "The audit reason exceeds the bounded length.",
            error_code="key_batch_reason",
        )
    if any(pattern.search(cleaned) for pattern in _REASON_SECRET_SHAPE_PATTERNS):
        raise KeyBatchError(
            "The audit reason contains a recognized credential shape.",
            error_code="key_batch_reason",
        )
    return cleaned


def _refuse_known_shape_document(document: Any) -> None:
    """Finite known-shape guard on canonical batch documents.

    A recognized credential shape in the typed input policy or in a
    selected key's retained canonical configuration is refused with a
    fixed safe error BEFORE shared validation/projection can produce an
    error reflecting the value back. This is known-shape protection at
    the new batch boundary, not a universal sanitizer: ordinary values
    and the existing per-key validation/error law are unchanged.
    """

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            if any(
                pattern.search(value) for pattern in _REASON_SECRET_SHAPE_PATTERNS
            ):
                raise KeyBatchError(
                    "A key batch policy or retained key configuration "
                    "contains a recognized credential shape.",
                    error_code="key_batch_policy",
                )
        elif isinstance(value, dict):
            for key, item in value.items():
                _walk(key)
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(document)


def _state_context(row: GatewayKey) -> dict[str, Any]:
    return {
        "owner_id": row.owner_id,
        "cohort_id": row.cohort_id,
        "status": row.status,
        "key_purpose": str(getattr(row, "key_purpose", "standard")),
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
    }


class KeyBatchService:
    """Reviewed key-configuration batch orchestration (flush-only).

    Callers own the transaction boundary (the CLI opens one caller-owned
    session transaction; plan exits it without commit, apply commits
    only after the whole batch is validated and applied).
    """

    def __init__(
        self,
        *,
        gateway_keys_repository: GatewayKeysRepository,
        cohorts_repository: CohortsRepository,
        key_service: KeyService,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._keys_repository = gateway_keys_repository
        self._cohorts_repository = cohorts_repository
        self._key_service = key_service
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    # -- shared selection/status validation (CLI fails fast; service law) --

    @staticmethod
    def _validate_statuses(statuses: Sequence[str]) -> tuple[str, ...]:
        if not statuses or not set(statuses) <= KEY_BATCH_STATUS_VALUES:
            raise KeyBatchError(
                "Status filters must be active, suspended, or revoked.",
                error_code="key_batch_selection",
            )
        return tuple(sorted(set(statuses)))

    # ------------------------------------------------------------------ plan

    async def plan(
        self,
        *,
        cohort_id: uuid.UUID | None = None,
        key_ids: Sequence[uuid.UUID] = (),
        statuses: Sequence[str],
        policy: KeyConfiguration,
    ) -> KeyBatchPlan:
        """READ ONLY preview of one bounded reviewed batch.

        No key/audit/material/usage writes, no secret
        generation/decryption, no email/broker/provider calls, and no
        quota mutation. Acquires the existing key row locks in sorted
        UUID order inside the caller's bounded read-only transaction.
        """
        if (cohort_id is None) == (not key_ids):
            raise KeyBatchError(
                "Use exactly one selection source: --cohort-id or --key-id.",
                error_code="key_batch_selection",
            )
        status_tuple = self._validate_statuses(statuses)
        if policy.is_empty():
            raise KeyBatchError(
                "The policy file requests no key configuration change.",
                error_code="key_batch_policy",
            )
        policy_document = key_configuration_export(policy)
        # New-batch boundary guard: a recognized credential shape in the
        # typed input policy is refused BEFORE shared validation can
        # reflect it into a route/model error message.
        _refuse_known_shape_document(policy_document)

        excluded: list[tuple[str, str]] = []
        if cohort_id is not None:
            cohort = await self._cohorts_repository.get_cohort_by_id(cohort_id)
            if cohort is None:
                raise KeyBatchError(
                    "The selected cohort was not found.",
                    error_code="key_batch_cohort_not_found",
                )
            rows = await self._keys_repository.list_key_batch_selection(
                cohort_id=cohort_id,
                statuses=status_tuple,
                limit=KEY_BATCH_MAX_KEYS + 1,
            )
            if len(rows) > KEY_BATCH_MAX_KEYS:
                raise KeyBatchError(
                    "The cohort selection exceeds the bounded key count.",
                    error_code="key_batch_selection_overflow",
                )
            selected_rows = list(rows)
        else:
            unique_ids = sorted(set(key_ids))
            if len(unique_ids) != len(list(key_ids)):
                raise KeyBatchError(
                    "The key selection contains duplicate key IDs.",
                    error_code="key_batch_selection",
                )
            if len(unique_ids) > KEY_BATCH_MAX_KEYS:
                raise KeyBatchError(
                    "The key selection exceeds the bounded key count.",
                    error_code="key_batch_selection_overflow",
                )
            rows = await self._keys_repository.get_gateway_keys_by_ids(
                key_ids=unique_ids
            )
            found = {row.id for row in rows}
            missing = [key_id for key_id in unique_ids if key_id not in found]
            if missing:
                raise KeyBatchError(
                    f"{len(missing)} requested keys were not found.",
                    error_code="key_batch_key_not_found",
                )
            selected_rows = [row for row in rows if row.status in status_tuple]
            excluded = sorted(
                (str(row.id), row.status)
                for row in rows
                if row.status not in status_tuple
            )

        # Deterministic locked preview (sorted UUID order = lock order).
        plan_keys: list[KeyBatchPlanKey] = []
        changed_count = 0
        for row in sorted(selected_rows, key=lambda r: r.id):
            locked = await self._keys_repository.get_gateway_key_for_update(row.id)
            if locked is None:
                raise KeyBatchError(
                    "A selected key was not found.",
                    error_code="key_batch_key_not_found",
                )
            # Retained current configuration guard: before the target
            # projection, whose shared validation errors may reference
            # configured values (route/model validation included).
            _refuse_known_shape_document(
                self._key_service.render_key_configuration_document(locked)
            )
            projection = await self._key_service.project_key_configuration_update(
                locked, policy, reason=_PLAN_INTERNAL_REASON
            )
            context = _state_context(locked)
            source_fingerprint = key_batch_state_fingerprint(
                config_document=projection.before_document, **context
            )
            post_fingerprint = key_batch_state_fingerprint(
                config_document=projection.after_document, **context
            )
            changes = key_batch_document_changes(
                projection.before_document, projection.after_document
            )
            if changes:
                changed_count += 1
            plan_keys.append(
                KeyBatchPlanKey(
                    key_id=str(locked.id),
                    source_fingerprint=source_fingerprint,
                    post_fingerprint=post_fingerprint,
                    before=projection.before_document,
                    after=projection.after_document,
                    changes=changes,
                )
            )

        return KeyBatchPlan(
            schema_version=1,
            operation="apply",
            selection_kind=(
                KEY_BATCH_SELECTION_COHORT
                if cohort_id is not None
                else KEY_BATCH_SELECTION_KEYS
            ),
            cohort_id=str(cohort_id) if cohort_id is not None else None,
            key_ids=tuple(str(row.id) for row in sorted(selected_rows, key=lambda r: r.id)),
            statuses=status_tuple,
            policy=policy_document,
            keys=tuple(plan_keys),
            selected_count=len(plan_keys),
            changed_count=changed_count,
            unchanged_count=len(plan_keys) - changed_count,
            excluded_by_status=tuple(excluded),
            planned_at=self._now_factory().isoformat(),
        )

    # ----------------------------------------------------------------- apply

    async def apply(
        self,
        *,
        plan: KeyBatchPlan,
        reason: str | None,
        actor_admin_id: uuid.UUID | None = None,
        confirm_external_tool_fenced: bool = False,
    ) -> KeyBatchApplyResult:
        """Apply one reviewed batch atomically in the caller transaction.

        Every check below completes BEFORE the first write; a late
        validation/write/audit failure propagates so the caller-owned
        transaction rolls back ALL keys and ALL provisional audits.

        ``confirm_external_tool_fenced`` is the FRESH operator
        acknowledgement for a fenced external-tool target. A saved plan
        is a review artifact, never authority: any confirmation
        recorded in the plan's policy document is informational and is
        stripped before the shared validation/actual update sees it;
        only this explicit apply-time value reaches the existing fenced
        law (repeated decisions re-require it through the same law).
        """
        cleaned_reason = _validate_apply_reason(reason)
        config = parse_key_configuration(plan.policy)
        # Strip the saved operation control (informational in the review
        # artifact, never authority) and keep only real configuration
        # fields; the fresh apply-time confirmation is the ONLY accepted
        # source of the fenced control.
        policy_fields = {
            name: value
            for name, value in config.as_present_fields().items()
            if name != "confirm_external_tool_fenced"
        }
        if not policy_fields:
            raise KeyBatchError(
                "The reviewed policy requests no key configuration change.",
                error_code="key_batch_policy",
            )
        config = KeyConfiguration()
        for name, value in policy_fields.items():
            setattr(config, name, value)
        config.confirm_external_tool_fenced = bool(confirm_external_tool_fenced)
        # New-batch boundary guard (re-applied: the saved plan is an
        # editable review artifact, never authority): a recognized
        # credential shape in the typed input policy is refused BEFORE
        # shared validation can reflect it into an error message.
        _refuse_known_shape_document(policy_fields)

        selected_ids = [uuid.UUID(key_id) for key_id in plan.key_ids]

        # 1. Lock/refetch ALL exact selected rows (sorted UUID order;
        #    existing FOR UPDATE + populate_existing).
        locked: dict[uuid.UUID, GatewayKey] = {}
        for key_id in selected_ids:
            row = await self._keys_repository.get_gateway_key_for_update(key_id)
            if row is None:
                raise KeyBatchStaleError(
                    "A reviewed key no longer exists; the batch was refused.",
                    error_code="key_batch_stale",
                )
            locked[key_id] = row

        # 2. Re-resolve current filtered membership AFTER the last
        #    potentially blocking selected-key lock (honest READ COMMITTED
        #    linearization point; additions after this check are
        #    untouched, and no global serializability is claimed).
        if plan.selection_kind == KEY_BATCH_SELECTION_COHORT:
            assert plan.cohort_id is not None
            current_rows = await self._keys_repository.list_key_batch_selection(
                cohort_id=uuid.UUID(plan.cohort_id),
                statuses=plan.statuses,
                limit=KEY_BATCH_MAX_KEYS + 1,
            )
            current_ids = {row.id for row in current_rows}
            if len(current_rows) > KEY_BATCH_MAX_KEYS or current_ids != set(selected_ids):
                raise KeyBatchStaleError(
                    "The currently eligible cohort membership changed after "
                    "the review; the batch was refused.",
                    error_code="key_batch_stale",
                )
        else:
            requested_ids = sorted(
                set(selected_ids)
                | {uuid.UUID(key_id) for key_id, _ in plan.excluded_by_status}
            )
            rows = await self._keys_repository.get_gateway_keys_by_ids(
                key_ids=requested_ids
            )
            by_id = {row.id: row for row in rows}
            for key_id in selected_ids:
                row = by_id.get(key_id)
                if row is None or row.status not in plan.statuses:
                    raise KeyBatchStaleError(
                        "A reviewed key's status or existence changed after "
                        "the review; the batch was refused.",
                        error_code="key_batch_stale",
                    )
            for key_id, reviewed_status in plan.excluded_by_status:
                row = by_id.get(uuid.UUID(key_id))
                if row is None or row.status != reviewed_status:
                    raise KeyBatchStaleError(
                        "A reviewed exclusion changed after the review; the "
                        "batch was refused.",
                        error_code="key_batch_stale",
                    )

        if not selected_ids:
            return KeyBatchApplyResult(
                status=APPLY_STATUS_NO_CHANGE,
                selected_count=0,
                changed_count=0,
                unchanged_count=0,
                key_ids=(),
            )

        # 3. Per-key re-derivation and no-op/first-apply decisions, ALL
        #    before any write. The target is re-derived through the SAME
        #    shared preparation law under the locks (route-aware policy,
        #    fences/holds/confirmations, module migration law); saved
        #    plan display values are never trusted.
        plan_keys = {key.key_id: key for key in plan.keys}
        pending: list[uuid.UUID] = []
        done = 0
        no_effect = 0
        for key_id in selected_ids:
            row = locked[key_id]
            plan_key = plan_keys[str(key_id)]
            context = _state_context(row)
            before_document = self._key_service.render_key_configuration_document(row)
            # Retained current configuration guard (before projection).
            _refuse_known_shape_document(before_document)
            projection = await self._key_service.project_key_configuration_update(
                row, config, reason=_PLAN_INTERNAL_REASON
            )
            if projection.after_document != plan_key.after:
                raise KeyBatchStaleError(
                    "The reviewed target no longer matches the current "
                    "shared policy law; the batch was refused.",
                    error_code="key_batch_stale",
                )
            # Saved-plan coherence BEFORE any first/repeat/no-op decision:
            # the recorded digests must still describe the advertised
            # documents under the key's CURRENT stable identity/lifecycle
            # context. A plan whose advertised before/after - or a
            # coherently edited patch with a stale post digest - no
            # longer matches its recorded source/post fingerprint is
            # refused, never re-trusted. The strict parser already
            # enforces diff<->before/after shape consistency; these are
            # the semantic digest relationships the parser cannot see.
            if (
                key_batch_state_fingerprint(config_document=plan_key.before, **context)
                != plan_key.source_fingerprint
            ):
                raise KeyBatchStaleError(
                    "The reviewed plan's source fingerprint no longer "
                    "matches its advertised before state; the batch was "
                    "refused.",
                    error_code="key_batch_stale",
                )
            if (
                key_batch_state_fingerprint(config_document=plan_key.after, **context)
                != plan_key.post_fingerprint
            ):
                raise KeyBatchStaleError(
                    "The reviewed plan's post fingerprint no longer "
                    "matches its advertised target; the batch was "
                    "refused.",
                    error_code="key_batch_stale",
                )
            current_fingerprint = key_batch_state_fingerprint(
                config_document=before_document, **context
            )
            if before_document == projection.after_document:
                # The row already equals the re-derived target: that is
                # the expected post-state only when the FULL reviewed
                # post fingerprint (target document plus the identity/
                # lifecycle/scope/validity context) matches. State
                # equality, NOT proof of a historical batch execution.
                if current_fingerprint != plan_key.post_fingerprint:
                    raise KeyBatchStaleError(
                        "A reviewed key's lifecycle or identity context "
                        "drifted after the review; the batch was refused.",
                        error_code="key_batch_stale",
                    )
                if plan_key.before == plan_key.after:
                    no_effect += 1
                else:
                    done += 1
            else:
                # A first-apply candidate must sit exactly in the
                # advertised canonical source state (document AND
                # context); an edited advertised before never matches
                # the actual row.
                if (
                    before_document != plan_key.before
                    or current_fingerprint != plan_key.source_fingerprint
                ):
                    raise KeyBatchStaleError(
                        "A reviewed key's configured state drifted after "
                        "the review; the batch was refused.",
                        error_code="key_batch_stale",
                    )
                pending.append(key_id)

        if not pending:
            # Whole set already at the re-derived target: explicit
            # no-write/no-new-audit state equality (NOT proof of a
            # historical batch execution).
            return KeyBatchApplyResult(
                status=APPLY_STATUS_ALREADY_AT_TARGET,
                selected_count=len(selected_ids),
                changed_count=0,
                unchanged_count=len(selected_ids),
                key_ids=tuple(str(key_id) for key_id in selected_ids),
            )
        if done:
            raise KeyBatchStaleError(
                "The reviewed set is partially changed; create a fresh plan.",
                error_code="key_batch_stale",
            )

        # 4. Apply through the EXISTING per-key law (same validation,
        #    same per-key audit, caller-owned transaction).
        for key_id in pending:
            await self._key_service.update_gateway_key_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=key_id,
                    configuration=config,
                    actor_admin_id=actor_admin_id,
                    reason=cleaned_reason,
                )
            )

        # 5. Post-update canonical-state check inside the SAME
        #    transaction: the ACTUAL persisted state (re-read under the
        #    held row locks, so database column coercion is observed)
        #    must equal the reviewed target; a mismatch fails and rolls
        #    everything back.
        for key_id in selected_ids:
            row = await self._keys_repository.get_gateway_key_for_update(key_id)
            if row is None:
                raise KeyBatchStaleError(
                    "A reviewed key no longer exists; the batch was refused.",
                    error_code="key_batch_stale",
                )
            document = self._key_service.render_key_configuration_document(row)
            if document != plan_keys[str(key_id)].after:
                raise KeyBatchError(
                    "The post-update state does not match the reviewed "
                    "target; the batch was rolled back.",
                    error_code="key_batch_apply",
                )

        return KeyBatchApplyResult(
            status=APPLY_STATUS_APPLIED,
            selected_count=len(selected_ids),
            changed_count=len(pending),
            unchanged_count=len(selected_ids) - len(pending),
            key_ids=tuple(str(key_id) for key_id in selected_ids),
        )
