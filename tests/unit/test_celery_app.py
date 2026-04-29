from __future__ import annotations

from slaif_gateway.config import Settings
from slaif_gateway.workers.celery_app import create_celery_app


def test_celery_app_includes_email_and_reconciliation_tasks() -> None:
    app = create_celery_app(Settings())

    assert "slaif_gateway.workers.tasks_email" in app.conf.include
    assert "slaif_gateway.workers.tasks_reconciliation" in app.conf.include


def test_reconciliation_beat_schedule_disabled_by_default() -> None:
    app = create_celery_app(Settings())

    assert app.conf.beat_schedule == {}


def test_reconciliation_beat_schedule_inspection_only_when_enabled() -> None:
    app = create_celery_app(
        Settings(
            ENABLE_SCHEDULED_RECONCILIATION=True,
            RECONCILIATION_INTERVAL_SECONDS=123,
        )
    )

    schedule = app.conf.beat_schedule
    assert schedule["inspect-reconciliation-backlog"]["task"] == (
        "slaif_gateway.reconciliation.inspect_backlog"
    )
    assert schedule["inspect-reconciliation-backlog"]["schedule"] == 123
    assert "reconcile-expired-reservations" not in schedule
    assert "reconcile-provider-completed" not in schedule


def test_reconciliation_beat_schedule_mutating_tasks_require_auto_execute() -> None:
    app = create_celery_app(
        Settings(
            ENABLE_SCHEDULED_RECONCILIATION=True,
            RECONCILIATION_DRY_RUN=False,
            RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=True,
            RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=True,
        )
    )

    schedule = app.conf.beat_schedule
    assert schedule["reconcile-expired-reservations"]["task"] == (
        "slaif_gateway.reconciliation.reconcile_expired_reservations"
    )
    assert schedule["reconcile-expired-reservations"]["kwargs"] == {"dry_run": False}
    assert schedule["reconcile-provider-completed"]["task"] == (
        "slaif_gateway.reconciliation.reconcile_provider_completed"
    )
    assert schedule["reconcile-provider-completed"]["kwargs"] == {"dry_run": False}
