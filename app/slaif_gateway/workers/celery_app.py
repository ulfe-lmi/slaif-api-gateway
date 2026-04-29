"""Celery application configuration for background workers."""

from __future__ import annotations

from celery import Celery

from slaif_gateway.config import Settings, get_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create the Celery app without importing FastAPI routes."""
    resolved = settings or get_settings()
    broker_url = resolved.get_celery_broker_url()
    app = Celery(
        "slaif_gateway",
        broker=broker_url,
        backend=resolved.CELERY_RESULT_BACKEND,
        include=(
            "slaif_gateway.workers.tasks_email",
            "slaif_gateway.workers.tasks_reconciliation",
        ),
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_ignore_result=resolved.CELERY_RESULT_BACKEND is None,
        beat_schedule=_reconciliation_beat_schedule(resolved),
    )
    return app

def _reconciliation_beat_schedule(settings: Settings) -> dict[str, dict[str, object]]:
    """Return opt-in Celery Beat entries for reconciliation tasks."""
    if not settings.ENABLE_SCHEDULED_RECONCILIATION:
        return {}

    interval = settings.RECONCILIATION_INTERVAL_SECONDS
    schedule: dict[str, dict[str, object]] = {
        "inspect-reconciliation-backlog": {
            "task": "slaif_gateway.reconciliation.inspect_backlog",
            "schedule": interval,
        }
    }
    if settings.RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS:
        schedule["reconcile-expired-reservations"] = {
            "task": "slaif_gateway.reconciliation.reconcile_expired_reservations",
            "schedule": interval,
            "kwargs": {"dry_run": settings.RECONCILIATION_DRY_RUN},
        }
    if settings.RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED:
        schedule["reconcile-provider-completed"] = {
            "task": "slaif_gateway.reconciliation.reconcile_provider_completed",
            "schedule": interval,
            "kwargs": {"dry_run": settings.RECONCILIATION_DRY_RUN},
        }
    return schedule


celery_app = create_celery_app()
