"""Service helpers for pricing rule metadata."""

from __future__ import annotations

import json
import hashlib
import uuid
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from slaif_gateway.db.models import PricingRule
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.services.model_route_service import normalize_endpoint
from slaif_gateway.services.record_errors import RecordNotFoundError


# 214-a: reviewed matching-model disable is bounded to at most this many
# matching ENABLED rows per plan.  Overbound scopes are refused outright;
# they are never silently trimmed or chunked non-atomically.
PRICING_DISABLE_MAX_REVIEWED_ROWS = 1000

_ALLOWED_IMPORT_FIELDS = {
    "provider",
    "model",
    "upstream_model",
    "endpoint",
    "currency",
    "input_price_per_1m",
    "output_price_per_1m",
    "cached_input_price_per_1m",
    "reasoning_price_per_1m",
    "request_price",
    "pricing_metadata",
    "valid_from",
    "valid_until",
    "source_url",
    "source_retrieved_at",
    "notes",
    "enabled",
}


@dataclass(frozen=True, slots=True)
class PricingImportResult:
    """Result for a pricing import operation."""

    imported_count: int
    dry_run: bool
    rows: tuple[PricingRule | dict[str, object], ...]


class PricingDisableScopeError(ValueError):
    """The reviewed disable scope exceeds the bounded plan (214-a).

    The message is fixed and safe (counts only, no row values or raw
    pricing metadata).
    """

    def __init__(self, *, matched_rows: int, max_rows: int) -> None:
        self.matched_rows = matched_rows
        self.max_rows = max_rows
        super().__init__(
            f"The matching-model scope matches {matched_rows} enabled pricing "
            f"rows, above the reviewed plan bound of {max_rows}. "
            "Narrow the scope (for example by endpoint) before reviewing."
        )


class PricingDisableNoMatchError(ValueError):
    """The reviewed disable scope matches no enabled pricing rows (214-a)."""

    def __init__(self) -> None:
        super().__init__(
            "No enabled pricing rows match this exact provider/model/endpoint "
            "scope. Nothing was previewed or changed."
        )


class PricingDisableStaleError(RuntimeError):
    """The reviewed pricing rows drifted after the preview (214-a).

    Raised under the row locks when the fresh post-lock source state no
    longer matches the reviewed fingerprints: a reviewed row is missing,
    its scope identity or validity opening instant changed, or the set is
    a mixed partially-disabled state that is neither the reviewed
    all-enabled state nor the honest already-applied repeat.  The caller
    transaction rolls back; NOTHING is disabled.
    """

    def __init__(self) -> None:
        super().__init__(
            "The reviewed pricing rows changed after the preview. Nothing "
            "was disabled; preview the scope again to review the current "
            "state."
        )


@dataclass(frozen=True, slots=True)
class PricingDisableReviewRow:
    """One SIGNED reviewed pricing row: identity plus stable fingerprint.

    The compact signed representation (``rows: [{id, fingerprint}]``) is
    what the review token binds; it fits the fixed 128 KiB plan budget
    for the bounded 1000-row plan.  The fingerprint is a private
    SHA-256 digest over the canonical source facts (see
    :func:`_pricing_disable_row_fingerprint`): scope identity, currency,
    the validity window, the typed price facts, and a canonical hash of
    the ``pricing_metadata`` pricing policy (the runtime pricing lookup
    consumes that policy for audio output, Codex accounting multipliers,
    and external-tool pricing).  Unrelated drift is deliberately NOT
    bound: ``notes``, ``updated_at``, and ``source_url`` edits do not
    invalidate a review, and the ``enabled`` flag is evaluated under the
    locks at apply time (repeat law) rather than frozen.  The raw
    metadata itself is never rendered, signed, or logged.
    """

    pricing_rule_id: uuid.UUID
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PricingDisableDisplayRow:
    """Safe per-row PREVIEW display facts (214-a), never signed.

    These are the operator-visible facts of one reviewed row for the
    preview page only.  They are NOT part of the signed document - the
    row's fingerprint alone binds them; this separation keeps the signed
    plan compact within the fixed 128 KiB budget.
    """

    pricing_rule_id: uuid.UUID
    provider: str
    upstream_model: str
    endpoint: str
    currency: str
    valid_from: datetime
    valid_until: datetime | None
    input_price_per_1m: Decimal
    cached_input_price_per_1m: Decimal | None
    output_price_per_1m: Decimal
    reasoning_price_per_1m: Decimal | None
    request_price: Decimal | None


@dataclass(frozen=True, slots=True)
class PricingDisablePlan:
    """Bounded reviewed plan: exact scope, signed rows, display facts."""

    provider: str
    model: str
    endpoint: str | None
    row_count: int
    rows: tuple[PricingDisableReviewRow, ...]
    display_rows: tuple[PricingDisableDisplayRow, ...] = ()



@dataclass(frozen=True, slots=True)
class PricingDisableApplyResult:
    """Truthful apply outcome for one reviewed plan.

    ``already_disabled`` marks the honest no-op repeat (every reviewed
    row was already disabled at apply time under matching fingerprints):
    no second disable and no invented receipt are produced.
    """

    disabled_count: int
    already_disabled: bool


class PricingRuleService:
    """Small service layer for pricing rule CLI operations."""

    def __init__(
        self,
        *,
        pricing_rules_repository: PricingRulesRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._pricing = pricing_rules_repository
        self._audit = audit_repository

    async def create_pricing_rule(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str,
        currency: str,
        input_price_per_1m: Decimal,
        output_price_per_1m: Decimal,
        cached_input_price_per_1m: Decimal | None,
        reasoning_price_per_1m: Decimal | None,
        valid_from: datetime,
        valid_until: datetime | None,
        source_url: str | None,
        notes: str | None,
        enabled: bool,
        request_price: Decimal | None = None,
        pricing_metadata: dict[str, object] | None = None,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> PricingRule:
        _validate_non_negative(input_price_per_1m, "input_price_per_1m")
        _validate_non_negative(output_price_per_1m, "output_price_per_1m")
        _validate_optional_non_negative(cached_input_price_per_1m, "cached_input_price_per_1m")
        _validate_optional_non_negative(reasoning_price_per_1m, "reasoning_price_per_1m")
        _validate_optional_non_negative(request_price, "request_price")
        valid_from = _aware_time(valid_from)
        valid_until = _optional_aware_time(valid_until)
        _validate_validity(valid_from, valid_until)

        row = await self._pricing.create_pricing_rule(
            provider=_required_text(provider, "Provider"),
            upstream_model=_required_text(model, "Model"),
            endpoint=normalize_endpoint(endpoint),
            currency=_normalize_currency(currency),
            input_price_per_1m=input_price_per_1m,
            cached_input_price_per_1m=cached_input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            reasoning_price_per_1m=reasoning_price_per_1m,
            request_price=request_price,
            pricing_metadata=pricing_metadata,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=enabled,
            source_url=_clean_optional(source_url),
            notes=_clean_optional(notes),
        )
        await self._audit.add_audit_log(
            action="pricing_rule_created",
            entity_type="pricing_rule",
            entity_id=row.id,
            admin_user_id=actor_admin_id,
            new_values=_safe_audit_values(row),
            note=_clean_optional(reason),
        )
        return row

    async def list_pricing_rules(
        self,
        *,
        provider: str | None,
        model: str | None,
        endpoint: str | None,
        enabled_only: bool,
        limit: int,
    ) -> list[PricingRule]:
        rows = await self._pricing.list_pricing_rules(
            provider=_clean_optional(provider),
            upstream_model=_clean_optional(model),
            endpoint=normalize_endpoint(endpoint) if endpoint else None,
            limit=limit,
        )
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    async def get_pricing_rule(self, pricing_rule_id: uuid.UUID) -> PricingRule:
        row = await self._pricing.get_pricing_rule_by_id(pricing_rule_id)
        if row is None:
            raise RecordNotFoundError("Pricing rule")
        return row

    async def disable_model(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str | None,
    ) -> list[PricingRule]:
        rows = await self._pricing.list_pricing_rules_for_provider_model(
            provider=_required_text(provider, "Provider"),
            upstream_model=_required_text(model, "Model"),
            endpoint=normalize_endpoint(endpoint) if endpoint else None,
        )
        disabled: list[PricingRule] = []
        for row in rows:
            if not row.enabled:
                continue
            old_enabled = row.enabled
            updated = await self._pricing.set_pricing_rule_enabled(row.id, enabled=False)
            if updated:
                row.enabled = False
                disabled.append(row)
                await self._audit.add_audit_log(
                    action="pricing_rule_disabled",
                    entity_type="pricing_rule",
                    entity_id=row.id,
                    old_values={"enabled": old_enabled},
                    new_values={"enabled": False},
                )
        return disabled

    async def preview_disable_model(
        self,
        *,
        provider: str,
        model: str,
        endpoint: str | None = None,
        max_rows: int = PRICING_DISABLE_MAX_REVIEWED_ROWS,
    ) -> PricingDisablePlan:
        """214-a: read-only preview of the reviewed matching-model disable.

        Resolves the EXACT scope (provider, model, optional normalized
        endpoint) with the existing repository query, filtered in SQL to
        currently enabled rows and bounded at ``max_rows + 1`` (cap+1):
        a larger match count is an overbound scope and is REFUSED
        outright - never silently trimmed or chunked non-atomically.
        Returns the bounded plan with one compact signed row (identity +
        stable source fingerprint) and safe per-row display facts.
        This is read-only: no write, no audit, no commit.  The legacy
        CLI ``disable_model`` default is preserved unchanged.
        """
        scope_provider, scope_model, scope_endpoint = _pricing_disable_scope(
            provider=provider, model=model, endpoint=endpoint
        )
        enabled = await self._pricing.list_pricing_rules_for_provider_model(
            provider=scope_provider,
            upstream_model=scope_model,
            endpoint=scope_endpoint,
            enabled_only=True,
            limit=max_rows + 1,
        )
        if not enabled:
            raise PricingDisableNoMatchError()
        if len(enabled) > max_rows:
            raise PricingDisableScopeError(matched_rows=len(enabled), max_rows=max_rows)
        enabled.sort(key=lambda row: row.id)
        plan_rows: list[PricingDisableReviewRow] = []
        display_rows: list[PricingDisableDisplayRow] = []
        for row in enabled:
            facts = _pricing_disable_row_facts(row)
            plan_rows.append(
                PricingDisableReviewRow(
                    pricing_rule_id=row.id,
                    fingerprint=_pricing_disable_row_fingerprint(facts),
                )
            )
            display_rows.append(
                PricingDisableDisplayRow(
                    pricing_rule_id=row.id,
                    provider=row.provider,
                    upstream_model=row.upstream_model,
                    endpoint=row.endpoint,
                    currency=row.currency,
                    valid_from=row.valid_from,
                    valid_until=row.valid_until,
                    input_price_per_1m=row.input_price_per_1m,
                    cached_input_price_per_1m=row.cached_input_price_per_1m,
                    output_price_per_1m=row.output_price_per_1m,
                    reasoning_price_per_1m=row.reasoning_price_per_1m,
                    request_price=row.request_price,
                )
            )
        return PricingDisablePlan(
            provider=scope_provider,
            model=scope_model,
            endpoint=scope_endpoint,
            row_count=len(plan_rows),
            rows=tuple(plan_rows),
            display_rows=tuple(display_rows),
        )

    async def apply_disable_model_reviewed(
        self,
        plan: PricingDisablePlan,
        *,
        actor_admin_id: uuid.UUID | None,
        reason: str | None,
    ) -> PricingDisableApplyResult:
        """214-a: apply ONE reviewed plan in the caller's transaction.

        Sequence (all in the caller's single transaction):

        1. validate the plan BEFORE locking (count, unique IDs, the
           bounded cap, fingerprint format);
        2. lock the reviewed rows deterministically (id ASC, one
           FOR UPDATE statement with ``populate_existing`` so the
           post-lock re-read refreshes already-loaded instances);
        3. re-check every reviewed row's full stable fingerprint against
           the fresh post-lock source facts (identity, currency,
           validity window, typed prices, and the pricing-policy
           metadata hash) - any policy/price/validity edit or scope
           drift is refused;
        4. the enabled law under the locks: a mixed enabled/disabled set
           is visible drift and is refused with zero writes; otherwise
           re-read the BOUNDED matching enabled membership AFTER the
           blocking locks in BOTH outcome paths - every row still
           enabled: the current matching enabled set must equal the
           reviewed set EXACTLY (no new or missing member) before each
           row is disabled with a real per-row
           ``pricing_rule_disabled`` audit carrying the session actor
           and the reviewed reason; every row already disabled (the
           honest no-op repeat): the matching enabled membership must be
           EMPTY - a newly matching unreviewed enabled row or a
           re-enabled reviewed row is refused, so a newly matching row
           is never silently disabled.

        The service never commits; the caller owns the single
        transaction, so a late audit failure rolls ALL changes back
        (nothing commits partially).  Signing a review token alone is
        not a stale guard: the fresh locked facts and the post-lock
        membership re-read are authoritative.  This is NOT a
        serializable catalog-wide insert exclusion: an uncommitted
        concurrent insert is not visible, and no such guarantee is
        claimed.
        """
        _validate_reviewed_plan(plan)
        if not plan.rows:
            return PricingDisableApplyResult(disabled_count=0, already_disabled=False)
        locked = await self._pricing.lock_pricing_rules_for_review(
            tuple(row.pricing_rule_id for row in plan.rows)
        )
        locked_by_id = {row.id: row for row in locked}
        reviewed_ids = {row.pricing_rule_id for row in plan.rows}
        if set(locked_by_id) != reviewed_ids:
            # A reviewed row is gone (or locked as a different row).
            raise PricingDisableStaleError()

        # Full post-lock fingerprint re-check against fresh facts.
        for reviewed in plan.rows:
            row = locked_by_id[reviewed.pricing_rule_id]
            if (
                _pricing_disable_row_fingerprint(_pricing_disable_row_facts(row))
                != reviewed.fingerprint
            ):
                raise PricingDisableStaleError()

        fresh_enabled_flags = tuple(
            locked_by_id[reviewed.pricing_rule_id].enabled for reviewed in plan.rows
        )
        all_still_enabled = all(enabled is True for enabled in fresh_enabled_flags)
        all_already_disabled = all(enabled is False for enabled in fresh_enabled_flags)
        if not (all_still_enabled or all_already_disabled):
            # Mixed state: part of the scope was disabled after the
            # preview.  That is visible drift, not the reviewed state
            # and not the full repeat - refuse with zero writes.
            raise PricingDisableStaleError()

        # Post-lock bounded enabled-membership refresh, re-checked in
        # BOTH outcome paths: a newly matching unreviewed enabled row is
        # visible drift and is refused (never silently disabled).
        members = await self._pricing.list_pricing_rules_for_provider_model(
            provider=plan.provider,
            upstream_model=plan.model,
            endpoint=plan.endpoint,
            enabled_only=True,
            limit=PRICING_DISABLE_MAX_REVIEWED_ROWS + 1,
        )
        if len(members) > PRICING_DISABLE_MAX_REVIEWED_ROWS:
            raise PricingDisableStaleError()
        member_ids = {row.id for row in members}

        if all_still_enabled:
            # All still enabled: the current matching enabled set must
            # equal the reviewed set exactly (no new or missing member).
            if member_ids != reviewed_ids:
                raise PricingDisableStaleError()
            for reviewed in plan.rows:
                row = locked_by_id[reviewed.pricing_rule_id]
                updated = await self._pricing.set_pricing_rule_enabled(row.id, enabled=False)
                if not updated:
                    raise PricingDisableStaleError()
                await self._audit.add_audit_log(
                    action="pricing_rule_disabled",
                    entity_type="pricing_rule",
                    entity_id=row.id,
                    admin_user_id=actor_admin_id,
                    old_values={"enabled": True},
                    new_values={"enabled": False},
                    # 214-a: the reviewed reason is stored VERBATIM
                    # (never trimmed) so the audit record matches the
                    # signed review value; the GUI validates nonblank
                    # content and the bound before signing.  The legacy
                    # disable_model/CLI reason handling is unchanged.
                    note=reason,
                )
            return PricingDisableApplyResult(disabled_count=len(plan.rows), already_disabled=False)

        # All already disabled: the honest no-op repeat.  The matching
        # enabled membership must be EMPTY - any enabled member (a newly
        # inserted row or a re-enabled reviewed row) is visible drift on
        # the repeat path and is refused too.  No second disable, no
        # duplicate audit, no invented receipt.
        if member_ids:
            raise PricingDisableStaleError()
        return PricingDisableApplyResult(disabled_count=0, already_disabled=True)


    async def update_pricing_rule(
        self,
        pricing_rule_id: uuid.UUID | str,
        *,
        provider: str,
        model: str,
        endpoint: str,
        currency: str,
        input_price_per_1m: Decimal,
        output_price_per_1m: Decimal,
        cached_input_price_per_1m: Decimal | None,
        reasoning_price_per_1m: Decimal | None,
        request_price: Decimal | None,
        pricing_metadata: dict[str, object],
        valid_from: datetime,
        valid_until: datetime | None,
        source_url: str | None,
        notes: str | None,
        enabled: bool,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> PricingRule:
        parsed_id = _parse_pricing_rule_id(pricing_rule_id)
        existing = await self.get_pricing_rule(parsed_id)
        old_values = _safe_audit_values(existing)

        _validate_non_negative(input_price_per_1m, "input_price_per_1m")
        _validate_non_negative(output_price_per_1m, "output_price_per_1m")
        _validate_optional_non_negative(cached_input_price_per_1m, "cached_input_price_per_1m")
        _validate_optional_non_negative(reasoning_price_per_1m, "reasoning_price_per_1m")
        _validate_optional_non_negative(request_price, "request_price")
        valid_from = _aware_time(valid_from)
        valid_until = _optional_aware_time(valid_until)
        _validate_validity(valid_from, valid_until)

        updated = await self._pricing.update_pricing_rule_metadata(
            parsed_id,
            provider=_required_text(provider, "Provider"),
            upstream_model=_required_text(model, "Model"),
            endpoint=normalize_endpoint(endpoint),
            currency=_normalize_currency(currency),
            input_price_per_1m=input_price_per_1m,
            cached_input_price_per_1m=cached_input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            reasoning_price_per_1m=reasoning_price_per_1m,
            request_price=request_price,
            pricing_metadata=pricing_metadata,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=enabled,
            source_url=_clean_optional(source_url),
            notes=_clean_optional(notes),
        )
        if not updated:
            raise RecordNotFoundError("Pricing rule")

        row = await self.get_pricing_rule(parsed_id)
        await self._audit.add_audit_log(
            action="pricing_rule_updated",
            entity_type="pricing_rule",
            entity_id=row.id,
            admin_user_id=actor_admin_id,
            old_values=old_values,
            new_values=_safe_audit_values(row),
            note=_clean_optional(reason),
        )
        return row

    async def set_pricing_rule_enabled(
        self,
        pricing_rule_id: uuid.UUID | str,
        *,
        enabled: bool,
        actor_admin_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> PricingRule:
        parsed_id = _parse_pricing_rule_id(pricing_rule_id)
        row = await self.get_pricing_rule(parsed_id)
        old_enabled = row.enabled
        updated = await self._pricing.set_pricing_rule_enabled(parsed_id, enabled=enabled)
        if not updated:
            raise RecordNotFoundError("Pricing rule")
        row.enabled = enabled
        await self._audit.add_audit_log(
            action="pricing_rule_enabled" if enabled else "pricing_rule_disabled",
            entity_type="pricing_rule",
            entity_id=row.id,
            admin_user_id=actor_admin_id,
            old_values={"enabled": old_enabled},
            new_values={"enabled": enabled},
            note=_clean_optional(reason),
        )
        return row

    async def import_pricing_rules(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        dry_run: bool,
    ) -> PricingImportResult:
        prepared = [_prepare_import_row(row, index=index) for index, row in enumerate(rows, start=1)]
        if dry_run:
            return PricingImportResult(imported_count=0, dry_run=True, rows=tuple(prepared))

        created: list[PricingRule] = []
        for row in prepared:
            created.append(await self.create_pricing_rule(**row))

        await self._audit.add_audit_log(
            action="pricing_rules_imported",
            entity_type="pricing_rule",
            new_values={"imported_count": len(created)},
        )
        return PricingImportResult(imported_count=len(created), dry_run=False, rows=tuple(created))


def _prepare_import_row(row: Mapping[str, object], *, index: int) -> dict[str, object]:
    unknown_fields = set(row) - _ALLOWED_IMPORT_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"Pricing import row {index} has unknown fields: {fields}")

    model = row.get("model", row.get("upstream_model"))
    return {
        "provider": _required_import_text(row.get("provider"), index=index, field_name="provider"),
        "model": _required_import_text(model, index=index, field_name="model"),
        "endpoint": str(row.get("endpoint") or "chat.completions"),
        "currency": str(row.get("currency") or "EUR"),
        "input_price_per_1m": _required_import_decimal(
            row.get("input_price_per_1m"),
            index=index,
            field_name="input_price_per_1m",
        ),
        "output_price_per_1m": _required_import_decimal(
            row.get("output_price_per_1m"),
            index=index,
            field_name="output_price_per_1m",
        ),
        "cached_input_price_per_1m": _optional_import_decimal(
            row.get("cached_input_price_per_1m"),
            index=index,
            field_name="cached_input_price_per_1m",
        ),
        "reasoning_price_per_1m": _optional_import_decimal(
            row.get("reasoning_price_per_1m"),
            index=index,
            field_name="reasoning_price_per_1m",
        ),
        "request_price": _optional_import_decimal(
            row.get("request_price"),
            index=index,
            field_name="request_price",
        ),
        "pricing_metadata": _optional_import_metadata(
            row.get("pricing_metadata"),
            row.get("source_retrieved_at"),
            index=index,
        ),
        "valid_from": _optional_import_datetime(row.get("valid_from"), index=index, field_name="valid_from")
        or datetime.now(UTC),
        "valid_until": _optional_import_datetime(
            row.get("valid_until"),
            index=index,
            field_name="valid_until",
        ),
        "source_url": _optional_import_text(row.get("source_url"), index=index, field_name="source_url"),
        "notes": _optional_import_text(row.get("notes"), index=index, field_name="notes"),
        "enabled": _optional_import_bool(row.get("enabled"), index=index, field_name="enabled", default=True),
    }


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized


def _pricing_disable_scope(
    *,
    provider: str,
    model: str,
    endpoint: str | None,
) -> tuple[str, str, str | None]:
    """Exact reviewed scope: trimmed provider/model, normalized endpoint."""
    return (
        _required_text(provider, "Provider"),
        _required_text(model, "Model"),
        normalize_endpoint(endpoint) if endpoint else None,
    )


# ----------------------------------------------------------------------
# 214-a: bounded reviewed-plan document (strict, closed, machine-safe).
# The signed plan is COMPACT: rows carry only {id, fingerprint}.  The
# fingerprint privately binds the source facts (scope identity, currency,
# validity window, typed prices, and a canonical hash of the
# pricing_metadata pricing policy) without rendering or signing the raw
# metadata.  The 128 KiB canonical envelope is ample for the bounded
# 1000 UUID+hash records.
# ----------------------------------------------------------------------
PRICING_DISABLE_PLAN_MAX_BYTES = 128 * 1024

_PRICING_DISABLE_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _pricing_disable_policy_hash(metadata: Mapping[str, object] | None) -> str:
    """Private canonical hash of the pricing-policy metadata.

    The runtime pricing lookup consumes ``pricing_metadata`` (audio output
    price, Codex accounting multipliers, external-tool pricing), so a
    policy edit is a relevant source change for the review.  Only the
    SHA-256 digest of the canonical JSON is bound; the metadata itself
    is never rendered, signed, or logged.
    """
    normalized: dict[str, object] = dict(metadata or {})
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pricing_disable_row_facts(row: PricingRule) -> dict[str, str | None]:
    """Canonical reviewed source facts for one pricing row.

    Binds: identity, scope identity, currency, the full validity window,
    the typed price facts, and the pricing-policy hash.  Deliberately
    EXCLUDES unrelated drift (``notes``, ``updated_at``, ``source_url``)
    and the ``enabled`` flag (evaluated under the locks at apply time).
    """
    return {
        "id": str(row.id),
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "endpoint": row.endpoint,
        "currency": row.currency,
        "valid_from": _utc_iso(row.valid_from),
        "valid_until": _utc_iso(row.valid_until),
        "input_price_per_1m": str(row.input_price_per_1m),
        "cached_input_price_per_1m": (
            None if row.cached_input_price_per_1m is None else str(row.cached_input_price_per_1m)
        ),
        "output_price_per_1m": str(row.output_price_per_1m),
        "reasoning_price_per_1m": (
            None if row.reasoning_price_per_1m is None else str(row.reasoning_price_per_1m)
        ),
        "request_price": None if row.request_price is None else str(row.request_price),
        "policy_hash": _pricing_disable_policy_hash(row.pricing_metadata),
    }


def _pricing_disable_row_fingerprint(facts: Mapping[str, str | None]) -> str:
    """Stable SHA-256 fingerprint over the canonical fact set."""
    encoded = json.dumps(
        dict(facts), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_reviewed_plan(plan: PricingDisablePlan) -> None:
    """Pre-lock plan validation (count, unique IDs, cap, format).

    The review-intent strict re-parse already enforces the document
    schema; this is the service-side defense-in-depth gate that runs
    BEFORE any locking, so a malformed plan can never touch the
    catalog.
    """
    if plan.row_count != len(plan.rows):
        raise ValueError("The pricing disable review plan count is inconsistent.")
    if plan.row_count > PRICING_DISABLE_MAX_REVIEWED_ROWS:
        raise ValueError("The pricing disable review plan exceeds the bounded cap.")
    seen: set[uuid.UUID] = set()
    for row in plan.rows:
        if row.pricing_rule_id in seen:
            raise ValueError("The pricing disable review plan has duplicate row IDs.")
        seen.add(row.pricing_rule_id)
        if not _PRICING_DISABLE_FINGERPRINT_RE.fullmatch(row.fingerprint):
            raise ValueError("The pricing disable review plan fingerprint is invalid.")


def render_pricing_disable_plan(plan: PricingDisablePlan) -> dict[str, object]:
    """Render one reviewed plan as the compact strict signed document.

    Safe preview display facts are NOT duplicated in the signed rows -
    only the identity plus the stable fingerprint, which fits the fixed
    128 KiB budget for the bounded 1000-row plan.
    """
    return {
        "provider": plan.provider,
        "model": plan.model,
        "endpoint": plan.endpoint,
        "row_count": plan.row_count,
        "rows": [
            {"id": str(row.pricing_rule_id), "fingerprint": row.fingerprint}
            for row in plan.rows
        ],
    }


def parse_pricing_disable_plan_document(document: object) -> PricingDisablePlan:
    """Strictly re-parse one signed plan document (closed schema).

    Validates the scope fields, the plan count against the bounded cap,
    the exact row set (unique IDs, {id, fingerprint} shape, fingerprint
    format), and returns the plan with EMPTY display rows (display is a
    preview-only concern).  Every failure raises ``ValueError`` with a
    fixed safe message; no document value is echoed.  This is the
    re-parse gate the review-intent verifier runs BEFORE canonical
    serialization on every verify.
    """

    def _fail() -> ValueError:
        return ValueError("The pricing disable review plan is missing or invalid.")

    if not isinstance(document, dict) or set(document) != {
        "provider",
        "model",
        "endpoint",
        "row_count",
        "rows",
    }:
        raise _fail()
    provider = document.get("provider")
    model = document.get("model")
    endpoint = document.get("endpoint")
    if (
        not isinstance(provider, str)
        or not provider.strip()
        or not isinstance(model, str)
        or not model.strip()
        or endpoint is not None
        and not isinstance(endpoint, str)
    ):
        raise _fail()
    row_count = document.get("row_count")
    rows = document.get("rows")
    if (
        not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count < 0
        or row_count > PRICING_DISABLE_MAX_REVIEWED_ROWS
        or not isinstance(rows, list)
        or len(rows) != row_count
    ):
        raise _fail()
    plan_rows: list[PricingDisableReviewRow] = []
    seen_ids: set[uuid.UUID] = set()
    for item in rows:
        if not isinstance(item, dict) or set(item) != {"id", "fingerprint"}:
            raise _fail()
        try:
            row_id = uuid.UUID(str(item.get("id")))
        except (ValueError, TypeError):
            raise _fail() from None
        fingerprint = item.get("fingerprint")
        if not isinstance(fingerprint, str) or not _PRICING_DISABLE_FINGERPRINT_RE.fullmatch(
            fingerprint
        ):
            raise _fail()
        if row_id in seen_ids:
            raise _fail()
        seen_ids.add(row_id)
        plan_rows.append(
            PricingDisableReviewRow(pricing_rule_id=row_id, fingerprint=fingerprint)
        )
    return PricingDisablePlan(
        provider=provider,
        model=model,
        endpoint=endpoint,
        row_count=row_count,
        rows=tuple(plan_rows),
    )


def _parse_pricing_rule_id(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("pricing_rule_id must be a valid UUID") from exc


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_currency(value: str) -> str:
    normalized = _required_text(value, "Currency").upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    return normalized


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _optional_aware_time(value: datetime | None) -> datetime | None:
    return _aware_time(value) if value is not None else None


def _validate_validity(valid_from: datetime, valid_until: datetime | None) -> None:
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from")


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_optional_non_negative(value: Decimal | None, field_name: str) -> None:
    if value is not None:
        _validate_non_negative(value, field_name)


def _required_import_text(value: object, *, index: int, field_name: str) -> str:
    if value is None:
        raise ValueError(f"Pricing import row {index} is missing {field_name}")
    return _required_text(str(value), field_name)


def _optional_import_text(value: object, *, index: int, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Pricing import row {index} field {field_name} must be a string")
    return _clean_optional(value)


def _required_import_decimal(value: object, *, index: int, field_name: str) -> Decimal:
    parsed = _optional_import_decimal(value, index=index, field_name=field_name)
    if parsed is None:
        raise ValueError(f"Pricing import row {index} is missing {field_name}")
    return parsed


def _optional_import_decimal(value: object, *, index: int, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise ValueError(f"Pricing import row {index} field {field_name} must be a decimal string")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Pricing import row {index} field {field_name} must be a decimal value"
        ) from exc
    _validate_non_negative(parsed, field_name)
    return parsed


def _optional_import_datetime(value: object, *, index: int, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"Pricing import row {index} field {field_name} must be an ISO datetime")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Pricing import row {index} field {field_name} must be an ISO datetime"
        ) from exc
    return _aware_time(parsed)


def _optional_import_metadata(
    value: object,
    source_retrieved_at: object,
    *,
    index: int,
) -> dict[str, object]:
    if value is None or value == "":
        metadata: dict[str, object] = {}
    elif isinstance(value, Mapping):
        metadata = dict(value)
    elif isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Pricing import row {index} field pricing_metadata must be a JSON object"
            ) from exc
        if not isinstance(loaded, Mapping):
            raise ValueError(f"Pricing import row {index} field pricing_metadata must be a JSON object")
        metadata = dict(loaded)
    else:
        raise ValueError(f"Pricing import row {index} field pricing_metadata must be a JSON object")

    retrieved_at = _optional_import_text(
        source_retrieved_at,
        index=index,
        field_name="source_retrieved_at",
    )
    if retrieved_at is not None:
        _optional_import_datetime(retrieved_at, index=index, field_name="source_retrieved_at")
        metadata.setdefault("source_retrieved_at", retrieved_at)
    return metadata


def _optional_import_bool(
    value: object,
    *,
    index: int,
    field_name: str,
    default: bool,
) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"Pricing import row {index} field {field_name} must be boolean")


def _safe_audit_values(row: PricingRule) -> dict[str, object]:
    return {
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "endpoint": row.endpoint,
        "currency": row.currency,
        "input_price_per_1m": str(row.input_price_per_1m) if row.input_price_per_1m is not None else None,
        "cached_input_price_per_1m": (
            str(row.cached_input_price_per_1m)
            if row.cached_input_price_per_1m is not None
            else None
        ),
        "output_price_per_1m": str(row.output_price_per_1m) if row.output_price_per_1m is not None else None,
        "reasoning_price_per_1m": (
            str(row.reasoning_price_per_1m) if row.reasoning_price_per_1m is not None else None
        ),
        "request_price": str(row.request_price) if row.request_price is not None else None,
        "pricing_metadata": row.pricing_metadata or {},
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until is not None else None,
        "enabled": row.enabled,
        "source_url": row.source_url,
        "notes": row.notes,
    }
