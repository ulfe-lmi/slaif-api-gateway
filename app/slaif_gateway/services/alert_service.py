"""Optional external alert sink for safe operator notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

from slaif_gateway.config import Settings
from slaif_gateway.services.alert_errors import AlertDeliveryError
from slaif_gateway.utils.redaction import redact_mapping, redact_text

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AlertResult:
    """Safe alert delivery result."""

    status: str
    event_type: str
    delivered: bool
    webhook_status_code: int | None = None
    reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-safe result without sink URL or secret material."""
        payload: dict[str, object] = {
            "status": self.status,
            "event_type": self.event_type,
            "delivered": self.delivered,
        }
        if self.webhook_status_code is not None:
            payload["webhook_status_code"] = self.webhook_status_code
        if self.reason:
            payload["reason"] = redact_text(self.reason)
        return payload


class AlertService:
    """Send safe reconciliation backlog alerts to a generic JSON webhook."""

    def build_reconciliation_alert_payload(
        self,
        summary: dict[str, object],
        *,
        settings: Settings,
        include_ids: bool = False,
    ) -> dict[str, object]:
        """Build a safe reconciliation backlog alert payload."""
        return build_reconciliation_alert_payload(
            summary,
            settings=settings,
            include_ids=include_ids,
        )

    async def send_reconciliation_backlog_alert(
        self,
        summary: dict[str, object],
        *,
        settings: Settings,
    ) -> AlertResult:
        """Send a reconciliation backlog alert when enabled and thresholds are met."""
        event_type = "reconciliation_backlog"
        if not settings.ENABLE_RECONCILIATION_ALERTS:
            return AlertResult(
                status="skipped",
                event_type=event_type,
                delivered=False,
                reason="alerts_disabled",
            )

        if not _threshold_met(summary, settings=settings):
            return AlertResult(
                status="skipped",
                event_type=event_type,
                delivered=False,
                reason="below_threshold",
            )

        payload = self.build_reconciliation_alert_payload(
            summary,
            settings=settings,
            include_ids=settings.RECONCILIATION_ALERT_INCLUDE_IDS,
        )
        async with httpx.AsyncClient(
            timeout=settings.RECONCILIATION_ALERT_WEBHOOK_TIMEOUT_SECONDS,
        ) as client:
            try:
                response = await client.post(
                    str(settings.RECONCILIATION_ALERT_WEBHOOK_URL),
                    json=payload,
                )
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                logger.warning(
                    "Reconciliation alert webhook timed out.",
                    event_type=event_type,
                )
                raise AlertDeliveryError("alert webhook request timed out") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "Reconciliation alert webhook returned non-success status.",
                    event_type=event_type,
                    webhook_status_code=status_code,
                )
                raise AlertDeliveryError(f"alert webhook returned HTTP {status_code}") from exc
            except httpx.RequestError as exc:
                logger.warning(
                    "Reconciliation alert webhook request failed.",
                    event_type=event_type,
                    error=redact_text(exc.__class__.__name__),
                )
                raise AlertDeliveryError("alert webhook request failed") from exc

        logger.info(
            "Reconciliation alert webhook delivered.",
            event_type=event_type,
            webhook_status_code=response.status_code,
        )
        return AlertResult(
            status="sent",
            event_type=event_type,
            delivered=True,
            webhook_status_code=response.status_code,
        )


def build_reconciliation_alert_payload(
    summary: dict[str, object],
    *,
    settings: Settings,
    include_ids: bool = False,
) -> dict[str, object]:
    """Build a safe webhook payload from reconciliation backlog summary."""
    expired = _mapping(summary.get("expired_reservations"))
    provider_completed = _mapping(summary.get("provider_completed"))
    payload: dict[str, object] = {
        "event_type": "reconciliation_backlog",
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": settings.APP_ENV,
        "expired_reservation_count": _int_value(expired.get("candidate_count")),
        "provider_completed_recovery_count": _int_value(
            provider_completed.get("candidate_count")
        ),
        "dry_run": bool(summary.get("dry_run", True)),
        "reconciliation": {
            "dry_run_default": settings.RECONCILIATION_DRY_RUN,
            "auto_execute_expired_reservations": settings.RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS,
            "auto_execute_provider_completed": settings.RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED,
        },
    }

    if include_ids:
        payload["expired_reservation_ids"] = _safe_id_list(expired.get("reservation_ids"))
        payload["provider_completed_usage_ledger_ids"] = _safe_id_list(
            provider_completed.get("usage_ledger_ids")
        )
        payload["provider_completed_reservation_ids"] = _safe_id_list(
            provider_completed.get("reservation_ids")
        )

    return redact_mapping(payload, accepted_gateway_key_prefixes=settings.get_gateway_key_accepted_prefixes())


def _threshold_met(summary: dict[str, object], *, settings: Settings) -> bool:
    expired = _mapping(summary.get("expired_reservations"))
    provider_completed = _mapping(summary.get("provider_completed"))
    expired_count = _int_value(expired.get("candidate_count"))
    provider_completed_count = _int_value(provider_completed.get("candidate_count"))
    return (
        expired_count >= settings.RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS
        or provider_completed_count >= settings.RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED
    )


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_id_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [redact_text(str(item)) for item in value]
