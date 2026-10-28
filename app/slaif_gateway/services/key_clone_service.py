"""Shared standard-key clone plan/execute operation (objective 198).

Replaces operator Python cloning with a typed, auditable, retry-safe
plan/execute operation. The plan is NON-secret reviewed data; execution
re-derives the canonical configuration from the (locked) source, revalidates
eligibility and the exact fingerprint, deduplicates on a stable operation
UUID via a bounded safe receipt on the NEW target key, and creates the target
plus its independent one-time secret / pending delivery / receipts / audits
in one caller-owned transaction.

Eligibility: standard purpose AND standard capability mode only; the source
must be active, valid (not not-yet-valid/expired), and not fenced. Only the
configured policy is copied (never usage, balance, replay, holds, or
template membership); the target starts as an independent active key.
"""

from __future__ import annotations

from typing import Any
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.schemas.key_clone import (
    CLONE_RECEIPT_METADATA_KEY,
    VALIDITY_COPY_SOURCE_EXPIRY,
    VALIDITY_DURATION_FROM_NOW,
    KeyClonePlan,
    KeyClonePlanError,
    compute_source_fingerprint,
    compute_policy_fingerprint,
    render_clone_plan,
)
from slaif_gateway.schemas.key_configuration import parse_key_configuration
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnPolicyError,
)
from slaif_gateway.services.external_tool_policy_contract import (
    EXTERNAL_TOOL_FENCED,
    parse_key_external_tool_policy,
)
from slaif_gateway.services.key_errors import (
    GatewayKeyNotFoundError,
    KeyManagementError,
)
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_STANDARD,
    KEY_PURPOSE_STANDARD,
)
from slaif_gateway.services.key_policy_configuration import (
    build_create_gateway_key_input,
    has_unsupported_chat_live_burn_fields,
)
from slaif_gateway.services.responses_streaming_live_burn import (
    RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY,
    default_responses_streaming_live_burn_policy,
    normalize_responses_streaming_live_burn_policy,
)
from slaif_gateway.utils.redaction import (
    _BEARER_PATTERN,
    _GATEWAY_KEY_TEXT_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)

# Known secret shapes reused from the existing redaction contract. These are
# finite, recognized authentication/provider secret patterns - not a general
# content sanitizer.
_CLONE_SECRET_SHAPE_PATTERNS = (
    _GATEWAY_KEY_TEXT_PATTERN,
    _BEARER_PATTERN,
    _PROVIDER_KEY_PATTERN,
    _SENSITIVE_ASSIGNMENT_PATTERN,
)


class KeyCloneError(KeyManagementError):
    """Base safe error for the clone operation."""

    error_code = "key_clone_error"
    message = "Key clone operation failed."


class KeyCloneEligibilityError(KeyCloneError):
    error_code = "key_clone_source_ineligible"
    message = "The source key is not eligible for cloning."


class KeyCloneUnsupportedSourcePolicyError(KeyCloneError):
    error_code = "key_clone_unsupported_source_policy"
    message = (
        "The source key carries a Responses-streaming live-burn policy that "
        "cannot be represented by standard key creation; cloning is refused."
    )


class KeyCloneSourceSecretShapeError(KeyCloneError):
    error_code = "key_clone_source_secret_shape"
    message = (
        "The source key's configured policy contains a recognized secret "
        "shape; cloning is refused."
    )


class KeyCloneTargetMissingError(KeyCloneError):
    error_code = "key_clone_target_missing"
    message = "The clone target owner or cohort does not exist."


class KeyCloneStalePlanError(KeyCloneError):
    error_code = "key_clone_stale_plan"
    message = (
        "The source key changed since the plan was created; the plan is stale "
        "and was not executed."
    )


class KeyClonePlanMismatchError(KeyCloneError):
    error_code = "key_clone_plan_mismatch"
    message = (
        "This operation already completed with a different plan; refusing to "
        "re-execute a changed plan."
    )


class KeyCloneConfirmationRequiredError(KeyCloneError):
    error_code = "key_clone_confirmation_required"
    message = "A fresh external-tool fenced confirmation is required to execute."


class KeyCloneTargetValidityError(KeyCloneError):
    error_code = "key_clone_target_validity"
    message = "The requested target validity window is invalid or already expired."


class KeyCloneUnsupportedIsolationError(KeyCloneError):
    error_code = "key_clone_unsupported_isolation"
    message = (
        "Clone execution requires the supported READ COMMITTED transaction "
        "isolation level; the active isolation is not supported."
    )


class KeyCloneReceiptAmbiguousError(KeyCloneError):
    error_code = "key_clone_receipt_ambiguous"
    message = (
        "Multiple clone receipts matched this operation; refusing to choose "
        "among them safely."
    )


class KeyCloneReviewedPolicyMismatchError(KeyCloneError):
    error_code = "key_clone_reviewed_policy_mismatch"
    message = (
        "The reviewed clone plan no longer matches the source key's canonical "
        "policy, identity, or confirmation requirement; the plan was not "
        "executed."
    )


@dataclass(frozen=True, slots=True)
class KeyCloneResult:
    """Safe, non-secret outcome of a clone plan or execution."""

    status: str  # "planned" | "created" | "already-applied"
    operation_uuid: str
    source_gateway_key_id: str
    source_fingerprint: str
    requires_fenced_confirmation: bool
    target_gateway_key_id: str | None = None
    target_public_key_id: str | None = None
    one_time_secret_id: str | None = None
    email_delivery_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    # In-process only: the one-time plaintext is returned to the CLI for the
    # explicitly selected output channel. It is never persisted, audited,
    # logged, or included in already-applied results.
    plaintext_key: str | None = None


class KeyCloneService:
    """Orchestrates the clone plan/execute operation.

    Flush-only; the caller owns the transaction boundary. Execution locks the
    source row, revalidates, deduplicates, and creates the target atomically.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        key_service: object,
        gateway_keys_repository: object,
        owners_repository: object,
        cohorts_repository: object,
        email_delivery_service: object,
        audit_repository: object,
    ) -> None:
        self._settings = settings
        self._key_service = key_service
        self._keys = gateway_keys_repository
        self._owners = owners_repository
        self._cohorts = cohorts_repository
        self._email_delivery = email_delivery_service
        self._audit = audit_repository

    # -- eligibility / canonical derivation ----------------------------------

    async def _load_source(self, source_id: uuid.UUID) -> GatewayKey:
        row = await self._keys.get_gateway_key_by_id(source_id)
        if row is None:
            raise GatewayKeyNotFoundError()
        return row

    def _assert_source_eligible(self, row: GatewayKey, *, now: datetime) -> None:
        if row.key_purpose != KEY_PURPOSE_STANDARD:
            raise KeyCloneEligibilityError(param="source.key_purpose")
        if row.capability_policy_mode != CAPABILITY_POLICY_MODE_STANDARD:
            raise KeyCloneEligibilityError(param="source.capability_policy_mode")
        if row.status != "active":
            raise KeyCloneEligibilityError(param="source.status")
        if getattr(row, "external_tool_fence_state", "none") != "none":
            raise KeyCloneEligibilityError(param="source.external_tool_fence_state")
        if now < row.valid_from:
            raise KeyCloneEligibilityError(param="source.valid_from")
        if now >= row.valid_until:
            raise KeyCloneEligibilityError(param="source.valid_until")

    def _assert_responses_live_burn_cloneable(self, row: GatewayKey) -> None:
        """Refuse a non-default or malformed raw Responses-streaming policy.

        ``CreateGatewayKeyInput`` has no Responses-streaming override; creation
        always writes the default. A recognized NON-DEFAULT or malformed raw
        source policy must be rejected, never silently reset.
        """
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        raw = metadata.get(RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY)
        if raw is None:
            return
        if not isinstance(raw, dict) or has_unsupported_chat_live_burn_fields(raw):
            raise KeyCloneUnsupportedSourcePolicyError(
                param=RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY
            )
        try:
            normalized = normalize_responses_streaming_live_burn_policy(
                raw,
                max_abs_cost_margin_eur=self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR,
                max_abs_token_margin=self._settings.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN,
            )
        except ChatStreamingLiveBurnPolicyError as exc:
            raise KeyCloneUnsupportedSourcePolicyError(
                param=exc.param or RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY
            ) from exc
        if normalized.to_metadata() != default_responses_streaming_live_burn_policy().to_metadata():
            raise KeyCloneUnsupportedSourcePolicyError(
                param=RESPONSES_STREAMING_LIVE_BURN_METADATA_KEY
            )

    @staticmethod
    def _assert_no_known_secret_shapes(policy_document: dict[str, Any]) -> None:
        """Refuse a source policy that carries a RECOGNIZED secret shape.

        Reuses the existing redaction patterns (gateway key text, bearer
        tokens, provider keys, sensitive assignments). A matched shape must
        fail with this fixed safe explanation instead of being emitted in
        the plan or silently altered while claiming exact policy equality.
        This is known-shape protection, not universal content sanitization.
        """

        def _contains(value: Any) -> bool:
            if isinstance(value, str):
                return any(pattern.search(value) for pattern in _CLONE_SECRET_SHAPE_PATTERNS)
            if isinstance(value, dict):
                return any(_contains(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return any(_contains(item) for item in value)
            return False

        if _contains(policy_document):
            raise KeyCloneSourceSecretShapeError(param="policy")

    def _source_fingerprint(self, row: GatewayKey, policy_document: dict[str, object]) -> str:
        return compute_source_fingerprint(
            public_key_id=row.public_key_id,
            status=row.status,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            key_purpose=row.key_purpose,
            capability_policy_mode=row.capability_policy_mode,
            policy_document=policy_document,
        )

    async def _canonical_policy_document(self, source_id: uuid.UUID) -> dict[str, object]:
        # Reuses the 196 strict canonical export (fails explicitly on
        # malformed/unsupported policy; never emits fresh confirmations).
        return await self._key_service.export_gateway_key_configuration(source_id)

    def _requires_fenced_confirmation(self, row: GatewayKey) -> bool:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        raw = metadata.get("external_tool_policy")
        if raw is None:
            return False
        parsed = parse_key_external_tool_policy(
            raw, ceilings=self._settings.get_external_tool_operator_ceilings()
        )
        return bool(parsed.valid and parsed.policy is not None and parsed.policy.mode == EXTERNAL_TOOL_FENCED)

    async def _assert_target_exists(
        self, target_owner_id: uuid.UUID, target_cohort_id: uuid.UUID | None
    ) -> None:
        owner = await self._owners.get_owner_by_id(target_owner_id)
        if owner is None:
            raise KeyCloneTargetMissingError(param="target_owner_id")
        if target_cohort_id is not None:
            cohort = await self._cohorts.get_cohort_by_id(target_cohort_id)
            if cohort is None:
                raise KeyCloneTargetMissingError(param="target_cohort_id")

    def _target_validity(
        self,
        plan: KeyClonePlan,
        *,
        now: datetime,
        source_valid_until: datetime,
    ) -> tuple[datetime, datetime]:
        if plan.validity_mode == VALIDITY_COPY_SOURCE_EXPIRY:
            valid_from = now
            valid_until = source_valid_until
        elif plan.validity_mode == VALIDITY_DURATION_FROM_NOW:
            valid_from = now
            valid_until = now + _seconds_to_timedelta(plan.validity_duration_seconds)
        else:  # absolute
            valid_from = _aware_fromiso(plan.validity_from)
            valid_until = _aware_fromiso(plan.validity_until)
        if valid_until <= valid_from:
            raise KeyCloneTargetValidityError(param="validity")
        if valid_until <= now:
            raise KeyCloneTargetValidityError(param="validity")
        return valid_from, valid_until

    # -- plan ----------------------------------------------------------------

    async def build_plan(
        self,
        *,
        source_gateway_key_id: uuid.UUID,
        target_owner_id: uuid.UUID,
        target_cohort_id: uuid.UUID | None,
        validity_mode: str,
        validity_duration_seconds: int | None = None,
        validity_from: str | None = None,
        validity_until: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Build a strict non-secret clone plan (no mutation, no audit)."""
        check_now = now or datetime.now(UTC)
        source = await self._load_source(source_gateway_key_id)
        self._assert_source_eligible(source, now=check_now)
        self._assert_responses_live_burn_cloneable(source)
        await self._assert_target_exists(target_owner_id, target_cohort_id)
        policy_document = await self._canonical_policy_document(source_gateway_key_id)
        self._assert_no_known_secret_shapes(policy_document)
        fingerprint = self._source_fingerprint(source, policy_document)
        requires_fenced = self._requires_fenced_confirmation(source)

        preview_from: datetime | None = None
        preview_until: datetime | None = None
        if validity_mode == VALIDITY_COPY_SOURCE_EXPIRY:
            preview_from = check_now
            preview_until = source.valid_until
        elif validity_mode == VALIDITY_DURATION_FROM_NOW:
            preview_from = check_now
            preview_until = check_now + _seconds_to_timedelta(validity_duration_seconds)
        else:
            preview_from = _aware_fromiso(validity_from)
            preview_until = _aware_fromiso(validity_until)
        if preview_until is not None and preview_from is not None:
            if preview_until <= preview_from:
                raise KeyCloneTargetValidityError(param="validity")
            if preview_until <= check_now:
                raise KeyCloneTargetValidityError(param="validity")

        plan = KeyClonePlan(
            operation_uuid=str(uuid.uuid4()),
            source_gateway_key_id=str(source_gateway_key_id),
            source_public_key_id=source.public_key_id,
            source_fingerprint=fingerprint,
            target_owner_id=str(target_owner_id),
            target_cohort_id=str(target_cohort_id) if target_cohort_id else None,
            validity_mode=validity_mode,
            validity_duration_seconds=validity_duration_seconds,
            validity_from=validity_from,
            validity_until=validity_until,
            source_valid_until_preview=source.valid_until.isoformat(),
            policy=policy_document,
            requires_fenced_confirmation=requires_fenced,
        )
        document = render_clone_plan(plan)
        document["preview"] = {
            "valid_from": preview_from.isoformat() if preview_from else None,
            "valid_until": preview_until.isoformat() if preview_until else None,
            "note": (
                "Preview only; duration-from-now and copy-source-expiry are "
                "recomputed from EXECUTION time and the fresh source."
            ),
        }
        return document

    # -- execute -------------------------------------------------------------

    async def execute_plan(
        self,
        *,
        plan: KeyClonePlan,
        reason: str,
        actor_admin_id: uuid.UUID | None,
        confirm_external_tool_fenced: bool,
        create_email_delivery: bool,
        now: datetime | None = None,
    ) -> KeyCloneResult:
        source_id = uuid.UUID(plan.source_gateway_key_id)
        target_owner_id = uuid.UUID(plan.target_owner_id)
        target_cohort_id = (
            uuid.UUID(plan.target_cohort_id) if plan.target_cohort_id else None
        )
        operation_uuid = uuid.UUID(plan.operation_uuid)

        # Serialize same-source executions on the existing source FOR UPDATE
        # lock, then dedup + revalidate + create in the caller transaction.
        locked = await self._keys.get_gateway_key_for_update(source_id)
        if locked is None:
            raise GatewayKeyNotFoundError()

        # R3: sample execution time AFTER acquiring the lock, so a source that
        # expired while the lock was acquired is refused. An explicit now
        # argument still wins for deterministic tests.
        exec_now = now if now is not None else _now()

        # Deduplication FIRST: a completed operation stays identifiable even
        # if the source later changed or became ineligible. The lookup is by
        # (source, operation) INDEPENDENT of the (mutable) target selection.
        receipts = await self._keys.find_clone_receipts(
            source_gateway_key_id=source_id,
            operation_uuid=operation_uuid,
        )
        if len(receipts) > 1:
            raise KeyCloneReceiptAmbiguousError(param="operation_uuid")
        existing = receipts[0] if receipts else None
        if existing is not None:
            return self._already_applied(existing, plan)

        # R3: enforce the supported isolation boundary BEFORE any write.
        isolation = await self._keys.current_transaction_isolation()
        if isolation != "read committed":
            raise KeyCloneUnsupportedIsolationError(param="transaction_isolation")

        self._assert_source_eligible(locked, now=exec_now)
        self._assert_responses_live_burn_cloneable(locked)
        await self._assert_target_exists(target_owner_id, target_cohort_id)

        fresh_document = await self._canonical_policy_document(source_id)
        self._assert_no_known_secret_shapes(fresh_document)
        fresh_fingerprint = self._source_fingerprint(locked, fresh_document)

        # R2: revalidate the reviewed business content against the fresh
        # locked source on FIRST execution (not only an opaque digest). A
        # changed source is stale; a reviewed policy/identity/confirmation the
        # (unchanged) source does not back is refused. The editable plan is
        # never authority to widen or narrow the source policy.
        if fresh_fingerprint != plan.source_fingerprint:
            raise KeyCloneStalePlanError(param="source_fingerprint")
        if compute_policy_fingerprint(plan.policy) != compute_policy_fingerprint(
            fresh_document
        ):
            raise KeyCloneReviewedPolicyMismatchError(param="policy")
        if locked.public_key_id != plan.source_public_key_id:
            raise KeyCloneReviewedPolicyMismatchError(param="source_public_key_id")
        if self._requires_fenced_confirmation(locked) != plan.requires_fenced_confirmation:
            raise KeyCloneReviewedPolicyMismatchError(param="requires_fenced_confirmation")

        if plan.requires_fenced_confirmation and not confirm_external_tool_fenced:
            raise KeyCloneConfirmationRequiredError(param="confirm_external_tool_fenced")

        valid_from, valid_until = self._target_validity(
            plan, now=exec_now, source_valid_until=locked.valid_until
        )

        config = parse_key_configuration(fresh_document)
        payload = build_create_gateway_key_input(
            config=config,
            owner_id=target_owner_id,
            valid_from=valid_from,
            valid_until=valid_until,
            cohort_id=target_cohort_id,
            created_by_admin_id=actor_admin_id,
            note=reason,
            key_purpose=KEY_PURPOSE_STANDARD,
            capability_policy_mode=CAPABILITY_POLICY_MODE_STANDARD,
        )
        payload.confirm_external_tool_fenced = bool(confirm_external_tool_fenced)

        key_result = await self._key_service.create_gateway_key(payload)

        email_delivery_id: uuid.UUID | None = None
        if create_email_delivery:
            delivery = await self._email_delivery.create_pending_key_email_delivery(
                gateway_key_id=key_result.gateway_key_id,
                one_time_secret_id=key_result.one_time_secret_id,
                owner_id=key_result.owner_id,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
            email_delivery_id = delivery.email_delivery_id

        await self._keys.attach_clone_receipt(
            key_result.gateway_key_id,
            source_gateway_key_id=source_id,
            operation_uuid=operation_uuid,
            target_owner_id=target_owner_id,
            one_time_secret_id=key_result.one_time_secret_id,
            email_delivery_id=email_delivery_id,
            source_fingerprint=plan.source_fingerprint,
            policy_fingerprint=compute_policy_fingerprint(fresh_document),
            target_cohort_id=target_cohort_id,
            requires_fenced_confirmation=plan.requires_fenced_confirmation,
            validity_mode=plan.validity_mode,
            validity_duration_seconds=plan.validity_duration_seconds,
            validity_from=plan.validity_from,
            validity_until=plan.validity_until,
        )

        await self._audit.add_audit_log(
            action="gateway_key_cloned",
            entity_type="gateway_key",
            entity_id=key_result.gateway_key_id,
            admin_user_id=actor_admin_id,
            note=reason,
            new_values={
                "target_gateway_key_id": str(key_result.gateway_key_id),
                "target_public_key_id": key_result.public_key_id,
                "source_gateway_key_id": str(source_id),
                "operation_uuid": str(operation_uuid),
                "source_fingerprint": plan.source_fingerprint,
                "target_owner_id": str(target_owner_id),
                "target_cohort_id": str(target_cohort_id) if target_cohort_id else None,
                "valid_from": valid_from.isoformat(),
                "valid_until": valid_until.isoformat(),
                "one_time_secret_id": str(key_result.one_time_secret_id),
                "email_delivery_id": str(email_delivery_id) if email_delivery_id else None,
            },
        )

        return KeyCloneResult(
            status="created",
            operation_uuid=plan.operation_uuid,
            source_gateway_key_id=plan.source_gateway_key_id,
            source_fingerprint=plan.source_fingerprint,
            requires_fenced_confirmation=plan.requires_fenced_confirmation,
            target_gateway_key_id=str(key_result.gateway_key_id),
            target_public_key_id=key_result.public_key_id,
            one_time_secret_id=str(key_result.one_time_secret_id),
            email_delivery_id=str(email_delivery_id) if email_delivery_id else None,
            valid_from=valid_from,
            valid_until=valid_until,
            plaintext_key=key_result.plaintext_key,
        )

    def _already_applied(self, existing: GatewayKey, plan: KeyClonePlan) -> KeyCloneResult:
        metadata = existing.metadata_json if isinstance(existing.metadata_json, dict) else {}
        receipt = metadata.get(CLONE_RECEIPT_METADATA_KEY) or {}
        if not isinstance(receipt, dict) or not self._receipt_matches_plan(receipt, plan):
            raise KeyClonePlanMismatchError(param="source_fingerprint")
        return KeyCloneResult(
            status="already-applied",
            operation_uuid=plan.operation_uuid,
            source_gateway_key_id=plan.source_gateway_key_id,
            source_fingerprint=plan.source_fingerprint,
            requires_fenced_confirmation=plan.requires_fenced_confirmation,
            target_gateway_key_id=str(existing.id),
            target_public_key_id=existing.public_key_id,
            one_time_secret_id=receipt.get("one_time_secret_id"),
            email_delivery_id=receipt.get("email_delivery_id"),
        )

    @staticmethod
    def _receipt_matches_plan(receipt: dict[str, object], plan: KeyClonePlan) -> bool:
        """Exact stable business-plan identity.

        Compares ALL execution-relevant reviewed fields: the source identity
        and fingerprint, the reviewed policy (via its fingerprint), the target
        owner/cohort selection, the validity parameters, and the fenced
        confirmation requirement. Only the explicitly inert preview block is
        excluded (it is never stored). A prior a-shape receipt missing any of
        these new identity members does NOT match, so it cannot permit a
        second creation (controlled refusal with safe recovery guidance).
        """
        return (
            receipt.get("source_fingerprint") == plan.source_fingerprint
            and receipt.get("policy_fingerprint")
            == compute_policy_fingerprint(plan.policy)
            and receipt.get("target_owner_id") == plan.target_owner_id
            and receipt.get("target_cohort_id") == plan.target_cohort_id
            and receipt.get("validity_mode") == plan.validity_mode
            and receipt.get("validity_duration_seconds")
            == plan.validity_duration_seconds
            and receipt.get("validity_from") == plan.validity_from
            and receipt.get("validity_until") == plan.validity_until
            and receipt.get("requires_fenced_confirmation")
            == plan.requires_fenced_confirmation
        )


def _seconds_to_timedelta(seconds: int | None):
    from datetime import timedelta

    if seconds is None:
        raise KeyClonePlanError("validity.duration_seconds: Field is required.")
    try:
        return timedelta(seconds=seconds)
    except OverflowError as exc:
        raise KeyClonePlanError(
            "validity.duration_seconds: Value exceeds the bounded maximum."
        ) from exc


def _aware_fromiso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _now() -> datetime:
    """Execution-time clock hook.

    ``execute_plan`` samples this AFTER acquiring the source lock so a source
    that expires while the lock is being acquired is refused. Deterministic
    tests monkeypatch this.
    """
    return datetime.now(UTC)
