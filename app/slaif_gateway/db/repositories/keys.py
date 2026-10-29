"""Repository helpers for gateway_keys table operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from slaif_gateway.db.models import GatewayKey, Owner
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError
from slaif_gateway.utils.admin_list_filters import (
    as_uuid_tuple,
    as_value_tuple,
    or_equals,
)


class GatewayKeysRepository:
    """Encapsulates CRUD-style access for GatewayKey rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_gateway_key_record(
        self,
        *,
        public_key_id: str,
        token_hash: str,
        owner_id: uuid.UUID,
        valid_from: datetime,
        valid_until: datetime,
        status: str = "active",
        key_prefix: str = "sk-slaif-",
        key_hint: str | None = None,
        hash_algorithm: str = "hmac-sha256",
        hmac_key_version: int = 1,
        cohort_id: uuid.UUID | None = None,
        cost_limit_eur: Decimal | None = None,
        token_limit_total: int | None = None,
        request_limit_total: int | None = None,
        created_by_admin_user_id: uuid.UUID | None = None,
        allow_all_models: bool = False,
        allowed_models: list[str] | None = None,
        allow_all_endpoints: bool = False,
        allowed_endpoints: list[str] | None = None,
        key_purpose: str = "standard",
        capability_policy_mode: str = "standard",
        calibration_metadata: dict[str, object] | None = None,
        template_id: uuid.UUID | None = None,
        template_revision_id: uuid.UUID | None = None,
        rate_limit_requests_per_minute: int | None = None,
        rate_limit_tokens_per_minute: int | None = None,
        max_concurrent_requests: int | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> GatewayKey:
        gateway_key = GatewayKey(
            public_key_id=public_key_id,
            token_hash=token_hash,
            owner_id=owner_id,
            valid_from=valid_from,
            valid_until=valid_until,
            status=status,
            key_prefix=key_prefix,
            key_hint=key_hint,
            hash_algorithm=hash_algorithm,
            hmac_key_version=hmac_key_version,
            cohort_id=cohort_id,
            cost_limit_eur=cost_limit_eur,
            token_limit_total=token_limit_total,
            request_limit_total=request_limit_total,
            created_by_admin_user_id=created_by_admin_user_id,
            allow_all_models=allow_all_models,
            allowed_models=allowed_models or [],
            allow_all_endpoints=allow_all_endpoints,
            allowed_endpoints=allowed_endpoints or [],
            key_purpose=key_purpose,
            capability_policy_mode=capability_policy_mode,
            calibration_metadata=calibration_metadata or {},
            template_id=template_id,
            template_revision_id=template_revision_id,
            rate_limit_requests_per_minute=rate_limit_requests_per_minute,
            rate_limit_tokens_per_minute=rate_limit_tokens_per_minute,
            max_concurrent_requests=max_concurrent_requests,
            metadata_json=metadata_json or {},
        )
        self._session.add(gateway_key)
        await self._session.flush()
        return gateway_key

    async def get_gateway_key_by_id(self, gateway_key_id: uuid.UUID) -> GatewayKey | None:
        return await self._session.get(GatewayKey, gateway_key_id)

    async def get_gateway_key_by_id_for_quota_update(
        self,
        gateway_key_id: uuid.UUID,
    ) -> GatewayKey | None:
        """Return a gateway key row locked for quota counter mutation."""
        statement = select(GatewayKey).where(GatewayKey.id == gateway_key_id).with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_gateway_key_for_update(self, gateway_key_id: uuid.UUID) -> GatewayKey | None:
        """Return a gateway key row locked for administrative mutation."""
        statement = (
            select(GatewayKey)
            .where(GatewayKey.id == gateway_key_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_gateway_key_by_public_key_id(self, public_key_id: str) -> GatewayKey | None:
        statement = select(GatewayKey).where(GatewayKey.public_key_id == public_key_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def find_clone_receipts(
        self,
        *,
        source_gateway_key_id: uuid.UUID,
        operation_uuid: uuid.UUID,
    ) -> list[GatewayKey]:
        """Locate every key carrying a clone receipt for (source, operation).

        Narrowly-typed read-only lookup INDEPENDENT of the (mutable) target
        selection: retry safety is namespaced by (source, operation) only.
        Returns every match so the caller can refuse an ambiguous result
        rather than silently choosing one. The receipt is a bounded safe JSONB
        member (UUIDs + fingerprints only).

        Bounded: at most TWO matches are ever materialized (limit 2) - two
        are sufficient to prove ambiguity; a corrupted third receipt adds no
        decision information and no unbounded scan cost.
        """
        from slaif_gateway.schemas.key_clone import CLONE_RECEIPT_METADATA_KEY

        needle = {
            CLONE_RECEIPT_METADATA_KEY: {
                "source_gateway_key_id": str(source_gateway_key_id),
                "operation_uuid": str(operation_uuid),
            }
        }
        statement = select(GatewayKey).where(
            GatewayKey.metadata_json.contains(needle),
        ).limit(2)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def current_transaction_isolation(self) -> str:
        """Return the CURRENT transaction's isolation level (bounded read).

        The clone operation enforces the supported READ COMMITTED boundary
        before writing; this narrow read lets it refuse an unsupported level
        (e.g. a pre-established REPEATABLE READ snapshot) rather than pretend
        row locks guarantee arbitrary-isolation dedup.
        """
        result = await self._session.execute(
            text("SELECT current_setting('transaction_isolation')")
        )
        return result.scalar_one()

    async def attach_clone_receipt(
        self,
        gateway_key_id: uuid.UUID,
        *,
        source_gateway_key_id: uuid.UUID,
        operation_uuid: uuid.UUID,
        target_owner_id: uuid.UUID,
        one_time_secret_id: uuid.UUID,
        email_delivery_id: uuid.UUID | None,
        source_fingerprint: str,
        policy_fingerprint: str,
        source_public_key_id: str,
        source_valid_until: str | None,
        target_cohort_id: uuid.UUID | None,
        requires_fenced_confirmation: bool,
        validity_mode: str,
        validity_duration_seconds: int | None,
        validity_from: str | None,
        validity_until: str | None,
    ) -> GatewayKey:
        """Persist a bounded safe clone receipt on the new target key's metadata.

        Flush-only; the caller owns the transaction boundary. The receipt
        carries safe UUIDs, the stable business-plan identity (target
        owner/cohort, validity parameters, confirmation requirement, and the
        source public identity + source/policy fingerprints) only - never
        key material, provider references, or secrets.
        """
        from slaif_gateway.schemas.key_clone import CLONE_RECEIPT_METADATA_KEY

        row = await self._session.get(GatewayKey, gateway_key_id)
        if row is None:
            raise ValueError("Clone receipt target key does not exist.")
        metadata = dict(row.metadata_json or {})
        metadata[CLONE_RECEIPT_METADATA_KEY] = {
            "source_gateway_key_id": str(source_gateway_key_id),
            "operation_uuid": str(operation_uuid),
            "target_gateway_key_id": str(gateway_key_id),
            "target_owner_id": str(target_owner_id),
            "one_time_secret_id": str(one_time_secret_id),
            "email_delivery_id": str(email_delivery_id) if email_delivery_id else None,
            "source_fingerprint": source_fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "source_public_key_id": source_public_key_id,
            "source_valid_until": source_valid_until,
            "target_cohort_id": str(target_cohort_id) if target_cohort_id else None,
            "requires_fenced_confirmation": requires_fenced_confirmation,
            "validity_mode": validity_mode,
            "validity_duration_seconds": validity_duration_seconds,
            "validity_from": validity_from,
            "validity_until": validity_until,
            "status": "created",
        }
        row.metadata_json = metadata
        await self._session.flush()
        return row

    async def list_key_batch_selection(
        self,
        *,
        cohort_id: uuid.UUID,
        statuses: Sequence[str],
        limit: int,
    ) -> list[GatewayKey]:
        """Bounded batch membership read for one cohort and finite statuses.

        Additive read-only selection used by the reviewed key-configuration
        batch: the cohort/status predicates are applied in SQL BEFORE the
        bound (cap+1 overflow is refused by the caller), and the
        deterministic ``id ASC`` order matches the batch lock order. All
        existing list/admin/clone/accounting behavior is unchanged.
        """
        statement = (
            select(GatewayKey)
            .where(GatewayKey.cohort_id == cohort_id)
            .where(GatewayKey.status.in_(tuple(statuses)))
            .order_by(GatewayKey.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_gateway_keys_by_ids(
        self, *, key_ids: Sequence[uuid.UUID]
    ) -> list[GatewayKey]:
        """Exact bounded ID-set read for batch scope checks (deterministic
        ``id ASC``). Additive read-only; no existing behavior is changed."""
        if not key_ids:
            return []
        statement = (
            select(GatewayKey)
            .where(GatewayKey.id.in_(tuple(key_ids)))
            .order_by(GatewayKey.id.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_gateway_keys(
        self,
        *,
        owner_id: uuid.UUID | None = None,
        cohort_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GatewayKey]:
        statement: Select[tuple[GatewayKey]] = select(GatewayKey)
        if owner_id is not None:
            statement = statement.where(GatewayKey.owner_id == owner_id)
        if cohort_id is not None:
            statement = statement.where(GatewayKey.cohort_id == cohort_id)
        if status is not None:
            statement = statement.where(GatewayKey.status == status)

        # Stable pagination: the UUID tiebreaker keeps equal-timestamp rows
        # on a deterministic page order (no duplicates or gaps across pages).
        statement = statement.order_by(
            GatewayKey.created_at.desc(), GatewayKey.id.desc()
        ).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_keys_for_admin(
        self,
        *,
        status: str | None = None,
        owner_email: str | Sequence[str] | None = None,
        public_key_id: str | Sequence[str] | None = None,
        institution_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        cohort_id: uuid.UUID | Sequence[uuid.UUID] | None = None,
        expired: bool | None = None,
        now: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GatewayKey]:
        """Return gateway keys with safe admin-dashboard relationships loaded."""
        owner_emails = as_value_tuple(owner_email)
        public_key_ids = as_value_tuple(public_key_id)
        institution_ids = as_uuid_tuple(institution_id)
        cohort_ids = as_uuid_tuple(cohort_id)
        statement: Select[tuple[GatewayKey]] = select(GatewayKey).options(
            selectinload(GatewayKey.owner).selectinload(Owner.institution),
            selectinload(GatewayKey.cohort),
        )
        if owner_emails is not None or institution_ids is not None:
            statement = statement.join(GatewayKey.owner)
        if status is not None:
            statement = statement.where(GatewayKey.status == status)
        # 195-a: OR WITHIN a filter field, AND ACROSS fields; predicates
        # apply in SQL BEFORE LIMIT/OFFSET (never post-fetch filtering).
        if owner_emails is not None:
            statement = statement.where(
                or_(
                    *[
                        func.lower(Owner.email).like(f"%{email.strip().lower()}%")
                        for email in owner_emails
                    ]
                )
            )
        if public_key_ids is not None:
            statement = statement.where(
                or_equals(
                    GatewayKey.public_key_id,
                    tuple(value.strip() for value in public_key_ids),
                )
            )
        if institution_ids is not None:
            statement = statement.where(or_equals(Owner.institution_id, institution_ids))
        if cohort_ids is not None:
            statement = statement.where(or_equals(GatewayKey.cohort_id, cohort_ids))
        if expired is not None and now is not None:
            if expired:
                statement = statement.where(GatewayKey.valid_until <= now)
            else:
                statement = statement.where(GatewayKey.valid_until > now)

        statement = statement.order_by(GatewayKey.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_key_for_admin_detail(self, gateway_key_id: uuid.UUID) -> GatewayKey | None:
        """Return one gateway key with safe admin-dashboard relationships loaded."""
        statement = (
            select(GatewayKey)
            .options(
                selectinload(GatewayKey.owner).selectinload(Owner.institution),
                selectinload(GatewayKey.cohort),
            )
            .where(GatewayKey.id == gateway_key_id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update_gateway_key_status(
        self,
        gateway_key_id: uuid.UUID,
        *,
        status: str,
        revoked_at: datetime | None = None,
        revoked_reason: str | None = None,
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False
        gateway_key.status = status
        gateway_key.revoked_at = revoked_at
        gateway_key.revoked_reason = revoked_reason
        await self._session.flush()
        return True

    async def update_gateway_key_limits(
        self,
        gateway_key_id: uuid.UUID,
        *,
        cost_limit_eur: Decimal | None = None,
        token_limit_total: int | None = None,
        request_limit_total: int | None = None,
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        gateway_key.cost_limit_eur = cost_limit_eur
        gateway_key.token_limit_total = token_limit_total
        gateway_key.request_limit_total = request_limit_total
        await self._session.flush()
        return True

    async def update_gateway_key_rate_limit_policy(
        self,
        gateway_key_id: uuid.UUID,
        *,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
        max_concurrent_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        gateway_key.rate_limit_requests_per_minute = requests_per_minute
        gateway_key.rate_limit_tokens_per_minute = tokens_per_minute
        gateway_key.max_concurrent_requests = max_concurrent_requests

        metadata = dict(gateway_key.metadata_json or {})
        existing_rate_policy = metadata.get("rate_limit_policy")
        rate_policy = dict(existing_rate_policy) if isinstance(existing_rate_policy, dict) else {}
        if window_seconds is None:
            rate_policy.pop("window_seconds", None)
        else:
            rate_policy["window_seconds"] = window_seconds

        if rate_policy:
            metadata["rate_limit_policy"] = rate_policy
        else:
            metadata.pop("rate_limit_policy", None)
        gateway_key.metadata_json = metadata

        await self._session.flush()
        return True

    async def update_gateway_key_metadata(
        self,
        gateway_key_id: uuid.UUID,
        *,
        metadata_json: dict[str, object],
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        gateway_key.metadata_json = metadata_json
        await self._session.flush()
        return True

    async def update_gateway_key_request_policy(
        self,
        gateway_key_id: uuid.UUID,
        *,
        allowed_models: list[str],
        allowed_endpoints: list[str],
        allow_all_models: bool,
        allow_all_endpoints: bool,
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        gateway_key.allowed_models = allowed_models
        gateway_key.allowed_endpoints = allowed_endpoints
        gateway_key.allow_all_models = allow_all_models
        gateway_key.allow_all_endpoints = allow_all_endpoints
        await self._session.flush()
        return True

    async def update_gateway_key_validity(
        self,
        gateway_key_id: uuid.UUID,
        *,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        if valid_from is not None:
            gateway_key.valid_from = valid_from
        if valid_until is not None:
            gateway_key.valid_until = valid_until
        await self._session.flush()
        return True

    async def reset_gateway_key_usage_counters(
        self,
        gateway_key: GatewayKey,
        *,
        reset_used_counters: bool = True,
        reset_reserved_counters: bool = False,
        reset_at: datetime,
    ) -> GatewayKey:
        """Reset selected usage counters on an already loaded gateway key row."""
        if reset_used_counters:
            gateway_key.cost_used_eur = Decimal("0")
            gateway_key.tokens_used_total = 0
            gateway_key.requests_used_total = 0
            gateway_key.last_used_at = None
        if reset_reserved_counters:
            gateway_key.cost_reserved_eur = Decimal("0")
            gateway_key.tokens_reserved_total = 0
            gateway_key.requests_reserved_total = 0

        gateway_key.last_quota_reset_at = reset_at
        gateway_key.quota_reset_count += 1
        await self._session.flush()
        return gateway_key

    async def set_last_used_at(self, gateway_key_id: uuid.UUID, *, last_used_at: datetime) -> bool:
        gateway_key = await self.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            return False

        gateway_key.last_used_at = last_used_at
        await self._session.flush()
        return True

    async def add_reserved_counters(
        self,
        gateway_key: GatewayKey,
        *,
        cost_reserved_eur: Decimal,
        tokens_reserved_total: int,
        requests_reserved_total: int,
    ) -> GatewayKey:
        """Increment reserved counters on an already locked gateway key row."""
        gateway_key.cost_reserved_eur += cost_reserved_eur
        gateway_key.tokens_reserved_total += tokens_reserved_total
        gateway_key.requests_reserved_total += requests_reserved_total
        await self._session.flush()
        return gateway_key

    async def list_external_tool_fences(self, *, limit: int = 100) -> list[GatewayKey]:
        """Return gateway key rows carrying an unresolved external-tool fence."""
        statement = (
            select(GatewayKey)
            .where(GatewayKey.external_tool_fence_state.in_(["active", "held"]))
            .order_by(GatewayKey.external_tool_fence_expires_at.asc().nulls_last())
            .limit(max(1, min(int(limit), 1000)))
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_external_tool_fence(
        self,
        gateway_key: GatewayKey,
        *,
        state: str,
        reservation_id: uuid.UUID | None,
        request_id: str | None,
        acquired_at: datetime | None,
        expires_at: datetime | None,
    ) -> GatewayKey:
        """Set or clear the exclusive external-tool fence on an already locked key row."""
        gateway_key.external_tool_fence_state = state
        gateway_key.external_tool_fence_reservation_id = reservation_id
        gateway_key.external_tool_fence_request_id = request_id
        gateway_key.external_tool_fence_acquired_at = acquired_at
        gateway_key.external_tool_fence_expires_at = expires_at
        await self._session.flush()
        return gateway_key

    async def subtract_reserved_counters(
        self,
        gateway_key: GatewayKey,
        *,
        cost_reserved_eur: Decimal,
        tokens_reserved_total: int,
        requests_reserved_total: int,
    ) -> GatewayKey:
        """Decrement reserved counters on an already locked row.

        Underflow means reservation lifecycle state has drifted from key
        counters, so fail explicitly instead of hiding it with zero clamping.
        """
        _ensure_reserved_counters_can_decrement(
            gateway_key,
            cost_reserved_eur=cost_reserved_eur,
            tokens_reserved_total=tokens_reserved_total,
            requests_reserved_total=requests_reserved_total,
        )
        gateway_key.cost_reserved_eur -= cost_reserved_eur
        gateway_key.tokens_reserved_total -= tokens_reserved_total
        gateway_key.requests_reserved_total -= requests_reserved_total
        await self._session.flush()
        return gateway_key

    async def finalize_reserved_counters(
        self,
        gateway_key: GatewayKey,
        *,
        reserved_cost_eur: Decimal,
        reserved_tokens_total: int,
        reserved_requests_total: int,
        actual_cost_eur: Decimal,
        actual_tokens_total: int,
        actual_requests_total: int,
        last_used_at: datetime,
    ) -> GatewayKey:
        """Move reserved counters into used counters on an already locked key row."""
        _ensure_reserved_counters_can_decrement(
            gateway_key,
            cost_reserved_eur=reserved_cost_eur,
            tokens_reserved_total=reserved_tokens_total,
            requests_reserved_total=reserved_requests_total,
        )
        gateway_key.cost_reserved_eur -= reserved_cost_eur
        gateway_key.tokens_reserved_total -= reserved_tokens_total
        gateway_key.requests_reserved_total -= reserved_requests_total
        gateway_key.cost_used_eur += actual_cost_eur
        gateway_key.tokens_used_total += actual_tokens_total
        gateway_key.requests_used_total += actual_requests_total
        gateway_key.last_used_at = last_used_at
        await self._session.flush()
        return gateway_key


def _ensure_reserved_counters_can_decrement(
    gateway_key: GatewayKey,
    *,
    cost_reserved_eur: Decimal,
    tokens_reserved_total: int,
    requests_reserved_total: int,
) -> None:
    if gateway_key.cost_reserved_eur < cost_reserved_eur:
        raise QuotaCounterInvariantError(
            "Reserved cost counter is lower than the requested decrement",
            param="cost_reserved_eur",
        )
    if gateway_key.tokens_reserved_total < tokens_reserved_total:
        raise QuotaCounterInvariantError(
            "Reserved token counter is lower than the requested decrement",
            param="tokens_reserved_total",
        )
    if gateway_key.requests_reserved_total < requests_reserved_total:
        raise QuotaCounterInvariantError(
            "Reserved request counter is lower than the requested decrement",
            param="requests_reserved_total",
        )
