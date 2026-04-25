"""Quota reservation service for hard PostgreSQL-backed quota enforcement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.db.models import GatewayKey, QuotaReservation
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.quota import QuotaReservationResult
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.quota_errors import (
    InvalidQuotaEstimateError,
    KeyNotReservableError,
    QuotaConcurrencyError,
    QuotaLimitExceededError,
    QuotaReservationNotFoundError,
)

_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
_DEFAULT_RESERVATION_TTL = timedelta(minutes=15)


class QuotaService:
    """Reserve and release estimated quota within the caller's DB transaction.

    The service does not commit. Atomicity comes from locking the gateway key row
    with ``SELECT ... FOR UPDATE`` through the repository before checking limits,
    mutating reserved counters, and creating/updating the reservation row.
    """

    def __init__(
        self,
        *,
        gateway_keys_repository: GatewayKeysRepository,
        quota_reservations_repository: QuotaReservationsRepository,
    ) -> None:
        self._gateway_keys_repository = gateway_keys_repository
        self._quota_reservations_repository = quota_reservations_repository

    async def reserve_for_chat_completion(
        self,
        *,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        policy: ChatCompletionPolicyResult,
        cost_estimate: ChatCostEstimate,
        request_id: str,
        now: datetime | None = None,
    ) -> QuotaReservationResult:
        check_now = _aware_now(now)
        reserved_cost_eur = _validate_cost(cost_estimate.estimated_total_cost_eur)
        reserved_tokens = _validate_tokens(
            policy.estimated_input_tokens + policy.effective_output_tokens
        )
        _validate_tokens(cost_estimate.estimated_input_tokens)
        _validate_tokens(cost_estimate.estimated_output_tokens)

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            authenticated_key.gateway_key_id
        )
        if gateway_key is None:
            raise KeyNotReservableError("Gateway key cannot reserve quota")

        self._validate_key_can_reserve(gateway_key=gateway_key, now=check_now)
        self._validate_limits(
            gateway_key=gateway_key,
            reserved_cost_eur=reserved_cost_eur,
            reserved_tokens=reserved_tokens,
            reserved_requests=1,
        )

        expires_at = check_now + _DEFAULT_RESERVATION_TTL
        reservation = await self._quota_reservations_repository.create_reservation(
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            endpoint=_CHAT_COMPLETIONS_ENDPOINT,
            requested_model=route.requested_model,
            reserved_cost_eur=reserved_cost_eur,
            reserved_tokens=reserved_tokens,
            reserved_requests=1,
            status="pending",
            expires_at=expires_at,
        )
        await self._gateway_keys_repository.add_reserved_counters(
            gateway_key,
            cost_reserved_eur=reserved_cost_eur,
            tokens_reserved_total=reserved_tokens,
            requests_reserved_total=1,
        )

        return _reservation_result(reservation)

    async def release_reservation(
        self,
        reservation_id: uuid.UUID,
        *,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> QuotaReservationResult:
        _ = reason
        released_at = _aware_now(now)
        reservation = (
            await self._quota_reservations_repository.get_reservation_by_id_for_update(
                reservation_id
            )
        )
        if reservation is None:
            raise QuotaReservationNotFoundError()

        if reservation.status != "pending":
            return _reservation_result(reservation)

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            reservation.gateway_key_id
        )
        if gateway_key is None:
            raise QuotaConcurrencyError("Gateway key disappeared while releasing quota")

        await self._gateway_keys_repository.subtract_reserved_counters(
            gateway_key,
            cost_reserved_eur=reservation.reserved_cost_eur,
            tokens_reserved_total=reservation.reserved_tokens,
            requests_reserved_total=reservation.reserved_requests,
        )
        updated = await self._quota_reservations_repository.mark_pending_reservation_released(
            reservation,
            released_at=released_at,
        )
        return _reservation_result(updated)

    def _validate_key_can_reserve(self, *, gateway_key: GatewayKey, now: datetime) -> None:
        if gateway_key.status != "active":
            raise KeyNotReservableError("Gateway key cannot reserve quota")
        if gateway_key.valid_from.tzinfo is None or gateway_key.valid_until.tzinfo is None:
            raise KeyNotReservableError("Gateway key validity timestamps are invalid")
        if now < gateway_key.valid_from or now >= gateway_key.valid_until:
            raise KeyNotReservableError("Gateway key cannot reserve quota outside its validity window")

    def _validate_limits(
        self,
        *,
        gateway_key: GatewayKey,
        reserved_cost_eur: Decimal,
        reserved_tokens: int,
        reserved_requests: int,
    ) -> None:
        if gateway_key.cost_limit_eur is not None:
            projected_cost = (
                gateway_key.cost_used_eur + gateway_key.cost_reserved_eur + reserved_cost_eur
            )
            if projected_cost > gateway_key.cost_limit_eur:
                raise QuotaLimitExceededError("Cost quota limit exceeded", param="cost_limit_eur")

        if gateway_key.token_limit_total is not None:
            projected_tokens = (
                gateway_key.tokens_used_total
                + gateway_key.tokens_reserved_total
                + reserved_tokens
            )
            if projected_tokens > gateway_key.token_limit_total:
                raise QuotaLimitExceededError("Token quota limit exceeded", param="token_limit_total")

        if gateway_key.request_limit_total is not None:
            projected_requests = (
                gateway_key.requests_used_total
                + gateway_key.requests_reserved_total
                + reserved_requests
            )
            if projected_requests > gateway_key.request_limit_total:
                raise QuotaLimitExceededError(
                    "Request quota limit exceeded",
                    param="request_limit_total",
                )


def _aware_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_cost(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidQuotaEstimateError("Estimated cost must use Decimal", param="estimated_cost_eur")
    if value < 0:
        raise InvalidQuotaEstimateError("Estimated cost must be non-negative", param="estimated_cost_eur")
    return value


def _validate_tokens(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidQuotaEstimateError("Estimated tokens must be an integer", param="estimated_tokens")
    if value < 0:
        raise InvalidQuotaEstimateError("Estimated tokens must be non-negative", param="estimated_tokens")
    return value


def _reservation_result(row: QuotaReservation) -> QuotaReservationResult:
    return QuotaReservationResult(
        reservation_id=row.id,
        gateway_key_id=row.gateway_key_id,
        request_id=row.request_id,
        reserved_cost_eur=row.reserved_cost_eur,
        reserved_tokens=row.reserved_tokens,
        status=row.status,
        expires_at=row.expires_at,
    )

