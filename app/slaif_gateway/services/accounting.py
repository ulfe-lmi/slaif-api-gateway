"""Service-layer usage extraction, quota finalization, and ledger creation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.accounting import (
    ActualCost,
    ActualUsage,
    FinalizationRecoveryResult,
    FinalizedAccountingResult,
    ProviderCompletedAccountingRecord,
    ProviderFailureAccountingResult,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.policy import ChatCompletionPolicyResult
from slaif_gateway.schemas.pricing import ChatCostEstimate
from slaif_gateway.schemas.providers import ProviderResponse
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.accounting_errors import (
    AccountingError,
    AccountingFinalizationRecoveryError,
    ActualCostExceededReservationError,
    FinalizationRecoveryNotSupportedError,
    InvalidUsageError,
    LedgerWriteError,
    ProviderCompletionRecordError,
    ReservationAlreadyFinalizedError,
    ReservationFinalizationError,
    UnsupportedProviderCostError,
    UsageMissingError,
)
from slaif_gateway.utils.redaction import redact_text
from slaif_gateway.utils.sanitization import sanitize_metadata_mapping

_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
_EUR = "EUR"
_PROVIDER_COMPLETED_PENDING = "provider_completed_finalization_pending"
_PROVIDER_COMPLETED_FAILED = "provider_completed_finalization_failed"
_ACCOUNTING_FINALIZATION_FAILED = "accounting_finalization_failed"


class AccountingService:
    """Finalize reserved quota and write usage ledger rows within caller transactions.

    The service does not commit and does not create database engines or sessions.
    Callers are expected to wrap finalization in their own transaction.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        gateway_keys_repository: GatewayKeysRepository | None = None,
        quota_reservations_repository: QuotaReservationsRepository | None = None,
        usage_ledger_repository: UsageLedgerRepository | None = None,
    ) -> None:
        if session is not None:
            gateway_keys_repository = gateway_keys_repository or GatewayKeysRepository(session)
            quota_reservations_repository = (
                quota_reservations_repository or QuotaReservationsRepository(session)
            )
            usage_ledger_repository = usage_ledger_repository or UsageLedgerRepository(session)

        if (
            gateway_keys_repository is None
            or quota_reservations_repository is None
            or usage_ledger_repository is None
        ):
            raise TypeError("AccountingService requires either a session or all repositories")

        self._gateway_keys_repository = gateway_keys_repository
        self._quota_reservations_repository = quota_reservations_repository
        self._usage_ledger_repository = usage_ledger_repository

    def extract_usage(self, provider_response: ProviderResponse) -> ActualUsage:
        """Extract and validate token usage from a provider response."""
        usage = provider_response.usage
        if usage is None:
            raise UsageMissingError()

        prompt_tokens = _optional_token_count(usage.prompt_tokens, "prompt_tokens")
        completion_tokens = _optional_token_count(
            usage.completion_tokens,
            "completion_tokens",
        )
        total_tokens = _optional_token_count(usage.total_tokens, "total_tokens")
        cached_tokens = _optional_token_count(usage.cached_tokens, "cached_tokens")
        reasoning_tokens = _optional_token_count(usage.reasoning_tokens, "reasoning_tokens")

        if total_tokens is None:
            if prompt_tokens is None or completion_tokens is None:
                raise UsageMissingError("Provider response did not include enough usage metadata")
            total_tokens = prompt_tokens + completion_tokens

        if prompt_tokens is None:
            prompt_tokens = 0
        if completion_tokens is None:
            completion_tokens = 0

        component_total = prompt_tokens + completion_tokens
        if component_total > total_tokens:
            raise InvalidUsageError(
                "Provider usage token components exceed total tokens",
                param="total_tokens",
            )

        return ActualUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            other_usage=_safe_json_mapping(usage.other_usage),
        )

    def compute_actual_cost(
        self,
        provider_response: ProviderResponse,
        route: RouteResolutionResult,
        usage: ActualUsage,
        pricing_estimate: ChatCostEstimate,
        at: datetime | None = None,
    ) -> ActualCost:
        """Compute actual cost from actual usage using prior pricing estimate details."""
        _ = route, at
        native_currency = _normalize_currency(pricing_estimate.native_currency)
        provider_reported_cost = _provider_reported_cost(provider_response)
        provider_reported_currency = _provider_reported_currency(provider_response)

        input_unit = _unit_cost(
            estimated_cost=pricing_estimate.estimated_input_cost_native,
            estimated_tokens=pricing_estimate.estimated_input_tokens,
            actual_tokens=usage.prompt_tokens,
            param="prompt_tokens",
        )
        output_unit = _unit_cost(
            estimated_cost=pricing_estimate.estimated_output_cost_native,
            estimated_tokens=pricing_estimate.estimated_output_tokens,
            actual_tokens=usage.completion_tokens,
            param="completion_tokens",
        )
        actual_native = (
            Decimal(usage.prompt_tokens) * input_unit
            + Decimal(usage.completion_tokens) * output_unit
        )

        actual_eur = _convert_estimate_native_to_eur(
            actual_native=actual_native,
            native_currency=native_currency,
            estimated_total_native=pricing_estimate.estimated_total_cost_native,
            estimated_total_eur=pricing_estimate.estimated_total_cost_eur,
        )

        return ActualCost(
            actual_cost_eur=actual_eur,
            actual_cost_native=actual_native,
            native_currency=native_currency,
            provider_reported_cost_native=provider_reported_cost,
            provider_reported_currency=provider_reported_currency,
        )

    async def finalize_successful_response(
        self,
        reservation_id: uuid.UUID,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        policy: ChatCompletionPolicyResult,
        pricing_estimate: ChatCostEstimate,
        provider_response: ProviderResponse,
        request_id: str,
        endpoint: str = "chat.completions",
        streaming: bool = False,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        provider_completed_usage_ledger_id: uuid.UUID | None = None,
    ) -> FinalizedAccountingResult:
        _ = policy
        finished = _aware_now(finished_at)
        reservation = await self._locked_pending_reservation(
            reservation_id,
            authenticated_key=authenticated_key,
        )
        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            authenticated_key.gateway_key_id
        )
        if gateway_key is None:
            raise ReservationFinalizationError("Gateway key was not found during finalization")

        usage = self.extract_usage(provider_response)
        actual_cost = self.compute_actual_cost(
            provider_response,
            route,
            usage,
            pricing_estimate,
            at=finished,
        )
        _validate_actual_within_reservation(
            actual_cost_eur=actual_cost.actual_cost_eur,
            actual_tokens=usage.total_tokens,
            reserved_cost_eur=reservation.reserved_cost_eur,
            reserved_tokens=reservation.reserved_tokens,
        )

        await self._gateway_keys_repository.finalize_reserved_counters(
            gateway_key,
            reserved_cost_eur=reservation.reserved_cost_eur,
            reserved_tokens_total=reservation.reserved_tokens,
            reserved_requests_total=reservation.reserved_requests,
            actual_cost_eur=actual_cost.actual_cost_eur,
            actual_tokens_total=usage.total_tokens,
            actual_requests_total=1,
            last_used_at=finished,
        )
        reservation = await self._quota_reservations_repository.mark_pending_reservation_finalized(
            reservation,
            finalized_at=finished,
        )

        started = _aware_now(started_at or getattr(reservation, "created_at", None))
        if provider_completed_usage_ledger_id is not None:
            ledger = await self._mark_provider_completed_ledger_finalized(
                usage_ledger_id=provider_completed_usage_ledger_id,
                provider_response=provider_response,
                actual_cost=actual_cost,
                finished_at=finished,
                latency_ms=_latency_ms(started, finished),
            )
        else:
            ledger = await self._create_success_ledger(
                request_id=request_id,
                reservation_id=reservation.id,
                authenticated_key=authenticated_key,
                route=route,
                provider_response=provider_response,
                endpoint=_normalize_endpoint(endpoint),
                usage=usage,
                pricing_estimate=pricing_estimate,
                actual_cost=actual_cost,
                streaming=streaming,
                started_at=started,
                finished_at=finished,
            )

        return FinalizedAccountingResult(
            usage_ledger_id=ledger.id,
            reservation_id=reservation.id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            actual_cost_eur=actual_cost.actual_cost_eur,
            actual_cost_native=actual_cost.actual_cost_native,
            native_currency=actual_cost.native_currency,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            accounting_status=ledger.accounting_status,
        )

    async def record_provider_completed_before_finalization(
        self,
        reservation_id: uuid.UUID,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        pricing_estimate: ChatCostEstimate,
        provider_response: ProviderResponse,
        request_id: str,
        endpoint: str = "chat.completions",
        streaming: bool = False,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> ProviderCompletedAccountingRecord:
        """Write durable provider-completed state before final counter mutation."""
        finished = _aware_now(finished_at)
        reservation = await self._quota_reservations_repository.get_reservation_by_id(
            reservation_id
        )
        if reservation is None:
            raise FinalizationRecoveryNotSupportedError("Quota reservation was not found")
        if reservation.gateway_key_id != authenticated_key.gateway_key_id:
            raise FinalizationRecoveryNotSupportedError(
                "Quota reservation does not belong to gateway key"
            )
        if reservation.status != "pending":
            raise FinalizationRecoveryNotSupportedError("Quota reservation is not pending")

        usage = self.extract_usage(provider_response)
        actual_cost = self.compute_actual_cost(
            provider_response,
            route,
            usage,
            pricing_estimate,
            at=finished,
        )

        existing = await self._usage_ledger_repository.get_usage_record_by_request_id(request_id)
        if existing is not None:
            return ProviderCompletedAccountingRecord(
                usage_ledger_id=existing.id,
                reservation_id=reservation.id,
                gateway_key_id=authenticated_key.gateway_key_id,
                request_id=request_id,
                provider=existing.provider,
                requested_model=existing.requested_model,
                resolved_model=existing.resolved_model,
                endpoint=existing.endpoint,
                upstream_request_id=existing.upstream_request_id,
                prompt_tokens=existing.prompt_tokens,
                completion_tokens=existing.completion_tokens,
                total_tokens=existing.total_tokens,
                estimated_cost_eur=existing.estimated_cost_eur or Decimal("0"),
                computed_actual_cost_eur=existing.actual_cost_eur,
                accounting_status=existing.accounting_status,
            )

        started = _aware_now(started_at or getattr(reservation, "created_at", None))
        try:
            ledger = await self._usage_ledger_repository.create_provider_completed_record(
                request_id=request_id,
                quota_reservation_id=reservation.id,
                gateway_key_id=authenticated_key.gateway_key_id,
                owner_id=authenticated_key.owner_id,
                cohort_id=authenticated_key.cohort_id,
                endpoint=_normalize_endpoint(endpoint),
                provider=route.provider,
                requested_model=route.requested_model,
                resolved_model=route.resolved_model,
                upstream_request_id=provider_response.upstream_request_id,
                streaming=streaming,
                http_status=provider_response.status_code,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cached_tokens=usage.cached_tokens or 0,
                reasoning_tokens=usage.reasoning_tokens or 0,
                total_tokens=usage.total_tokens,
                estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
                actual_cost_eur=actual_cost.actual_cost_eur,
                actual_cost_native=actual_cost.actual_cost_native,
                native_currency=actual_cost.native_currency,
                usage_raw=dict(usage.other_usage),
                response_metadata={
                    **_response_metadata(provider_response, actual_cost),
                    "recovery_state": _PROVIDER_COMPLETED_PENDING,
                    "needs_reconciliation": False,
                },
                started_at=started,
                finished_at=None,
                latency_ms=None,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderCompletionRecordError() from exc

        return ProviderCompletedAccountingRecord(
            usage_ledger_id=ledger.id,
            reservation_id=reservation.id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            endpoint=_normalize_endpoint(endpoint),
            upstream_request_id=provider_response.upstream_request_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
            computed_actual_cost_eur=actual_cost.actual_cost_eur,
            accounting_status=ledger.accounting_status,
        )

    async def mark_provider_completed_finalization_failed(
        self,
        usage_ledger_id: uuid.UUID,
        reservation_id: uuid.UUID,
        error: AccountingError | Exception,
        *,
        finished_at: datetime | None = None,
    ) -> FinalizationRecoveryResult:
        """Mark pre-finalization provider-completed state as needing repair."""
        finished = _aware_now(finished_at)
        row = await self._usage_ledger_repository.get_usage_record_by_id(usage_ledger_id)
        if row is None:
            raise AccountingFinalizationRecoveryError("Provider completion record was not found")
        if row.quota_reservation_id != reservation_id:
            raise AccountingFinalizationRecoveryError("Provider completion record mismatch")

        previous_status = row.accounting_status
        metadata = _safe_json_mapping(row.response_metadata or {})
        error_code = getattr(error, "error_code", _ACCOUNTING_FINALIZATION_FAILED)
        safe_message = getattr(
            error,
            "safe_message",
            "Provider completed but accounting finalization failed",
        )
        metadata.update(
            {
                "recovery_state": _PROVIDER_COMPLETED_FAILED,
                "needs_reconciliation": True,
                "finalization_error_code": _safe_short_string(error_code),
            }
        )
        try:
            row = await self._usage_ledger_repository.mark_provider_completed_record_finalization_failed(
                usage_ledger_id,
                error_type=_ACCOUNTING_FINALIZATION_FAILED,
                error_message=_safe_short_string(error_code) or _ACCOUNTING_FINALIZATION_FAILED,
                response_metadata=metadata,
                finished_at=finished,
                latency_ms=_latency_ms(_aware_now(row.started_at), finished),
            )
        except Exception as exc:  # noqa: BLE001
            raise AccountingFinalizationRecoveryError() from exc

        return FinalizationRecoveryResult(
            usage_ledger_id=row.id,
            reservation_id=reservation_id,
            previous_status=previous_status,
            new_status=row.accounting_status,
            needs_reconciliation=True,
            safe_message=_safe_short_string(safe_message)
            or "Provider completed but accounting finalization failed",
        )

    async def record_provider_failure_and_release(
        self,
        reservation_id: uuid.UUID,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        policy: ChatCompletionPolicyResult,
        pricing_estimate: ChatCostEstimate,
        request_id: str,
        error_type: str,
        error_code: str | None = None,
        status_code: int | None = None,
        streaming: bool = False,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> ProviderFailureAccountingResult:
        _ = policy
        finished = _aware_now(finished_at)
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            reservation_id
        )
        if reservation is None:
            raise ReservationFinalizationError("Quota reservation was not found")
        if reservation.gateway_key_id != authenticated_key.gateway_key_id:
            raise ReservationFinalizationError("Quota reservation does not belong to gateway key")

        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id_for_quota_update(
            authenticated_key.gateway_key_id
        )
        if gateway_key is None:
            raise ReservationFinalizationError("Gateway key was not found during release")

        released = False
        if reservation.status == "pending":
            await self._gateway_keys_repository.subtract_reserved_counters(
                gateway_key,
                cost_reserved_eur=reservation.reserved_cost_eur,
                tokens_reserved_total=reservation.reserved_tokens,
                requests_reserved_total=reservation.reserved_requests,
            )
            reservation = await self._quota_reservations_repository.mark_pending_reservation_released(
                reservation,
                released_at=finished,
            )
            released = True

        started = _aware_now(started_at or getattr(reservation, "created_at", None))
        ledger = await self._create_failure_ledger(
            request_id=request_id,
            reservation_id=reservation.id,
            authenticated_key=authenticated_key,
            route=route,
            endpoint=_normalize_endpoint("chat.completions"),
            pricing_estimate=pricing_estimate,
            error_type=error_type,
            error_code=error_code,
            status_code=status_code,
            streaming=streaming,
            started_at=started,
            finished_at=finished,
        )

        return ProviderFailureAccountingResult(
            usage_ledger_id=ledger.id if ledger is not None else None,
            reservation_id=reservation.id,
            gateway_key_id=authenticated_key.gateway_key_id,
            request_id=request_id,
            released=released,
            accounting_status=ledger.accounting_status if ledger is not None else reservation.status,
            error_type=error_type,
            error_code=error_code,
        )

    async def _locked_pending_reservation(
        self,
        reservation_id: uuid.UUID,
        *,
        authenticated_key: AuthenticatedGatewayKey,
    ):
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            reservation_id
        )
        if reservation is None:
            raise ReservationFinalizationError("Quota reservation was not found")
        if reservation.gateway_key_id != authenticated_key.gateway_key_id:
            raise ReservationFinalizationError("Quota reservation does not belong to gateway key")
        if reservation.status != "pending":
            raise ReservationAlreadyFinalizedError()
        return reservation

    async def _create_success_ledger(
        self,
        *,
        request_id: str,
        reservation_id: uuid.UUID,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        provider_response: ProviderResponse,
        endpoint: str,
        usage: ActualUsage,
        pricing_estimate: ChatCostEstimate,
        actual_cost: ActualCost,
        streaming: bool,
        started_at: datetime,
        finished_at: datetime,
    ):
        try:
            return await self._usage_ledger_repository.create_success_record(
                request_id=request_id,
                quota_reservation_id=reservation_id,
                gateway_key_id=authenticated_key.gateway_key_id,
                owner_id=authenticated_key.owner_id,
                cohort_id=authenticated_key.cohort_id,
                endpoint=endpoint,
                provider=route.provider,
                requested_model=route.requested_model,
                resolved_model=route.resolved_model,
                upstream_request_id=provider_response.upstream_request_id,
                streaming=streaming,
                http_status=provider_response.status_code,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cached_tokens=usage.cached_tokens or 0,
                reasoning_tokens=usage.reasoning_tokens or 0,
                total_tokens=usage.total_tokens,
                estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
                actual_cost_eur=actual_cost.actual_cost_eur,
                actual_cost_native=actual_cost.actual_cost_native,
                native_currency=actual_cost.native_currency,
                usage_raw=dict(usage.other_usage),
                response_metadata=_response_metadata(provider_response, actual_cost),
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=_latency_ms(started_at, finished_at),
            )
        except Exception as exc:  # noqa: BLE001
            raise LedgerWriteError() from exc

    async def _mark_provider_completed_ledger_finalized(
        self,
        *,
        usage_ledger_id: uuid.UUID,
        provider_response: ProviderResponse,
        actual_cost: ActualCost,
        finished_at: datetime,
        latency_ms: int | None,
    ):
        try:
            return await self._usage_ledger_repository.mark_provider_completed_record_finalized(
                usage_ledger_id,
                http_status=provider_response.status_code,
                response_metadata={
                    **_response_metadata(provider_response, actual_cost),
                    "recovery_state": "finalized",
                    "needs_reconciliation": False,
                },
                finished_at=finished_at,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            raise LedgerWriteError() from exc

    async def _create_failure_ledger(
        self,
        *,
        request_id: str,
        reservation_id: uuid.UUID,
        authenticated_key: AuthenticatedGatewayKey,
        route: RouteResolutionResult,
        endpoint: str,
        pricing_estimate: ChatCostEstimate,
        error_type: str,
        error_code: str | None,
        status_code: int | None,
        streaming: bool,
        started_at: datetime,
        finished_at: datetime,
    ):
        try:
            return await self._usage_ledger_repository.create_failure_record(
                request_id=request_id,
                quota_reservation_id=reservation_id,
                gateway_key_id=authenticated_key.gateway_key_id,
                owner_id=authenticated_key.owner_id,
                cohort_id=authenticated_key.cohort_id,
                endpoint=endpoint,
                provider=route.provider,
                requested_model=route.requested_model,
                resolved_model=route.resolved_model,
                streaming=streaming,
                http_status=status_code,
                error_type=_safe_short_string(error_type),
                error_message=_safe_short_string(error_code),
                estimated_cost_eur=pricing_estimate.estimated_total_cost_eur,
                actual_cost_eur=Decimal("0"),
                actual_cost_native=Decimal("0"),
                native_currency=_normalize_currency(pricing_estimate.native_currency),
                usage_raw={},
                response_metadata={},
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=_latency_ms(started_at, finished_at),
            )
        except Exception as exc:  # noqa: BLE001
            raise LedgerWriteError() from exc


def _optional_token_count(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidUsageError("Provider usage token counts must be integers", param=field_name)
    if value < 0:
        raise InvalidUsageError("Provider usage token counts must be non-negative", param=field_name)
    return value


def _provider_reported_cost(provider_response: ProviderResponse) -> Decimal | None:
    cost = provider_response.raw_cost_native
    if cost is None:
        return None
    if not isinstance(cost, Decimal) or cost < 0:
        raise UnsupportedProviderCostError("Provider-reported cost is invalid", param="raw_cost_native")
    return cost


def _provider_reported_currency(provider_response: ProviderResponse) -> str | None:
    if provider_response.native_currency is None:
        return None
    return _normalize_currency(provider_response.native_currency)


def _unit_cost(
    *,
    estimated_cost: Decimal,
    estimated_tokens: int,
    actual_tokens: int,
    param: str,
) -> Decimal:
    if not isinstance(estimated_cost, Decimal):
        raise UnsupportedProviderCostError("Estimated cost must use Decimal", param=param)
    if estimated_cost < 0:
        raise UnsupportedProviderCostError("Estimated cost must be non-negative", param=param)
    if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int):
        raise UnsupportedProviderCostError("Estimated token count must be an integer", param=param)
    if estimated_tokens < 0:
        raise UnsupportedProviderCostError("Estimated token count must be non-negative", param=param)
    if estimated_tokens == 0:
        if actual_tokens == 0:
            return Decimal("0")
        raise UnsupportedProviderCostError(
            "Actual cost cannot be computed from a zero-token estimate",
            param=param,
        )
    return estimated_cost / Decimal(estimated_tokens)


def _convert_estimate_native_to_eur(
    *,
    actual_native: Decimal,
    native_currency: str,
    estimated_total_native: Decimal,
    estimated_total_eur: Decimal,
) -> Decimal:
    if not isinstance(estimated_total_native, Decimal) or not isinstance(estimated_total_eur, Decimal):
        raise UnsupportedProviderCostError("Estimated total costs must use Decimal")
    if estimated_total_native < 0 or estimated_total_eur < 0:
        raise UnsupportedProviderCostError("Estimated total costs must be non-negative")
    if estimated_total_native == 0:
        if actual_native == 0:
            return Decimal("0")
        raise UnsupportedProviderCostError("Actual cost cannot be converted from a zero-cost estimate")
    if native_currency == _EUR and estimated_total_native == estimated_total_eur:
        return actual_native
    fx_ratio = estimated_total_eur / estimated_total_native
    return actual_native * fx_ratio


def _validate_actual_within_reservation(
    *,
    actual_cost_eur: Decimal,
    actual_tokens: int,
    reserved_cost_eur: Decimal,
    reserved_tokens: int,
) -> None:
    if actual_cost_eur > reserved_cost_eur:
        raise ActualCostExceededReservationError(param="actual_cost_eur")
    if actual_tokens > reserved_tokens:
        raise ActualCostExceededReservationError(param="total_tokens")


def _normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise UnsupportedProviderCostError("Currency is required", param="currency")
    return currency


def _normalize_endpoint(value: str) -> str:
    endpoint = value.strip()
    if endpoint == "chat.completions":
        return _CHAT_COMPLETIONS_ENDPOINT
    return endpoint


def _aware_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _latency_ms(started_at: datetime, finished_at: datetime) -> int | None:
    delta_ms = int((finished_at - started_at).total_seconds() * 1000)
    return max(0, delta_ms)


def _response_metadata(provider_response: ProviderResponse, actual_cost: ActualCost) -> dict[str, object]:
    metadata: dict[str, object] = {
        "provider": provider_response.provider,
        "upstream_model": provider_response.upstream_model,
        "status_code": provider_response.status_code,
    }
    if actual_cost.provider_reported_cost_native is not None:
        metadata["provider_reported_cost_native"] = str(actual_cost.provider_reported_cost_native)
    if actual_cost.provider_reported_currency is not None:
        metadata["provider_reported_currency"] = actual_cost.provider_reported_currency
    return _safe_json_mapping(metadata)


def _safe_short_string(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_text(value.strip())[:128]


def _safe_json_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    return sanitize_metadata_mapping(value, drop_content_keys=True)
