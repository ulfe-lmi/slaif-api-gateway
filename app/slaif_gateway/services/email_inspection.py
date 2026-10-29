"""Shared read-only service for email delivery inspection.

`email list` / `email show` resolve exact persisted metadata with
allowlisted fields only. Inspection is strictly READ ONLY: no
decrypt/render/consume, no audit insertion, no mutation, no enqueue, no
SMTP, and no network. Secret lifecycle/sendability reuses the existing
`EmailDeliveryService.get_key_email_delivery_sendability` (bound method
injected here) so there is no second divergent eligibility validator.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from slaif_gateway.schemas.email_inspection import (
    KNOWN_EMAIL_ERROR_CODES,
    EmailDeliveryDetail,
    EmailDeliveryLastRecordedFailure,
    EmailDeliveryListItem,
    EmailDeliveryListPage,
    EmailDeliverySecretLifecycle,
    LIST_LIMIT_DEFAULT,
    validate_creation_window,
    validate_delivery_status,
    validate_page,
)
from slaif_gateway.services.email_delivery_service import KeyEmailDeliverySendability
from slaif_gateway.utils.redaction import redact_text

SendabilityProvider = Callable[[uuid.UUID], Awaitable[KeyEmailDeliverySendability]]


class EmailInspectionService:
    """Bounded read-only queries over email deliveries and safe audit facts."""

    def __init__(
        self,
        *,
        email_deliveries_repository: object,
        audit_repository: object,
        sendability_provider: SendabilityProvider,
    ) -> None:
        self._email_deliveries_repository = email_deliveries_repository
        self._audit_repository = audit_repository
        self._sendability_provider = sendability_provider

    async def list_deliveries(
        self,
        *,
        delivery_id: uuid.UUID | None = None,
        gateway_key_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        owner_email_normalized: str | None = None,
        status: str | None = None,
        created_from: datetime | None = None,
        created_until: datetime | None = None,
        limit: int = LIST_LIMIT_DEFAULT,
        offset: int = 0,
    ) -> EmailDeliveryListPage:
        """AND-combined exact filters applied in SQL BEFORE deterministic paging.

        The repository fetches at most `limit + 1` rows ordered by
        `(created_at DESC, id DESC)`; `has_more`/`next_offset` are derived
        from that bounded fetch. No in-memory filtering after pagination,
        no unbounded all-history materialization.
        """
        if status is not None:
            validate_delivery_status(status)
        created_from, created_until = validate_creation_window(created_from, created_until)
        limit, offset = validate_page(limit, offset)

        rows = await self._email_deliveries_repository.list_email_deliveries_for_inspection(
            delivery_id=delivery_id,
            gateway_key_id=gateway_key_id,
            owner_id=owner_id,
            owner_email_normalized=owner_email_normalized,
            status=status,
            created_from=created_from,
            created_until=created_until,
            limit=limit + 1,
            offset=offset,
        )
        has_more = len(rows) > limit
        items = [_delivery_item(row) for row in rows[:limit]]
        return EmailDeliveryListPage(
            items=items,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=offset + limit if has_more else None,
        )

    async def show_delivery(self, delivery_id: uuid.UUID) -> EmailDeliveryDetail | None:
        """Resolve the EXACT supplied delivery UUID (no neighbor inference).

        Returns None for a missing delivery (distinct from store
        unavailable, which the CLI maps from store access failures).
        """
        row = await self._email_deliveries_repository.get_email_delivery_by_id(delivery_id)
        if row is None:
            return None

        detail = EmailDeliveryDetail(item=_delivery_item(row))

        sendability = await self._sendability_provider(delivery_id)
        detail = EmailDeliveryDetail(
            item=detail.item,
            secret_lifecycle=EmailDeliverySecretLifecycle(
                status=sendability.one_time_secret_status,
                can_send=sendability.can_send,
                blocking_reason=sendability.blocking_reason,
            ),
        )

        failure = await self._latest_recorded_failure(delivery_id)
        if failure is not None:
            detail = EmailDeliveryDetail(
                item=detail.item,
                secret_lifecycle=detail.secret_lifecycle,
                last_recorded_failure=failure,
            )
        return detail

    async def _latest_recorded_failure(self, delivery_id: uuid.UUID) -> EmailDeliveryLastRecordedFailure | None:
        """Project a finite known error code from the latest matching audit entry.

        Exact entity_type `email_delivery` + exact entity_id; no broad
        action/type matching. Missing/unsafe/unknown code is unavailable,
        not guessed or parsed from prose; no fallback to an older entry.
        """
        row = await self._audit_repository.get_latest_email_error_for_delivery(delivery_id)
        if row is None:
            return None
        new_values = row.new_values if isinstance(row.new_values, dict) else {}
        raw_code = new_values.get("error_code") if new_values else None
        error_code = raw_code if isinstance(raw_code, str) and raw_code in KNOWN_EMAIL_ERROR_CODES else "unavailable"
        return EmailDeliveryLastRecordedFailure(
            error_code=error_code,
            action=row.action,
            recorded_at=row.created_at,
        )


def _delivery_item(row: object) -> EmailDeliveryListItem:
    """Map an ORM row to allowlisted metadata (no raw ORM serialization).

    202-a: the persisted recipient is re-checked with the existing
    known-shape redaction at the output boundary (known-shape protection,
    not universal content sanitization). Normal addresses pass through
    unchanged.
    """
    return EmailDeliveryListItem(
        delivery_id=row.id,  # type: ignore[attr-defined]
        owner_id=row.owner_id,  # type: ignore[attr-defined]
        gateway_key_id=row.gateway_key_id,  # type: ignore[attr-defined]
        one_time_secret_id=row.one_time_secret_id,  # type: ignore[attr-defined]
        recipient_email=redact_text(row.recipient_email),  # type: ignore[attr-defined]
        status=row.status,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        sent_at=row.sent_at,  # type: ignore[attr-defined]
        failed_at=row.failed_at,  # type: ignore[attr-defined]
    )
