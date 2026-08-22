from datetime import UTC, datetime, timedelta

from slaif_gateway.services.observability import evaluate_slos, reconciliation_plan, sanitize_metric_labels


def test_slo_breach_returns_runbook_and_request_id():
    alerts = evaluate_slos({"provider_5xx_rate": 0.2}, request_id="req-1")
    assert len(alerts) == 1
    assert alerts[0].slo_key == "provider_errors"
    assert alerts[0].request_id == "req-1"
    assert alerts[0].runbook == "runbook:provider-errors"


def test_safe_labels_limit_cardinality():
    labels = sanitize_metric_labels({
        "provider": "openai", "endpoint": "/v1/responses", "status_class": "5xx",
        "user_id": "secret", "raw": "x",
    })
    assert set(labels) == {"provider", "endpoint", "status_class"}


def test_reconciliation_plan_releases_expired_and_finalizes_active():
    now = datetime.now(UTC)
    rows = [
        {"status": "pending", "expires_at": now - timedelta(seconds=1)},
        {"status": "pending", "expires_at": now + timedelta(minutes=5)},
        {"status": "finalized", "expires_at": now - timedelta(days=1)},
    ]
    assert reconciliation_plan(rows, now=now) == {"finalize": 1, "release": 1}
