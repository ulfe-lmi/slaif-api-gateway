"""PostgreSQL-authoritative exclusive per-key external-tool fence foundation.

This service coordinates and reserves durable exposure for the future
provider-hosted external-tool fenced quota mode. It is *flush-only*: callers
own commit/rollback. No prompt, body, tool argument/result, raw MCP value/URL,
authorization material, or provider response content is ever stored. No Redis or
in-memory lock is used as authority; the locked ``gateway_keys`` row is the
single concurrency truth. Acquisition fails closed when committed ordinary exposure (a pending reservation or any non-zero reserved counter) already occupies the key. Objective 014 writes only the ``none`` and ``active``
fence states; the reserved ``held`` transition and provider-hosted execution are
owned by later objectives and are not enabled here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID


from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.external_tool_fence import (
    ExternalToolFenceAcquireInput,
    ExternalToolFenceProjection,
    ExternalToolFenceResolveInput,
    ExternalToolFenceResolveResult,
    ExternalToolFenceResult,
)
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    EXTERNAL_TOOL_FENCED,
    KNOWN_EXTERNAL_CAPABILITIES,
    ExternalToolAdmissionDecision,
    parse_key_external_tool_policy,
)

_MAX_REQUEST_ID_LENGTH = 255
_MAX_ENDPOINT_LENGTH = 255
_MAX_MODEL_LENGTH = 255
_MAX_PROVIDER_LENGTH = 255

# The exact reason code the objective-012 admission reducer emits for the
# positive fenced decision; any other reason is a different (non-acquirable)
# contract outcome.
_FENCED_ALLOWED_REASON_CODE = "external_tool_fenced_allowed"

FENCE_NONE = "none"
FENCE_ACTIVE = "active"
FENCE_HELD = "held"
_BOUND_FENCE_STATES = ("active", "held")

_DESTINATION_ID_PATTERN = re.compile(
    r"^(?P<kind>connector|remote_mcp):(?P<opaque>[a-z0-9][a-z0-9_-]{0,47})$"
)


class ExternalToolFenceError(Exception):
    """Base safe domain error for external-tool fence operations."""

    status_code = 500
    error_type = "server_error"
    error_code = "external_tool_fence_error"
    message = "External tool fence operation failed"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.safe_message = message or self.message
        self.error_code = code or self.error_code
        super().__init__(self.safe_message)


class InvalidExternalToolFenceInputError(ExternalToolFenceError):
    """Raised when acquisition/resolution input is structurally invalid."""

    status_code = 400
    error_type = "invalid_request_error"
    error_code = "invalid_external_tool_fence_input"
    message = "Invalid external tool fence input"


class ExternalToolFenceActiveError(ExternalToolFenceError):
    """Raised when a different unresolved fence blocks a new acquisition."""

    status_code = 409
    error_type = "rate_limit_error"
    error_code = "external_tool_fence_active"
    message = "A durable external-tool request is pending for this key"


class ExternalToolFenceConflictError(ExternalToolFenceError):
    """Raised when a retried request ID no longer matches its fence facts."""

    status_code = 409
    error_type = "conflict_error"
    error_code = "external_tool_fence_conflict"
    message = "External tool fence state conflicts with the requested facts"


class ExternalToolFenceOccupiedError(ExternalToolFenceError):
    """Raised when committed ordinary exposure already occupies the key's quota."""

    status_code = 409
    error_type = "conflict_error"
    error_code = "external_tool_fence_occupied"
    message = "Existing reserved quota on this key blocks a new external tool fence"


class ExternalToolFenceExhaustedError(ExternalToolFenceError):
    """Raised when no positive remaining balance is available to fence."""

    status_code = 429
    error_type = "rate_limit_error"
    error_code = "external_tool_fence_exhausted"
    message = "No remaining quota balance is available for an external tool fence"


class ExternalToolFenceInvariantError(ExternalToolFenceError):
    """Raised when durable fence/reservation/ledger evidence is inconsistent."""

    status_code = 500
    error_type = "server_error"
    error_code = "external_tool_fence_invariant_error"
    message = "External tool fence invariant violation"


class ExternalToolFenceService:
    """Exclusive per-key external-tool fence acquisition, blocking, and resolution.

    The service only flushes; the caller owns the surrounding transaction.
    """

    def __init__(
        self,
        *,
        gateway_keys_repository: GatewayKeysRepository,
        quota_reservations_repository: QuotaReservationsRepository,
        usage_ledger_repository: UsageLedgerRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._gateway_keys_repository = gateway_keys_repository
        self._quota_reservations_repository = quota_reservations_repository
        self._usage_ledger_repository = usage_ledger_repository
        self._audit_repository = audit_repository

    # -- acquisition ---------------------------------------------------------

    async def acquire(
        self,
        acquire_input: ExternalToolFenceAcquireInput,
    ) -> ExternalToolFenceResult:
        now = _aware_now(acquire_input.now)
        ttl = _validate_ttl(acquire_input.ttl)
        expires_at = now + ttl

        request_id = _validate_request_id(acquire_input.request_id)
        endpoint = _validate_endpoint(acquire_input.route.endpoint)
        requested_model = _validate_requested_model(acquire_input.route.requested_model)
        provider = _validate_provider(acquire_input.route.provider)
        route_id = _validate_route_id(acquire_input.route.route_id)
        capabilities = self._validate_capabilities(acquire_input.capabilities)
        destination_ids = self._validate_destination_ids(
            acquire_input.destination_ids, capabilities
        )
        decision = self._validate_decision(acquire_input.decision)

        gateway_key = await self._gateway_keys_repository.get_gateway_key_for_update(
            acquire_input.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolFenceInvariantError(
                "Gateway key could not be locked for fence acquisition",
                code="external_tool_fence_key_missing",
            )

        self._validate_key_for_fence(gateway_key, now=now)
        self._validate_stored_fenced_policy(gateway_key, capabilities, destination_ids, decision)

        if gateway_key.external_tool_fence_state in _BOUND_FENCE_STATES:
            if (
                gateway_key.external_tool_fence_state == FENCE_ACTIVE
                and gateway_key.external_tool_fence_request_id == request_id
                and gateway_key.external_tool_fence_reservation_id is not None
            ):
                reservation = (
                    await self._quota_reservations_repository.get_reservation_by_id(
                        gateway_key.external_tool_fence_reservation_id
                    )
                )
                if reservation is None:
                    raise ExternalToolFenceInvariantError(
                        "Fence references a missing reservation",
                        code="external_tool_fence_reservation_missing",
                    )
                if reservation.gateway_key_id != gateway_key.id:
                    raise ExternalToolFenceInvariantError(
                        "Fence reservation does not belong to the fenced key",
                        code="external_tool_fence_reservation_key_mismatch",
                    )
                if reservation.status != "pending":
                    raise ExternalToolFenceInvariantError(
                        "Active fence retry requires a pending reservation",
                        code="external_tool_fence_reservation_not_pending",
                    )
                if reservation.quota_mode != EXTERNAL_TOOL_FENCED:
                    raise ExternalToolFenceInvariantError(
                        "Active fence retry requires a fenced reservation",
                        code="external_tool_fence_reservation_not_fenced",
                    )
                if self._reservation_matches(
                    reservation,
                    gateway_key_id=gateway_key.id,
                    request_id=request_id,
                    endpoint=endpoint,
                    requested_model=requested_model,
                    provider=provider,
                    route_id=route_id,
                    capabilities=capabilities,
                    destination_ids=destination_ids,
                ):
                    return self._projection_result(gateway_key, reservation, idempotent=True)
                raise ExternalToolFenceConflictError()
            raise ExternalToolFenceActiveError()

        await self._reject_existing_key_exposure(gateway_key)

        existing = await self._quota_reservations_repository.get_reservation_by_request_id(
            request_id
        )
        if existing is not None:
            raise ExternalToolFenceConflictError(
                "This request ID is already bound to a quota reservation",
                code="external_tool_fence_request_id_reused",
            )

        remaining_cost = (
            gateway_key.cost_limit_eur - gateway_key.cost_used_eur - gateway_key.cost_reserved_eur
        )
        remaining_tokens = (
            gateway_key.token_limit_total
            - gateway_key.tokens_used_total
            - gateway_key.tokens_reserved_total
        )
        remaining_requests = (
            gateway_key.request_limit_total
            - gateway_key.requests_used_total
            - gateway_key.requests_reserved_total
        )
        if remaining_requests < 1 or remaining_tokens <= 0 or remaining_cost <= 0:
            raise ExternalToolFenceExhaustedError()

        reservation = await self._quota_reservations_repository.create_reservation(
            gateway_key_id=acquire_input.gateway_key_id,
            request_id=request_id,
            endpoint=endpoint,
            requested_model=requested_model,
            reserved_cost_eur=remaining_cost,
            reserved_tokens=remaining_tokens,
            reserved_requests=1,
            status="pending",
            expires_at=expires_at,
            quota_mode=EXTERNAL_TOOL_FENCED,
            external_tool_capabilities=list(capabilities),
            external_tool_destination_ids=list(destination_ids),
            external_tool_provider=provider,
            external_tool_route_id=route_id,
        )
        await self._gateway_keys_repository.add_reserved_counters(
            gateway_key,
            cost_reserved_eur=remaining_cost,
            tokens_reserved_total=remaining_tokens,
            requests_reserved_total=1,
        )
        await self._gateway_keys_repository.set_external_tool_fence(
            gateway_key,
            state=FENCE_ACTIVE,
            reservation_id=reservation.id,
            request_id=request_id,
            acquired_at=now,
            expires_at=expires_at,
        )
        await self._audit_repository.add_audit_log(
            action="external_tool_fence_acquired",
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            request_id=request_id,
            note="external tool fence acquired",
        )
        return self._projection_result(gateway_key, reservation, idempotent=False)

    # -- resolution ----------------------------------------------------------

    async def resolve(
        self,
        resolve_input: ExternalToolFenceResolveInput,
    ) -> ExternalToolFenceResolveResult:
        gateway_key = await self._gateway_keys_repository.get_gateway_key_by_id(
            resolve_input.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolFenceInvariantError(
                "Gateway key could not be locked for fence resolution",
                code="external_tool_fence_key_missing",
            )

        state = gateway_key.external_tool_fence_state
        if state == FENCE_NONE:
            return ExternalToolFenceResolveResult(
                gateway_key_id=resolve_input.gateway_key_id,
                fence_state=FENCE_NONE,
                resolved=False,
            )
        if state == FENCE_HELD:
            # ``held`` transitions are owned by a later objective; resolution
            # here is a no-op and the fence keeps blocking.
            return ExternalToolFenceResolveResult(
                gateway_key_id=resolve_input.gateway_key_id,
                fence_state=state,
                resolved=False,
            )

        if (
            gateway_key.external_tool_fence_request_id != resolve_input.request_id
            or gateway_key.external_tool_fence_reservation_id is None
        ):
            raise ExternalToolFenceConflictError(
                code="external_tool_fence_resolution_request_mismatch",
            )

        reservation_id = gateway_key.external_tool_fence_reservation_id
        reservation = await self._quota_reservations_repository.get_reservation_by_id_for_update(
            reservation_id
        )
        if reservation is None:
            raise ExternalToolFenceInvariantError(
                "Fence references a missing reservation",
                code="external_tool_fence_reservation_missing",
            )
        gateway_key = await self._gateway_keys_repository.get_gateway_key_for_update(
            resolve_input.gateway_key_id
        )
        if gateway_key is None:
            raise ExternalToolFenceInvariantError(
                "Gateway key could not be locked for fence resolution",
                code="external_tool_fence_key_missing",
            )
        if (
            gateway_key.external_tool_fence_state != FENCE_ACTIVE
            or gateway_key.external_tool_fence_reservation_id != reservation_id
            or gateway_key.external_tool_fence_request_id != resolve_input.request_id
        ):
            if gateway_key.external_tool_fence_state == FENCE_NONE:
                return ExternalToolFenceResolveResult(
                    gateway_key_id=resolve_input.gateway_key_id,
                    fence_state=FENCE_NONE,
                    resolved=False,
                )
            if gateway_key.external_tool_fence_state == FENCE_HELD:
                return ExternalToolFenceResolveResult(
                    gateway_key_id=resolve_input.gateway_key_id,
                    fence_state=FENCE_HELD,
                    resolved=False,
                )
            raise ExternalToolFenceConflictError(
                code="external_tool_fence_resolution_state_changed",
            )
        if reservation.gateway_key_id != gateway_key.id:
            raise ExternalToolFenceInvariantError(
                "Fence reservation does not belong to the locked key",
                code="external_tool_fence_reservation_key_mismatch",
            )
        if reservation.request_id != resolve_input.request_id:
            raise ExternalToolFenceInvariantError(
                "Fence reservation request ID does not match the fence",
                code="external_tool_fence_reservation_request_mismatch",
            )
        if reservation.quota_mode != EXTERNAL_TOOL_FENCED:
            raise ExternalToolFenceInvariantError(
                "Fence reservation is not in the external tool fenced mode",
                code="external_tool_fence_reservation_not_fenced",
            )
        self._validate_bound_route_facts(reservation)
        if reservation.status not in ("finalized", "released"):
            raise ExternalToolFenceInvariantError(
                "Cannot resolve a fence whose reservation is not terminal",
                code="external_tool_fence_reservation_not_terminal",
            )

        ledgers = await self._usage_ledger_repository.get_usage_records_by_reservation_id(
            reservation.id
        )
        if len(ledgers) != 1:
            raise ExternalToolFenceInvariantError(
                "Fence resolution requires exactly one linked usage ledger",
                code="external_tool_fence_ledger_count",
            )
        ledger = ledgers[0]
        if ledger.gateway_key_id != gateway_key.id:
            raise ExternalToolFenceInvariantError(
                "Linked usage ledger does not belong to the locked key",
                code="external_tool_fence_ledger_key_mismatch",
            )
        if (
            ledger.endpoint != reservation.endpoint
            or ledger.provider != reservation.external_tool_provider
            or ledger.requested_model != reservation.requested_model
            or ledger.request_id != reservation.request_id
        ):
            raise ExternalToolFenceInvariantError(
                "Usage ledger endpoint, provider, or model facts disagree with the reservation",
                code="external_tool_fence_ledger_facts_mismatch",
            )
        if reservation.status == "finalized":
            if ledger.accounting_status != "finalized" or ledger.success is not True:
                raise ExternalToolFenceInvariantError(
                    "Finalized reservation requires a finalized success usage ledger",
                    code="external_tool_fence_ledger_mismatch",
                )
        else:  # released
            if ledger.accounting_status != "failed" or ledger.success is not False:
                raise ExternalToolFenceInvariantError(
                    "Released reservation requires a failed usage ledger",
                    code="external_tool_fence_ledger_mismatch",
                )

        self._verify_reserved_counters_zero(gateway_key)

        await self._gateway_keys_repository.set_external_tool_fence(
            gateway_key,
            state=FENCE_NONE,
            reservation_id=None,
            request_id=None,
            acquired_at=None,
            expires_at=None,
        )
        await self._audit_repository.add_audit_log(
            action="external_tool_fence_resolved",
            entity_type="gateway_key",
            entity_id=gateway_key.id,
            request_id=resolve_input.request_id,
            note="external tool fence resolved from authoritative terminal evidence",
        )
        return ExternalToolFenceResolveResult(
            gateway_key_id=resolve_input.gateway_key_id,
            fence_state=FENCE_NONE,
            resolved=True,
        )

    # -- read-only inspection ------------------------------------------------

    async def list_unresolved_fences(
        self, *, limit: int = 100
    ) -> list[ExternalToolFenceProjection]:
        rows = await self._gateway_keys_repository.list_external_tool_fences(limit=limit)
        return [self._project_key(row) for row in rows]

    def _project_key(self, gateway_key: GatewayKey) -> ExternalToolFenceProjection:
        return ExternalToolFenceProjection(
            gateway_key_id=gateway_key.id,
            fence_state=gateway_key.external_tool_fence_state,
            reservation_id=gateway_key.external_tool_fence_reservation_id,
            request_id=gateway_key.external_tool_fence_request_id,
            acquired_at=gateway_key.external_tool_fence_acquired_at,
            expires_at=gateway_key.external_tool_fence_expires_at,
        )

    def _projection_result(
        self,
        gateway_key: GatewayKey,
        reservation,
        *,
        idempotent: bool,
    ) -> ExternalToolFenceResult:
        return ExternalToolFenceResult(
            gateway_key_id=gateway_key.id,
            request_id=gateway_key.external_tool_fence_request_id or reservation.request_id,
            reservation_id=reservation.id,
            fence_state=gateway_key.external_tool_fence_state,
            reserved_cost_eur=reservation.reserved_cost_eur,
            reserved_tokens=reservation.reserved_tokens,
            reserved_requests=reservation.reserved_requests,
            acquired_at=gateway_key.external_tool_fence_acquired_at,
            expires_at=gateway_key.external_tool_fence_expires_at,
            capabilities=tuple(reservation.external_tool_capabilities),
            destination_ids=tuple(reservation.external_tool_destination_ids),
            idempotent=idempotent,
        )

    # -- validation helpers --------------------------------------------------

    async def _reject_existing_key_exposure(self, gateway_key: GatewayKey) -> None:
        """Fail closed if committed exposure already occupies the key.

        Under the already-held key row lock, any pending reservation for the
        key (ordinary, or stale fence-derived) or any non-zero reserved
        counter means the key is not fully reconciled; a new exclusive fence
        must never coexist with it. Stale or drifted state stays blocked for
        operator reconciliation and is never guessed away.
        """
        pending = await self._quota_reservations_repository.list_reservations_for_key(
            gateway_key.id, status="pending"
        )
        if pending:
            raise ExternalToolFenceOccupiedError(
                "This key has a pending quota reservation that blocks a new fence",
                code="external_tool_fence_pending_reservation",
            )
        if (
            gateway_key.cost_reserved_eur != 0
            or gateway_key.tokens_reserved_total != 0
            or gateway_key.requests_reserved_total != 0
        ):
            raise ExternalToolFenceOccupiedError(
                "This key has unreconciled reserved counters that block a new fence",
                code="external_tool_fence_counters_nonzero",
            )

    @staticmethod
    def _validate_decision(decision: object) -> ExternalToolAdmissionDecision:
        """Require the exact objective-012 positive fenced decision contract."""
        if not isinstance(decision, ExternalToolAdmissionDecision):
            raise InvalidExternalToolFenceInputError(
                "The exact objective-012 external tool admission decision type is required",
                code="external_tool_fence_decision_type",
            )
        if decision.allowed is not True:
            raise InvalidExternalToolFenceInputError(
                "External tool admission decision is not allowed",
                code="external_tool_fence_decision_denied",
            )
        if decision.quota_mode != EXTERNAL_TOOL_FENCED:
            raise InvalidExternalToolFenceInputError(
                "External tool admission decision is not fenced",
                code="external_tool_fence_decision_not_fenced",
            )
        if (
            type(decision.effective_tool_call_cap) is not int
            or decision.effective_tool_call_cap <= 0
        ):
            raise InvalidExternalToolFenceInputError(
                "A fenced decision requires a positive effective tool call cap",
                code="external_tool_fence_decision_call_cap",
            )
        if decision.reason_code != _FENCED_ALLOWED_REASON_CODE:
            raise InvalidExternalToolFenceInputError(
                "A fenced decision must carry the canonical allowed reason",
                code="external_tool_fence_decision_reason",
            )
        for field in (
            "exclusive_key_fence_required",
            "single_request_overrun_accepted",
            "hold_on_missing_or_ambiguous_final_cost",
            "following_requests_block_after_exhaustion",
        ):
            if decision.__getattribute__(field) is not True:
                raise InvalidExternalToolFenceInputError(
                    "A fenced decision requires all exclusive obligations to be true",
                    code="external_tool_fence_decision_obligations",
                )
        return decision

    def _validate_key_for_fence(self, gateway_key: GatewayKey, *, now: datetime) -> None:
        if gateway_key.status != "active":
            raise InvalidExternalToolFenceInputError(
                "Only an active gateway key can acquire a fence",
                code="external_tool_fence_key_not_active",
            )
        if getattr(gateway_key, "key_purpose", "standard") != "standard":
            raise InvalidExternalToolFenceInputError(
                "Only a standard gateway key can acquire a fence",
                code="external_tool_fence_key_not_standard",
            )
        if gateway_key.valid_from.tzinfo is None or gateway_key.valid_until.tzinfo is None:
            raise InvalidExternalToolFenceInputError(
                "Gateway key validity timestamps are invalid",
                code="external_tool_fence_invalid_window",
            )
        if now < gateway_key.valid_from or now >= gateway_key.valid_until:
            raise InvalidExternalToolFenceInputError(
                "Gateway key is outside its validity window",
                code="external_tool_fence_invalid_window",
            )
        self._require_positive_finite_limits(gateway_key)

    def _require_positive_finite_limits(self, gateway_key: GatewayKey) -> None:
        cost_limit = gateway_key.cost_limit_eur
        token_limit = gateway_key.token_limit_total
        request_limit = gateway_key.request_limit_total
        if cost_limit is None or _is_finite_positive(cost_limit) is not True:
            raise InvalidExternalToolFenceInputError(
                "Fenced keys require a positive finite cost limit",
                code="external_tool_fence_cost_limit",
            )
        if token_limit is None or token_limit <= 0:
            raise InvalidExternalToolFenceInputError(
                "Fenced keys require a positive token limit",
                code="external_tool_fence_token_limit",
            )
        if request_limit is None or request_limit <= 0:
            raise InvalidExternalToolFenceInputError(
                "Fenced keys require a positive request limit",
                code="external_tool_fence_request_limit",
            )

    @staticmethod
    def _validate_stored_fenced_policy(
        gateway_key: GatewayKey,
        capabilities: tuple[str, ...],
        destination_ids: tuple[str, ...],
        decision: ExternalToolAdmissionDecision,
    ) -> None:
        """Parse the stored key policy through the exact 012 contract.

        Missing, malformed, noncanonical, wrong-version, duplicate,
        over-ceiling, non-acknowledged, or non-fenced stored policy all fail
        closed here; the parser itself rejects anything that is not the exact
        v1 shape.
        """
        stored = (gateway_key.metadata_json or {}).get("external_tool_policy")
        parsed = parse_key_external_tool_policy(
            stored, ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
        )
        if parsed.valid is not True or parsed.policy is None:
            raise InvalidExternalToolFenceInputError(
                "Stored external tool policy is missing or malformed",
                code="external_tool_fence_policy_invalid",
            )
        policy = parsed.policy
        if policy.mode != EXTERNAL_TOOL_FENCED:
            raise InvalidExternalToolFenceInputError(
                "Gateway key stored policy is not fenced",
                code="external_tool_fence_policy_not_fenced",
            )
        if not set(capabilities) <= set(policy.allowed_capabilities):
            raise InvalidExternalToolFenceInputError(
                "Requested capabilities are not permitted by the stored policy",
                code="external_tool_fence_capability_not_permitted",
            )
        if not set(destination_ids) <= set(policy.allowed_destination_ids):
            raise InvalidExternalToolFenceInputError(
                "Requested destinations are not permitted by the stored policy",
                code="external_tool_fence_destination_not_permitted",
            )
        if decision.effective_tool_call_cap > policy.max_provider_tool_calls_per_request:
            raise InvalidExternalToolFenceInputError(
                "Decision call cap exceeds the stored policy ceiling",
                code="external_tool_fence_decision_call_cap_over_ceiling",
            )

    @staticmethod
    def _validate_capabilities(capabilities: object) -> tuple[str, ...]:
        if not isinstance(capabilities, (list, tuple)) or len(capabilities) == 0:
            raise InvalidExternalToolFenceInputError(
                "A fenced acquisition requires at least one canonical capability",
                code="external_tool_fence_capabilities_empty",
            )
        values = [c for c in capabilities]
        if any(not isinstance(c, str) or c not in KNOWN_EXTERNAL_CAPABILITIES for c in values):
            raise InvalidExternalToolFenceInputError(
                "Capabilities must be known canonical external tool capability IDs",
                code="external_tool_fence_capability_unknown",
            )
        if len(set(values)) != len(values):
            raise InvalidExternalToolFenceInputError(
                "Capabilities must be unique",
                code="external_tool_fence_capability_duplicate",
            )
        if len(values) > DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS.max_distinct_capabilities:
            raise InvalidExternalToolFenceInputError(
                "Capabilities exceed the operator ceiling",
                code="external_tool_fence_capabilities_over_ceiling",
            )
        return tuple(sorted(set(values)))

    @staticmethod
    def _validate_destination_ids(
        destination_ids: object, capabilities: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not isinstance(destination_ids, (list, tuple)):
            raise InvalidExternalToolFenceInputError(
                "Destination IDs must be a list",
                code="external_tool_fence_destination_type",
            )
        values = [d for d in destination_ids]
        normalized = []
        for value in values:
            if not isinstance(value, str) or _DESTINATION_ID_PATTERN.fullmatch(value) is None:
                raise InvalidExternalToolFenceInputError(
                    "Destination IDs must be normalized opaque identifiers",
                    code="external_tool_fence_destination_malformed",
                )
            normalized.append(value)
        if len(set(normalized)) != len(normalized):
            raise InvalidExternalToolFenceInputError(
                "Destination IDs must be unique",
                code="external_tool_fence_destination_duplicate",
            )
        if len(normalized) > DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS.max_approved_destinations:
            raise InvalidExternalToolFenceInputError(
                "Destination IDs exceed the operator ceiling",
                code="external_tool_fence_destinations_over_ceiling",
            )
        for value in normalized:
            kind = _DESTINATION_ID_PATTERN.fullmatch(value).group("kind")
            required = "provider_connector" if kind == "connector" else "provider_remote_mcp"
            if required not in capabilities:
                raise InvalidExternalToolFenceInputError(
                    "A destination requires its matching capability to be present",
                    code="external_tool_fence_destination_capability_mismatch",
                )
        return tuple(sorted(set(normalized)))

    def _reservation_matches(
        self,
        reservation,
        *,
        gateway_key_id: UUID,
        request_id: str,
        endpoint: str,
        requested_model: str,
        provider: str,
        route_id: UUID,
        capabilities: tuple[str, ...],
        destination_ids: tuple[str, ...],
    ) -> bool:
        """Exact retry identity: every durable request/policy/fence fact must agree."""
        return (
            reservation.gateway_key_id == gateway_key_id
            and reservation.request_id == request_id
            and reservation.endpoint == endpoint
            and reservation.requested_model == requested_model
            and reservation.external_tool_provider == provider
            and reservation.external_tool_route_id == route_id
            and tuple(reservation.external_tool_capabilities) == capabilities
            and tuple(reservation.external_tool_destination_ids) == destination_ids
            and reservation.quota_mode == EXTERNAL_TOOL_FENCED
        )

    @staticmethod
    def _validate_bound_route_facts(reservation) -> None:
        """The terminal reservation must still carry valid bound route facts."""
        try:
            _validate_provider(reservation.external_tool_provider)
            _validate_requested_model(reservation.requested_model)
        except InvalidExternalToolFenceInputError:
            raise ExternalToolFenceInvariantError(
                "Fence reservation bound provider or model facts are invalid",
                code="external_tool_fence_reservation_route_facts_invalid",
            ) from None
        if reservation.external_tool_route_id is None:
            raise ExternalToolFenceInvariantError(
                "Fence reservation is missing its bound route identifier",
                code="external_tool_fence_reservation_route_facts_invalid",
            )

    @staticmethod
    def _verify_reserved_counters_zero(gateway_key: GatewayKey) -> None:
        """Every key reserved counter must be exactly zero before the fence clears."""
        if (
            gateway_key.cost_reserved_eur != 0
            or gateway_key.tokens_reserved_total != 0
            or gateway_key.requests_reserved_total != 0
        ):
            raise ExternalToolFenceInvariantError(
                "Key reserved counters are not exactly zero; the fence must stay",
                code="external_tool_fence_counters_inconsistent",
            )


def _aware_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_ttl(value: timedelta) -> timedelta:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise InvalidExternalToolFenceInputError(
            "Fence TTL must be a positive duration",
            code="external_tool_fence_ttl_invalid",
        )
    return value


def _validate_request_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExternalToolFenceInputError(
            "A bounded non-empty request ID is required",
            code="external_tool_fence_request_id_invalid",
        )
    if len(value) > _MAX_REQUEST_ID_LENGTH or any(ord(ch) < 0x20 for ch in value):
        raise InvalidExternalToolFenceInputError(
            "Request ID exceeds the safe length or contains control characters",
            code="external_tool_fence_request_id_invalid",
        )
    return value


def _validate_requested_model(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExternalToolFenceInputError(
            "A requested model is required for fence acquisition",
            code="external_tool_fence_model_invalid",
        )
    if len(value) > _MAX_MODEL_LENGTH or any(ord(ch) < 0x20 for ch in value):
        raise InvalidExternalToolFenceInputError(
            "Requested model exceeds the safe length or contains control characters",
            code="external_tool_fence_model_invalid",
        )
    return value


def _validate_provider(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExternalToolFenceInputError(
            "A provider is required for fence acquisition",
            code="external_tool_fence_provider_invalid",
        )
    if len(value) > _MAX_PROVIDER_LENGTH or any(ord(ch) < 0x20 for ch in value):
        raise InvalidExternalToolFenceInputError(
            "Provider exceeds the safe length or contains control characters",
            code="external_tool_fence_provider_invalid",
        )
    return value


def _validate_route_id(value: object) -> UUID:
    if type(value) is not UUID:
        raise InvalidExternalToolFenceInputError(
            "A route UUID is required for fence acquisition",
            code="external_tool_fence_route_id_invalid",
        )
    return value


def _validate_endpoint(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExternalToolFenceInputError(
            "A safe endpoint is required",
            code="external_tool_fence_endpoint_invalid",
        )
    if len(value) > _MAX_ENDPOINT_LENGTH or any(ord(ch) < 0x20 for ch in value):
        raise InvalidExternalToolFenceInputError(
            "Endpoint exceeds the safe length or contains control characters",
            code="external_tool_fence_endpoint_invalid",
        )
    return value


def _is_finite_positive(value: object) -> bool:
    if not isinstance(value, Decimal):
        return False
    if not value.is_finite():
        return False
    return value > 0
