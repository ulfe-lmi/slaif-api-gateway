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
        include=("slaif_gateway.workers.tasks_email",),
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_ignore_result=resolved.CELERY_RESULT_BACKEND is None,
    )
    return app


celery_app = create_celery_app()
