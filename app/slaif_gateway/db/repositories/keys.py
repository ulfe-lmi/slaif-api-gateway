"""Repository helpers for gateway_keys table operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import GatewayKey
from slaif_gateway.services.quota_errors import QuotaCounterInvariantError


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
        rate_limit_requests_per_minute: int | None = None,
        rate_limit_tokens_per_minute: int | None = None,
        max_concurrent_requests: int | None = None,
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
            rate_limit_requests_per_minute=rate_limit_requests_per_minute,
            rate_limit_tokens_per_minute=rate_limit_tokens_per_minute,
            max_concurrent_requests=max_concurrent_requests,
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
        statement = select(GatewayKey).where(GatewayKey.id == gateway_key_id).with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_gateway_key_by_public_key_id(self, public_key_id: str) -> GatewayKey | None:
        statement = select(GatewayKey).where(GatewayKey.public_key_id == public_key_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

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

        statement = statement.order_by(GatewayKey.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

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
